"""Unit tests for `index`'s pure shredding (§14.6 — chunk on structure, not bytes). The section
stable id must match `normalize`'s `refs.yaml` (`<doc_key>/<slug>`), so the same fence-aware
heading scan + GitHub-slug dedup is reused (§9.2)."""

from __future__ import annotations

import pytest

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


# --- P6.1b: the RETRIEVAL predicate is not the QA floor. `kind` keeps MIN_SUBSTANTIVE_TOKENS (it
# --- answers "did normalize gut this section?"); `searchable` answers "is there anything to index
# --- here at all?" — measured: 1,896 live sections carried 1-7 tokens of real prose and reached
# --- neither `chunks` nor `chunks_fts`, so their text AND their heading were unfindable.


def test_shred_marks_container_with_own_lead_in_searchable():
    # the audit's [S10] case: a container's own lead-in IS the API contract in a reference manual
    body = (
        "## $$GET^DIQ\n\n"
        "Returns a single field value from a FileMan file, formatted for external display.\n\n"
        "### Input Parameters\n\nFILE is the file number.\n\n"
        "## Other\n\nSomething else entirely that stands on its own as a section body.\n"
    )
    secs = {s.slug: s for s in ip.shred_sections(body, "DI/di_pm")}
    s = secs["getdiq"]
    assert s.kind == "container"  # nav-map semantics untouched — only the retrieval flag moves
    assert s.searchable is True


def test_shred_marks_sub_floor_leaf_searchable_but_still_hollow():
    # "There are no QUASAR package-wide variables." — 6 substantive tokens, a REAL answer to a real
    # question, and dark before P6.1b. It stays `hollow` for over-strip scoring; it is now findable.
    body = (
        "## Package-wide Variables\n\n[↑ Back to Contents](#contents)\n\n"
        "There are no QUASAR package-wide variables.\n\n"
        "## Real Section\n\nThis section has plenty of real prose to stand alone when retrieved.\n"
    )
    secs = {s.slug: s for s in ip.shred_sections(body, "ACKQ/ackq3_0tm")}
    s = secs["package-wide-variables"]
    assert s.kind == "hollow"  # the QA floor is unchanged — this IS a thin section
    assert s.searchable is True  # …but thin is not empty, and it must be retrievable


def test_shred_keeps_genuinely_empty_sections_off_the_search_surface():
    # the floor that remains: nothing but a heading (and round-trip nav) — nothing to index
    body = (
        "## Bare Container\n\n[↑ Back to Contents](#contents)\n\n"
        "### Child\n\nThe child carries all of the substance for this part of the document.\n\n"
        "## Bare Leaf\n\n[↑ Back to Contents](#contents)\n\n"
        "## Real\n\nThis section has plenty of real prose to stand alone when retrieved.\n"
    )
    secs = {s.slug: s for s in ip.shred_sections(body, "SD/x")}
    assert secs["bare-container"].kind == "container"
    assert secs["bare-container"].searchable is False
    assert secs["bare-leaf"].kind == "hollow" and secs["bare-leaf"].searchable is False


def test_shred_marks_referent_only_section_searchable_whatever_its_kind():
    # content lifted to a tables/*.csv sidecar contributes no tokens by design; the section is still
    # on the search surface (index re-introduces the table as a chunk citing it — B3b, §8.4)
    body = (
        "## Table Section\n\n_[Table 1 (extracted to CSV)](tables/table-01.csv)_\n\n"
        "### Child\n\nThe child carries all of the substance for this part of the document.\n\n"
        "## Leaf Table\n\n_[Table 2 (extracted to CSV)](tables/table-02.csv)_\n"
    )
    secs = {s.slug: s for s in ip.shred_sections(body, "ACR/acr_tm")}
    assert secs["table-section"].kind == "container" and secs["table-section"].searchable is True
    assert secs["leaf-table"].kind == "stub" and secs["leaf-table"].searchable is True


def test_shred_sections_fallback_when_no_headings():
    # Heading-less sources (menu listings, quick-reference cards, change-pages) still carry real
    # body text; without a fallback, shred returns [] → the doc gets zero chunks, no preview/search.
    # Emit the whole body as one searchable section titled from the document.
    body = (
        "OPTION NAME | SUGGESTED RUN FREQUENCY | REMARKS\n"
        "DG G&L RECALCULATION AUTO | Nightly | Recommended to run at 9 PM.\n"
        "This menu document lists the background job options for the package.\n"
    )
    secs = ip.shred_sections(body, "ACR/acr_puse", doc_title="ACR — Menu")
    assert len(secs) == 1
    s = secs[0]
    assert s.slug == "body" and s.section_id == "ACR/acr_puse/body"
    assert s.title == "ACR — Menu"  # carries the doc title for the single TOC entry / FTS
    assert s.kind == "ok" and s.searchable is True
    assert "DG G&L RECALCULATION" in s.text and s.section_path == ""


def test_shred_sections_no_fallback_for_blank_body():
    # A genuinely empty body stays zero sections — the fallback only rescues real heading-less text.
    # (whitespace-only input must not synthesize a section)
    assert ip.shred_sections("   \n\n", "ADT/x") == []


def test_fts_doc_title_folds_in_app_name():
    # Titles are namespace-prefixed ("DI — …"), so a name search by the package's well-known name
    # ("FileMan") misses every doc but the rare one with it in the title. Fold app_name into the FTS
    # doc_title surface so package-name search finds them all.
    assert ip.fts_doc_title("FileMan", "DI — Technical Manual") == "FileMan DI — Technical Manual"
    assert (
        ip.fts_doc_title("FileMan", "FileMan — DDE Utility Tutorial")
        == "FileMan — DDE Utility Tutorial"  # already present → no doubling
    )
    assert ip.fts_doc_title("", "DI — User Guide") == "DI — User Guide"  # no app_name → unchanged


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


def _chunks_for(section):
    """Chunk one section through the LIVE path the stage uses: chunk_units → chunks_for_unit."""
    units = ip.chunk_units([section], merge=False)
    return [c for u in units for c in ip.chunks_for_unit(u)]


def test_chunking_single_for_small_searchable_section():
    chunks = _chunks_for(_section("## S\n\nshort body", sid="SD/x/s"))
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "SD/x/s" and chunks[0].section_id == "SD/x/s"
    assert chunks[0].part == 0 and "short body" in chunks[0].text


def test_chunking_empty_for_non_searchable_section():
    assert _chunks_for(_section("## C\n", kind="container", searchable=False)) == []
    assert _chunks_for(_section("## H\n", kind="hollow", searchable=False)) == []


def test_chunking_splits_oversized_with_pN_suffix_part0_bare():
    big = "## S\n\n" + "\n\n".join(f"Paragraph {i}: " + "word " * 80 for i in range(40))
    chunks = _chunks_for(_section(big, sid="SD/x/big"))
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
    # schema_version is REQUIRED — the read contract (contracts/read/v1.json) is the only
    # version source; a module-level default here once stamped a stale "1.0" silently.
    rows = dict(ip.meta_rows(_DOCS_A, schema_version="1.5"))
    assert rows["read_schema_version"] == "1.5"
    assert rows["corpus_doc_count"] == "2"
    assert rows["corpus_content_hash"] == ip.corpus_content_hash(_DOCS_A)
    with pytest.raises(TypeError):
        ip.meta_rows(_DOCS_A)  # type: ignore[call-arg]


# --- the last-updated date (inventory browser step 1, proposal §4) -------------------------------


def test_last_updated_is_the_newest_revision_when_official_date_is_one():
    member = {
        "official_date": "2022-08",
        "revisions": [{"date": "2005-01"}, {"date": "2022-08"}],
    }
    assert ip.last_updated(member) == ("2022-08", "revision-history")


def test_last_updated_falls_back_to_the_title_page():
    """official_date is the newest revision date when there is one, else the title-page date —
    so a date that is none of the revision dates came from the title page."""
    member = {"official_date": "2005-01", "revisions": [{"date": "ACKQ*3.0*13 Removed …"}]}
    assert ip.last_updated(member) == ("2005-01", "title-page")
    assert ip.last_updated({"official_date": "2005-01"}) == ("2005-01", "title-page")


def test_a_member_with_no_date_is_undated():
    assert ip.last_updated({"official_date": "", "revisions": [{"date": ""}]}) == ("", "")
    assert ip.last_updated({"official_date": None}) == ("", "")


# --- A1: the clean index projection (end-to-end review §3.1 / §6 A1, decision D1) ---------------
# `chunks.text` stays markdown (vdocs-web rebuilds previews from it); only the FTS `body` and
# `title` columns receive the projection. Every rule has its own case.

_HEX = "423150d509e08571d51a105b88535c889463cae606df6229e815ece5d077df43"


def test_index_text_drops_the_nav_line_and_table_marker():
    src = (
        "## Purge Files\n\n[↑ Back to Contents](#contents)\n\nEach installation adds one entry.\n\n"
        "_[Table 3 (extracted to CSV)](tables/table-03.csv)_\n"
    )
    assert ip.index_text(src) == "Purge Files Each installation adds one entry."


def test_index_text_strips_whitelisted_html_tags_and_keeps_inner_text():
    src = (
        '<p>Use <strong>DIC</strong> for <u>lookups</u>.</p><span id="_Toc123"></span>'
        '<blockquote><p><span class="mark">Note</span></p></blockquote>'
    )
    assert ip.index_text(src) == "Use DIC for lookups. Note"


def test_index_text_keeps_html_table_cell_text_and_drops_the_tags():
    src = (
        '<table>\n<colgroup>\n<col style="width: 20%" />\n</colgroup>\n<thead>\n'
        '<tr class="header">\n<th>Field</th>\n<th>Meaning</th>\n</tr>\n</thead>\n<tbody>\n'
        '<tr class="odd">\n<td style="text-align: left;">DFN</td>\n<td>patient ien</td>\n</tr>\n'
        "</tbody>\n</table>"
    )
    out = ip.index_text(src)
    assert out == "Field Meaning DFN patient ien"
    assert "width" not in out and "odd" not in out


def test_index_text_reduces_img_to_its_alt_text_and_drops_the_asset_hash():
    src = f'<img src="{_HEX}.png" style="width:6.79in;height:8in" alt="Audiogram data flow" />'
    assert ip.index_text(src) == "Audiogram data flow"
    assert ip.index_text(f'<img src="{_HEX}.png" style="width:6in" />') == ""
    assert ip.index_text(f"![Flow diagram](assets/{_HEX}.png)") == "Flow diagram"


def test_index_text_strips_pandoc_html_headings_and_footnote_backlinks():
    src = (
        '<h3 id="a-needed-rpc-is-not-available.">A needed RPC is not available.</h3>'
        '<a href="#fnref1" class="footnote-back" role="doc-backlink">↩︎</a><hr />'
    )
    assert ip.index_text(src) == "A needed RPC is not available. ↩︎"


@pytest.mark.parametrize(
    "token",
    ["<Enter>", "<RET>", "<Tab>", "<CR>", "<PF1>", "<ServerName>", "<A>", "<P>", "<Code>",
     "<name of file>", "<http://x.gov>", "<Logger name=\"x\"/>"],
)  # fmt: skip
def test_index_text_leaves_keystroke_and_placeholder_notation_as_written(token):
    # the corpus writes keystrokes as <Enter>/<RET>/<Tab>; placeholders collide with element names
    # only in CASE (<A>, <P>, <Code>) — the whitelist is case-sensitive lowercase, so a tag strip
    # never deletes them (kickoff step 4).
    assert ip.index_text(f"press {token} to continue") == f"press {token} to continue"


@pytest.mark.parametrize(
    ("escaped", "plain"),
    [("\\<Enter\\>", "<Enter>"), ("\\<RET\\>", "<RET>"), ("\\<A\\>", "<A>"),
     ("<Code\\>", "<Code>"), ("</Code\\>", "</Code>"), ("<B\\>", "<B>"),
     ("\\$\\$GET1^DIQ", "$$GET1^DIQ"), ("\\| a \\| b \\|", "| a | b |"), ("2\\. step", "2. step"),
     ("\\*not emphasis\\*", "*not emphasis*"), ("\\\\server\\share", "\\server\\share"),
     ("\\<!-- xml comment --\\>", "<!-- xml comment -->")],
)  # fmt: skip
def test_index_text_restores_pandoc_backslash_escapes_last(escaped, plain):
    # Pandoc escapes literal markdown punctuation (12,805 `\<Enter\>` vs 1,313 bare `<Enter>` in
    # the corpus; `\$\$GET1^DIQ`, `\|` table pipes). The escape is markdown syntax, the character
    # is content: it is restored as the LAST step, so a restored `*` or `<` is never re-read as
    # emphasis or a tag — `\<p\>` written about HTML stays `<p>` in the index text.
    assert ip.index_text(f"press {escaped} now") == f"press {plain} now"


def test_index_text_strips_a_tag_nested_inside_placeholder_notation():
    # an XML example escaped by Pandoc with a real <span class="mark"> highlight inside it: the
    # attribute scan stops at `<`, so the inner tag is seen (and stripped) and the outer `<Logger`
    # placeholder stays as written
    src = '\\<Logger name="<span class="mark">gov.va.med</span>" level="info"/\\>'
    assert ip.index_text(src) == '<Logger name="gov.va.med" level="info"/>'
    assert ip.index_text('\\<Back Button <img src="ab12.png" alt="back" />\\>') == (
        "<Back Button back >"
    )


def test_index_text_reduces_links_whose_labels_carry_escapes_or_footnote_refs():
    assert ip.index_text("[ASCD Compile \\[SDSC SITE PARAMETER\\] Option](#ascd-compile)") == (
        "ASCD Compile [SDSC SITE PARAMETER] Option"
    )
    assert ip.index_text("- [M routines[^16]](#m-routines16) - [Delphi[^17]](#delphi17)") == (
        "- M routines[^16] - Delphi[^17]"
    )
    assert (
        ip.index_text(
            "[[The XXXXXXXX program\\[option name\\] could not be accessed. 2](#the-x)](#the-x)"
        )
        == "The XXXXXXXX program[option name] could not be accessed. 2"
    )


def test_index_text_reduces_a_link_whose_label_ends_in_a_lone_backslash():
    # 89 live TOC links end their label with a bare `\` (the heading text ended in one and Pandoc
    # did not double it): `\]` there is a literal backslash and the link's end, not an escape
    assert ip.index_text("- [MSH – Field Separator \\/\\/\\](#msh--field-separator-) - x") == (
        "- MSH – Field Separator //\\ - x"
    )
    assert ip.index_text("[Tab Symbol \\](#tab-symbol-)") == "Tab Symbol \\"


def test_index_text_reduces_an_img_whose_alt_text_carries_keystroke_notation():
    # a FileMan figure's alt text quotes the prompt dialogue, `<Enter>` included (675 characters
    # in DI/fm22_2um1); the attribute scan must step over a nested `<…>` to find the tag's end
    src = '<img src="1509f3.jpeg" style="width:5in" alt="NAME: FMUSER,ONE// <Enter> accepts it" />'
    assert ip.index_text(src) == "NAME: FMUSER,ONE// <Enter> accepts it"


def test_index_text_strips_a_tag_that_follows_a_literal_backslash():
    # content ending in a backslash right before a tag — HL7's `\F\</p>`, a path `\image\</p>`
    # (12 live cases) — is a real tag's; only a tag ending in `\>` is Pandoc's escaped literal
    assert ip.index_text("<p>DOS c:\\scratch\\</p><p>UNIX /home</p>") == (
        "DOS c:\\scratch\\ UNIX /home"
    )
    assert ip.index_text("<li><p>\\F\\</p></li>") == "\\F\\"
    assert ip.index_text("<p>\\\\servername\\image\\</p>") == "\\servername\\image\\"
    assert ip.index_text("a \\<p\\> b \\</p\\>") == "a <p> b </p>"  # escaped literals stay text


def test_index_text_never_reads_escaped_brackets_as_a_link():
    # a screen capture: `\[ENTER\](JUN 17, 1996@09:00)` is a keystroke followed by the value in
    # parentheses — content, not a link whose target may be dropped
    src = "Check out date: JUN 17,1996@09:00// \\[ENTER\\](JUN 17, 1996@09:00) Patient's Service"
    assert ip.index_text(src) == (
        "Check out date: JUN 17,1996@09:00// [ENTER](JUN 17, 1996@09:00) Patient's Service"
    )


def test_index_text_reduces_links_to_their_labels():
    src = "See [the Finder API](#finder-api) and [Table 2](tables/table-02.csv) for [DIC](dic.md)."
    assert ip.index_text(src) == "See the Finder API and Table 2 for DIC."


def test_index_text_drops_legacy_toc_page_numbers_with_their_targets():
    # the 320 polluted titles have this shape; the inner link is a page number, not label text
    assert ip.index_text("[Scope of Manual [ii](#scope-of-manual)](#scope-of-manual)") == (
        "Scope of Manual"
    )
    assert ip.index_text("[Chapter [7-9](#ch)](#ch) and [Intro [vii](#i)](#i)") == (
        "Chapter and Intro"
    )
    # a nested link that is not a page number keeps both labels
    assert ip.index_text("[Outer [inner](#a)](#b)") == "Outer inner"


def test_index_text_drops_heading_emphasis_and_code_marks_but_not_intra_word_operators():
    src = "## **Bold** _title_\n\nUse `$$GET1^DIQ` with *care*; S X=A_B*C and **Note:** done."
    assert ip.index_text(src) == "Bold title Use $$GET1^DIQ with care; S X=A_B*C and Note: done."


def test_index_text_keeps_fenced_code_content_and_drops_the_fence_lines():
    src = 'Example:\n\n```text\nS DIC="^VA(200,"\nD ^DIC\n```\n\ndone'
    assert ip.index_text(src) == 'Example: S DIC="^VA(200," D ^DIC done'
    assert ip.index_text("~~~\nI X<Y D ^XUP\n~~~") == "I X<Y D ^XUP"


def test_index_text_drops_html_comments_and_collapses_whitespace():
    assert ip.index_text("a <!-- hidden\nnote --> b\n\n\n   c\t d") == "a b c d"
    assert ip.index_text("") == ""
    assert ip.index_text("   \n\n ") == ""


def test_index_text_on_a_table_chunk_only_collapses_whitespace():
    plain = ip.table_chunk_text("Table 1", [["Field", "Meaning"], ["DFN", "patient ien"]])
    assert ip.index_text(plain) == "Table 1 Field | Meaning DFN | patient ien"


def test_link_labels_cleans_a_title_without_touching_other_markup():
    assert ip.link_labels("[Preface [ii](#preface)](#preface)") == "Preface"
    # the one live title whose label carries escaped brackets (ACKQ/ackq3_0_p12tm); escapes are
    # left in a title as they are today — only the link rule applies to titles
    assert (
        ip.link_labels(
            "[The XXXXXXXX program\\[option name\\] could not be accessed. 2](#the-xxxxxxxx)"
        )
        == "The XXXXXXXX program\\[option name\\] could not be accessed. 2"
    )
    assert ip.link_labels("FP Food Preference \\[FHSELX\\][1](#_bookmark6)") == (
        "FP Food Preference \\[FHSELX\\]1"
    )
    assert ip.link_labels("**Bold** plain <Enter>") == "**Bold** plain <Enter>"


def test_shred_cleans_the_title_but_keeps_the_slug_from_the_raw_heading():
    # the slug (hence section_id) is what refs.yaml and every consumer cite — it must not move;
    # the stored title and the section_path built from titles become the label text (kickoff step 4)
    body = (
        "# Doc\n\n## [Preface [ii](#preface)](#preface)\n\nintro text here\n\n"
        "### Child\n\nchild text\n\n## [](#empty)\n\nkept raw when the label is empty\n"
    )
    secs = {s.slug: s for s in ip.shred_sections(body, "ACKQ/ackq3_0_p12tm")}
    pre = secs["preface-iiprefacepreface"]
    assert pre.section_id == "ACKQ/ackq3_0_p12tm/preface-iiprefacepreface"
    assert pre.title == "Preface"
    assert secs["child"].section_path == "Doc > Preface"
    assert secs["empty"].title == "[](#empty)"
