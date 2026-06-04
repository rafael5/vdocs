"""Unit tests for `index`'s pure shredding (§14.6 — chunk on structure, not bytes). The section
stable id must match `normalize`'s `refs.yaml` (`<doc_key>/<slug>`), so the same fence-aware
heading scan + GitHub-slug dedup is reused (§9.2)."""

from __future__ import annotations

from vdocs.stages.index import index_pure as ip

_BODY = (
    "# Title\n\nintro para\n\n"
    "## Setup\n\nstep one\n\n"
    "### Sub Step\n\ndetail here\n\n"
    "## Usage\n\nuse it\n"
)


def test_shred_sections_one_per_heading_with_stable_ids():
    secs = ip.shred_sections(_BODY, "ADT/ig_doc")
    assert [s.slug for s in secs] == ["title", "setup", "sub-step", "usage"]
    assert [s.section_id for s in secs] == [
        "ADT/ig_doc/title",
        "ADT/ig_doc/setup",
        "ADT/ig_doc/sub-step",
        "ADT/ig_doc/usage",
    ]
    assert [s.level for s in secs] == [1, 2, 3, 2]


def test_section_text_spans_to_next_heading_only():
    secs = {s.slug: s for s in ip.shred_sections(_BODY, "ADT/ig_doc")}
    assert "step one" in secs["setup"].text
    assert "use it" not in secs["setup"].text  # stops at the next heading
    assert "detail here" not in secs["setup"].text  # the H3 begins a new section


def test_toc_level_follows_depth():
    secs = {s.slug: s for s in ip.shred_sections(_BODY, "ADT/ig_doc", toc_depth=(2, 3))}
    assert secs["title"].toc_level is False  # H1 is the doc title, never in-TOC
    assert secs["setup"].toc_level is True and secs["sub-step"].toc_level is True


def test_shred_is_fence_aware():
    body = "## Real\n\n```\n## not a heading\n```\n\ntext\n"
    secs = ip.shred_sections(body, "ADT/x")
    assert [s.slug for s in secs] == ["real"]  # the fenced "## not a heading" is not a section


def test_shred_section_ids_are_unique_despite_github_slug_collisions():
    # real-corpus edge: repeated "Example" headings slug to example/example-1/… while a literal
    # "Example 1" heading *also* slugs to example-1 — GitHub's quirk. section_id is a PRIMARY KEY,
    # so shred must keep them unique (a deterministic disambiguator on true collisions).
    body = "## Example\n\na\n\n## Example 1\n\nb\n\n## Example\n\nc\n"
    secs = ip.shred_sections(body, "ADT/x")
    ids = [s.section_id for s in secs]
    assert len(ids) == len(set(ids)) == 3  # all unique despite the example-1 collision


def test_shred_skips_generated_contents():
    body = "# Doc\n\n## Contents\n\n- [Setup](#setup)\n\n## Setup\n\nbody\n"
    slugs = [s.slug for s in ip.shred_sections(body, "ADT/x")]
    assert "contents" not in slugs and slugs == ["doc", "setup"]


# --- A1 increment 1: structure-aware classification (container/ok/stub/hollow + searchable) ---


def test_shred_classifies_container_vs_leaf_and_marks_searchable():
    # "Pre-installation Considerations" has only deeper subsections + no own prose → a CONTAINER:
    # it must NOT be a searchable chunk (its substance lives in its children), but it stays a row.
    body = (
        "## Pre-installation Considerations\n\n"
        "[↑ Back to Contents](#contents)\n\n"
        "### Client Requirements\n\nInstall the v32 client on each workstation before upgrade.\n\n"
        "## Overview\n\nThis manual describes the scheduling package and all its options.\n"
    )
    secs = {s.slug: s for s in ip.shred_sections(body, "SD/sd_ig")}
    assert secs["pre-installation-considerations"].kind == "container"
    assert secs["pre-installation-considerations"].searchable is False
    assert secs["client-requirements"].kind == "ok"  # a substantive leaf
    assert secs["client-requirements"].searchable is True
    assert secs["overview"].kind == "ok" and secs["overview"].searchable is True


def test_shred_marks_hollow_leaf_not_searchable():
    # a leaf reduced to a bare heading + back-link, no children, no referent → HOLLOW (the defect):
    # excluded from the search surface, but still emitted as a row (anchor/nav map stays complete).
    body = (
        "## Empty Section\n\n[↑ Back to Contents](#contents)\n\n"
        "## Real Section\n\nThis section has plenty of real prose to stand alone when retrieved.\n"
    )
    secs = {s.slug: s for s in ip.shred_sections(body, "SD/x")}
    assert secs["empty-section"].kind == "hollow" and secs["empty-section"].searchable is False
    assert secs["real-section"].kind == "ok" and secs["real-section"].searchable is True
    assert "empty-section" in {s.slug for s in ip.shred_sections(body, "SD/x")}  # row still present


def test_shred_marks_stub_leaf_searchable():
    # a thin leaf whose content was relocated to a referent (shared boilerplate / CSV) is a STUB,
    # not hollow — content isn't lost, so it stays searchable (reported, never penalised).
    body = (
        "## Standard Notice\n\n_[VA notice — shared boilerplate](_shared/boilerplate/va.md)_\n\n"
        "## Data\n\nSee [the table](tables/table-01.csv) for the full field list.\n"
    )
    secs = {s.slug: s for s in ip.shred_sections(body, "SD/x")}
    assert secs["standard-notice"].kind == "stub" and secs["standard-notice"].searchable is True
