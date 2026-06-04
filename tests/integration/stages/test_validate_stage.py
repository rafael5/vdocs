"""validate integration — the sidecar-verification HARD GATE (Steps 2-3; §8, FF C2/C5).

Seeds a normalized tree of bundles (each with capture.yaml + refs.yaml), blesses the normalize
upstream with its emitted counts, runs ValidateStage through the orchestrator, and asserts the gate:
PASSES on a clean corpus (writing the findings report), and FAILS loudly on a per-document
absent-unexpected (typed absence), a corpus-zero whole-detector failure (count reconciliation), a
severed cross-ref (ref resolution), and a cross-run count drop.
"""

from __future__ import annotations

import json

import pytest
import yaml

from vdocs.contracts.registry import CONSOLIDATED, TEXT_NORMALIZED
from vdocs.kernel import bundle as kbundle
from vdocs.kernel import cas, frontmatter
from vdocs.models.stage import StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.orchestrator.stage import PostflightError
from vdocs.stages.normalize import capture_pure as cap
from vdocs.stages.validate.stage import ValidateStage


def _bless(ctx, stage, art, counts=None):
    ctx.state.record(
        StageRun(
            stage=stage,
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={art.key: art.fingerprint(ctx.cfg)},
            counts=counts or {},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )  # fmt: skip
    )


def _seed_consolidated_ok(ctx):
    """One valid gold anchor bundle (body.md + a correct bundle.yaml) so validate's CONSOLIDATED
    requirement + bundle-integrity gate pass by default; bundle-gate tests tamper it instead."""
    anchor = ctx.cfg.gold_consolidated / "ADT" / "doc"
    cas.atomic_write(anchor / "body.md", b"# Anchor\n")
    manifest = kbundle.build_manifest(
        {"body.md": b"# Anchor\n"}, doc_id="ADT/doc", anchor_key="ADT:ADT:DOC",
        tool_ver=ctx.cfg.tool_ver, source_sha256=["abc"],
    )  # fmt: skip
    cas.atomic_write(anchor / "bundle.yaml", yaml.safe_dump(manifest).encode())
    _bless(ctx, "consolidate", CONSOLIDATED)


def _bless_normalize(ctx, counts):
    """Bless both upstreams validate now requires: normalize (with counts) + a clean consolidate."""
    _bless(ctx, "normalize", TEXT_NORMALIZED, counts)
    _seed_consolidated_ok(ctx)


def _seed_bundle(ctx, slug, *, captures, anchors=("intro",), outbound=None):
    """Write one normalized bundle: body.md + capture.yaml + refs.yaml."""
    bundle = ctx.cfg.silver_normalized / "ADT" / slug
    cas.atomic_write(
        bundle / "body.md",
        frontmatter.emit(
            {"title": slug, "app_code": "ADT", "tool_ver": "0.1.0"}, "# Doc\n"
        ).encode(),
    )
    cas.atomic_write(
        bundle / "capture.yaml",
        yaml.safe_dump(
            {"doc_id": f"ADT/{slug}", "captures": {k: {"outcome": v} for k, v in captures.items()}}
        ).encode(),
    )
    cas.atomic_write(
        bundle / "refs.yaml",
        yaml.safe_dump(
            {
                "doc_id": f"ADT/{slug}",
                "anchors": [{"slug": s, "title": s} for s in anchors],
                "outbound": outbound or {},
            }
        ).encode(),
    )


def test_validate_passes_clean_corpus_and_writes_report(ctx):
    _seed_bundle(ctx, "a", captures={"refs": "captured", "tables": "captured"})
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1, "tables_sidecars": 1})

    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.status == "ok"
    assert result.counts["blocking"] == 0

    report = json.loads(ctx.cfg.validation_report.read_text())
    assert report["blocking"] is False
    assert report["counts"]["documents"] == 1  # recorded as the cross-run baseline


def test_validate_fails_on_absent_unexpected(ctx):
    # Step 1's per-document silent miss must trip the gate (typed-absence gate)
    _seed_bundle(ctx, "a", captures={"refs": "captured", "revisions": "absent-unexpected"})
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1, "absent_unexpected": 1})

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert report["blocking"] is True
    assert any(f["kind"] == "absent-unexpected" for f in report["reconcile_findings"])


def test_validate_fails_on_severed_cross_ref(ctx):
    # Step 3: an outbound ref pointing at a slug no heading carries — a dead anchor (hard floor 0)
    _seed_bundle(
        ctx, "a", captures={"refs": "captured"}, anchors=("intro",),
        outbound={"_Toc1": "intro", "_Toc9": "gone"},
    )  # fmt: skip
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert report["ref_findings"]["severed"]
    assert report["blocking"] is True


def test_validate_fails_on_corpus_zero_tables(ctx):
    # Step 2: zero tables across a large corpus ⇒ whole-detector failure (count reconciliation)
    for i in range(60):
        _seed_bundle(ctx, f"d{i}", captures={"refs": "captured", "tables": "absent-expected"})
    _bless_normalize(ctx, {"documents": 60, "refs_sidecars": 60, "tables_sidecars": 0})

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert any(f["kind"] == "corpus-zero" for f in report["reconcile_findings"])


def test_validate_fails_on_count_drop_vs_prior_report(ctx):
    # Step 2: a sidecar count that dropped vs. the prior run over a same-or-larger corpus
    ctx.cfg.validation_report.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.validation_report.write_text(
        json.dumps({"counts": {"documents": 60, "refs_sidecars": 60, "tables_sidecars": 55}})
    )
    for i in range(60):
        _seed_bundle(ctx, f"d{i}", captures={"refs": "captured", "tables": "captured"})
    _bless_normalize(ctx, {"documents": 60, "refs_sidecars": 60, "tables_sidecars": 40})

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert any(f["kind"] == "count-drop" for f in report["reconcile_findings"])


def test_validate_does_not_block_on_high_unmapped_rate(ctx):
    # the real corpus is ~92% UNRESOLVED (Word cross-refs point at non-heading anchors) — a high
    # unmapped rate is expected, not a defect, so it is reported as a metric and never gated
    # (memory: normalize anchor reality; FF C5: the hard floor is for TOC + the heading tree).
    outbound = {f"_Toc{i}": "UNRESOLVED" for i in range(92)}
    outbound.update({f"_Ref{i}": "intro" for i in range(8)})  # ~92% unmapped, like the real corpus
    _seed_bundle(ctx, "a", captures={"refs": "captured"}, outbound=outbound)
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})

    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.status == "ok" and result.counts["blocking"] == 0
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert report["ref_findings"]["unmapped_above_c5_target"] is True  # reported…
    assert not report["ref_findings"]["severed"]  # …but no severed refs, so not blocked


def test_validate_reports_expected_unmapped_separately_from_c5_rate(ctx):
    # Recalibration (triage 2026-06-03): _Ref… cross-refs target non-heading objects and can never
    # resolve to a heading anchor → reported as expected-unmapped, OUTSIDE the C5 heading-
    # resolvability rate. Only _Toc… (heading-targeting) bookmarks count toward unmapped_rate, whose
    # denominator is the heading-targeting universe (outbound_total − expected_unmapped).
    outbound = {
        "_Ref1": "UNRESOLVED",  # expected-unmapped (non-heading target)
        "_Ref2": "UNRESOLVED",  # expected-unmapped
        "_Toc1": "UNRESOLVED",  # unmapped (recoverable _Toc→heading miss) — the C5 class
        "_Toc2": "intro",  # resolved
    }
    _seed_bundle(ctx, "a", captures={"refs": "captured"}, anchors=("intro",), outbound=outbound)
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})

    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.status == "ok" and result.counts["blocking"] == 0
    rf = json.loads(ctx.cfg.validation_report.read_text())["ref_findings"]
    assert rf["expected_unmapped_count"] == 2  # the two _Ref refs, not C5-counted
    assert rf["unmapped_count"] == 1  # only the _Toc miss
    assert rf["outbound_total"] == 4
    # rate over the heading-targeting universe (4 − 2 expected = 2): 1 unmapped / 2 = 0.5
    assert rf["unmapped_rate"] == 0.5


def test_validate_handles_bundle_without_sidecars(ctx):
    # a bundle with only body.md (no capture.yaml / refs.yaml) is skipped, not crashed
    bundle = ctx.cfg.silver_normalized / "ADT" / "bare"
    cas.atomic_write(
        bundle / "body.md",
        frontmatter.emit(
            {"title": "bare", "app_code": "ADT", "tool_ver": "0.1.0"}, "# Doc\n"
        ).encode(),
    )
    _bless_normalize(ctx, {"documents": 1})
    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.status == "ok" and result.counts["blocking"] == 0


def test_validate_tolerates_corrupt_prior_report(ctx):
    # a malformed prior report must not crash the gate (no cross-run baseline → no drop check)
    ctx.cfg.validation_report.parent.mkdir(parents=True, exist_ok=True)
    ctx.cfg.validation_report.write_text("not json{")
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})
    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.status == "ok"


def test_validate_blocks_on_tampered_bundle(ctx):
    # Step 4: a gold bundle whose body.md no longer matches its bundle.yaml manifest hash → the
    # bundle-integrity gate catches the tamper (recompute-to-verify).
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless(ctx, "normalize", TEXT_NORMALIZED, {"documents": 1})
    anchor = ctx.cfg.gold_consolidated / "ADT" / "doc"
    cas.atomic_write(anchor / "body.md", b"# Real body\n")
    bad = kbundle.build_manifest(
        {"body.md": b"# Different bytes\n"}, doc_id="ADT/doc", anchor_key="ADT:ADT:DOC",
        tool_ver=ctx.cfg.tool_ver, source_sha256=["abc"],
    )  # fmt: skip
    cas.atomic_write(anchor / "bundle.yaml", yaml.safe_dump(bad).encode())
    _bless(ctx, "consolidate", CONSOLIDATED)

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert any(
        f["kind"] == "hash-mismatch" and f["path"] == "body.md" for f in report["bundle_findings"]
    )


def test_validate_blocks_on_unmanifested_bundle(ctx):
    # a gold bundle with no bundle.yaml cannot be verified → blocks (not silently skipped)
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless(ctx, "normalize", TEXT_NORMALIZED, {"documents": 1})
    anchor = ctx.cfg.gold_consolidated / "ADT" / "doc"
    cas.atomic_write(anchor / "body.md", b"# No manifest\n")  # no bundle.yaml
    _bless(ctx, "consolidate", CONSOLIDATED)

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert any(f["kind"] == "unmanifested" for f in report["bundle_findings"])


# --- fault injection: prove the gate BITES on a planted silent detector miss (not just on a hand-
# --- seeded capture.yaml). The capture.yaml here is the REAL capture_pure.build_manifest output,
# --- so the chain residue-rescan → absent-unexpected → gate-block is exercised end-to-end.
def _seed_bundle_real_capture(ctx, slug, body, manifest, *, anchors=("intro",), outbound=None):
    bundle = ctx.cfg.silver_normalized / "ADT" / slug
    cas.atomic_write(
        bundle / "body.md",
        frontmatter.emit({"title": slug, "app_code": "ADT", "tool_ver": "0.1.0"}, body).encode(),
    )
    cas.atomic_write(bundle / "capture.yaml", yaml.safe_dump(manifest).encode())
    cas.atomic_write(
        bundle / "refs.yaml",
        yaml.safe_dump(
            {
                "doc_id": f"ADT/{slug}",
                "anchors": [{"slug": s, "title": s} for s in anchors],
                "outbound": outbound or {},
            }
        ).encode(),
    )


def test_validate_blocks_on_injected_silent_revision_miss(ctx):
    # FAULT INJECTION: the normalized body still carries a revision-history section under a VARIANT
    # heading ("Change History") that the strict detector (REVISION_HEADING_TEXTS) misses, and the
    # detector reports a clean miss (count=0, no parse flag) — a *silent* per-document loss that
    # corpus aggregates cannot see. The detector-INDEPENDENT residue rescan (broader tails set)
    # must reclassify it absent-unexpected, and the gate must block — proving the second signal is
    # genuinely independent for the revision class (the review's residue-independence concern).
    body = "# Doc\n\n## Change History\n\n| Date | Note |\n| --- | --- |\n| 2020 | first |\n"
    manifest = cap.build_manifest(
        "ADT/rev", body, frozenset(),
        revisions_count=0, revision_failed=False,  # silent miss: found nothing, not flagged
        tables_count=1, refs_count=1, toc_count=0, title_date_captured=True,
    )  # fmt: skip
    assert manifest["captures"]["revisions"]["outcome"] == cap.ABSENT_UNEXPECTED
    assert cap.has_unexpected_absence(manifest)

    _seed_bundle_real_capture(ctx, "rev", body, manifest)
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1, "absent_unexpected": 1})
    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert report["blocking"] is True
    assert any(f["kind"] == "absent-unexpected" for f in report["reconcile_findings"])


def test_validate_blocks_on_injected_silent_table_miss(ctx):
    # FAULT INJECTION: a qualifying (≥10-row) table remains in the body but the table detector
    # reported zero extractions — the residue post-condition (count_qualifying_tables) catches the
    # leftover → absent-unexpected → gate blocks. KNOWN BOUNDARY (tracked as code-review-stage-4
    # increment 4): this residue shares the detector's `_qualifies` predicate, so a table the
    # detector *rejects by threshold* is NOT caught here — only the corpus-zero reconciliation
    # backstops that. This pins the post-condition the residue DOES provide.
    rows = "\n".join(f"| {i} | row{i} |" for i in range(12))
    body = f"# Doc\n\n| A | B |\n| --- | --- |\n{rows}\n"
    manifest = cap.build_manifest(
        "ADT/tbl", body, frozenset(),
        revisions_count=0, revision_failed=False,
        tables_count=0, refs_count=1, toc_count=0, title_date_captured=True,  # detector missed it
    )  # fmt: skip
    assert manifest["captures"]["tables"]["outcome"] == cap.ABSENT_UNEXPECTED
    _seed_bundle_real_capture(ctx, "tbl", body, manifest)
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1, "absent_unexpected": 1})
    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
