"""validate integration — the sidecar-verification HARD GATE (Steps 2-3; §8, FF C2/C5).

Seeds a normalized tree of bundles (each with capture.yaml + refs.yaml), blesses the normalize
upstream with its emitted counts, runs ValidateStage through the orchestrator, and asserts the gate:
PASSES on a clean corpus (writing the findings report), and FAILS loudly on a per-document
absent-unexpected (typed absence), a corpus-zero whole-detector failure (count reconciliation), a
severed cross-ref (ref resolution), and a cross-run count drop.
"""

from __future__ import annotations

import hashlib
import json

import pytest
import yaml

from vdocs.contracts.registry import (
    CONSOLIDATED,
    GOLD_INVENTORY,
    RAW_INDEX,
    TEXT_CONVERTED,
    TEXT_NORMALIZED,
)
from vdocs.kernel import bundle as kbundle
from vdocs.kernel import cas, frontmatter
from vdocs.models.catalog import EnrichedInventory, EnrichedRecord
from vdocs.models.stage import Acquisition, StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.orchestrator.stage import PostflightError
from vdocs.stages.fetch.fetch_pure import RAW_INDEX_FORMAT
from vdocs.stages.normalize import capture_pure as cap
from vdocs.stages.validate import chain_pure as ch
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


def _history_yaml(body: bytes, *, sha=None):
    """A truthful one-member `history.yaml` for a gold bundle — the latest member records the sha of
    the body beside it, which is exactly what the P5.2 lineage check verifies. ``sha`` overrides it
    to stage the stale-lineage red path."""
    return yaml.safe_dump(
        {
            "anchor_key": "ADT:ADT:DOC",
            "member_count": 1,
            "members": [
                {
                    "doc_id": "ADT:doc",
                    "doc_slug": "doc",
                    "patch_id": "ADT*1.0*1",
                    "official_date": "2024-01",
                    "source_sha256": "abc",
                    "body_sha256": sha or hashlib.sha256(body).hexdigest(),
                    "is_latest": True,
                    "revisions": [],
                }
            ],
        }
    ).encode()


def _seed_consolidated_ok(
    ctx, *, verdict="PASS", retention=0.97, with_capture=True, hist_sha=None, history=None
):
    """One valid gold anchor bundle (body.md + history.yaml + the travelling capture.yaml + a
    correct bundle.yaml) so validate's CONSOLIDATED requirement, the bundle-integrity gate, the
    P5.2 lineage check and the Step-6 retention gate all pass by default; the gate tests vary this
    instead.

    The retention block is what P3.3 reads: it rides in the gold bundle's capture.yaml and is
    covered by bundle.yaml's part hashes, so the gate reads a *verified* record. ``hist_sha`` stales
    the lineage **before** bundle.yaml is built, so the manifest stays green and the lineage check
    is the only thing that can fire."""
    anchor = ctx.cfg.gold_consolidated / "ADT" / "doc"
    capture = yaml.safe_dump(
        {
            "doc_id": "ADT:doc",
            "captures": {},
            "retention": {
                "retention": retention,
                "verdict": verdict,
                "enriched_words": 100,
                "kept_words": int(100 * retention),
            },
        }
    ).encode()
    history = history or _history_yaml(b"# Anchor\n", sha=hist_sha)
    parts = {"body.md": b"# Anchor\n", "history.yaml": history}
    cas.atomic_write(anchor / "body.md", b"# Anchor\n")
    cas.atomic_write(anchor / "history.yaml", history)
    if with_capture:  # an unscored bundle is seeded that way, never mutated after blessing
        parts["capture.yaml"] = capture
        cas.atomic_write(anchor / "capture.yaml", capture)
    manifest = kbundle.build_manifest(
        parts, doc_id="ADT/doc", anchor_key="ADT:ADT:DOC",
        tool_ver=ctx.cfg.tool_ver, source_sha256=["abc"],
    )  # fmt: skip
    cas.atomic_write(anchor / "bundle.yaml", yaml.safe_dump(manifest).encode())
    _bless(ctx, "consolidate", CONSOLIDATED)


def _normalized_slugs(ctx):
    """The slugs the test actually seeded into the normalized tree — the chain is seeded to match
    it, so a chain finding in these tests always means a real Step-5 defect, never fixture skew."""
    root = ctx.cfg.silver_normalized
    return sorted(p.parent.name for p in root.rglob("body.md")) if root.is_dir() else []


def _seed_chain(ctx, slugs, *, converted_slugs=None, unadmitted=()):
    """Seed an intact acquisition chain for ``slugs`` — gold inventory ⋈ acquisitions ⋈
    raw/index.json ⋈ converted bundles — so validate's Step-5 chain gate (P1.2) has all five
    seams to join. Each record must clear the REAL admission gate (VistA app, kept doc-type),
    since the gate policy is read from the repo registries.

    ``converted_slugs`` (default: all of ``slugs``) narrows which docs get a converted bundle, so
    a test can seed a *broken* chain **before** blessing — mutating the tree afterwards would trip
    the upstream-drift preflight instead of the gate under test. ``unadmitted`` slugs get the full
    downstream treatment (acquisition + index entry + both bundles) but **no inventory record** —
    the withdrawn/renamed document the gate no longer admits."""
    converted_slugs = slugs if converted_slugs is None else converted_slugs
    records = [
        EnrichedRecord(
            doc_title=slug,
            doc_url=f"https://va.gov/d/{slug}.docx",
            doc_filename=f"{slug}.docx",
            doc_format="docx",
            app_name_abbrev="ADT",
            section_code="CLIN",
            app_status="active",
            system_type="VistA",
            doc_slug=slug,
            doc_code="UM",
            anchor_key=f"ADT:ADT:UM:{slug}",
        )
        for slug in slugs
    ]
    cas.atomic_write(
        ctx.cfg.gold_inventory_json,
        EnrichedInventory(records=records).model_dump_json().encode(),
    )
    docs = {}
    for slug in [*slugs, *unadmitted]:
        ctx.state.record_acquisition(
            Acquisition(
                doc_id=f"ADT:{slug}",
                source_url=f"https://va.gov/d/{slug}.docx",
                status="fetched",
                sha256=f"sha-{slug}",
                tool_ver=ctx.cfg.tool_ver,
            )
        )
        docs[f"ADT:{slug}"] = {
            "sha256": f"sha-{slug}",
            "app_code": "ADT",
            "doc_slug": slug,
            "title": slug,
            "source_url": f"https://va.gov/d/{slug}.docx",
            "ext": "docx",
        }
        if slug in converted_slugs or slug in unadmitted:
            cas.atomic_write(ctx.cfg.silver_converted / "ADT" / slug / "body.md", b"# Doc\n")
        if slug in unadmitted:  # it made it all the way through before the gate changed
            cas.atomic_write(ctx.cfg.silver_normalized / "ADT" / slug / "body.md", b"# Doc\n")
    cas.atomic_write(
        ctx.cfg.raw_index,
        json.dumps({"format": RAW_INDEX_FORMAT, "docs": docs}).encode(),
    )
    _bless(ctx, "serve-inventory", GOLD_INVENTORY)
    _bless(ctx, "fetch", RAW_INDEX)
    _bless(ctx, "convert", TEXT_CONVERTED)


def _bless_normalize(ctx, counts, slugs=None):
    """Bless every upstream validate requires: normalize (with counts), a clean consolidate, and
    an intact fetch-side chain matching the seeded bundles (the Step-5 gate joins it)."""
    _bless(ctx, "normalize", TEXT_NORMALIZED, counts)
    _seed_consolidated_ok(ctx)
    _seed_chain(ctx, slugs if slugs is not None else _normalized_slugs(ctx))


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
    _seed_chain(ctx, _normalized_slugs(ctx))  # intact chain: the bundle gate is what must fire
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


def test_validate_blocks_on_stale_lineage(ctx):
    # Step 4 extension (P5.2): the gold bundle is INTACT — bundle.yaml verifies, every part hashes
    # correctly — but its history.yaml's latest member records a body_sha256 that is not this
    # body.md. That is the audit's [S9]a defect (measured at 615/615 before P5.1), and it is exactly
    # what a recomputed-from-disk manifest cannot see. The lineage check must fire on its own.
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless(ctx, "normalize", TEXT_NORMALIZED, {"documents": 1})
    _seed_chain(ctx, _normalized_slugs(ctx))
    _seed_consolidated_ok(ctx, hist_sha="dead" * 16)  # staled BEFORE bundle.yaml is built

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    stale = [f for f in report["bundle_findings"] if f["kind"] == "stale-lineage"]
    assert len(stale) == 1
    assert "ADT:doc" in stale[0]["detail"] and stale[0]["path"] == "history.yaml"
    # the manifest itself is clean — proving the lineage check is what caught it, not integrity
    assert not [f for f in report["bundle_findings"] if f["kind"] != "stale-lineage"]


def test_validate_blocks_on_a_gold_bundle_with_no_lineage(ctx):
    # absence is UNKNOWN, never OK: a bundle whose history.yaml is gone cannot be verified against
    # its body, so it is reported rather than silently passed over
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless(ctx, "normalize", TEXT_NORMALIZED, {"documents": 1})
    _seed_chain(ctx, _normalized_slugs(ctx))
    anchor = ctx.cfg.gold_consolidated / "ADT" / "doc"
    cas.atomic_write(anchor / "body.md", b"# Anchor\n")  # no history.yaml, no bundle.yaml
    _bless(ctx, "consolidate", CONSOLIDATED)

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert any(f["kind"] == "unverifiable-lineage" for f in report["bundle_findings"])


def test_validate_passes_a_bundle_whose_lineage_matches(ctx):
    # the positive half: a truthful lineage — including a PRIOR member recording a different
    # (retained) body — is clean. Only the replay head is checked against this bundle.
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless(ctx, "normalize", TEXT_NORMALIZED, {"documents": 1})
    _seed_chain(ctx, _normalized_slugs(ctx))
    body = b"# Anchor\n"
    history = yaml.safe_dump(
        {
            "anchor_key": "ADT:ADT:DOC",
            "member_count": 2,
            "members": [
                {"doc_id": "ADT:old", "body_sha256": "old" * 21 + "0", "is_latest": False},
                {
                    "doc_id": "ADT:doc",
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                    "is_latest": True,
                    # a P5.1 demotion rides along untouched — it is lineage about a retained body
                    "superseded": [{"doc_id": "ADT:doc", "body_sha256": "prior" * 12}],
                },
            ],
        }
    ).encode()
    _seed_consolidated_ok(ctx, history=history)

    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.status == "ok" and result.counts["bundle_findings"] == 0


def test_validate_blocks_on_unmanifested_bundle(ctx):
    # a gold bundle with no bundle.yaml cannot be verified → blocks (not silently skipped)
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless(ctx, "normalize", TEXT_NORMALIZED, {"documents": 1})
    _seed_chain(ctx, _normalized_slugs(ctx))  # intact chain: the bundle gate is what must fire
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


# --- Step 5: the acquisition-chain gate (P1.2, audit R-3) ------------------------------------


def test_validate_blocks_when_a_fetched_doc_is_missing_from_the_raw_index(ctx):
    # THE regression test for the measured defect: six documents were recorded `fetched`, fell out
    # of the sha-keyed raw/index.json, had no bundle anywhere — and raised a finding NOWHERE.
    # After P1.2 that state is a blocking, per-doc-id finding.
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})
    ctx.state.record_acquisition(
        Acquisition(
            doc_id="ADT:lost_um",  # fetched…
            source_url="https://va.gov/d/lost_um.docx",
            status="fetched",
            sha256="sha-lost",
            tool_ver=ctx.cfg.tool_ver,
        )
    )  # …but never added to raw/index.json → no bundle will ever be produced

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert report["blocking"] is True
    kinds = {(f["kind"], f["doc_id"]) for f in report["chain_findings"]}
    assert (ch.FETCHED_NOT_INDEXED, "ADT:lost_um") in kinds
    # the finding names the LOST DOCUMENT, not just a count — that is what makes it actionable
    assert any("re-run" in f["detail"] for f in report["chain_findings"])


def test_validate_blocks_when_an_indexed_doc_never_converted(ctx):
    # The index claims two docs; convert only ever produced one. Seeded broken BEFORE blessing so
    # the CHAIN gate is what fires (mutating the tree after would trip the drift preflight, and
    # emptying it would trip the "empty tree" input check — both coarser, different guards).
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _seed_bundle(ctx, "b", captures={"refs": "captured"})
    _bless(ctx, "normalize", TEXT_NORMALIZED, {"documents": 2, "refs_sidecars": 2})
    _seed_consolidated_ok(ctx)
    _seed_chain(ctx, ["a", "b"], converted_slugs=["b"])

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert any(f["kind"] == ch.INDEXED_NOT_CONVERTED for f in report["chain_findings"])


def test_validate_blocks_on_a_doc_the_gate_no_longer_admits(ctx):
    # audit R-10: a withdrawn/renamed document (or one a policy edit narrowed out) stays in the
    # corpus until something reconciles it. It is fully present downstream — fetched, indexed,
    # converted, normalized — and only the inventory disagrees, so no per-stage count can see it.
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _seed_chain(ctx, ["a"], unadmitted=["stale"])  # writes the stale bundles…
    _bless(ctx, "normalize", TEXT_NORMALIZED, {"documents": 2, "refs_sidecars": 1})  # …then bless
    _seed_consolidated_ok(ctx)

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert any(
        f["kind"] == ch.FETCHED_NOT_ADMITTED and f["doc_id"] == "ADT:stale"
        for f in report["chain_findings"]
    )


def test_an_intact_chain_produces_no_chain_findings(ctx):
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})
    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.counts["chain_findings"] == 0
    assert json.loads(ctx.cfg.validation_report.read_text())["chain_findings"] == []


# --- Step 6: the content-retention gate (P3.3, audit R‑5 / [S8]) ---------------------------------
# `score_retention` has fired since Phase 3 and `blocks_publish` has encoded the rule since then,
# but nothing called it — so QUARANTINE documents shipped into gold under a green pipeline. These
# are the permanent red-path tests for the wiring (a scratch-lake demonstration cannot rot).


def _signoffs(ctx, *doc_ids, reason="measured: change-pages partial"):
    (ctx.cfg.registries / "retention-signoff.yaml").write_text(
        yaml.safe_dump(
            {"signoffs": [{"doc_id": d, "reason": reason, "date": "2026-08-01"} for d in doc_ids]}
        )
    )


@pytest.fixture
def repo_registries(ctx, tmp_path):
    """Point cfg.registries at a writable copy so a test can curate the sign-off registry."""
    import shutil

    dst = tmp_path / "registries"
    shutil.copytree(ctx.cfg.registries, dst)
    ctx.cfg.registries_dir = dst
    return dst


def test_quarantined_document_blocks_the_gate(ctx, repo_registries):
    # the measured live case: a document whose body was over-stripped must not ship
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})
    _seed_consolidated_ok(ctx, verdict="QUARANTINE", retention=0.05)

    with pytest.raises(PostflightError, match="content-retention"):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    (finding,) = report["retention_findings"]
    assert finding["kind"] == "retention-quarantine" and finding["blocking"] is True
    assert "0.05" in finding["detail"]


def test_quarantine_cannot_be_signed_off(ctx, repo_registries):
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})
    _seed_consolidated_ok(ctx, verdict="QUARANTINE", retention=0.05)
    _signoffs(ctx, "ADT:doc")

    with pytest.raises(PostflightError, match="content-retention"):
        Orchestrator([ValidateStage()]).run(ctx)


def test_review_blocks_until_signed_off(ctx, repo_registries):
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})
    _seed_consolidated_ok(ctx, verdict="REVIEW", retention=0.61)

    with pytest.raises(PostflightError, match="content-retention"):
        Orchestrator([ValidateStage()]).run(ctx)

    _signoffs(ctx, "ADT:doc")
    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.counts["retention_findings"] == 0
    assert json.loads(ctx.cfg.validation_report.read_text())["blocking"] is False


def test_gold_bundle_with_no_retention_record_blocks(ctx, repo_registries):
    # UNKNOWN is not PASS: a bundle that was never scored has not been cleared. Seeded unscored
    # from the start — mutating the tree after blessing trips the upstream-drift preflight (a
    # coarser guard) instead of the gate under test.
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless(ctx, "normalize", TEXT_NORMALIZED, {"documents": 1, "refs_sidecars": 1})
    _seed_consolidated_ok(ctx, with_capture=False)
    _seed_chain(ctx, _normalized_slugs(ctx))

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert any(f["kind"] == "retention-unscored" for f in report["retention_findings"])


def test_stale_signoff_is_reported_without_blocking(ctx, repo_registries):
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless_normalize(ctx, {"documents": 1, "refs_sidecars": 1})
    _seed_consolidated_ok(ctx)  # PASS
    _signoffs(ctx, "ADT:withdrawn")

    (result,) = Orchestrator([ValidateStage()]).run(ctx)
    assert result.counts["retention_findings"] == 0  # counts the BLOCKING ones
    report = json.loads(ctx.cfg.validation_report.read_text())
    assert report["blocking"] is False
    (stale,) = report["retention_findings"]
    assert stale["kind"] == "retention-signoff-stale" and stale["blocking"] is False


def test_validate_blocks_when_a_retained_body_is_missing_from_the_cas(ctx):
    # The lineage's PRIOR members are what a replay replays. `consolidate` promises the CAS is
    # write-once so "they remain by construction"; this is the gate that makes it a fact. Seeded
    # broken BEFORE blessing, so the bundle manifest stays clean and only the lineage check fires.
    _seed_bundle(ctx, "a", captures={"refs": "captured"})
    _bless(ctx, "normalize", TEXT_NORMALIZED, {"documents": 1})
    _seed_chain(ctx, _normalized_slugs(ctx))
    body = b"# Anchor\n"
    history = yaml.safe_dump(
        {
            "anchor_key": "ADT:ADT:DOC",
            "member_count": 2,
            "members": [
                {"doc_id": "ADT:v1", "body_sha256": "a" * 64, "is_latest": False},
                {"doc_id": "ADT:doc", "body_sha256": hashlib.sha256(body).hexdigest(),
                 "is_latest": True},
            ],
        }
    ).encode()  # fmt: skip
    # the LATEST body is retained; the prior one never made it into the store
    cas.atomic_write(ctx.cfg.history_bodies / f"{hashlib.sha256(body).hexdigest()}.md", body)
    _seed_consolidated_ok(ctx, history=history)

    with pytest.raises(PostflightError):
        Orchestrator([ValidateStage()]).run(ctx)
    report = json.loads(ctx.cfg.validation_report.read_text())
    missing = [f for f in report["bundle_findings"] if f["kind"] == "missing-retained-body"]
    assert len(missing) == 1 and "ADT:v1" in missing[0]["detail"]
