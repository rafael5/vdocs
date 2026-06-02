"""The `normalize` stage — text@enriched → text@normalized (the F-steps, §6.7, §9.6).

Per-document, deterministic: for each enriched bundle it applies the pure F-steps (strip
Pandoc artifacts → subtract the **curated** ``registries/phrases`` → regenerate the
``## Contents`` TOC from the heading tree), stamps ``source_sha256`` into the frontmatter (the
bronze provenance it alone holds), and writes the gold-quality body to
``silver/text/03-normalized``. Subtracts only the *curated* registry — so it stays a pure
function of ``(document, registry)`` and re-runs idempotently (§7.4, §9.6).
"""

from __future__ import annotations

import json

import yaml

from vdocs.contracts.registry import RAW_INDEX, REGISTRIES, TEXT_ENRICHED, TEXT_NORMALIZED
from vdocs.kernel import cas, frontmatter
from vdocs.kernel.text import safe_component
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext


class NormalizeStage(Stage):
    name = "normalize"
    description = "normalize enriched bodies (strip artifacts, subtract phrases, regenerate TOC)"
    requires = [TEXT_ENRICHED, RAW_INDEX, REGISTRIES]
    produces = [TEXT_NORMALIZED]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.normalize import normalize_pure as nz
        from vdocs.stages.normalize import revision_pure as rev

        phrases = _load_phrases(ctx.cfg.registries / "phrases.yaml")
        sha_by_path = _sha_by_bundle_path(ctx.cfg.raw_index)

        enriched_root = ctx.cfg.silver_enriched
        normalized_root = ctx.cfg.silver_normalized
        n_docs = n_history = 0
        for body_path in sorted(enriched_root.rglob("body.md")):
            rel = body_path.parent.relative_to(enriched_root)  # <app>/<slug>
            meta, body = frontmatter.parse(body_path.read_text(encoding="utf-8"))
            sha = sha_by_path.get((rel.parts[0], rel.parts[1]))
            if sha:
                meta["source_sha256"] = sha
            # strip the version apparatus → history.yaml sidecar (§6.6), then run the body F-steps
            body, revisions = rev.extract_revision_history(body)
            out = frontmatter.emit(meta, nz.normalize_body(body, phrases))
            cas.atomic_write(normalized_root / rel / "body.md", out.encode("utf-8"))
            if revisions:
                cas.atomic_write(
                    normalized_root / rel / "history.yaml",
                    yaml.safe_dump(
                        rev.history_sidecar(revisions), sort_keys=False, allow_unicode=True
                    ).encode("utf-8"),
                )
                n_history += 1
            n_docs += 1

        return RunResult(
            counts={"documents": n_docs, "history_sidecars": n_history, "phrases": len(phrases)}
        )


def _load_phrases(path) -> frozenset[str]:  # type: ignore[no-untyped-def]
    """The curated dead phrases (empty if the registry file is absent — a no-op subtraction)."""
    if not path.exists():
        return frozenset()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return frozenset(data.get("phrases") or [])


def _sha_by_bundle_path(raw_index):  # type: ignore[no-untyped-def]
    """Map ``(safe app, safe slug)`` → source sha256 from ``raw/index.json`` (bronze provenance)."""
    index = json.loads(raw_index.read_text(encoding="utf-8"))
    return {
        (safe_component(e["app_code"]), safe_component(e["doc_slug"])): sha
        for sha, e in index.items()
    }
