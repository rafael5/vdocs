"""Unit tests for the over-strip guardrail (fidelity §10.5 / vdocs-design §6.5).

Condensation raises signal-to-noise only up to an optimum; past it a chunk is stripped so bare it
no longer stands alone. ``overstrip_pure`` flags those **hollow** chunks — a content heading whose
retained body is below the substantive-token floor *and* carries no resolvable referent — while
never penalising a chunk whose content was *relocated* to a referent (boilerplate link / CSV stub /
asset), which is by-design decomposition. T-only, pure, deterministic — like ``compliance_pure``.
"""

from __future__ import annotations

from vdocs.stages.fidelity import overstrip_pure as op

_PROSE = "This section carries genuine substantive prose that stands on its own when retrieved."


def test_pass_when_every_chunk_has_substance():
    body = f"# Doc\n\n## Purpose\n\n{_PROSE}\n\n## Scope\n\n{_PROSE}\n"
    v = op.score_over_strip(body)
    assert v.verdict == op.PASS
    assert v.score == 1.0
    assert v.content_chunks == 2
    assert v.hollow == ()
    assert v.over_strip_rate == 0.0


def test_hollow_chunk_drops_below_pass():
    # three content chunks, one stripped to only a back-link → hollow → never silently PASS
    body = (
        f"# Doc\n\n## Purpose\n\n{_PROSE}\n\n"
        "## Empty\n\n[↑ Back to Contents](#contents)\n\n"
        f"## Scope\n\n{_PROSE}\n"
    )
    v = op.score_over_strip(body)
    assert v.verdict == op.REVIEW
    assert v.hollow == ("Empty",)
    assert v.content_chunks == 3
    assert abs(v.over_strip_rate - 1 / 3) < 1e-9


def test_csv_sidecar_stub_is_not_hollow():
    # a big data table lifted to tables/*.csv leaves only the stub — content RELOCATED, not lost.
    # This is the §6.5/§4 correctness point: by-design decomposition must never read as over-strip.
    body = (
        f"# Doc\n\n## Field Listing\n\n"
        "_[Table 1 (extracted to CSV)](tables/table-01.csv)_\n\n"
        f"## Scope\n\n{_PROSE}\n"
    )
    v = op.score_over_strip(body)
    assert v.verdict == op.PASS
    assert v.hollow == ()
    assert "Field Listing" in v.stubs


def test_boilerplate_reference_is_not_hollow():
    # a referenced boilerplate block (single-sourced to gold/_shared) is recoverable → not hollow.
    body = (
        "# Doc\n\n## How To Use This Manual\n\n"
        "[How to use this manual](_shared/boilerplate/bp-9ea93a696b.md)\n\n"
        f"## Scope\n\n{_PROSE}\n"
    )
    v = op.score_over_strip(body)
    assert v.verdict == op.PASS
    assert v.hollow == ()


def test_container_heading_excluded():
    # an H2 with no own prose but real H3 subsections is a container — its substance is in children,
    # so it is excluded from the content-chunk denominator and never flagged hollow.
    body = f"# Doc\n\n## Procedures\n\n### Step One\n\n{_PROSE}\n\n### Step Two\n\n{_PROSE}\n"
    v = op.score_over_strip(body)
    assert v.verdict == op.PASS
    assert v.content_chunks == 2  # the two H3 leaves, not the H2 container
    assert v.hollow == ()


def test_quarantine_when_most_chunks_hollow():
    body = (
        f"# Doc\n\n## A\n\n{_PROSE}\n\n"
        "## B\n\n[↑ Back to Contents](#contents)\n\n"
        "## C\n\n[↑ Back to Contents](#contents)\n\n"
        "## D\n\n[↑ Back to Contents](#contents)\n"
    )
    v = op.score_over_strip(body)
    assert v.verdict == op.QUARANTINE  # 3/4 hollow → score 0.25 < 0.5
    assert v.score == 0.25


def test_no_content_sections_scores_pass():
    v = op.score_over_strip("# Just A Title\n\nsome intro\n")
    assert v.verdict == op.PASS
    assert v.content_chunks == 0
    assert v.over_strip_rate == 0.0


def test_audit_chunks_classification():
    body = (
        f"# Doc\n\n## Real\n\n{_PROSE}\n\n"
        "## Stub\n\n_[Table 1 (extracted to CSV)](tables/table-01.csv)_\n\n"
        "## Hollow\n\n[↑ Back to Contents](#contents)\n"
    )
    by_title = {a.title: a for a in op.audit_chunks(body)}
    assert by_title["Real"].classification == "ok"
    assert by_title["Stub"].classification == "stub"
    assert by_title["Stub"].has_referent is True
    assert by_title["Hollow"].classification == "hollow"
    assert by_title["Hollow"].has_referent is False


def test_min_tokens_is_tunable():
    # a short-but-real chunk passes a lenient floor and fails a strict one
    body = "# Doc\n\n## Note\n\nShort note here.\n"
    assert op.score_over_strip(body, min_tokens=2).verdict == op.PASS
    assert op.score_over_strip(body, min_tokens=20).hollow == ("Note",)


def test_blocks_publish_gate_semantics():
    assert op.blocks_publish(op.QUARANTINE) is True
    assert op.blocks_publish(op.REVIEW) is True
    assert op.blocks_publish(op.REVIEW, signed_off=True) is False
    assert op.blocks_publish(op.PASS) is False
