"""End-to-end proof of the §9.6 induction→curation→application→validation seam (Phase 3/5).

The other tests exercise the halves in isolation (`discover` proposes; `normalize` applies
hand-written registries). This test proves the **whole loop on one fixture corpus, with real
objects and no mocks**:

  discover (mine) → reports/patterns (candidates + evidence + disposition)
      → CURATE (promote candidates verbatim into a tmp `registries/`)
      → normalize (consume the *curated* registry: STRIP template scaffold + stamp template_id,
        REFERENCE boilerplate to gold/_shared, regenerate the TOC) — idempotent
      → fidelity compliance oracle scores the body vs. the retained schema (§9.8) and the
        validate gate blocks a non-conformant doc.

The point is that `discover`'s output is curation-shaped and flows straight through `normalize`'s
deterministic application, and that the application is a pure function of `(document, registry)`.
"""

from __future__ import annotations

import yaml

from vdocs.contracts.registry import CATALOG_ENRICHED, RAW_INDEX, TEXT_CONVERTED, TEXT_ENRICHED
from vdocs.kernel import cas, frontmatter
from vdocs.models.catalog import EnrichedInventory, EnrichedRecord
from vdocs.models.stage import StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.discover.discover_pure import PatternReport
from vdocs.stages.discover.stage import DiscoverStage
from vdocs.stages.fidelity import compliance_pure as cp
from vdocs.stages.normalize.stage import NormalizeStage

_APP = "DEP"
_BOILER = (
    "This document describes the Deployment, Installation, Back-out, and Rollback Plan for new "
    "products going into the VA Enterprise, and is shared verbatim across every DIBR manual."
)


def _bless(ctx, *stage_arts):
    for stage, art in stage_arts:
        ctx.state.record(
            StageRun(
                stage=stage,
                scope="",
                status="ok",
                started_at="t",
                finished_at="t",
                inputs_fp={},
                outputs_fp={art.key: art.fingerprint(ctx.cfg)},
                counts={},
                contract_ver=1,
                tool_ver=ctx.cfg.tool_ver,
            )  # fmt: skip
        )


def _seed_converted(ctx, n=4):
    """A small DIBR cohort in text@converted: shared (Purpose, Rollback) scaffold, a 2021 title
    page, and a shared boilerplate block."""
    for i in range(n):
        body = (
            f"# DIBR Doc {i}\n\nDeployment Guide\n\nSeptember 2021\n\n"
            f"## Purpose\n\nThe specific deployment purpose for document {i} with real words.\n\n"
            f"## Rollback\n\nRollback steps for document {i} described in real sentences here.\n\n"
            f"{_BOILER}\n\nUnique closing content for document {i}.\n"
        )
        cas.atomic_write(ctx.cfg.silver_converted / _APP / f"doc_{i}" / "body.md", body.encode())
    records = [
        EnrichedRecord(
            app_name_abbrev=_APP, doc_slug=f"doc_{i}", doc_code="DIBR", doc_format="docx"
        )
        for i in range(n)
    ]
    cas.atomic_write(
        ctx.cfg.catalog_enriched, EnrichedInventory(records=records).model_dump_json().encode()
    )
    _bless(ctx, ("catalog", CATALOG_ENRICHED), ("convert", TEXT_CONVERTED))


def _curate(ctx, template, boiler):
    """The curation gate: promote the discovered candidates verbatim into a tmp registries/."""
    regs = ctx.cfg.data_dir / "curated_registries"
    (regs / "templates").mkdir(parents=True)
    (regs / "boilerplate").mkdir(parents=True)
    (regs / "templates" / "templates.yaml").write_text(
        yaml.safe_dump(
            {
                "templates": [
                    {
                        "template_id": template.template_id,
                        "doc_type": template.doc_type,
                        "era": template.era,
                        "disposition": template.disposition,
                        "status": "approved",
                        "sections": [{"title": s.title} for s in template.sections],
                    }
                ]
            }
        )
    )
    (regs / "boilerplate" / "boilerplate.yaml").write_text(
        yaml.safe_dump(
            {
                "boilerplate": [
                    {
                        "id": "bp-seam01",
                        "label": "DIBR plan intro",
                        "key": boiler.key,
                        "text": boiler.text,
                        "status": "approved",
                    }
                ]  # fmt: skip
            }
        )
    )
    ctx.cfg = ctx.cfg.model_copy(update={"registries_dir": regs})


def _seed_enriched_doc(ctx):
    """One enriched DIBR bundle: Purpose filled (kept), Rollback empty (scaffold → stripped),
    the curated boilerplate block present (→ REFERENCE)."""
    enriched = frontmatter.emit(
        {"title": "DEP Deploy", "doc_type": "DIBR", "app_code": _APP, "tool_ver": "0.1.0"},
        "# DEP Deploy\n\nSeptember 2021\n\n## Purpose\n\nReal filled purpose text.\n\n"
        f"{_BOILER}\n\n## Rollback\n\n",
    )
    cas.atomic_write(ctx.cfg.silver_enriched / _APP / "dep_doc" / "body.md", enriched.encode())
    ctx.cfg.raw_index.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.raw_index.write_text(
        '{"sha": {"app_code": "%s", "doc_slug": "dep_doc", "ext": "docx"}}' % _APP
    )
    _bless(ctx, ("enrich", TEXT_ENRICHED), ("fetch", RAW_INDEX))


def test_curation_seam_discover_to_normalize_to_oracle(ctx):
    # --- 1. DISCOVER (mine) → candidates with evidence + disposition -------------------------
    _seed_converted(ctx, n=4)
    bodies_before = {p: p.read_bytes() for p in ctx.cfg.silver_converted.rglob("body.md")}

    (dres,) = Orchestrator([DiscoverStage()]).run(ctx)
    assert dres.status == "ok"
    report = PatternReport.model_validate_json(ctx.cfg.patterns_report.read_text())

    # discover mutates no body (induction only, §9.6 / spike §4.1)
    assert {p: p.read_bytes() for p in ctx.cfg.silver_converted.rglob("body.md")} == bodies_before

    template = next(t for t in report.templates if t.doc_type == "DIBR" and t.era == "2020s")
    assert template.disposition == "STRIP" and template.doc_count == 4
    titles = [s.title for s in template.sections]
    assert "Purpose" in titles and "Rollback" in titles
    # the §9.8 computable schema travelled with the candidate (the curation/oracle payload)
    assert all(s.title_pattern for s in template.sections)

    boiler = next(
        c
        for c in report.blocks
        if c.registry == "boilerplate" and "this document describes" in c.key
    )
    assert boiler.disposition == "REFERENCE" and boiler.doc_count == 4

    # --- 2. CURATE → promote the candidates verbatim into registries/ ------------------------
    _curate(ctx, template, boiler)

    # --- 3. APPLY (normalize) consumes the curated registry, deterministically ---------------
    _seed_enriched_doc(ctx)
    (nres,) = Orchestrator([NormalizeStage()]).run(ctx)
    assert nres.status == "ok"
    assert nres.counts["templates_stamped"] == 1 and nres.counts["boilerplate_refs"] == 1

    out_path = ctx.cfg.silver_normalized / _APP / "dep_doc" / "body.md"
    meta, body = frontmatter.parse(out_path.read_text())
    assert meta["template_id"] == template.template_id  # STRIP+STAMP from the discovered template
    assert "Real filled purpose text." in body  # filled scaffold section kept
    assert "## Rollback" not in body  # empty scaffold section stripped
    assert _BOILER not in body  # boilerplate REFERENCEd, not inlined
    assert "(_shared/boilerplate/bp-seam01.md)" in body
    assert body.count("## Contents") == 1  # TOC regenerated from headings (§6.7)

    # --- 3b. normalize is a PURE function of (document, registry): idempotent -----------------
    first = out_path.read_bytes()
    Orchestrator([NormalizeStage()]).run(ctx, force=True)
    assert out_path.read_bytes() == first

    # --- 4. VALIDATE: the retained schema is the compliance oracle (§9.8) ---------------------
    expected = [
        cp.ExpectedSection(title=s.title, title_pattern=s.title_pattern, required=s.required)
        for s in template.sections
    ]
    conformant = "# X\n\n## Purpose\n\np\n\n## Rollback\n\nr\n"
    assert cp.score_extraction_compliance(conformant, expected).verdict == cp.PASS

    broken = "# X\n\n## Purpose\n\np\n"  # a required section dropped → extraction-bug signal
    verdict = cp.score_extraction_compliance(broken, expected)
    assert verdict.verdict in (cp.REVIEW, cp.QUARANTINE)
    assert cp.blocks_publish(verdict.verdict) is True  # the validate hard gate blocks it (§8)
