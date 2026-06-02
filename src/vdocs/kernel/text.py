"""Text repair primitives — the single shared implementation (design §9.2).

v1 carried *three* mojibake fixers; v2 has exactly one — ``ftfy`` — used by the kernel and the
catalog enrichment alike. Pure functions only: no I/O, no logging side effects.
"""

from __future__ import annotations

import html
import re
import unicodedata

import ftfy

# C0 controls except tab/newline/carriage-return, plus the lone DEL.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# The single HTML-tag matcher (§9.2): one ``<[^>]+>`` shared by every tag-stripper across the
# kernel and the normalize stages (was copy-pasted 5×). ``kernel.markdown`` re-exports it.
TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
# Bundle-path slug: app codes may carry slashes/plus (AR/WS, DRM+) — collapse any run of
# path-unsafe characters before they reach a filesystem path (§5.2, §8).
_PATH_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
# Block-equality key: collapse *all* whitespace (incl. newlines — a block may span lines).
_BLOCK_WS_RE = re.compile(r"\s+")
# GitHub heading-anchor slug: drop punctuation, keep word chars/hyphens, spaces→hyphens (§6.7).
_GH_SLUG_DROP = re.compile(r"[^\w\- ]+")
# Publication-era signal: the first "Month YYYY" printed on a title page (§9.8). The decade bucket
# of this date is the era axis for `(doc_type, era)` template induction/matching — the only
# trustworthy era signal (DOCX metadata is a bulk-re-export artifact; the VDL file_date is ~empty).
_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_MONTH_YEAR_RE = re.compile(rf"\b{_MONTH}\.?,?\s+(\d{{4}})\b", re.IGNORECASE)


def safe_component(name: str) -> str:
    """Filesystem-safe path component: non-[A-Za-z0-9._-] runs → '_', trimmed (e.g. AR/WS→AR_WS).

    The single bundle-path slug sanitiser shared across the document-silver stages (§9.2): a
    primitive used by ``convert``/``enrich``/``normalize`` lives in the kernel, not a stage."""
    return _PATH_UNSAFE.sub("_", name).strip("_") or "_"


def slugify(text: str, *, sep: str = "-", fallback: str = "") -> str:
    """The single slug primitive (§9.2/D3): lowercase, drop punctuation, keep word chars and
    existing hyphens, render spaces as ``sep``; empty result → ``fallback``.

    This is the **GitHub heading-anchor rule** (so the anchors ``normalize`` emits, ``discover``'s
    section ids, and ``index``'s canonical section ids all agree — closing the latent index-join
    divergence). ``sep`` lets a caller pick the separator (``-`` for anchors, ``_`` elsewhere);
    ``fallback`` names an otherwise-empty slug. *Not* the catalog **filesystem** slug —
    ``catalog.make_doc_slug`` keeps its own path-safety rule (collapse every non-alnum run,
    so ``5.3`` → ``5_3``), a deliberately different transform for bundle paths, not anchors."""
    return (_GH_SLUG_DROP.sub("", text.strip().lower()).replace(" ", sep)) or fallback


def github_slug_base(text: str) -> str:
    """The GitHub heading-anchor slug *base* (lowercase, punctuation dropped, spaces→hyphens),
    **without** duplicate disambiguation (§6.7).

    Thin alias for :func:`slugify` (sep ``-``) — the shared home for the GitHub-slug rule used by
    the published-markdown anchors, the TOC, ``discover``'s section ids, and ``index``'s canonical
    section IDs (§5.5/§9.2). ``anchors_pure.github_slug`` layers GitHub's ``-1``/``-2``
    document-order dedup on top of this base."""
    return slugify(text)


def block_key(block: str) -> str:
    """Whitespace-collapsed, lowercased identity of a text block — the shared block-equality key.

    Used by ``discover`` (recurring-block mining) and ``normalize`` (boilerplate subtraction) to
    decide when two blocks are "the same" modulo spacing/case (§9.2 — one primitive, two stages)."""
    return _BLOCK_WS_RE.sub(" ", block.strip().lower())


def decade_bucket(text: str, *, max_lines: int | None = None) -> str:
    """Decade bucket (``"1990s"`` …) of the first ``Month YYYY`` in ``text``, or ``"unknown"``.

    Optionally scan only the first ``max_lines`` (the title-page window). The shared era helper
    used by ``discover`` (template induction) and ``normalize`` (template matching) — §9.2."""
    head = "\n".join(text.splitlines()[:max_lines]) if max_lines is not None else text
    m = _MONTH_YEAR_RE.search(head)
    if m is None:
        return "unknown"
    return f"{(int(m.group(1)) // 10) * 10}s"


def repair_mojibake(s: str) -> str:
    """Repair encoding artifacts via ``ftfy`` + NFC — the single shared fixer (§9.2).

    ``ftfy.fix_text`` undoes cp1252-through-utf8 mojibake (the tell-tale "Ã"/"â€" sequences),
    decodes stray HTML/numeric entities, repairs the lossy curly-quote cases the old round-trip
    could not, and (its default ``uncurl_quotes``) normalises smart quotes to straight ASCII.
    Idempotent; leaves already-clean text untouched. This is exactly the call the catalog
    enrichment runs, so the kernel and ``catalog.fix_mojibake`` are byte-identical."""
    return ftfy.fix_text(s, normalization="NFC")


def scrub_control_chars(s: str) -> str:
    """Drop C0/DEL control characters; keep tab, newline, carriage return."""
    return _CONTROL_RE.sub("", s)


def strip_tags(s: str) -> str:
    """Remove HTML tags (``<…>``) from ``s`` — the bare tag-strip primitive (§9.2).

    The minimal shared form (no entity-unescape, no whitespace collapse): callers that need
    those layer them on. :func:`strip_html` is the full repair; ``kernel.markdown`` re-exports
    this for the heading/markdown call sites."""
    return TAG_RE.sub("", s)


def strip_html(s: str) -> str:
    """Strip HTML tags and unescape entities, collapsing the residual spaces."""
    no_tags = TAG_RE.sub("", s)
    unescaped = html.unescape(no_tags)
    return _WS_RE.sub(" ", unescaped).strip()


def clean(s: str) -> str:
    """The full repair pipeline: control scrub → mojibake → HTML strip → NFC.

    Idempotent: ``clean(clean(x)) == clean(x)``. Control characters are scrubbed **before** the
    mojibake repair: an interstitial control byte (e.g. a form feed between two mojibake bytes)
    would otherwise hide adjacent mojibake from ftfy on the first pass and surface it on the
    second, breaking idempotency. Scrubbing first makes adjacency stable.
    """
    s = scrub_control_chars(s)
    s = repair_mojibake(s)
    s = strip_html(s)
    return unicodedata.normalize("NFC", s)
