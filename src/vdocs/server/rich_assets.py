"""``vdocs publish-rich-assets`` — build the rich-publication subset **image bundle**.

The curated-subset registry (``registries/rich-publication.yaml``) names the gold ``doc_key``s that
get figures in the ``vdocs-web`` reading pane (rich-publication proposal §3/§6, tenet #13). This
collects the **union** of those docs' referenced assets — resolved through the shared
:mod:`vdocs.kernel.figures` resolver — into a flat, content-addressed bundle dir
(``DATA_DIR/rich-assets/``) that rides *alongside* ``index.db`` (so ``index.db`` stays text-only,
D3). ``vdocs-web`` serves those bytes via ``GET /api/asset/{sha}``; docs not in the subset still
render their text, just without figures (D5).

The pure planner (:func:`plan_bundle`) takes already-read bodies, so it is unit-tested without the
lake; :func:`build_bundle` is the thin driver that reads each subset doc's gold body, copies the
union of assets into the bundle, prunes anything no longer selected, and writes the manifest.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from vdocs.kernel import figures, markdown
from vdocs.kernel import registry as kregistry

# Bump when the manifest's shape changes (a consumer reads this to know it can parse the bundle).
MANIFEST_VER = 1


@dataclass(frozen=True)
class DocFigures:
    """One subset doc's figure accounting for the bundle plan."""

    doc_key: str
    present: bool  # was the gold body found on disk?
    image_count: int  # distinct figures that resolved in the asset CAS
    missing: int  # referenced figures that did *not* resolve (missing/external)


@dataclass(frozen=True)
class BundlePlan:
    """The planned bundle: the per-doc accounting + the deduped union of asset files to ship."""

    docs: list[DocFigures]
    assets: list[Path]  # union of resolved asset files, sorted by basename
    total_bytes: int


def load_subset(registries_dir: Path) -> list[str]:
    """The curated ``doc_key`` list from ``rich-publication.yaml`` (empty if the file is absent)."""
    data = kregistry.load_mapping(registries_dir / "rich-publication.yaml", missing_ok=True)
    return list(data.get("rich") or [])


def plan_bundle(
    subset: Sequence[str], bodies: Mapping[str, str | None], assets_dir: Path
) -> BundlePlan:
    """Plan the bundle for ``subset`` given each doc's already-read ``body`` (``None`` ⇒ no gold
    body on disk). Resolves each doc's figures through the shared resolver, records per-doc counts
    (and how many refs didn't resolve), and unions the resolved asset files — a figure shared by
    two docs is shipped once. Pure aside from reading asset existence/size (the CAS boundary)."""
    union: dict[str, Path] = {}
    docs: list[DocFigures] = []
    for doc_key in subset:
        body = bodies.get(doc_key)
        if body is None:
            docs.append(DocFigures(doc_key=doc_key, present=False, image_count=0, missing=0))
            continue
        resolved = figures.resolve_assets(body, assets_dir)
        referenced = len(markdown.image_targets(body))
        for p in resolved:
            union.setdefault(p.name, p)
        docs.append(
            DocFigures(
                doc_key=doc_key,
                present=True,
                image_count=len(resolved),
                missing=referenced - len(resolved),
            )
        )
    assets = [union[name] for name in sorted(union)]
    return BundlePlan(docs=docs, assets=assets, total_bytes=sum(p.stat().st_size for p in assets))


def _read_gold_body(gold_consolidated: Path, doc_key: str) -> str | None:
    """The consolidated gold body for ``doc_key`` (``<gold>/consolidated/<app>/<slug>/body.md``),
    or ``None`` when no such bundle exists (a withdrawn/mistyped registry entry)."""
    body_path = gold_consolidated / doc_key / "body.md"
    return body_path.read_text(encoding="utf-8") if body_path.is_file() else None


def build_bundle(cfg, subset: Sequence[str] | None = None) -> BundlePlan:  # type: ignore[no-untyped-def]
    """Read the subset's gold bodies, copy the union of their assets into ``cfg.rich_assets``,
    prune any asset no longer selected (so removing a doc shrinks the bundle), write the manifest,
    and return the plan. ``subset`` defaults to the curated registry list."""
    keys = list(subset) if subset is not None else load_subset(cfg.registries)
    bodies = {dk: _read_gold_body(cfg.gold_consolidated, dk) for dk in keys}
    plan = plan_bundle(keys, bodies, cfg.assets)

    cfg.rich_assets.mkdir(parents=True, exist_ok=True)
    wanted = {p.name for p in plan.assets}
    for src in plan.assets:  # content-addressed ⇒ write-once; skip a byte-identical existing copy
        dst = cfg.rich_assets / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
    for existing in cfg.rich_assets.glob("*"):  # prune stale assets from a prior, larger bundle
        if existing.name != cfg.rich_assets_manifest.name and existing.name not in wanted:
            existing.unlink()

    _write_manifest(cfg, plan)
    return plan


def _write_manifest(cfg, plan: BundlePlan) -> None:  # type: ignore[no-untyped-def]
    """Write ``manifest.json`` describing the bundle (the descriptor a consumer reads)."""
    manifest = {
        "contract_ver": MANIFEST_VER,
        "doc_count": len(plan.docs),
        "asset_count": len(plan.assets),
        "total_bytes": plan.total_bytes,
        "docs": [
            {
                "doc_key": d.doc_key,
                "present": d.present,
                "image_count": d.image_count,
                "missing": d.missing,
            }
            for d in plan.docs
        ],
        "assets": sorted(p.name for p in plan.assets),
    }
    cfg.rich_assets_manifest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
