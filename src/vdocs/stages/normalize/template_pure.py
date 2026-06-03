"""Pure ``(doc_type, era)`` template STRIP + ``template_id`` stamp (§9.7/§9.8/ADR-018,019).

A document matched to a curated ``(doc_type, era)`` template gets its **scaffold stripped** and a
``template_id`` **stamped** as provenance, while the template's structural schema stays computable
in ``registries/templates`` (RETAIN — the validation oracle + reuse source, §9.8).

What "strip the scaffold" means concretely here: remove the **unfilled scaffold sections** — a
template-schema heading the author left empty (no content and no subsections), the literal skeleton
remnant. Filled sections and their content are retained; non-scaffold headings are never touched.
This is a stage-level pre-step (like ``revision_pure``/``tables_pure``): pure values in, the stage
holds ``doc_type`` (enriched frontmatter) + ``era`` (``kernel.decade_bucket`` over the title page)
and stamps the returned ``template_id`` into the frontmatter (identity provenance, §6.3 — mirroring
``source_sha256``). Idempotent: once the empty scaffold headings are gone, a second pass is a no-op.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from vdocs.kernel.markdown import (
    HEADING_RE,
    LEGACY_TOC_TITLES,
    heading_furniture_text,
    is_legacy_toc_entry,
    is_revision_heading,
    iter_headings,
    strip_tags,
)
from vdocs.kernel.text import month_year_iso


@dataclass(frozen=True)
class Template:
    """A curated template's match key + the (normalized) titles of its scaffold sections."""

    template_id: str
    doc_type: str
    era: str
    section_titles: frozenset[str]  # normalized (lowercased, whitespace-collapsed) heading titles


def _norm(title: str) -> str:
    return " ".join(title.lower().split())


# --- title-page publication-date capture + standardized block (§6.4) ---------------------------
TITLE_PAGE_LINES = 40  # the title-page window (front matter) — shared with `discover` era induction
_MAX_COVER_LINES = 80  # never treat more than this as cover (a flat doc has no early boundary)

# Cover furniture that marks the pre-content region as a *legacy title page* rather than real
# content: the VA imprint, blank-page residue, a logo image, or a bare ``Month YYYY`` cover date.
# Used as the safety signal so a doc that already opens with content is never mistaken for a cover
# (and partly stripped) — the date is gated separately on having been captured into ``published``.
_COVER_SIGNAL_RE = re.compile(
    r"(?i)department of veterans affairs|intentionally left blank|<img\b|!\["
)


def _is_cover_line(line: str) -> bool:
    return _COVER_SIGNAL_RE.search(line) is not None or month_year_iso(line) is not None


@dataclass(frozen=True)
class TitlePageFields:
    """The identity-frontmatter values the standardized title block is built from (§6.4)."""

    title: str
    version: str
    patch_id: str
    published: str
    source_url: str


def extract_published(body: str) -> str | None:
    """Lift the title-page **publication date** — the first ``Month YYYY`` in the title-page window
    — as a normalised ``"YYYY-MM"`` string, or ``None`` when the cover carries no date (§6.4).

    This is the capture-gate value for title-page removal: the legacy cover is the sole source of
    the publication date for ~97% of the corpus, so it must be lifted into the ``published``
    identity field *before* the cover is stripped. Reuses the same ``Month YYYY`` window as
    ``discover``'s ``era`` (``kernel.month_year_iso`` over ``TITLE_PAGE_LINES``)."""
    return month_year_iso(body, max_lines=TITLE_PAGE_LINES)


_DVA_CORE = "department of veterans affairs"


def _is_furniture_text(line: str) -> bool:
    """A cover-furniture line by its *text* (tags stripped): the VA imprint (possibly with an office
    suffix) or a short standalone ``Month YYYY`` cover date. Recognised even when authored as an ATX
    heading — late-gen docs put the imprint/date in ``# …`` headings, which would otherwise become
    ``## Contents`` entries — so the cover boundary skips past them rather than stopping there."""
    visible = strip_tags(line)
    core = " ".join(re.sub(r"[^a-z0-9 ]", " ", visible.lower()).split())
    if core.startswith(_DVA_CORE):
        return True
    return len(visible.strip()) < 50 and month_year_iso(visible) is not None


def _cover_end(lines: list[str]) -> int:
    """Index of the first line that ends the title-page cover — the first real ATX heading, legacy
    revision/Table-of-Contents marker, or legacy TOC entry. Cover-furniture lines (incl. an imprint
    or cover-date *heading*) are skipped, not treated as the boundary. The furniture above the
    returned index is the cover."""
    for i, ln in enumerate(lines):
        if _is_furniture_text(ln):
            continue  # cover furniture (even as a heading) is part of the cover, not the boundary
        if HEADING_RE.match(ln):
            return i
        if is_revision_heading(ln) or is_legacy_toc_entry(ln):
            return i
        if heading_furniture_text(ln) in LEGACY_TOC_TITLES and ln.strip():
            return i
    return len(lines)


def _title_block(fields: TitlePageFields) -> list[str]:
    """The standardized title block built from identity frontmatter — uniform across the corpus,
    carrying no raw cover furniture (no VA imprint, no ``Month YYYY`` line, no blank-page text)."""
    meta = " · ".join(
        part
        for part in (
            f"Version {fields.version}" if fields.version else "",
            f"Patch {fields.patch_id}" if fields.patch_id else "",
            f"Published {fields.published}" if fields.published else "",
        )
        if part
    )
    block: list[str] = []
    if fields.title:
        block.append(f"**{fields.title}**")
    if meta:
        block += ["", f"_{meta}_"]
    if fields.source_url:
        block += ["", f"Source: <{fields.source_url}>"]
    return block


def _strip_cover_furniture(lines: list[str]) -> str:
    """Fallback when no clean cover boundary exists (an all-bold flat cover with no ATX/TOC marker):
    surgically drop just the cover furniture — the VA imprint and a short ``Month YYYY`` cover-date
    line (:func:`_is_furniture_text`) — from the title-page window, keeping the real title/body
    in place. Safe because the date has already been captured into ``published`` (the caller gate)
    and the removals are confined to the first ``TITLE_PAGE_LINES``."""
    out: list[str] = []
    for idx, ln in enumerate(lines):
        if idx < TITLE_PAGE_LINES and _is_furniture_text(ln):
            continue
        out.append(ln)
    return "\n".join(out)


def standardize_title_page(body: str, fields: TitlePageFields) -> str:
    """Replace the raw legacy cover with the standardized :func:`_title_block` (§6.4).

    **Capture-gate:** the cover is touched only when ``fields.published`` is present (Task 2 lifted
    it from this very cover) — otherwise the body is returned unchanged so the sole copy of the date
    is never destroyed (retain + flag elsewhere). When the pre-content region has a cover signal and
    a clean boundary (an ATX heading / legacy revision or TOC marker within ``_MAX_COVER_LINES``),
    the whole cover is **replaced** by the standardized block; for an all-bold flat cover with no
    such boundary, the furniture is **surgically stripped** instead (see _strip_cover_furniture).
    Idempotent: the emitted block carries no cover signal and no bare ``Month YYYY`` line."""
    if not fields.published:
        return body
    lines = body.split("\n")
    end = _cover_end(lines)
    # Region-replace only when a *real* content boundary was found (``end < len(lines)``) within the
    # window — otherwise ``end == len(lines)`` (no boundary) would replace the whole flat doc. With
    # no boundary, fall back to the surgical furniture strip.
    bounded = 0 < end < len(lines) and end <= _MAX_COVER_LINES
    if bounded and any(_is_cover_line(ln) for ln in lines[:end]):
        return "\n".join([*_title_block(fields), "", *lines[end:]]).lstrip("\n")
    return _strip_cover_furniture(lines)


def apply_template(
    body: str, doc_type: str, era: str, templates: Sequence[Template]
) -> tuple[str, str]:
    """Match ``(doc_type, era)`` → strip unfilled scaffold sections and return the ``template_id``.

    No matching template → ``(body, "")`` unchanged (so the stage stamps nothing)."""
    match = next((t for t in templates if t.doc_type == doc_type and t.era == era), None)
    if match is None:
        return body, ""
    return strip_template_scaffold(body, match.section_titles), match.template_id


def strip_template_scaffold(body: str, section_titles: frozenset[str]) -> str:
    """Remove each **empty** heading whose (normalized) title is a template-scaffold section.

    A heading is empty when every line from it up to the next heading (of any level) is blank — i.e.
    it has neither prose nor subsections. Fence-aware; non-scaffold and filled headings are kept."""
    if not section_titles:
        return body
    lines = body.split("\n")
    # (line index, level, raw text), fence- + Contents-aware, in document order (kernel.markdown,
    # §9.2). `#+` now recognizes >6-`#` headings too (the canonical resolution).
    headings = list(iter_headings(body))

    drop: set[int] = set()
    for pos, (idx, level, raw) in enumerate(headings):
        title = _norm(raw)
        if title not in section_titles:
            continue
        # the section runs to the next heading of the *same or shallower* level — so subsections
        # (deeper headings) count as content and keep the parent from being treated as empty.
        end = len(lines)
        for nidx, nlevel, _ in headings[pos + 1 :]:
            if nlevel <= level:
                end = nidx
                break
        if all(not lines[j].strip() for j in range(idx + 1, end)):  # no prose, no subsections
            drop.update(range(idx, end))
    if not drop:
        return body
    return "\n".join(line for i, line in enumerate(lines) if i not in drop)
