"""Imported-baseline front-matter rewrite for ``export-fileman`` (FileMan docs-as-code pilot, L1;
see ``docs/fileman-docs-pilot-implementation-plan.md`` and
``docs/vdl-content-quality-and-ia-strategy.md`` §3/§5).

When a gold VDL document is materialized into the ``fileman-docs`` master, three things change in
its front matter, all here and all pure (gold meta dict → imported-baseline meta dict):

1. **doc_type → Diátaxis mode.** The VDL ships opaque doc-kind codes (DG/UM/TM/SG/TRG/…). The
   docs-as-code standard types every topic by the controlled Diátaxis vocab (S1/S6). We rewrite
   ``doc_type`` to the mode and keep the original code as ``source_doc_type`` for traceability. The
   mode here is the *default* for the whole imported doc; the L3 re-chunk refines per topic.
2. **Provenance frozen.** ``source_url``/``source_sha256`` stop being live ingestion keys and become
   the "imported-from" stamp; ``imported_from``/``imported_by``/``imported_date`` record the
   one-time import (the inversion — the master is now the markdown, not the Word doc).
3. **Lifecycle added.** ``status: imported`` (the freshness signal the §6 proofread gate drives to
   ``reviewed``), ``last_reviewed``, and ``owner`` (CODEOWNERS routing, derived from ``app_code``).

``imported_by``/``imported_date`` are passed in (not read from the clock) so the transform stays
pure and deterministic — the CLI driver supplies them.
"""

from __future__ import annotations

from typing import Any

# The controlled Diátaxis vocab (the ms.topic analog). doc_type must be one of these post-rewrite.
DIATAXIS_MODES = ("tutorial", "how-to", "reference", "explanation", "overview")

# VDL doc-kind code → default Diátaxis mode. Defaults are deliberately conservative; the L3
# editorial re-chunk splits a doc across modes (e.g. File Security → how-to + explanation) and
# refines per topic. Unknown codes fail soft to reference (most VDL material is reference-shaped).
_MODE_BY_DOCTYPE = {
    "DG": "reference",  # Developer's / Programmer Guide — API reference
    "PM": "reference",  # Programmer Manual (alias)
    "TM": "how-to",  # Technical Manual — install/admin (how-to + reference)
    "SMG": "how-to",  # Systems Management Guide
    "UM": "how-to",  # User Manual — end-user procedures
    "UG": "how-to",  # User Guide
    "IG": "how-to",  # Installation Guide
    "CG": "how-to",  # Configuration Guide
    "SG": "reference",  # Security Guide — file-access reference
    "TRG": "tutorial",  # Training / tutorial
    "RN": "reference",  # Release Notes
}
_DEFAULT_MODE = "reference"

# Identity fields carried verbatim from the gold front matter (everything that is still true of the
# imported topic). tool_ver is intentionally excluded — superseded by imported_by.
_CARRIED = (
    "title",
    "app_code",
    "section",
    "pkg_ns",
    "version",
    "published",
    "app_user",
    "doc_user",
    "software_class",
    "function_category",
    "patch_id",
)


def diataxis_mode(doc_type_code: str) -> str:
    """Map a VDL doc-kind code to its default Diátaxis mode (fail-soft to reference)."""
    return _MODE_BY_DOCTYPE.get(str(doc_type_code).upper(), _DEFAULT_MODE)


def rewrite_frontmatter(
    gold_meta: dict[str, Any],
    *,
    slug: str,
    imported_by: str,
    imported_date: str,
) -> dict[str, Any]:
    """Rewrite a gold document's front matter into the imported-baseline form."""
    out: dict[str, Any] = {k: gold_meta[k] for k in _CARRIED if k in gold_meta}

    code = str(gold_meta.get("doc_type", ""))
    out["doc_type"] = diataxis_mode(code)
    out["source_doc_type"] = code

    # frozen provenance
    for k in ("source_url", "source_sha256"):
        if k in gold_meta:
            out[k] = gold_meta[k]
    out["imported_from"] = slug
    out["imported_by"] = imported_by
    out["imported_date"] = imported_date

    # git-owned lifecycle
    out["status"] = "imported"
    out["last_reviewed"] = ""
    out["owner"] = f"{str(gold_meta.get('app_code', '')).lower()}-maintainers"

    return out
