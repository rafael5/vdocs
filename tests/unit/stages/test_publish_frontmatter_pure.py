"""Unit tests for stages.publish.frontmatter_pure — the imported-baseline front-matter rewrite
(FileMan docs-as-code pilot, L1; docs/fileman-docs-pilot-implementation-plan.md).

`export-fileman` materializes each gold doc into a fileman-docs topic. The first transform freezes
the VDL provenance, adds the git-owned lifecycle fields, and — the load-bearing decision — rewrites
the VDL `doc_type` code into the controlled Diátaxis vocab (S1/S6 of the IA strategy), keeping the
original code for traceability. Pure: gold meta dict → imported-baseline meta dict.
"""

from __future__ import annotations

import pytest

from vdocs.kernel import frontmatter as fm
from vdocs.stages.publish import frontmatter_pure as fp

_GOLD_DG = {
    "title": "FM 22.2 Developer's Guide",
    "doc_type": "DG",
    "app_code": "DI",
    "section": "INF",
    "pkg_ns": "DI",
    "version": "22.2",
    "published": "2025-07",
    "app_user": "developer",
    "doc_user": "developer",
    "software_class": "I",
    "function_category": "Infrastructure",
    "source_url": "https://www.va.gov/vdl/documents/Infrastructure/Fileman/fm22_2dg.docx",
    "source_sha256": "b5786b30",
    "tool_ver": "0.1.0",
    "patch_id": "DI*22.2",
}


def _rewrite(gold=None, slug="fm22_2dg"):
    return fp.rewrite_frontmatter(
        gold or _GOLD_DG, slug=slug, imported_by="vdocs 0.1.0", imported_date="2026-06-16"
    )


# --- the Diátaxis doc_type mapping (the decision under test) ------------------------------------
@pytest.mark.parametrize(
    "code,mode",
    [
        ("DG", "reference"),
        ("SG", "reference"),
        ("TRG", "tutorial"),
        ("TM", "how-to"),
        ("UM", "how-to"),
        ("UG", "how-to"),
    ],
)
def test_doc_type_maps_to_diataxis_vocab(code, mode):
    assert fp.diataxis_mode(code) == mode


def test_unknown_doc_type_falls_back_to_a_valid_mode():
    assert fp.diataxis_mode("ZZ") in fp.DIATAXIS_MODES


def test_rewrite_sets_doc_type_to_mode_and_preserves_source_code():
    out = _rewrite()
    assert out["doc_type"] == "reference"  # DG → reference
    assert out["source_doc_type"] == "DG"  # original VDL code retained


# --- frozen provenance --------------------------------------------------------------------------
def test_provenance_is_frozen_from_the_gold_source():
    out = _rewrite()
    assert out["source_url"].endswith("fm22_2dg.docx")
    assert out["source_sha256"] == "b5786b30"
    assert out["imported_from"] == "fm22_2dg"
    assert out["imported_by"] == "vdocs 0.1.0"
    assert out["imported_date"] == "2026-06-16"


# --- git-owned lifecycle ------------------------------------------------------------------------
def test_lifecycle_fields_added_as_imported():
    out = _rewrite()
    assert out["status"] == "imported"
    assert out["owner"] == "di-maintainers"  # routed from app_code
    assert "last_reviewed" in out


# --- identity carried through -------------------------------------------------------------------
def test_identity_fields_carried_verbatim():
    out = _rewrite()
    for k in ("title", "app_code", "section", "version", "published", "patch_id"):
        assert out[k] == _GOLD_DG[k]


def test_no_stale_pipeline_only_fields_leak():
    # tool_ver is a pipeline field — superseded by imported_by, not carried verbatim.
    assert "tool_ver" not in _rewrite()


# --- emits valid, round-trippable frontmatter ---------------------------------------------------
def test_result_emits_and_reparses_via_the_kernel_codec():
    out = _rewrite()
    meta, body = fm.parse(fm.emit(out, "# Title\n\nbody\n"))
    assert meta["doc_type"] == "reference"
    assert meta["status"] == "imported"
    assert body == "# Title\n\nbody\n"


def test_deterministic():
    assert _rewrite() == _rewrite()
