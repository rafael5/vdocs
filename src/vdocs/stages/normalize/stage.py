"""The `normalize` stage — text@enriched → text@normalized (the F-steps, §6.7, §9.6).

Per-document, deterministic: for each enriched bundle it applies the pure F-steps (strip
Pandoc artifacts → subtract the **curated** ``registries/phrases`` → reference the **curated**
``registries/boilerplate`` → strip the matched ``(doc_type, era)`` template scaffold + stamp
``template_id`` → infer consistent heading levels → rewrite Word-bookmark cross-refs to GitHub
slugs → regenerate the ``## Contents`` TOC from the heading tree → insert round-trip back-links),
stamps ``source_sha256`` into the frontmatter (the bronze provenance it
alone holds), and writes the gold-quality body to ``silver/text/03-normalized``. Subtracts only
the *curated* registry — so it stays a pure function of ``(document, registry)`` and re-runs
idempotently (§7.4, §9.6).

Recognised bundle sidecars written next to ``body.md`` (the ``TEXT_NORMALIZED`` contract is a
``TREE_TEXT`` over the whole bundle, so they need no separate contract):
  * ``revisions.yaml`` — this document's own structured revision-history table (§6.4); the
    cross-version ``history.yaml`` lineage is ``consolidate``'s artifact (§6.6).
  * ``tables/*.csv`` — qualifying complex tables lifted out of the body, body left a reference
    link (§6.4/§6.5).
  * ``refs.yaml`` — the ``(stable_section_id ↔ github_slug ↔ original_bookmark)`` anchor map +
    chosen ``toc_depth`` + outbound cross-ref map (§6.7, §5.5).
"""

from __future__ import annotations

import json

import structlog
import yaml

from vdocs.contracts.registry import RAW_INDEX, REGISTRIES, TEXT_ENRICHED, TEXT_NORMALIZED
from vdocs.kernel import cas, frontmatter
from vdocs.kernel import registry as kregistry
from vdocs.kernel.text import safe_component
from vdocs.models.stage import Idempotency, PostflightResult, RunResult
from vdocs.orchestrator.stage import Stage, StageContext

log = structlog.get_logger(__name__)


class NormalizeStage(Stage):
    name = "normalize"
    description = "normalize enriched bodies (strip artifacts, subtract phrases, regenerate TOC)"
    requires = [TEXT_ENRICHED, RAW_INDEX, REGISTRIES]
    produces = [TEXT_NORMALIZED]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def __init__(self) -> None:
        self._errors = 0  # per-document failures isolated this run (R6 — see doc_error_gate)
        self._total = 0

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.kernel.text import decade_bucket
        from vdocs.stages.normalize import anchors_pure as anchors
        from vdocs.stages.normalize import normalize_pure as nz
        from vdocs.stages.normalize import revision_pure as rev
        from vdocs.stages.normalize import tables_pure as tbl
        from vdocs.stages.normalize import template_pure as tmpl

        phrases = _load_phrases(ctx.cfg.registries / "phrases" / "phrases.yaml")
        boilerplate = _load_boilerplate(
            ctx.cfg.registries / "boilerplate" / "boilerplate.yaml", nz.Boilerplate
        )
        templates = _load_templates(
            ctx.cfg.registries / "templates" / "templates.yaml", tmpl.Template
        )
        toc_titles = _load_structure_toc_titles(
            ctx.cfg.registries / "structures" / "structures.yaml"
        )
        sha_by_path = _sha_by_bundle_path(ctx.cfg.raw_index)

        enriched_root = ctx.cfg.silver_enriched
        normalized_root = ctx.cfg.silver_normalized
        n_docs = n_revision = n_tables = n_refs = n_boiler = n_template = n_errors = 0
        n_published = n_titlepage = n_flags = 0
        body_files = sorted(enriched_root.rglob("body.md"))
        kept = {p.parent.relative_to(enriched_root).as_posix() for p in body_files}
        for body_path in body_files:
            rel = body_path.parent.relative_to(enriched_root)  # <app>/<slug>
            # Per-document error isolation (R6): a single bad doc is logged + counted + skipped so
            # one failure never abandons the batch; doc_error_gate fails the stage only if the
            # error *rate* is systemic.
            try:
                meta, body = frontmatter.parse(body_path.read_text(encoding="utf-8"))
                sha = sha_by_path.get((rel.parts[0], rel.parts[1]))
                if sha:
                    meta["source_sha256"] = sha
                doc_flags: list[str] = []
                # CAPTURE-BEFORE-STRIP (§6.4): lift the title-page publication date into the
                # identity `published` field *before* any title-page/revision strip — sole copy of
                # the date for ~97% of the corpus and the capture-gate for title-page removal.
                published = tmpl.extract_published(body)
                if published:
                    meta["published"] = published
                    n_published += 1
                else:
                    doc_flags.append("title-page-uncaptured-date")  # no date → cover retained below
                # strip the version apparatus → revisions.yaml (§6.4, capture-gated); a revision
                # heading with no parseable table is retained + flagged, never deleted blind. Then
                # lift qualifying tables → tables/*.csv (§6.4/§6.5) — *after* revision extraction so
                # it never grabs the revision table; then run the body F-steps.
                # TEMPLATE SEAM: toc_depth defaults to the H2–H3 fallback; the template F-step will
                # resolve it per (doc_type, era) and pass it to normalize_body (§6.7).
                body, revisions, rev_flag = rev.extract_revision_history(body)
                if rev_flag:
                    doc_flags.append(rev_flag)
                body, tables = tbl.extract_tables(body)
                # STRIP the matched (doc_type, era) template scaffold + stamp template_id (§9.8).
                # era is the title-page-date decade bucket (kernel.decade_bucket); doc_type is the
                # baked identity FM. template_id is provenance → frontmatter, like source_sha256.
                era = decade_bucket(body, max_lines=40)
                body, template_id = tmpl.apply_template(
                    body, str(meta.get("doc_type", "")), era, templates
                )
                if template_id:
                    meta["template_id"] = template_id
                    n_template += 1
                # STANDARDIZE the title page (§6.4): replace the raw legacy cover with a block built
                # from frontmatter — gated on `published` (capture-before-strip). Within the
                # template/scaffold F-step seam (the title page is part of the scaffold).
                standardized = tmpl.standardize_title_page(
                    body,
                    tmpl.TitlePageFields(
                        title=str(meta.get("title", "")),
                        version=str(meta.get("version", "")),
                        patch_id=str(meta.get("patch_id", "")),
                        published=published or "",
                        source_url=str(meta.get("source_url", "")),
                    ),
                )
                if standardized != body:
                    n_titlepage += 1
                body = standardized
                body, anchor_map = nz.normalize_body(
                    body, phrases, doc_id=str(rel), boilerplate=boilerplate, toc_titles=toc_titles
                )
                if anchor_map.toc_unresolved:
                    doc_flags.append(f"legacy-toc-unresolved:{len(anchor_map.toc_unresolved)}")
                n_boiler += body.count("](_shared/boilerplate/")  # REFERENCE links inserted
                out = frontmatter.emit(meta, body)
                cas.atomic_write(normalized_root / rel / "body.md", out.encode("utf-8"))
                if revisions:
                    cas.atomic_write(
                        normalized_root / rel / "revisions.yaml",
                        yaml.safe_dump(
                            rev.revision_sidecar(revisions), sort_keys=False, allow_unicode=True
                        ).encode("utf-8"),
                    )
                    n_revision += 1
                for tab in tables:  # one CSV per lifted table, inside the bundle's tables/ dir
                    cas.atomic_write(
                        normalized_root / rel / "tables" / tab.name, tab.csv_text.encode("utf-8")
                    )
                n_tables += len(tables)
                if anchor_map.rows:  # conditional, like revisions.yaml — no anchors → no sidecar
                    cas.atomic_write(
                        normalized_root / rel / "refs.yaml",
                        yaml.safe_dump(
                            anchors.anchor_sidecar(anchor_map), sort_keys=False, allow_unicode=True
                        ).encode("utf-8"),
                    )
                    n_refs += 1
                # FIDELITY FLAGS (§6.4/§6.7): record the capture-before-strip signals — a retained
                # unparseable revision apparatus, an uncaptured title-page date (cover left in
                # place), unresolved legacy-TOC anchors — so nothing is dropped without a trace.
                if doc_flags:
                    cas.atomic_write(
                        normalized_root / rel / "flags.yaml",
                        yaml.safe_dump(
                            {"doc_id": str(rel), "flags": doc_flags},
                            sort_keys=False,
                            allow_unicode=True,
                        ).encode("utf-8"),
                    )
                    n_flags += 1
                n_docs += 1
            except Exception as exc:
                n_errors += 1
                log.warning("normalize-doc-failed", doc=str(rel), error=str(exc))

        n_pruned = cas.prune_bundles(normalized_root, kept)
        self._errors, self._total = n_errors, len(body_files)
        return RunResult(
            counts={
                "documents": n_docs,
                "revision_sidecars": n_revision,
                "tables_sidecars": n_tables,
                "refs_sidecars": n_refs,
                "boilerplate_refs": n_boiler,
                "templates_stamped": n_template,
                "published_captured": n_published,
                "titlepages_standardized": n_titlepage,
                "flag_sidecars": n_flags,
                "phrases": len(phrases),
                "errors": n_errors,
                "pruned": n_pruned,
            }
        )

    def deep_gate(self, ctx: StageContext) -> PostflightResult:
        """Fail only if the per-document error rate is systemic (R6); one bad doc is isolated."""
        return self.doc_error_gate(self._errors, self._total)


def _load_phrases(path) -> frozenset[str]:  # type: ignore[no-untyped-def]
    """The curated dead phrases (empty if the registry file is absent — a no-op subtraction)."""
    data = kregistry.load_mapping(path, missing_ok=True)
    return frozenset(data.get("phrases") or [])


def _load_boilerplate(path, cls):  # type: ignore[no-untyped-def]
    """The curated boilerplate registry as ``Boilerplate`` entries (empty if absent — a no-op)."""
    data = kregistry.load_mapping(path, missing_ok=True)
    return tuple(
        cls(id=e["id"], label=e["label"], key=e["key"]) for e in (data.get("boilerplate") or [])
    )


def _load_templates(path, cls):  # type: ignore[no-untyped-def]
    """The curated ``(doc_type, era)`` templates as ``Template`` entries (empty if absent).

    Each template's scaffold-section titles are normalised (lowercased, whitespace-collapsed) for
    matching against body headings."""
    data = kregistry.load_mapping(path, missing_ok=True)
    out = []
    for t in data.get("templates") or []:
        titles = frozenset(
            " ".join(str(s["title"]).lower().split()) for s in (t.get("sections") or [])
        )
        out.append(
            cls(
                template_id=t["template_id"],
                doc_type=t["doc_type"],
                era=t["era"],
                section_titles=titles,
            )
        )
    return tuple(out)


def _load_structure_toc_titles(path) -> frozenset[str]:  # type: ignore[no-untyped-def]
    """Curated ``registries/structures`` heading texts for the ``toc`` CANONICALIZE convention —
    the legacy-TOC variants ``normalize`` strips before deriving ``## Contents`` (§6.7/§9.6).

    Empty if the registry is absent or carries no approved ``toc`` convention (a no-op strip)."""
    data = kregistry.load_mapping(path, missing_ok=True)
    titles: set[str] = set()
    for conv in data.get("conventions") or []:
        if conv.get("convention") == "toc" and conv.get("disposition") == "CANONICALIZE":
            titles.update(str(m).strip().lower() for m in (conv.get("match") or []))
    return frozenset(titles)


def _sha_by_bundle_path(raw_index):  # type: ignore[no-untyped-def]
    """Map ``(safe app, safe slug)`` → source sha256 from ``raw/index.json`` (bronze provenance)."""
    index = json.loads(raw_index.read_text(encoding="utf-8"))
    return {
        (safe_component(e["app_code"]), safe_component(e["doc_slug"])): sha
        for sha, e in index.items()
    }
