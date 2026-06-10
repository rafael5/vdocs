"""Two-axis persona / profile resolution (design §7) — the ONE place the four profile tags
(`app_user`, `doc_user`, `software_class`, `function_category`) are derived from the inventory
registries. Shared by the `enrich` stage (which bakes them into gold ``body.md`` frontmatter) and
the `server.facets` reader (which queries the baked columns), so the resolution rule lives once
(§9.2) rather than being copied into both planes.

**One vocabulary, two axes** (``clinical · clinical-admin · business-admin · developer ·
sysadmin``):

- **app_user** — who *operates the app* (``app-profiles.yaml`` ``app_user_primary``). Keyed by the
  app abbrev (= inventory ``app_name_abbrev`` = the ``documents.app_code`` column).
- **doc_user** — who *reads the doc* (``doc-user.yaml``). A doc_type is either role-fixed to a
  persona (a Technical Manual is read by developers, any app) or ``operator`` — read by the app's
  operators, so it **delegates** to that app's ``app_user``.

``software_class`` (I/II/III) and ``function_category`` (SPM product line) are flat per-app
attributes from the same profiles.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path

import structlog
import yaml

log = structlog.get_logger(__name__)

__all__ = [
    "PROFILE_TAGS",
    "ProfileMaps",
    "app_names",
    "load_profile_maps",
    "profile_tags",
    "resolve_doc_user",
]

# the four tags baked into gold frontmatter + index.db (in canonical frontmatter order)
PROFILE_TAGS: tuple[str, ...] = ("app_user", "doc_user", "software_class", "function_category")

# app-profiles.yaml sections holding per-app profiles, and the needs-review sentinel never surfaced
_PROFILE_SECTIONS = ("profiles", "fallback_profiles")
_NEEDS_REVIEW = "needs-review"


@dataclass(frozen=True)
class ProfileMaps:
    """The registry-derived lookup maps for the four baked profile tags.

    ``app_user``/``software_class``/``function_category`` are keyed by app abbrev; ``doc_user`` is
    keyed by doc_type code (value is a persona or the literal ``operator``).
    """

    app_user: dict[str, str]
    software_class: dict[str, str]
    function_category: dict[str, str]
    doc_user: dict[str, str]


def resolve_doc_user(
    doc_type: str, app_code: str, doc_user_map: dict[str, str], app_user_map: dict[str, str]
) -> str:
    """Who reads one doc: the role-fixed persona, or — for ``operator`` doc-types — the app's
    ``app_user``. Empty string if neither resolves."""
    who = doc_user_map.get(doc_type, "")
    return app_user_map.get(app_code, "") if who == "operator" else who


def profile_tags(app_code: str, doc_type: str, maps: ProfileMaps) -> dict[str, str]:
    """The four resolved tags for one document, **empties dropped** so the frontmatter stays
    minimal (a doc whose app has no profile gets no profile tags)."""
    tags = {
        "app_user": maps.app_user.get(app_code, ""),
        "doc_user": resolve_doc_user(doc_type, app_code, maps.doc_user, maps.app_user),
        "software_class": maps.software_class.get(app_code, ""),
        "function_category": maps.function_category.get(app_code, ""),
    }
    return {k: v for k, v in tags.items() if v}


def load_profile_maps(registries_dir: Path) -> ProfileMaps:
    """Build the four lookup maps from ``inventory/{app-profiles,doc-user}.yaml`` (the same
    registries the control plane curates). Missing files yield empty maps — never raises."""
    inv = registries_dir / "inventory"
    profiles = _load_profiles(inv / "app-profiles.yaml")
    return ProfileMaps(
        app_user=_app_field(profiles, "app_user_primary", drop={_NEEDS_REVIEW}),
        software_class=_app_field(profiles, "software_class"),
        # function_category is the curated functional taxonomy (function-domains.yaml),
        # NOT the Monograph SPM product line (an ownership axis kept in app-profiles for
        # provenance). See docs/function-domain-taxonomy.md.
        function_category=_load_function_domains(inv / "function-domains.yaml"),
        doc_user=_load_doc_user(inv / "doc-user.yaml"),
    )


def _load_function_domains(path: Path) -> dict[str, str]:
    """``app_code → functional domain`` from ``function-domains.yaml`` (``apps:``)."""
    data = _load_yaml(path)
    apps = data.get("apps") or {}
    return {str(k): str(v) for k, v in apps.items() if v}


def app_names(registries_dir: Path) -> dict[str, str]:
    """``app_code → canonical application name`` from ``app-profiles.yaml`` (the ``name`` field).

    Used by the ``index`` stage as the display-title app-name fallback (a title that de-noises
    to only a doc-type label is prefixed with this). Missing file yields an empty map."""
    profiles = _load_profiles(registries_dir / "inventory" / "app-profiles.yaml")
    return {app: str(p["name"]) for app, p in profiles.items() if p.get("name")}


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _load_profiles(path: Path) -> dict[str, dict]:
    """The merged ``app_code → profile`` map across the profile sections."""
    data = _load_yaml(path)
    out: dict[str, dict] = {}
    for section in _PROFILE_SECTIONS:
        for app, prof in (data.get(section) or {}).items():
            if isinstance(prof, dict):
                out[str(app)] = prof
    return out


def _app_field(
    profiles: dict[str, dict], field: str, *, drop: AbstractSet[str] = frozenset()
) -> dict[str, str]:
    """``app_code → <field>`` for every profile with a non-empty, non-dropped value."""
    out: dict[str, str] = {}
    for app, prof in profiles.items():
        value = str(prof.get(field, "") or "")
        if value and value not in drop:
            out[app] = value
    return out


def _load_doc_user(path: Path) -> dict[str, str]:
    """The ``doc_type → doc_user`` map (``operator`` | persona)."""
    data = _load_yaml(path)
    return {str(k): str(v) for k, v in (data.get("doc_user") or {}).items()}
