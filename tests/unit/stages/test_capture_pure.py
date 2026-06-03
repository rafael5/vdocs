"""Unit tests for capture_pure — typed capture-attempt classification → capture.yaml (§6.4).

The capture manifest makes a *missing* sidecar unambiguous: every capture attempt records a typed
outcome (captured / failed / absent-expected / absent-unexpected), and an independent residue
re-scan of the normalized body promotes a silent per-document miss to absent-unexpected — the gap
flags.yaml cannot catch (vdocs-design §6.4).
"""

from __future__ import annotations

import yaml

from vdocs.stages.normalize import capture_pure as cp

_TOC_TITLES = frozenset({"table of contents", "contents"})


def _residue(**kw):
    base = dict(
        revision_heading_present=False,
        legacy_toc_heading_present=False,
        heading_present=False,
        qualifying_table_count=0,
    )
    base.update(kw)
    return cp.Residue(**base)


# --- scan_residue: the independent second-signal re-scan -------------------------------------
def test_scan_residue_detects_loose_revision_heading():
    # deliberately broader than kernel.is_revision_heading: "Change History" is NOT in the curated
    # vocabulary, so the strict detector misses it — the residue scan must still see it.
    body = "# Doc\n\n## Change History\n\nstuff\n"
    assert cp.scan_residue(body, _TOC_TITLES).revision_heading_present is True


def test_scan_residue_ignores_generated_contents_heading():
    # the generated `## Contents` is not a legacy TOC and not a content heading (iter_headings skips
    # it) — with no other heading present, the residue scan sees nothing.
    r = cp.scan_residue("## Contents\n\n- [x](#x)\n\nprose\n", _TOC_TITLES)
    assert r.legacy_toc_heading_present is False
    assert r.heading_present is False


def test_scan_residue_detects_legacy_toc_heading():
    r = cp.scan_residue("# Doc\n\n## Table of Contents\n\nentries\n", _TOC_TITLES)
    assert r.legacy_toc_heading_present is True


def test_scan_residue_reports_heading_present():
    assert cp.scan_residue("# Doc\n\n## Setup\n\nx\n", _TOC_TITLES).heading_present is True


def test_scan_residue_counts_qualifying_table():
    rows = "".join(f"<tr><td>a{i}</td><td>b{i}</td></tr>" for i in range(12))
    body = "# Doc\n\n<table><tr><th>A</th><th>B</th></tr>" + rows + "</table>\n"
    assert cp.scan_residue(body, _TOC_TITLES).qualifying_table_count == 1


# --- classify: outcomes per kind ------------------------------------------------------------
def test_classify_captured_when_count_positive():
    out = cp.classify(
        revisions_count=2,
        revision_failed=False,
        tables_count=3,
        refs_count=10,
        toc_count=1,
        title_date_captured=True,
        residue=_residue(),
    )
    assert out["revisions"] == cp.CaptureOutcome(cp.CAPTURED, 2)
    assert out["tables"] == cp.CaptureOutcome(cp.CAPTURED, 3)
    assert out["refs"] == cp.CaptureOutcome(cp.CAPTURED, 10)
    assert out["toc"] == cp.CaptureOutcome(cp.CAPTURED, 1)
    assert out["title_date"].outcome == cp.CAPTURED


def test_classify_revisions_failed_takes_precedence_over_absence():
    out = cp.classify(
        revisions_count=0,
        revision_failed=True,
        tables_count=0,
        refs_count=0,
        toc_count=0,
        title_date_captured=True,
        residue=_residue(revision_heading_present=True),
    )
    # a recognised-but-unparseable apparatus is `failed`, not absent-unexpected
    assert out["revisions"].outcome == cp.FAILED


def test_classify_revisions_absent_unexpected_from_residue():
    out = cp.classify(
        revisions_count=0,
        revision_failed=False,
        tables_count=0,
        refs_count=0,
        toc_count=0,
        title_date_captured=True,
        residue=_residue(revision_heading_present=True),
    )
    assert out["revisions"].outcome == cp.ABSENT_UNEXPECTED


def test_classify_revisions_absent_expected_when_nothing():
    out = cp.classify(
        revisions_count=0,
        revision_failed=False,
        tables_count=0,
        refs_count=0,
        toc_count=0,
        title_date_captured=True,
        residue=_residue(),
    )
    assert out["revisions"].outcome == cp.ABSENT_EXPECTED


def test_classify_tables_absent_unexpected_from_residue():
    out = cp.classify(
        revisions_count=0,
        revision_failed=False,
        tables_count=0,
        refs_count=0,
        toc_count=0,
        title_date_captured=True,
        residue=_residue(qualifying_table_count=1),
    )
    assert out["tables"].outcome == cp.ABSENT_UNEXPECTED


def test_classify_refs_absent_unexpected_when_headings_present():
    out = cp.classify(
        revisions_count=0,
        revision_failed=False,
        tables_count=0,
        refs_count=0,
        toc_count=0,
        title_date_captured=True,
        residue=_residue(heading_present=True),
    )
    assert out["refs"].outcome == cp.ABSENT_UNEXPECTED


def test_classify_toc_absent_unexpected_from_residue():
    out = cp.classify(
        revisions_count=0,
        revision_failed=False,
        tables_count=0,
        refs_count=0,
        toc_count=0,
        title_date_captured=True,
        residue=_residue(legacy_toc_heading_present=True),
    )
    assert out["toc"].outcome == cp.ABSENT_UNEXPECTED


def test_classify_title_date_absent_expected_when_uncaptured():
    out = cp.classify(
        revisions_count=0,
        revision_failed=False,
        tables_count=0,
        refs_count=0,
        toc_count=0,
        title_date_captured=False,
        residue=_residue(),
    )
    # title-page date absence is already a flags.yaml signal; capture.yaml records it benign here
    assert out["title_date"].outcome == cp.ABSENT_EXPECTED


# --- build_manifest: the serialisable capture.yaml ------------------------------------------
def test_build_manifest_round_trips_through_yaml():
    body = "# Doc\n\n## Change History\n\nx\n"  # a leftover revision heading, nothing captured
    manifest = cp.build_manifest(
        "ADT/doc",
        body,
        _TOC_TITLES,
        revisions_count=0,
        revision_failed=False,
        tables_count=0,
        refs_count=0,
        toc_count=0,
        title_date_captured=False,
    )
    loaded = yaml.safe_load(yaml.safe_dump(manifest))
    assert loaded["doc_id"] == "ADT/doc"
    assert loaded["captures"]["revisions"]["outcome"] == cp.ABSENT_UNEXPECTED
    assert set(loaded["captures"]) == {"revisions", "tables", "refs", "toc", "title_date"}
    assert loaded["residue"]["revision_heading_present"] is True


def test_build_manifest_includes_count_for_captured_kinds():
    manifest = cp.build_manifest(
        "ADT/doc",
        "# Doc\n\n## Setup\n\nx\n",
        _TOC_TITLES,
        revisions_count=3,
        revision_failed=False,
        tables_count=1,
        refs_count=5,
        toc_count=0,
        title_date_captured=True,
    )
    assert manifest["captures"]["revisions"]["count"] == 3
    assert manifest["captures"]["refs"]["count"] == 5


def test_has_unexpected_absence_helper():
    # the driver/verifier convenience: does any capture attempt indicate a silent miss?
    clean = cp.build_manifest(
        "ADT/a", "# Doc\n\n## Setup\n\nx\n", _TOC_TITLES,
        revisions_count=0, revision_failed=False, tables_count=0,
        refs_count=1, toc_count=0, title_date_captured=True,
    )  # fmt: skip
    dirty = cp.build_manifest(
        "ADT/b", "# Doc\n\n## Change History\n\nx\n", _TOC_TITLES,
        revisions_count=0, revision_failed=False, tables_count=0,
        refs_count=1, toc_count=0, title_date_captured=True,
    )  # fmt: skip
    assert cp.has_unexpected_absence(clean) is False
    assert cp.has_unexpected_absence(dirty) is True
