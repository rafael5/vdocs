"""Pure core for `consolidate` — version-group grouping, ordering, append-only lineage (§6.6).

Zero I/O: the thin ``stage.py`` driver reads each normalized bundle (frontmatter + folded
``revisions.yaml`` + retained body sha), builds a :class:`Member` per document, and hands plain
values here; these functions group members by ``anchor_key``, order each group oldest→newest, and
fold the ordered chain into the ``history.yaml`` lineage. **Append-only** (§6.6): a later run in
which a new patch becomes the latest body appends one entry and re-points the derived ``is_latest``
flag — it never rewrites a captured member's facts.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from vdocs.kernel.ids import slug_stem
from vdocs.kernel.text import safe_component


@dataclass
class Member:
    """One version of a logical document — a single normalized bundle within a version group.

    Everything here is read from the bundle's identity frontmatter, its folded ``revisions.yaml``,
    and the content hash of its retained normalized body (``body_sha256``). Pure values only; the
    driver does the I/O that fills them."""

    anchor_key: str  # the version-group key (app:pkg:doc_code) — kernel.ids.anchor_key
    app_code: str
    pkg_ns: str
    doc_code: str
    doc_slug: str
    doc_id: str  # the stable inventory id (app_code:doc_slug)
    version: str  # patch_ver string (e.g. "3.0") — display only; patch_num governs order
    patch_id: str  # e.g. "OR*3.0*539" (or "" for a base/initial release)
    patch_num: int | None  # parsed from patch_id; None when the doc carries no patch number
    official_date: str  # newest revision-table date (from revisions.yaml) — the order tiebreak
    source_sha256: str  # the bronze docx provenance hash
    body_sha256: str  # CAS ref to this version's retained normalized body
    revisions: list[dict[str, Any]] = field(default_factory=list)  # folded revisions.yaml entries


def official_date(revision_newest: str, published: str) -> str:
    """The document's official date: the newest revision-table date when one was captured, else the
    title-page ``published`` date (§6.4). The fallback is what lets ``official_date`` populate for
    docs whose only date is on the cover (no revision table) — ``consolidate`` no longer depends
    *solely* on the revision table, closing the P1 gap where ~280 docs had an empty date."""
    return revision_newest or published


def parse_patch_num(patch_id: str) -> int | None:
    """The integer patch number from a ``NS*ver*num`` patch id, or ``None`` when absent.

    A base/initial release (``"NS*ver"`` or ``""``) and any non-numeric trailing segment yield
    ``None`` — "no patch number", distinct from an explicit patch ``0`` (``"OR*3*0"`` → ``0``)."""
    parts = patch_id.split("*")
    if len(parts) < 3:
        return None
    tail = parts[-1]
    return int(tail) if tail.isdigit() else None


def _sort_key(m: Member) -> tuple[bool, int, str, str]:
    """Order key: base docs (no patch number) first, then by patch number, then official date,
    then ``doc_slug`` as the stable final tiebreak (a group can hold members with one patch id)."""
    return (m.patch_num is not None, m.patch_num or 0, m.official_date, m.doc_slug)


def anchor_relpath(app_code: str, pkg_ns: str, doc_code: str, *, doc_slug: str = "") -> str:
    """The **stable, version-free** ``<app>/<slug>`` path of a version group's anchor bundle (§6.6).

    Keyed on the logical-document identity (the version-stripped ``doc_slug`` stem), so the living
    file's path is invariant as patches accrue **and** distinct manuals that merely share an
    ``app:pkg:doc_code`` get distinct paths (B1 — without the stem, all 42 ``XU:XU:UG`` Kernel
    guides collided into one ``XU/xu_ug``). A standalone document with no ``doc_code`` keeps its own
    ``doc_slug``. Falls back to ``<pkg>_<doc_code>`` if the stem strips to nothing. Uniqueness
    follows from ``anchor_key`` uniqueness: one group ⇒ one path."""
    if doc_code:
        stem = slug_stem(doc_slug) or f"{pkg_ns}_{doc_code}"
        return f"{safe_component(app_code)}/{safe_component(stem.lower())}"
    return f"{safe_component(app_code)}/{safe_component(doc_slug)}"


def group_by_anchor_key(members: list[Member]) -> dict[str, list[Member]]:
    """Partition members into version groups (insertion order preserved).

    Keyed on ``anchor_key`` — except a member with an **empty** ``anchor_key`` (no ``doc_code`` ⇒ no
    version group) falls back to its own ``doc_id``, so unrelated standalone documents each form a
    group of one rather than collapsing together. The returned dict key is only the grouping handle;
    a group's real (possibly empty) ``anchor_key`` lives on its members."""
    groups: dict[str, list[Member]] = defaultdict(list)
    for m in members:
        groups[m.anchor_key or m.doc_id].append(m)
    return dict(groups)


def order_members(members: list[Member]) -> list[Member]:
    """Order a version group's members **oldest → newest** (§6.6), deterministically."""
    return sorted(members, key=_sort_key)


def history_entry(m: Member, *, is_latest: bool) -> dict[str, Any]:
    """One ordered lineage record for ``history.yaml`` — the captured facts of one version."""
    return {
        "doc_id": m.doc_id,
        "doc_slug": m.doc_slug,
        "version": m.version,
        "patch_id": m.patch_id,
        "official_date": m.official_date,
        "source_sha256": m.source_sha256,
        "body_sha256": m.body_sha256,
        "is_latest": is_latest,
        "revisions": m.revisions,
    }


def build_history(anchor_key: str, ordered: list[Member]) -> dict[str, Any]:
    """Assemble the group-level ``history.yaml`` mapping from an ordered member list.

    ``is_latest`` flags only the newest (last) member; the anchor document's body is that member's
    retained body. Folds each member's ``revisions.yaml`` (§6.4) into its entry."""
    last = len(ordered) - 1
    members = [history_entry(m, is_latest=(i == last)) for i, m in enumerate(ordered)]
    return {"anchor_key": anchor_key, "member_count": len(members), "members": members}


def merge_history(existing: dict[str, Any] | None, fresh: dict[str, Any]) -> dict[str, Any]:
    """Fold a freshly-built history into the prior one, **append-only** (§6.6).

    A new VDL patch appears as a member in ``fresh`` not present in ``existing``; it is appended in
    ``fresh``'s order. Members already captured keep every recorded fact unchanged — only the
    derived ``is_latest`` pointer re-points to the new newest member. Re-running with the same
    membership is a no-op (idempotent); a first run (``existing is None``) returns ``fresh``."""
    if existing is None:
        return fresh
    seen = {e["doc_id"] for e in existing["members"]}
    appended = [e for e in fresh["members"] if e["doc_id"] not in seen]
    members = [*existing["members"], *appended]
    last = len(members) - 1
    members = [{**e, "is_latest": (i == last)} for i, e in enumerate(members)]
    return {"anchor_key": fresh["anchor_key"], "member_count": len(members), "members": members}
