"""The `consolidate` stage — text@normalized → consolidated (the gold version rollup, §6.6).

Per version group, not per document: it gathers every normalized member of a logical document
(grouped by the version-free ``anchor_key`` reconstructed from each bundle's identity frontmatter),
orders them oldest→newest, and collapses each group to **one anchor document** at a stable,
version-free path whose ``body.md`` is the *latest* normalized body. The full lineage is captured
into a travel-with ``history.yaml`` (ordered patch chain, each member folding its own
``revisions.yaml`` + a content-addressed ref to its **retained** normalized body), and every prior
body is kept write-once in the gold body CAS (``gold/_shared/history``). Capture is **append-only**
(§6.6): a later patch appends one entry + retains its body; nothing already captured is rewritten.
This is the captured replay source for the deferred ``push --replay-history`` — the git replay is
**not** built here.

Reuses the kernel: ``cas`` for content-addressed body retention + the hardened content-skip/atomic
tree write + stale-bundle pruning, ``frontmatter`` for the identity FM, ``ids`` for the shared
``anchor_key``/``doc_id`` formulas (§9.2). No primitive is re-spelled here.
"""

from __future__ import annotations

import structlog
import yaml

from vdocs.contracts.registry import ASSETS, CONSOLIDATED, TEXT_NORMALIZED
from vdocs.kernel import cas, frontmatter
from vdocs.kernel import ids as kids
from vdocs.models.stage import Idempotency, PostflightResult, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.consolidate import consolidate_pure as cp

log = structlog.get_logger(__name__)


class ConsolidateStage(Stage):
    name = "consolidate"
    description = "collapse each version group to one anchor document + capture the lineage (§6.6)"
    requires = [TEXT_NORMALIZED, ASSETS]
    produces = [CONSOLIDATED]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def __init__(self) -> None:
        self._errors = 0  # per-document failures isolated this run (R6 — see doc_error_gate)
        self._total = 0

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        normalized_root = ctx.cfg.silver_normalized
        consolidated_root = ctx.cfg.gold_consolidated
        bodies = cas.Cas(ctx.cfg.history_bodies)  # write-once store of retained normalized bodies

        body_files = sorted(normalized_root.rglob("body.md"))
        members: list[cp.Member] = []
        body_bytes: dict[str, bytes] = {}  # doc_id → the bundle's body.md bytes (the anchor body)
        flag_bytes: dict[str, bytes] = {}  # doc_id → the member's flags.yaml (fidelity signals)
        n_errors = 0
        for body_path in body_files:
            rel = body_path.parent.relative_to(normalized_root)  # <app>/<slug>
            # Per-document error isolation (R6): one unreadable/malformed bundle is logged + counted
            # + skipped; the batch continues. doc_error_gate fails the stage only if systemic.
            try:
                raw = body_path.read_bytes()
                meta, _ = frontmatter.parse(raw.decode("utf-8"))
                member = _member_from(meta, rel.parts[1], raw, bodies, body_path.parent)
                members.append(member)
                body_bytes[member.doc_id] = raw
                flags_path = body_path.parent / "flags.yaml"
                if flags_path.is_file():
                    flag_bytes[member.doc_id] = flags_path.read_bytes()
            except Exception as exc:  # noqa: BLE001 — isolate one bad doc, never abort the batch
                n_errors += 1
                log.warning("consolidate-doc-failed", doc=str(rel), error=str(exc))

        groups = cp.group_by_anchor_key(members)
        kept: set[str] = set()
        for group in groups.values():
            ordered = cp.order_members(group)
            latest = ordered[-1]
            relpath = cp.anchor_relpath(
                latest.app_code, latest.pkg_ns, latest.doc_code, doc_slug=latest.doc_slug
            )
            kept.add(relpath)
            anchor = consolidated_root / relpath
            # promote the latest body unchanged (content-skip keeps the fingerprint honest)
            cas.atomic_write(anchor / "body.md", body_bytes[latest.doc_id])
            # the latest member's fidelity flags (capture-before-strip signals, §6.4/§6.7) travel
            # with the anchor so a retained/flagged residue is visible at the gold grain too
            if latest.doc_id in flag_bytes:
                cas.atomic_write(anchor / "flags.yaml", flag_bytes[latest.doc_id])
            # append-only lineage: fold the fresh chain into any prior history.yaml (§6.6)
            existing = _read_history(anchor / "history.yaml")
            merged = cp.merge_history(existing, cp.build_history(latest.anchor_key, ordered))
            cas.atomic_write(
                anchor / "history.yaml",
                yaml.safe_dump(merged, sort_keys=False, allow_unicode=True).encode("utf-8"),
            )

        n_pruned = cas.prune_bundles(consolidated_root, kept)
        self._errors, self._total = n_errors, len(body_files)
        return RunResult(
            counts={
                "groups": len(groups),
                "documents": len(members),
                "retained_bodies": len({m.body_sha256 for m in members}),
                "errors": n_errors,
                "pruned": n_pruned,
            }
        )

    def deep_gate(self, ctx: StageContext) -> PostflightResult:
        """Fail only if the per-document error rate is systemic (R6); one bad bundle is isolated."""
        return self.doc_error_gate(self._errors, self._total)


def _member_from(meta, doc_slug, raw, bodies, bundle_dir):  # type: ignore[no-untyped-def]
    """Build a :class:`~consolidate_pure.Member` from a bundle's FM + folded revisions + retained
    body. The version-group identity is reconstructed from the FM exactly as ``catalog`` computed it
    (shared ``kernel.ids.anchor_key``), so a bundle groups identically end-to-end (§9.2)."""
    app_code = str(meta.get("app_code", ""))
    pkg_ns = str(meta.get("pkg_ns", ""))
    doc_code = str(meta.get("doc_type", ""))
    patch_id = str(meta.get("patch_id", ""))
    revisions, revision_newest = _fold_revisions(bundle_dir / "revisions.yaml")
    # official_date: the revision table's newest date when captured, else the title-page `published`
    # date baked into identity FM (§6.4) — so it populates even where no revision table exists.
    official_date = cp.official_date(revision_newest, str(meta.get("published", "")))
    return cp.Member(
        anchor_key=kids.anchor_key(app_code, pkg_ns, doc_code),
        app_code=app_code,
        pkg_ns=pkg_ns,
        doc_code=doc_code,
        doc_slug=doc_slug,
        doc_id=f"{app_code}:{doc_slug}",
        version=str(meta.get("version", "")),
        patch_id=patch_id,
        patch_num=cp.parse_patch_num(patch_id),
        official_date=official_date,
        source_sha256=str(meta.get("source_sha256", "")),
        body_sha256=bodies.put(raw, ext="md"),  # retain this version's body, write-once
        revisions=revisions,
    )


def _fold_revisions(path):  # type: ignore[no-untyped-def]
    """The member's own ``revisions.yaml`` (§6.4) folded into the lineage: the revision entries +
    the newest date (the order tiebreak). Absent sidecar → no entries, no date."""
    if not path.is_file():
        return [], ""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("revisions") or []), str(data.get("revision_newest", ""))


def _read_history(path):  # type: ignore[no-untyped-def]
    """Load a prior ``history.yaml`` (the append-only base), or ``None`` on the first run."""
    if not path.is_file():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))
