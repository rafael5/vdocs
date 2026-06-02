"""Text repair primitives — the single shared implementation (design §9.2).

v1 carried *three* mojibake fixers; v2 has exactly one, pure and property-tested.
Pure functions only: no I/O, no logging side effects.
"""

from __future__ import annotations

import html
import re
import unicodedata

# Mojibake: utf-8 bytes mis-decoded as cp1252 produce the tell-tale "Ã"/"â€"
# sequences. The general repair is the round-trip — encode back to cp1252 and
# decode as utf-8 — which recovers any *complete* byte sequence.
_MOJIBAKE_MARKERS = ("Ã", "â€", "Â")

# Some mojibake is lossy: the closing curly quote ”/U+201D mis-renders through a
# cp1252-undefined byte, leaving a bare "â€" the round-trip cannot reconstruct.
# These known sequences are repaired by direct substitution (longest key first).
_MOJIBAKE_FALLBACK = (
    ("â€™", "’"),
    ("â€˜", "‘"),
    ("â€œ", "“"),
    ("â€\x9d", "”"),  # closing ” lost its byte through a cp1252-undefined slot
    ("â€¦", "…"),
    ("â€", "”"),  # bare residue → closing double quote
)

# C0 controls except tab/newline/carriage-return, plus the lone DEL.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
# Bundle-path slug: app codes may carry slashes/plus (AR/WS, DRM+) — collapse any run of
# path-unsafe characters before they reach a filesystem path (§5.2, §8).
_PATH_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_component(name: str) -> str:
    """Filesystem-safe path component: non-[A-Za-z0-9._-] runs → '_', trimmed (e.g. AR/WS→AR_WS).

    The single bundle-path slug sanitiser shared across the document-silver stages (§9.2): a
    primitive used by ``convert``/``enrich``/``normalize`` lives in the kernel, not a stage."""
    return _PATH_UNSAFE.sub("_", name).strip("_") or "_"


def repair_mojibake(s: str) -> str:
    """Repair cp1252-through-utf8 mojibake; leave already-clean text untouched."""
    if not any(marker in s for marker in _MOJIBAKE_MARKERS):
        return s
    try:
        # cp1252 is the right codec: byte 0x80 is €, which is how a UTF-8 lead
        # byte sequence like E2 80 99 (’) gets mis-rendered as "â€™".
        repaired = s.encode("cp1252").decode("utf-8")
        # Only accept the round-trip if it actually removed the markers —
        # otherwise we risk corrupting text that legitimately contains them.
        if not any(marker in repaired for marker in _MOJIBAKE_MARKERS):
            return repaired
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    # Round-trip failed or left residue (lossy sequences) — substitute the
    # known mojibake sequences directly.
    for bad, good in _MOJIBAKE_FALLBACK:
        s = s.replace(bad, good)
    return s


def scrub_control_chars(s: str) -> str:
    """Drop C0/DEL control characters; keep tab, newline, carriage return."""
    return _CONTROL_RE.sub("", s)


def strip_html(s: str) -> str:
    """Strip HTML tags and unescape entities, collapsing the residual spaces."""
    no_tags = _TAG_RE.sub("", s)
    unescaped = html.unescape(no_tags)
    return _WS_RE.sub(" ", unescaped).strip()


def clean(s: str) -> str:
    """The full repair pipeline: mojibake → control scrub → HTML strip → NFC.

    Idempotent: ``clean(clean(x)) == clean(x)``.
    """
    s = repair_mojibake(s)
    s = scrub_control_chars(s)
    s = strip_html(s)
    return unicodedata.normalize("NFC", s)
