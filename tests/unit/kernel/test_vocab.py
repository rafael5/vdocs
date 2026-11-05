"""Unit tests for the published vocabulary builder (ADR-0001 P2): controlled vocabularies sourced
from the registries (the SSOT), emitted into index.db's `vocab` table so consumers read them as
data instead of hardcoding them — and so `doctor` can gate that every facet value is defined."""

from __future__ import annotations

from vdocs.config import Settings
from vdocs.kernel import vocab


def _rows():
    return vocab.vocab_rows(Settings().registries)


def test_vocab_rows_are_kind_code_label_description_tuples():
    rows = _rows()
    assert rows and all(len(r) == 4 for r in rows)
    kinds = {r[0] for r in rows}
    assert {"function_category", "doc_type", "section", "persona"} <= kinds


def test_function_domains_carry_their_definition():
    rows = {(k, c): (lbl, desc) for k, c, lbl, desc in _rows()}
    lbl, desc = rows[("function_category", "Laboratory")]
    assert lbl == "Laboratory" and "blood bank" in desc
    assert "\n" not in desc  # folded multiline definition collapses to one line


def test_doc_type_label_and_section_and_persona_present():
    rows = {(k, c): (lbl, desc) for k, c, lbl, desc in _rows()}
    assert rows[("doc_type", "UM")][0] == "User Manual"
    sec_label, sec_desc = rows[("section", "CLI")]
    assert sec_label == "Clinical" and "patient-care" in sec_desc
    assert "care staff" in rows[("persona", "clinical")][1]


def test_vocab_rows_are_deterministic():
    assert _rows() == _rows()


# --- namespace names (inventory browser step 1; read by the Inventory mode only, D4) ----------


def _ns_rows(namespaces: dict[str, str]) -> dict[str, tuple[str, str]]:
    return {
        c: (lbl, desc)
        for k, c, lbl, desc in vocab.vocab_rows(Settings().registries, namespaces=namespaces)
        if k == "namespace"
    }


def test_a_namespace_is_named_by_the_package_file_verbatim():
    label, desc = _ns_rows({"DI": "FileMan"})["DI"]
    assert label == "VA FILEMAN"  # capitals kept: casing is decided with the Library renames
    assert "PACKAGE file (#9.4)" in desc


def test_the_operators_four_names_override_the_copy():
    rows = _ns_rows({ns: "" for ns in ("OR", "GMRV", "LR", "MAG")})
    assert {ns: label for ns, (label, _) in rows.items()} == {
        "OR": "Order Entry (CPRS)",
        "GMRV": "Vitals",
        "LR": "Lab",
        "MAG": "VistA Imaging",
    }
    assert "ORDER ENTRY/RESULTS REPORTING" in rows["OR"][1]  # the name it replaces stays visible


def test_a_namespace_outside_the_package_file_takes_its_applications_name_flagged():
    label, desc = _ns_rows({"WEBP": "Web Patient Access"})["WEBP"]
    assert label == "Web Patient Access"
    assert "not in the PACKAGE file" in desc


def test_a_namespace_named_nowhere_gets_no_row():
    assert "XUSC" not in _ns_rows({"XUSC": ""})


def test_namespace_rows_cover_only_the_namespaces_given():
    assert set(_ns_rows({"DI": "", "XU": ""})) == {"DI", "XU"}
    assert not [r for r in _rows() if r[0] == "namespace"]


def test_every_override_names_a_namespace_the_copy_holds():
    """An override for a namespace the PACKAGE file does not name is a typo, not a rename."""
    from vdocs.kernel.registry import load_mapping

    names = load_mapping(Settings().registries / "inventory" / "namespace-names.yaml")
    assert set(names["overrides"]) <= set(names["package_file"])


# --- dispositions and reason kinds (inventory browser step 1) ---------------------------------


def _kind(kind: str) -> dict[str, tuple[str, str]]:
    return {c: (lbl, desc) for k, c, lbl, desc in _rows() if k == kind}


def test_the_published_dispositions_are_exactly_the_six_classify_uses():
    from vdocs.stages.serve_inventory.completeness_pure import DISPOSITIONS

    rows = _kind("disposition")
    assert set(rows) == DISPOSITIONS
    assert all(label and desc for label, desc in rows.values())


def test_every_reason_kind_classify_emits_is_explained_in_one_sentence():
    """Both directions: an unexplained kind would show an operator a bare code, and an
    explanation for a kind classify() never emits would describe nothing."""
    from vdocs.stages.serve_inventory.completeness_pure import REASON_KINDS

    rows = _kind("reason_kind")
    assert set(rows) == REASON_KINDS
    for label, desc in rows.values():
        assert label and desc.endswith(".") and desc.count(". ") == 0, desc


# --- doc-type families (moved from vdocs-web's TYPE_FAMILIES) ---------------------------------


def test_doc_type_families_publish_one_row_per_member_type():
    rows = _kind("doc_type_family")
    families: dict[str, list[str]] = {}
    for code, (family, _) in sorted(rows.items()):
        families.setdefault(family, []).append(code)
    # the three families vdocs-web hardcodes; every other type is Other
    assert families == {
        "Manuals & Guides": sorted(["UM", "UG", "QRG", "TRG", "FAQ", "TG"]),
        "Technical": sorted(["TM", "DG", "API", "INT", "REF"]),
        "Admin & Security": sorted(["SG", "SM", "AG"]),
    }


def test_a_doc_type_in_two_families_is_refused(tmp_path):
    import pytest

    inv = tmp_path / "inventory"
    inv.mkdir()
    (inv / "doctype-families.yaml").write_text("families:\n  A: [UM]\n  B: [UM, TM]\n")
    with pytest.raises(ValueError, match="UM"):
        vocab.vocab_rows(tmp_path)
