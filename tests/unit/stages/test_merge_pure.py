"""Unit tests for `merge`'s pure cores (SKL → entity-keyed index.db, S3.3).

`merge` augments `index.db` from the SKL (`knowledge.db`) **additively** (D-S3.3b): it reconciles
the two entity-id schemes (`index` keys `fileman_file:200` colon, the SKL keys `fileman_file/200`
slash) on `(type, canonical)`, projects the SKL surfaces into a synonym catalog, and tags chunks
with the resolved entity. Pure: SKL nodes + index rows in, sorted unique tuples out.

The load-bearing safety property (found in the real SKL — common-word names like "FILE"/"OPTION"
exist): tagging/expansion use **distinctive surfaces only** (numbers, globals, multi-word names),
never a bare common word.
"""

from __future__ import annotations

from vdocs.stages.merge import merge_pure as mp

# The headline entity + a couple of common-word entities that must NOT over-tag (from the real SKL).
_E200 = mp.SklEntity(
    node_id="fileman_file/200",
    type="fileman_file",
    canonical="200",
    canonical_name="NEW PERSON",
    synonyms=("NEW PERSON", "^VA(200,", "NEW PERSON file", "the 200 file", "user file"),
)
_E1 = mp.SklEntity(
    node_id="fileman_file/1",
    type="fileman_file",
    canonical="1",
    canonical_name="FILE",
    synonyms=("FILE", "^DIC(", "file of files"),
)


def test_index_entity_id_mirrors_index_colon_keying():
    assert mp.index_entity_id("fileman_file", "200") == "fileman_file:200"


def test_reconcile_maps_colon_id_to_slash_node_only_when_present_in_index():
    # index has 200 and 60, but not 1 → only 200 reconciles (1 isn't in index's entity set)
    rows = mp.reconcile([_E200, _E1], index_entity_ids={"fileman_file:200", "fileman_file:60"})
    assert rows == [("fileman_file:200", "fileman_file/200", "fileman_file", "200", "NEW PERSON")]


def test_synonym_rows_carry_canonical_name_then_synonyms_deduped():
    rows = mp.synonym_rows([_E200])
    assert ("fileman_file/200", "NEW PERSON", "canonical_name") in rows
    assert ("fileman_file/200", "^VA(200,", "synonym") in rows
    # "NEW PERSON" appears in synonyms too but is emitted once (as canonical_name)
    assert sum(1 for r in rows if r[1] == "NEW PERSON") == 1


def test_is_distinctive_keeps_numbers_globals_multiword_drops_bare_common_words():
    assert mp.is_distinctive("200")  # carries a digit
    assert mp.is_distinctive("^VA(200,")  # global
    assert mp.is_distinctive("NEW PERSON")  # multi-word
    assert mp.is_distinctive("the 200 file")  # has a digit
    assert not mp.is_distinctive("FILE")  # bare common word → never tag/expand on it
    assert not mp.is_distinctive("OPTION")
    assert not mp.is_distinctive("")


def test_distinctive_surfaces_filters_the_common_word_name():
    # _E1's name "FILE" and synonym "FILE" are dropped; only the distinctive ones survive
    assert mp.distinctive_surfaces(_E1) == ["^DIC(", "file of files"]


def test_tag_chunks_links_chunks_by_distinctive_surface_only():
    chunks = [
        ("c1", "the NEW PERSON file stores users"),  # name → 200
        ("c2", "data lives in ^VA(200,0) here"),  # global mid-token → 200
        ("c3", "open the FILE and read it"),  # only common word "FILE" → NO tag
        ("c4", "nothing relevant here"),
    ]
    tags = mp.tag_chunks(chunks, [_E200, _E1])
    assert ("c1", "fileman_file/200") in tags
    assert ("c2", "fileman_file/200") in tags
    assert not any(c == "c3" for c, _ in tags)  # common-word "FILE" never tags file/1
    assert not any(c == "c4" for c, _ in tags)


def test_tag_chunks_is_sorted_and_deduped():
    chunks = [("c1", "NEW PERSON and NEW PERSON file again ^VA(200,")]
    tags = mp.tag_chunks(chunks, [_E200])
    assert tags == [("c1", "fileman_file/200")]  # one tag despite many surface hits
