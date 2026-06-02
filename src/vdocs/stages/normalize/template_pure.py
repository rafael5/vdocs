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

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


@dataclass(frozen=True)
class Template:
    """A curated template's match key + the (normalized) titles of its scaffold sections."""

    template_id: str
    doc_type: str
    era: str
    section_titles: frozenset[str]  # normalized (lowercased, whitespace-collapsed) heading titles


def _norm(title: str) -> str:
    return " ".join(title.lower().split())


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
    # heading (line index, level), fence-aware, in document order
    headings: list[tuple[int, int]] = []
    in_fence = False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence and (m := _HEADING_RE.match(line)) is not None:
            headings.append((i, len(m.group(1))))

    drop: set[int] = set()
    for pos, (idx, level) in enumerate(headings):
        title = _norm(_HEADING_RE.match(lines[idx]).group(2))  # type: ignore[union-attr]
        if title not in section_titles:
            continue
        # the section runs to the next heading of the *same or shallower* level — so subsections
        # (deeper headings) count as content and keep the parent from being treated as empty.
        end = len(lines)
        for nidx, nlevel in headings[pos + 1 :]:
            if nlevel <= level:
                end = nidx
                break
        if all(not lines[j].strip() for j in range(idx + 1, end)):  # no prose, no subsections
            drop.update(range(idx, end))
    if not drop:
        return body
    return "\n".join(line for i, line in enumerate(lines) if i not in drop)
