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


def _section(text, *, kind="ok", searchable=True, sid="SD/x/s", path=""):
    return ip.Section(
        section_id=sid,
        slug="s",
        title="S",
        level=2,
        text=text,
        toc_level=True,
        kind=kind,
        searchable=searchable,
        section_path=path,
    )


def test_search_chunks_single_for_small_searchable_section():
    chunks = ip.search_chunks(_section("## S\n\nshort body", sid="SD/x/s"))
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "SD/x/s" and chunks[0].section_id == "SD/x/s"
    assert chunks[0].part == 0 and "short body" in chunks[0].text


def test_search_chunks_empty_for_non_searchable_section():
    assert ip.search_chunks(_section("## C\n", kind="container", searchable=False)) == []
    assert ip.search_chunks(_section("## H\n", kind="hollow", searchable=False)) == []


def test_search_chunks_splits_oversized_with_pN_suffix_part0_bare():
    big = "## S\n\n" + "\n\n".join(f"Paragraph {i}: " + "word " * 80 for i in range(40))
    chunks = ip.search_chunks(_section(big, sid="SD/x/big"))
    assert len(chunks) > 1
    assert chunks[0].chunk_id == "SD/x/big" and chunks[0].part == 0  # part 0 keeps the bare id
    assert chunks[1].chunk_id == "SD/x/big#p2" and chunks[1].part == 1
    assert all(c.section_id == "SD/x/big" for c in chunks)  # every part cites the same anchor


# --- A2b: small-leaf merge (§9c) -----------------------------------------------------------------


def _leaf(sid, text, *, path="Options", kind="ok", searchable=True):
    return _section(text, kind=kind, searchable=searchable, sid=sid, path=path)


def _unsearchable(sid, kind):
    return _leaf(sid, "", kind=kind, searchable=False)


def test_chunk_units_merges_small_adjacent_leaves_under_same_parent():
    secs = [_leaf("d/a", "alpha"), _leaf("d/b", "beta"), _leaf("d/c", "gamma")]
    units = ip.chunk_units(secs, target=100, merge=True)
    assert len(units) == 1
    u = units[0]
    assert u.section_id == "d/a"  # cites the first leaf (the anchor)
    assert u.member_ids == ("d/a", "d/b", "d/c")
    assert "alpha" in u.text and "beta" in u.text and "gamma" in u.text


def test_chunk_units_does_not_merge_across_different_parents():
    secs = [_leaf("d/a", "alpha", path="P1"), _leaf("d/b", "beta", path="P2")]
    units = ip.chunk_units(secs, target=100, merge=True)
    assert [u.section_id for u in units] == ["d/a", "d/b"]


def test_chunk_units_does_not_merge_top_level_leaves():
    # empty section_path = top-level (no common parent heading) → never merged (H2-boundary rule)
    secs = [_leaf("d/a", "alpha", path=""), _leaf("d/b", "beta", path="")]
    units = ip.chunk_units(secs, target=100, merge=True)
    assert [u.section_id for u in units] == ["d/a", "d/b"]
    assert all(len(u.member_ids) == 1 for u in units)


def test_chunk_units_flushes_on_non_searchable_section():
    secs = [_leaf("d/a", "alpha"), _unsearchable("d/c", "container"), _leaf("d/b", "beta")]
    units = ip.chunk_units(secs, target=100, merge=True)
    # container breaks the run; no unit for it
    assert [u.section_id for u in units] == ["d/a", "d/b"]


def test_chunk_units_large_leaf_stands_alone():
    big = "x" * 200  # ≥ target → not mergeable
    secs = [_leaf("d/a", "alpha"), _leaf("d/big", big), _leaf("d/b", "beta")]
    units = ip.chunk_units(secs, target=100, merge=True)
    assert [u.section_id for u in units] == ["d/a", "d/big", "d/b"]
    assert units[1].member_ids == ("d/big",)


def test_chunk_units_starts_new_unit_when_cumulative_exceeds_target():
    secs = [_leaf("d/a", "a" * 60), _leaf("d/b", "b" * 60), _leaf("d/c", "c" * 60)]
    units = ip.chunk_units(secs, target=100, merge=True)
    # a(60) starts a run; +b=120>100 → flush a alone; b(60) starts; +c=120>100 → b alone, c alone
    assert [u.member_ids for u in units] == [("d/a",), ("d/b",), ("d/c",)]


def test_chunks_for_unit_single_and_oversized():
    one = ip.ChunkUnit("d/a", "A", "Options", "small body", ("d/a",))
    assert [c.chunk_id for c in ip.chunks_for_unit(one)] == ["d/a"]
    big = "\n\n".join(f"Paragraph {i}: " + "word " * 80 for i in range(40))
    many = ip.chunks_for_unit(ip.ChunkUnit("d/big", "B", "Options", big, ("d/big",)))
    assert len(many) > 1
    assert many[0].chunk_id == "d/big" and many[1].chunk_id == "d/big#p2"
    assert all(c.section_id == "d/big" for c in many)


def test_chunk_units_skips_non_searchable_entirely():
    secs = [_unsearchable("d/c", "container"), _unsearchable("d/h", "hollow")]
    assert ip.chunk_units(secs, target=100, merge=True) == []


# --- B3b: extracted tables as searchable data (§8.4) ---------------------------------------------


def test_find_table_refs_extracts_filename_and_caption():
    text = (
        "## Routines\n\n"
        "_[Table 5: VA FileMan Routines (extracted to CSV)](tables/table-02.csv)_\n\n"
        "Some prose.\n"
    )
    assert ip.find_table_refs(text) == [("table-02.csv", "Table 5: VA FileMan Routines")]


def test_find_table_refs_ignores_ordinary_links():
    text = "See _[the manual](other.md)_ and [boilerplate](_shared/boilerplate/bp-x.md)."
    assert ip.find_table_refs(text) == []


def test_table_chunk_text_flattens_caption_header_rows():
    rows = [["Term", "Description"], ["GUI", "Graphical UI"], ["DLL", "Dynamic Link Library"]]
    out = ip.table_chunk_text("Table 1: Acronyms", rows)
    assert out.startswith("Table 1: Acronyms")
    assert "Term | Description" in out
    assert "GUI | Graphical UI" in out
    assert "DLL | Dynamic Link Library" in out


def test_table_chunk_text_handles_empty_caption_and_rows():
    assert ip.table_chunk_text("", []) == ""
    assert ip.table_chunk_text("Cap", []) == "Cap"


def test_table_chunk_texts_single_window_when_small():
    rows = [["Term", "Def"], ["A", "alpha"]]
    assert ip.table_chunk_texts("Cap", rows) == [ip.table_chunk_text("Cap", rows)]


def test_table_chunk_texts_splits_oversized_tables_repeating_caption():
    # a big table must be windowed so no single chunk blows the embedder token budget; the caption
    # repeats in each window so every part is self-describing.
    rows = [[f"ROW{i}", "x" * 50] for i in range(400)]  # well over the hard cap
    windows = ip.table_chunk_texts("Acronyms", rows, target=2000, hard=4000)
    assert len(windows) > 1
    assert all(w.startswith("Acronyms") for w in windows)  # caption in every window
    assert all(len(w) <= 4000 for w in windows)  # each within the hard cap
    # no rows lost across windows
    assert sum(w.count("ROW") for w in windows) == 400


def test_table_chunk_texts_empty_is_no_windows():
    assert ip.table_chunk_texts("", []) == []


def test_chunk_units_default_is_one_unit_per_leaf_merge_gated_off():
    # MERGE_SMALL_LEAVES is off by default (Phase-C-gated): every searchable leaf stands alone,
    # identical to the pre-A2b per-leaf chunking — so the live lexical surface is unchanged.
    assert ip.MERGE_SMALL_LEAVES is False
    secs = [_leaf("d/a", "alpha"), _leaf("d/b", "beta"), _leaf("d/c", "gamma")]
    units = ip.chunk_units(secs, target=100)  # default merge=MERGE_SMALL_LEAVES
    assert [u.section_id for u in units] == ["d/a", "d/b", "d/c"]
    assert all(len(u.member_ids) == 1 for u in units)


def test_split_oversized_returns_single_window_when_under_threshold():
    assert ip.split_oversized("short body\n\nanother para") == ["short body\n\nanother para"]


def test_split_oversized_windows_large_body_preserving_all_paragraphs():
    paras = [f"Paragraph {i}: " + "word " * 80 for i in range(40)]  # ~17 KB, over the threshold
    text = "\n\n".join(paras)
    windows = ip.split_oversized(text)
    assert len(windows) > 1
    for p in paras:  # no content dropped — every source paragraph survives in some window
        assert any(p in w for w in windows)
    # consecutive windows overlap by a shared block (context continuity across the boundary)
    assert any(set(a.split("\n\n")) & set(b.split("\n\n")) for a, b in zip(windows, windows[1:]))
    # part windows stay within a sane bound (atomic blocks aside — none here)
    assert all(len(w) <= ip.OVERSIZED_CHUNK_CHARS for w in windows)


def test_split_oversized_never_splits_inside_a_fence():
    fence = "```\n" + "\n".join(f"code line {i}" for i in range(300)) + "\n```"  # one atomic block
    text = "intro para\n\n" + fence + "\n\n" + ("word " * 2000)  # > threshold, forces a split
    windows = ip.split_oversized(text)
    assert len(windows) > 1
    assert any(fence in w for w in windows)  # the whole fence lives intact in exactly one window


def test_split_oversized_bounds_a_giant_blank_lineless_block():
    # an unextracted inline HTML table is one block with no blank-line boundaries — it must still be
    # bounded to ≤ hard so it can't blow the embedder token budget the embed gate asserts.
    giant = "\n".join(f"<td>cell {i} value</td>" for i in range(3000))  # ~60k chars, no blank lines
    windows = ip.split_oversized(giant, target=2000, hard=4000)
    assert len(windows) > 1
    assert all(len(w) <= 4000 for w in windows)  # every window within the hard cap
    assert sum(w.count("<td>") for w in windows) == 3000  # no rows lost


def test_shred_sets_section_path_to_ancestor_chain():
    # section_path = the ancestor-title chain (context as metadata, §14.6) — so a condensed chunk is
    # self-interpretable. Real ancestors only (the doc-title H1 is a real heading, not fabricated).
    secs = {s.slug: s for s in ip.shred_sections(_BODY, "ADT/ig_doc")}
    assert secs["title"].section_path == ""  # top-level heading: no ancestors
    assert secs["setup"].section_path == "Title"
    assert secs["sub-step"].section_path == "Title > Setup"
    assert secs["usage"].section_path == "Title"  # H3 closed; back to a child of the H1


def test_shred_section_path_carries_container_title():
    body = (
        "## Pre-installation Considerations\n\n"
        "### Client Requirements\n\nInstall the v32 client on each workstation before upgrade.\n"
    )
    secs = {s.slug: s for s in ip.shred_sections(body, "SD/x")}
    assert secs["client-requirements"].section_path == "Pre-installation Considerations"


def test_shred_marks_stub_leaf_searchable():
    # a thin leaf whose content was relocated to a referent (shared boilerplate / CSV) is a STUB,
    # not hollow — content isn't lost, so it stays searchable (reported, never penalised).
    body = (
        "## Standard Notice\n\n_[VA notice — shared boilerplate](_shared/boilerplate/va.md)_\n\n"
        "## Data\n\nSee [the table](tables/table-01.csv) for the full field list.\n"
    )
    secs = {s.slug: s for s in ip.shred_sections(body, "SD/x")}
    assert secs["standard-notice"].kind == "stub" and secs["standard-notice"].searchable is True


# --- P0: read-contract meta (schema version + corpus fingerprint) -------------------------------
# Pure construction of the index.db `meta` rows: a structural-contract version axis
# (read_schema_version) + a data fingerprint axis (corpus_content_hash). The hash must be
# deterministic and order-independent (so an identical corpus rebuilds to the same fingerprint —
# no build timestamps in it) and must change when any document row changes.

_DOCS_A = [("CPRS/or_ig", "CPRS:or_ig", "CPRS", 1), ("ADT/um", "ADT:um", "ADT", 0)]
_DOCS_B = [("ADT/um", "ADT:um", "ADT", 0), ("CPRS/or_ig", "CPRS:or_ig", "CPRS", 1)]  # reordered


def test_corpus_content_hash_is_deterministic_and_order_independent():
    assert ip.corpus_content_hash(_DOCS_A) == ip.corpus_content_hash(_DOCS_B)
    # a fingerprint, not empty
    assert len(ip.corpus_content_hash(_DOCS_A)) == 64  # sha256 hexdigest


def test_corpus_content_hash_changes_when_a_document_changes():
    # flip is_latest on the first doc → a different fingerprint
    changed = [("CPRS/or_ig", "CPRS:or_ig", "CPRS", 0), ("ADT/um", "ADT:um", "ADT", 0)]
    assert ip.corpus_content_hash(changed) != ip.corpus_content_hash(_DOCS_A)


def test_meta_rows_carry_schema_version_and_fingerprint():
    rows = dict(ip.meta_rows(_DOCS_A))
    assert rows["read_schema_version"] == ip.READ_SCHEMA_VERSION == "1.0"
    assert rows["corpus_doc_count"] == "2"
    assert rows["corpus_content_hash"] == ip.corpus_content_hash(_DOCS_A)
