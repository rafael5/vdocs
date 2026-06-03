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
