"""Unit tests for `index`'s generic entity recognizer (§8 note, D2). The recognizer is a pure
function of `(text, compiled registry rules)` — no entity pattern is hard-coded in stage code;
the vocabulary/patterns come from `registries/entities` (tenet #13)."""

from __future__ import annotations

from vdocs.stages.index import entities_pure as ent

_RULES = ent.compile_rules(
    [
        {
            "type": "build",
            "pattern": r"\b[A-Z][A-Z0-9]{1,7}\*\d+(?:\.\d+)?\*\d+\b",
            "casefold": True,
        },
        {"type": "global", "pattern": r"\^%?[A-Z][A-Z0-9]+\b", "casefold": True},
        {
            "type": "fileman_file",
            "pattern": r"(?i)\bfiles?\s+#?(\d+(?:\.\d+)?)\b",
            "canonical": "group1",
        },
        {"type": "package_namespace", "terms": ["DG", "LR", "PXRM"], "case_sensitive": True},
    ]
)


def _find(text):
    return set(ent.extract(text, _RULES))


def test_build_patch_ids():
    assert _find("Install OR*3.0*539 then PSO*7*123.") == {
        ("build", "OR*3.0*539"),
        ("build", "PSO*7*123"),
    }


def test_globals_with_caret():
    assert _find("Set ^DPT and ^%ZOSF before run.") == {
        ("global", "^DPT"),
        ("global", "^%ZOSF"),
    }


def test_fileman_file_requires_file_context():
    # "file #N" context captures the number; a bare "#2" page ref must not match
    got = _find("Stored in file #2 and File 200.5; see page #2 too.")
    assert ("fileman_file", "2") in got and ("fileman_file", "200.5") in got
    # the bare "#2" (no 'file' keyword) contributed nothing beyond the real file #2
    assert sum(1 for t, c in got if t == "fileman_file" and c == "2") == 1


def test_namespace_terms_are_case_sensitive_whole_words():
    got = _find("The DG package and PXRM. Not 'dg' nor a digraph.")
    assert ("package_namespace", "DG") in got and ("package_namespace", "PXRM") in got
    assert not any(c == "LR" for _, c in got)  # LR absent from the text


def test_casefold_unifies_global_case():
    # ^dpt and ^DPT are the same entity (casefold) → one canonical occurrence in the set
    assert _find("^dpt then ^DPT") == {("global", "^DPT")}


def test_extract_returns_each_occurrence_for_mention_counting():
    # extract yields one tuple per occurrence (deduping is the caller's job) so index can count
    occ = ent.extract("^DPT ^DPT ^DGPM", _RULES)
    assert occ.count(("global", "^DPT")) == 2 and occ.count(("global", "^DGPM")) == 1


# --- A3: the deeper VistA entity types (routine, hl7_segment, rpc, mail_group) ---

_RULES_A3 = ent.compile_rules(
    [
        {"type": "routine", "pattern": r"\b[A-Z%][A-Z0-9]*\^(%?[A-Z][A-Z0-9]{1,7})\b",
         "canonical": "group1", "casefold": True},
        {"type": "routine", "pattern": r"\bDO?\s+\^(%?[A-Z][A-Z0-9]{1,7})\b",
         "canonical": "group1", "casefold": True},
        {"type": "hl7_segment", "terms": ["MSH", "PID", "OBX", "OBR", "ORC"],
         "case_sensitive": True},
        {"type": "mail_group", "pattern": r"\bG\.([A-Z][A-Z0-9.]+)\b",
         "canonical": "group1", "casefold": True},
        {"type": "rpc", "pattern": r"\b([A-Z][A-Z0-9]+(?:\s+[A-Z0-9]+){0,4})\s+RPC\b",
         "canonical": "group1", "casefold": True},
    ]
)  # fmt: skip


def _find3(text):
    return set(ent.extract(text, _RULES_A3))


def test_routine_refs_distinct_from_globals():
    # TAG^ROUTINE, $$F^ROUTINE, and DO ^ROUTINE are routine calls; a bare ^GLOBAL is NOT a routine
    got = _find3("Call EN^XQOR and $$GET^ORWU; then DO ^XUP. Set ^DPT(1).")
    assert ("routine", "XQOR") in got and ("routine", "ORWU") in got and ("routine", "XUP") in got
    assert not any(t == "routine" and n == "DPT" for t, n in got)  # ^DPT stays a global here


def test_hl7_segments_closed_vocab():
    assert _find3("Map the PID and OBX segments; the MSH header.") == {
        ("hl7_segment", "PID"),
        ("hl7_segment", "OBX"),
        ("hl7_segment", "MSH"),
    }


def test_mail_group_g_prefix_and_rpc_suffix():
    assert ("mail_group", "IRM") in _find3("Add the user to G.IRM for alerts.")
    assert ("rpc", "ORWPT LIST") in _find3("The ORWPT LIST RPC returns the cover sheet.")


def test_rule_without_pattern_or_terms_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        ent.compile_rules([{"type": "bad"}])


def test_optional_capture_group_that_does_not_match_is_skipped():
    # a group1-canonical rule whose group 1 is optional and absent in a match yields no entity
    rules = ent.compile_rules([{"type": "opt", "pattern": r"a(b)?", "canonical": "group1"}])
    assert ent.extract("a then ab", rules) == [("opt", "b")]  # the bare "a" (group1=None) skipped
