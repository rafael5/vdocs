"""Pure DOCX (OOXML) image extraction — alt-text + media, in document order (ADR-010 image path).

Docling's DOCX backend parses **no** alt-text and emits ``<!-- image -->`` placeholders for the
images it doesn't materialise. For documents routed to Docling, we read each picture's alt-text
and media straight from the DOCX XML — in document order, 1:1 with the placeholders — and inject
proper ``![alt](media)`` refs. This is the v1 ``vista-docs`` approach, ported and made pure (it
operates on the DOCX *bytes*, no filesystem). Alt-text lives on the drawing wrapper
``<wp:docPr>``; group members fall back to ``<pic:cNvPr>``; ``<mc:AlternateContent>`` collapses
to its ``Choice`` so VML fallbacks don't double-count.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from vdocs.stages.convert.convert_pure import ConvertedImage

_NS_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PLACEHOLDER = "<!-- image -->"


@dataclass(frozen=True)
class DocxPicture:
    """One placed picture: its alt-text + media filename + bytes (empty media if unresolved)."""

    alt: str
    media: str  # the word/media basename, e.g. "image1.png"
    data: bytes
    ext: str


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_descendant(el: ET.Element, name: str) -> ET.Element | None:
    for d in el.iter():
        if _local_name(d.tag) == name:
            return d
    return None


def _collect(el: ET.Element, rels: dict[str, str], out: list[tuple[str, str]]) -> None:
    """Depth-first, document-order walk emitting one ``(alt, media)`` per placed picture."""
    name = _local_name(el.tag)
    if name == "AlternateContent":
        branch = el.find(f"{{{_NS_MC}}}Choice")
        if branch is None:
            branch = el.find(f"{{{_NS_MC}}}Fallback")
        if branch is not None:
            for child in branch:
                _collect(child, rels, out)
        return
    if name in ("inline", "anchor"):  # a DrawingML drawing container
        docpr = _find_descendant(el, "docPr")
        draw_alt = (docpr.get("descr") if docpr is not None else "") or ""
        draw_title = (docpr.get("title") if docpr is not None else "") or ""
        for pic in (d for d in el.iter() if _local_name(d.tag) == "pic"):
            cnv = _find_descendant(pic, "cNvPr")
            blip = _find_descendant(pic, "blip")
            embed = blip.get(f"{{{_NS_R}}}embed") if blip is not None else None
            pic_alt = (cnv.get("descr") if cnv is not None else "") or ""
            target = rels.get(embed, "") if embed else ""
            out.append(((pic_alt or draw_alt or draw_title).strip(), target.split("/")[-1]))
        return
    if name == "imagedata":  # standalone VML image (no DrawingML choice)
        embed = el.get(f"{{{_NS_R}}}id")
        target = rels.get(embed, "") if embed else ""
        out.append(("", target.split("/")[-1] if target else ""))
        return
    for child in el:
        _collect(child, rels, out)


def extract_pictures(docx_bytes: bytes) -> list[DocxPicture]:
    """Every placed picture in ``document.xml`` order, with alt-text + media bytes."""
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        rels: dict[str, str] = {}
        for rel in ET.fromstring(z.read("word/_rels/document.xml.rels")):
            rid, target = rel.get("Id"), rel.get("Target")
            if rid is not None and target is not None:
                rels[rid] = target
        records: list[tuple[str, str]] = []
        _collect(ET.fromstring(z.read("word/document.xml")), rels, records)
        media = {
            e.rsplit("/", 1)[-1]: z.read(e) for e in z.namelist() if e.startswith("word/media/")
        }
    pics: list[DocxPicture] = []
    for alt, name in records:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        pics.append(DocxPicture(alt=alt, media=name, data=media.get(name, b""), ext=ext))
    return pics


def inject_placeholders(
    markdown: str, pictures: list[DocxPicture]
) -> tuple[str, list[ConvertedImage]]:
    """Replace each ``<!-- image -->`` with ``![alt](media)`` against ``pictures`` in order.

    Requires a 1:1 count (raises otherwise) — silently misaligning would mislabel every caption.
    A picture with no resolved media keeps the bare placeholder. Returns the rewritten markdown
    plus the :class:`ConvertedImage` list for the CAS."""
    n = markdown.count(_PLACEHOLDER)
    if n != len(pictures):
        raise ValueError(f"docling placeholder/picture mismatch: {n} vs {len(pictures)} pictures")
    it = iter(pictures)
    images: list[ConvertedImage] = []

    def repl(_m: re.Match[str]) -> str:
        p = next(it)
        if not p.media:
            return _PLACEHOLDER
        images.append(ConvertedImage(ref=p.media, data=p.data, ext=p.ext))
        alt = p.alt.replace("]", ")").replace("\n", " ")
        return f"![{alt}]({p.media})"

    return re.sub(re.escape(_PLACEHOLDER), repl, markdown), images
