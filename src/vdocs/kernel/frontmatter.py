"""The single YAML frontmatter codec (design §9.2 / §6.3).

v1 had three frontmatter parsers; v2 has exactly one. Pure: parse / canonical-order
emit / round-trip-safe. Identity keys are emitted in a fixed order (§6.3); computed
metadata is never written here (it lives in ``index.db``).
"""

from __future__ import annotations

import re
from typing import Any

import structlog
import yaml

log = structlog.get_logger(__name__)

# Identity / human-curated keys, in canonical emit order (§6.3). Anything else is
# appended alphabetically — but computed fields should never reach this codec.
_IDENTITY_ORDER = (
    "title",
    "doc_type",
    "app_code",
    "section",
    "pkg_ns",
    "version",
    "source_url",
    "source_sha256",
    "converter",
    "tool_ver",
)

# A frontmatter block: leading "---\n", body of the block, "\n---\n", then an
# optional single blank line, then the document body.
_FM_RE = re.compile(r"^---\n(.*?)\n---\n(?:\n)?(.*)$", re.DOTALL)


def parse(text: str) -> tuple[dict[str, Any], str]:
    """Split ``text`` into (frontmatter mapping, body).

    Fail-safe: text without a well-formed, terminated frontmatter block returns
    ``({}, text)`` unchanged — never raises on missing frontmatter. **Malformed YAML** inside an
    otherwise-delimited block is isolated the same way (R8): a WARN is logged and the document is
    treated as having no frontmatter, so one bad doc never aborts ``normalize``/``enrich``.
    """
    match = _FM_RE.match(text)
    if match is None:
        return {}, text
    try:
        loaded = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        log.warning("frontmatter-malformed-yaml", error=str(exc))
        return {}, text
    if not isinstance(loaded, dict):
        return {}, text
    return loaded, match.group(2)


def _canonical(meta: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {k: meta[k] for k in _IDENTITY_ORDER if k in meta}
    for key in sorted(meta):
        if key not in ordered:
            ordered[key] = meta[key]
    return ordered


def emit(meta: dict[str, Any], body: str) -> str:
    """Render frontmatter + body with identity keys in canonical order.

    Round-trips with :func:`parse`: ``parse(emit(m, b)) == (m, b)``.
    """
    block = yaml.safe_dump(
        _canonical(meta),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip("\n")
    return f"---\n{block}\n---\n\n{body}"
