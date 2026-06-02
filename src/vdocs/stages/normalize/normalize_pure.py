"""Pure normalize transforms — the F-steps (§6.7, §9.6). Real-corpus-driven, incremental.

`normalize` is deterministic and per-document: same ``(body, registries)`` in → same body out
(idempotent, §7.4). This first set of F-steps, grounded in the real VA corpus, covers:

  F-strip   — remove Pandoc artifacts (empty ``<!-- -->`` comments, runaway blank lines).
  F-phrases — subtract the **curated** ``registries/phrases`` (dead text deleted outright, §9.6).
  F-toc     — regenerate ``## Contents`` from the **actual heading tree** with GitHub-slug anchors
              (§6.7: derive structure, never trust the extracted TOC).

Deferred (noted in the tracker): tables→``tables/*.csv``, revision-history→``history.yaml``,
boilerplate REFERENCE + ``gold/_shared``, template STRIP+STAMP, ``refs.yaml`` + back-links +
Word-bookmark rewrite, and old-generation heading recovery. ``source_sha256`` is added by the
stage (it has the bronze sha); these functions stay pure over the body text + registries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_HEADING_LINE_RE = re.compile(r"^#{1,6} ", re.MULTILINE)
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_HTML_COMMENT_RE = re.compile(r"^<!--.*-->$")
_SLUG_DROP = re.compile(r"[^\w\- ]+")  # GitHub slug: drop punctuation, keep word chars/space/hyphen
_MULTI_BLANK = re.compile(r"\n{3,}")
_TOC_ENTRY_RE = re.compile(r"^\s*- \[.*\]\(#.*\)\s*$")
# a paragraph the original Word TOC linked to: a `_Toc…` bookmark anchor span at line start,
# followed by the heading text. Pandoc leaves these as plain paragraphs (no `#`) — §6.7 recovery.
_TOC_BOOKMARK_HEADING = re.compile(r'^<span id="_Toc\d+"[^>]*></span>\s*(.+?)\s*$', re.MULTILINE)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    slug: str


def github_slug(text: str, seen: dict[str, int]) -> str:
    """A GitHub-compatible heading anchor slug (lowercase, punctuation dropped, spaces→hyphens),
    with GitHub's ``-1``/``-2`` duplicate disambiguation in document order (§6.7)."""
    base = _SLUG_DROP.sub("", text.strip().lower()).replace(" ", "-")
    n = seen.get(base, 0)
    seen[base] = n + 1
    return base if n == 0 else f"{base}-{n}"


def parse_headings(body: str) -> list[Heading]:
    """The ATX heading tree (``#``…``######``), skipping fenced code and our own ``## Contents``."""
    headings: list[Heading] = []
    seen: dict[str, int] = {}
    in_fence = False
    for line in body.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if m is None:
            continue
        text = m.group(2).strip()
        if not text or text.lower() == "contents":
            continue
        headings.append(Heading(len(m.group(1)), text, github_slug(text, seen)))
    return headings


def recover_headings(body: str) -> str:
    """F-recover (§6.7): give a heading tree to docs Pandoc flattened. The original Word TOC links
    to ``_Toc…`` bookmarks; Pandoc emits those targets as plain paragraphs (a leading
    ``<span id="_Toc…" …></span>`` + the heading text). Promote each to a level-2 heading,
    stripping inline markup. Runs **only when the body has no markdown headings**, so
    well-structured docs are left untouched. (Level inference from TOC depth/numbering is deferred —
    a flat tree still gives a working TOC + anchors where there were none.)"""
    if _HEADING_LINE_RE.search(body):
        return body

    def repl(m: re.Match[str]) -> str:
        # strip inline HTML tags and any wrapping markdown emphasis (**bold**/_italic_)
        text = _TAG_RE.sub("", m.group(1)).strip().strip("*_ ").strip()
        return f"## {text}" if text else m.group(0)

    return _TOC_BOOKMARK_HEADING.sub(repl, body)


def strip_artifacts(body: str) -> str:
    """F-strip: drop standalone empty HTML comments (Pandoc emits many) + collapse blank runs."""
    kept = [ln for ln in body.split("\n") if not _HTML_COMMENT_RE.match(ln.strip())]
    return _MULTI_BLANK.sub("\n\n", "\n".join(kept)).strip("\n") + "\n"


def subtract_phrases(body: str, phrases: frozenset[str]) -> str:
    """F-phrases: delete whole blocks matching a curated dead phrase (case-insensitive)."""
    if not phrases:
        return body
    lowered = {p.strip().lower() for p in phrases}
    blocks = re.split(r"\n\s*\n", body)
    kept = [b for b in blocks if b.strip().lower() not in lowered]
    return "\n\n".join(kept)


def strip_existing_toc(body: str) -> str:
    """Remove a previously-generated ``## Contents`` block (its heading + list) for idempotency."""
    lines = body.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip().lower() == "## contents":
            i += 1
            while i < len(lines) and (not lines[i].strip() or _TOC_ENTRY_RE.match(lines[i])):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def build_toc(headings: list[Heading]) -> str:
    """A ``## Contents`` GFM list linking each heading to its slug anchor (nested by level)."""
    if not headings:
        return ""
    base = min(h.level for h in headings)
    lines = ["## Contents", ""]
    lines += [f"{'  ' * (h.level - base)}- [{h.text}](#{h.slug})" for h in headings]
    return "\n".join(lines)


def regenerate_toc(body: str) -> str:
    """F-toc: replace any stale ``## Contents`` with a fresh TOC derived from the heading tree.

    Inserted after a leading top-level title heading if present, else at the top of the body."""
    body = strip_existing_toc(body)
    toc = build_toc(parse_headings(body))
    if not toc:
        return body
    lines = body.split("\n")
    # find a leading H1 (skipping blanks) → place Contents just after it; else prepend
    insert_at = 0
    for idx, ln in enumerate(lines):
        if not ln.strip():
            continue
        if _HEADING_RE.match(ln) and ln.startswith("# "):
            insert_at = idx + 1
        break
    head, tail = lines[:insert_at], lines[insert_at:]
    return "\n".join([*head, "", toc, "", *tail]).strip("\n") + "\n"


def normalize_body(body: str, phrases: frozenset[str]) -> str:
    """Apply the F-steps in order: recover headings → strip artifacts → subtract curated phrases
    → regenerate TOC (recovery first so the regenerated TOC sees the rebuilt heading tree)."""
    return regenerate_toc(subtract_phrases(strip_artifacts(recover_headings(body)), phrases))
