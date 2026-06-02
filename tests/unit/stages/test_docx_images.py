"""Unit tests for docx_images — pure OOXML alt-text/media extraction + injection (ADR-010)."""

from __future__ import annotations

import io
import zipfile

import pytest

from vdocs.stages.convert import docx_images as di

_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

_RELS = """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Target="media/image1.png"/>
  <Relationship Id="rId2" Target="media/image2.gif"/>
</Relationships>"""

# two drawings: the first has alt-text on the drawing wrapper, the second has none
_DOC = f"""<?xml version="1.0"?>
<w:document xmlns:w="urn:w" xmlns:wp="urn:wp" xmlns:a="urn:a" xmlns:pic="urn:pic" xmlns:r="{_R}">
  <w:body>
    <w:p><w:r><w:drawing><wp:inline>
      <wp:docPr id="1" name="Picture 1" descr="VA logo"/>
      <a:graphic><a:graphicData><pic:pic>
        <pic:nvPicPr><pic:cNvPr id="0" name="image1" descr=""/></pic:nvPicPr>
        <pic:blipFill><a:blip r:embed="rId1"/></pic:blipFill>
      </pic:pic></a:graphicData></a:graphic>
    </wp:inline></w:drawing></w:r></w:p>
    <w:p><w:r><w:drawing><wp:anchor>
      <wp:docPr id="2" name="Picture 2"/>
      <a:graphic><a:graphicData><pic:pic>
        <pic:nvPicPr><pic:cNvPr id="0" name="image2" descr="a diagram"/></pic:nvPicPr>
        <pic:blipFill><a:blip r:embed="rId2"/></pic:blipFill>
      </pic:pic></a:graphicData></a:graphic>
    </wp:anchor></w:drawing></w:r></w:p>
  </w:body>
</w:document>"""


def _docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/_rels/document.xml.rels", _RELS)
        z.writestr("word/document.xml", _DOC)
        z.writestr("word/media/image1.png", b"\x89PNG logo bytes")
        z.writestr("word/media/image2.gif", b"GIF89a diagram bytes")
    return buf.getvalue()


def test_extract_pictures_reads_alt_text_and_media_in_order():
    pics = di.extract_pictures(_docx_bytes())
    assert [(p.alt, p.media, p.ext) for p in pics] == [
        ("VA logo", "image1.png", "png"),  # alt from the drawing wrapper <wp:docPr descr>
        ("a diagram", "image2.gif", "gif"),  # alt from the inner <pic:cNvPr descr>
    ]
    assert pics[0].data == b"\x89PNG logo bytes"


def test_inject_placeholders_replaces_in_order_with_alt():
    pics = di.extract_pictures(_docx_bytes())
    md = "# Doc\n\n<!-- image -->\n\nText.\n\n<!-- image -->\n"
    out, images = di.inject_placeholders(md, pics)
    assert "![VA logo](image1.png)" in out
    assert "![a diagram](image2.gif)" in out
    assert "<!-- image -->" not in out
    assert [(i.ref, i.ext) for i in images] == [("image1.png", "png"), ("image2.gif", "gif")]


def test_inject_placeholders_raises_on_count_mismatch():
    pics = di.extract_pictures(_docx_bytes())  # 2 pictures
    with pytest.raises(ValueError, match="mismatch"):
        di.inject_placeholders("only <!-- image --> one placeholder", pics)


def test_inject_placeholders_keeps_bare_placeholder_for_pic_without_media():
    pic = di.DocxPicture(alt="x", media="", data=b"", ext="")  # no resolved media
    out, images = di.inject_placeholders("<!-- image -->", [pic])
    assert out == "<!-- image -->" and images == []


_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"

# AlternateContent (collapse to Choice, ignore Fallback) + a VML imagedata image
_DOC_VARIANTS = f"""<?xml version="1.0"?>
<w:document xmlns:w="urn:w" xmlns:wp="urn:wp" xmlns:a="urn:a" xmlns:pic="urn:pic"
            xmlns:v="urn:v" xmlns:mc="{_MC}" xmlns:r="{_R}">
  <w:body>
    <w:p><w:r><mc:AlternateContent>
      <mc:Choice Requires="wpg"><w:drawing><wp:inline>
        <wp:docPr id="1" name="P1" descr="chosen"/>
        <a:graphic><a:graphicData><pic:pic>
          <pic:nvPicPr><pic:cNvPr id="0" name="i1"/></pic:nvPicPr>
          <pic:blipFill><a:blip r:embed="rId1"/></pic:blipFill>
        </pic:pic></a:graphicData></a:graphic>
      </wp:inline></w:drawing></mc:Choice>
      <mc:Fallback><w:pict><v:imagedata r:id="rId2"/></w:pict></mc:Fallback>
    </mc:AlternateContent></w:r></w:p>
    <w:p><w:r><w:pict><v:imagedata r:id="rId2"/></w:pict></w:r></w:p>
  </w:body>
</w:document>"""


def _docx_variants() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/_rels/document.xml.rels", _RELS)
        z.writestr("word/document.xml", _DOC_VARIANTS)
        z.writestr("word/media/image1.png", b"png")
        z.writestr("word/media/image2.gif", b"gif")
    return buf.getvalue()


_DOC_FALLBACK = f"""<?xml version="1.0"?>
<w:document xmlns:w="urn:w" xmlns:wp="urn:wp" xmlns:a="urn:a" xmlns:pic="urn:pic"
            xmlns:mc="{_MC}" xmlns:r="{_R}">
  <w:body><w:p><w:r><mc:AlternateContent>
    <mc:Fallback><w:drawing><wp:inline>
      <wp:docPr id="1" descr="fallback alt"/>
      <a:graphic><a:graphicData><pic:pic>
        <pic:blipFill><a:blip r:embed="rId1"/></pic:blipFill>
      </pic:pic></a:graphicData></a:graphic>
    </wp:inline></w:drawing></mc:Fallback>
  </mc:AlternateContent></w:r></w:p></w:body>
</w:document>"""


def test_extract_pictures_alternatecontent_fallback_and_missing_cnvpr():
    # no Choice → use Fallback; the pic has no <pic:cNvPr> → alt falls back to the drawing wrapper
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/_rels/document.xml.rels", _RELS)
        z.writestr("word/document.xml", _DOC_FALLBACK)
        z.writestr("word/media/image1.png", b"png")
    pics = di.extract_pictures(buf.getvalue())
    assert [(p.alt, p.media) for p in pics] == [("fallback alt", "image1.png")]


def test_extract_pictures_handles_alternatecontent_and_vml():
    pics = di.extract_pictures(_docx_variants())
    # AlternateContent collapses to its Choice (no Fallback double-count); standalone VML image too
    assert [(p.alt, p.media) for p in pics] == [
        ("chosen", "image1.png"),  # from the Choice branch's DrawingML picture
        ("", "image2.gif"),  # the standalone VML <v:imagedata>
    ]
