"""Smoke test — a REAL Pandoc DOCX→markdown conversion (proves the pipeline *runs*, not just lints).

`make check` green proves the code type-checks and the unit/integration tests pass with *fake*
converters — it does **not** prove the actual `convert` backend works. This exercises the real
`_pandoc_convert` subprocess on a minimal valid DOCX. Skipped when pandoc is absent (so a no-pandoc
dev box still gets a green gate); CI installs pandoc, so it runs there and guards the convert seam.
"""
# ruff: noqa: E501 — the minimal-OOXML literals below carry unavoidably long namespace URLs.

from __future__ import annotations

import io
import shutil
import zipfile

import pytest

from vdocs.stages.convert.stage import _pandoc_convert

pytestmark = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOCUMENT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
</w:document>"""


def _minimal_docx(text: str) -> bytes:
    """A minimal but valid .docx (OOXML zip of the three required parts) carrying one paragraph."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", _DOCUMENT.format(text=text))
    return buf.getvalue()


def test_pandoc_converts_a_real_docx():
    doc = _pandoc_convert(_minimal_docx("Smoke test paragraph"), "docx")
    assert "Smoke test paragraph" in doc.markdown
    assert doc.images == ()  # no media in this document
