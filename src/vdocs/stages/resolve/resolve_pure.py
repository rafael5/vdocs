"""Pure cores of the `resolve` stage — recognize → resolve → classify → relate → verify (S2.2/S2.3).

`resolve` promotes scattered entity work into one governed transform that emits the SKL
(`knowledge.db`). Every sub-transform here is a pure function (no I/O): the thin `stage.py` driver
reads the gold + registries and calls these.

* **recognize** — reuse `index.entities_pure` (the *same* generic, registry-driven recognizer — not
  a fork); a mention is `(type, surface)`.
* **resolve** — map every surface to its canonical entity id, **data-driven** from the DD seed
  (`registries/entities/dd-seed.*.yaml`, Q6): `file #200` (via the recognizer's file-number), the
  prose name `the NEW PERSON file`, and the global root `^VA(200,` all resolve to one canonical id
  (`fileman_file/200`). No file identity lives in this code — only the resolution mechanics.
* **classify** — fold the S1 Term facets (class / canonical casing / English-collision) into
  TermNodes (see `kernel.products` + `kernel.casing_pure`).
* **relate** — emit typed edges, but only for `rel`s in the closed registered set (Q3); an
  unregistered type is rejected and never reaches `knowledge.db`.
* **verify** — stamp every node `verification.status = asserted` (corpus provenance; Q2 defers live
  verification to S5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from vdocs.kernel import casing_pure
from vdocs.models.knowledge import (
    EntityNode,
    Provenance,
    RelationshipNode,
    TermNode,
)
from vdocs.stages.index import entities_pure as ent


def normalize_surface(surface: str) -> str:
    """The match key for a surface: upper-cased, internal whitespace collapsed. Globals keep their
    `^`/`(`/`,` punctuation (it is identifying); only case and spacing are folded."""
    return re.sub(r"\s+", " ", surface.strip()).upper()


@dataclass(frozen=True)
class EntitySeed:
    """The seed identity of one entity (from the DD export) — drives EntityNode construction."""

    node_id: str
    type: str
    canonical: str
    canonical_name: str
    synonyms: tuple[str, ...]


@dataclass
class ResolutionIndex:
    """The data-driven surface→entity resolution table (built from the DD seed, never code)."""

    by_number: dict[str, str] = field(default_factory=dict)  # file number → node_id
    by_surface: dict[str, str] = field(default_factory=dict)  # normalized literal surface → node_id
    entities: dict[str, EntitySeed] = field(default_factory=dict)  # node_id → seed identity
    _surface_re: re.Pattern[str] | None = None

    def surface_regex(self) -> re.Pattern[str] | None:
        """A compiled alternation over every literal surface (names/globals/synonyms), longest-first
        so the most specific surface wins. None when the seed declares no literal surfaces."""
        return self._surface_re


def resolution_index(dd_files: list[dict]) -> ResolutionIndex:
    """Build the resolution table from the DD seed `files` entries (pure).

    Each file yields the canonical entity id `fileman_file/<number>` plus the surfaces that resolve
    to it: the number (matched via the recognizer's file-number context), the DD name, the global
    root, and any corpus-mined synonyms (all matched as literal text)."""
    idx = ResolutionIndex()
    literals: list[str] = []
    for f in dd_files:
        number = str(f["number"])
        node_id = f"fileman_file/{number}"
        name = str(f.get("name", "") or "")
        global_root = str(f.get("global", "") or "")
        synonyms = tuple(str(s) for s in (f.get("synonyms") or []))
        idx.by_number[number] = node_id
        idx.entities[node_id] = EntitySeed(
            node_id=node_id,
            type="fileman_file",
            canonical=number,
            canonical_name=name,
            synonyms=tuple(s for s in (name, global_root, *synonyms) if s),
        )
        for surface in (name, global_root, *synonyms):
            if not surface:
                continue
            idx.by_surface[normalize_surface(surface)] = node_id
            literals.append(surface)
    if literals:
        # longest-first so "NEW PERSON FILE" wins over "NEW PERSON". Each surface carries its own
        # boundary guards, applied only at an *alphanumeric* edge: a name like "NEW PERSON" must not
        # match inside a longer word, but a global root ending in `,`/`(` (e.g. `^VA(200,`) is
        # deliberately followed by subscripts — guarding it would wrongly reject `^VA(200,0)`.
        branches = [_bounded(s) for s in sorted(set(literals), key=len, reverse=True)]
        idx._surface_re = re.compile("|".join(branches), re.IGNORECASE)
    return idx


def _bounded(surface: str) -> str:
    """One alternation branch: the escaped surface, with a non-alphanumeric boundary guard added
    only at an alphanumeric edge (so punctuation-edged globals stay matchable mid-token)."""
    left = r"(?<![A-Za-z0-9])" if surface[:1].isalnum() else ""
    right = r"(?![A-Za-z0-9])" if surface[-1:].isalnum() else ""
    return f"{left}{re.escape(surface)}{right}"


@dataclass
class ResolveResult:
    """What `resolve` produced over one body of text: each canonical node and the surfaces that
    resolved to it, plus the recognized-but-unmapped mentions (candidates for the propose queue —
    never asserted into knowledge.db, §10)."""

    resolved: dict[str, set[str]] = field(default_factory=dict)
    unresolved: list[tuple[str, str]] = field(default_factory=list)


def recognize(text: str, rules: list[ent.EntityRule]) -> list[tuple[str, str]]:
    """Every `(type, surface)` mention in `text` — the shared generic recognizer (no fork)."""
    return ent.extract(text, rules)


def resolve(text: str, rules: list[ent.EntityRule], idx: ResolutionIndex) -> ResolveResult:
    """Resolve the recognized mentions + literal seed surfaces in `text` to canonical entity ids."""
    out = ResolveResult()

    def _add(node_id: str, surface: str) -> None:
        out.resolved.setdefault(node_id, set()).add(surface)

    # 2 first: literal seed surfaces (DD name, global root, synonyms) scanned directly in the prose.
    # Done before the recognizer pass so the *full* resolved surfaces are known when we decide which
    # recognizer mentions are genuinely unresolved.
    resolved_surfaces: set[str] = set()
    rx = idx.surface_regex()
    if rx is not None:
        for m in rx.finditer(text):
            node_id = idx.by_surface[normalize_surface(m.group(0))]
            _add(node_id, m.group(0))
            resolved_surfaces.add(m.group(0))

    # 1. recognizer mentions: a `fileman_file` canonical is a number → look it up; everything else
    #    that isn't seed-known becomes an unresolved candidate — EXCEPT a truncated global fragment
    #    of an already-resolved root: the `global` rule stops at `(`, so `^VA(200,` yields a bare
    #    `^VA`; that fragment is already accounted for, so it must not pollute the queue (S2.4).
    for etype, surface in recognize(text, rules):
        if etype == "fileman_file" and surface in idx.by_number:
            _add(idx.by_number[surface], f"file #{surface}")
        elif normalize_surface(surface) in idx.by_surface:
            _add(idx.by_surface[normalize_surface(surface)], surface)
        elif etype == "global" and _is_fragment_of(surface, resolved_surfaces):
            continue
        else:
            out.unresolved.append((etype, surface))
    return out


def _is_fragment_of(surface: str, resolved_surfaces: set[str]) -> bool:
    """True when `surface` is the truncated head of an already-resolved literal (a global root the
    recognizer clipped at `(`): `^VA` is a fragment of the resolved `^VA(200,`. Bounded to a
    non-alphanumeric continuation so `^DI` doesn't swallow an unrelated `^DIC`-rooted resolution."""
    n = len(surface)
    for full in resolved_surfaces:
        if len(full) > n and full.startswith(surface) and not full[n].isalnum():
            return True
    return False


# --- classify (S2.3): fold the S1 Term facets into TermNodes -------------------------------------


def classify_terms(
    products: dict[str, list[dict]],
    *,
    english_words: frozenset[str],
    appears: set[str],
    provenance: dict[str, list[Provenance]] | None = None,
) -> list[TermNode]:
    """Build TermNodes for the curated product/brand terms that appear in the corpus (`appears` =
    the set of surfaces seen). Each carries the S1 facets: `term_class`, `canonical_casing`,
    `enforce_case`, and the auto-derived `collides_with_english` (`kernel.casing_pure`)."""
    provenance = provenance or {}
    seen: dict[str, TermNode] = {}
    for entries in products.values():
        for e in entries:
            surface = str(e["abbr"])
            if surface not in appears or surface in seen:
                continue
            seen[surface] = TermNode(
                surface=surface,
                term_class=e.get("term_class"),
                canonical_casing=str(e.get("canonical_casing") or surface),
                enforce_case=bool(e.get("enforce_case", True)),
                collides_with_english=casing_pure.collides_with_english(surface, english_words),
                expand_on_first_use=bool(e.get("expand_on_first_use", False)),
                provenance=provenance.get(surface, []),
            )
    return [seen[k] for k in sorted(seen)]


# --- relate (S2.3): typed edges, closed registered set (Q3) --------------------------------------


def partition_edges(
    edges: list[RelationshipNode], registered: frozenset[str]
) -> tuple[list[RelationshipNode], list[RelationshipNode]]:
    """Split candidate edges into (kept, rejected) by whether `rel` is registered. Closed-by-default
    (Q3): an unregistered edge type is rejected here and never reaches `knowledge.db`."""
    kept = [e for e in edges if e.rel in registered]
    rejected = [e for e in edges if e.rel not in registered]
    return kept, rejected


def documented_in_edges(
    resolved_by_doc: dict[str, set[str]],
    *,
    provenance: dict[str, list[Provenance]] | None = None,
) -> list[RelationshipNode]:
    """One `documented-in` edge per (entity, doc): every resolved entity is documented in the gold
    doc it resolved in. `resolved_by_doc` maps doc_key → the node_ids resolved in that doc."""
    provenance = provenance or {}
    edges: list[RelationshipNode] = []
    for doc_key in sorted(resolved_by_doc):
        for node_id in sorted(resolved_by_doc[doc_key]):
            edges.append(
                RelationshipNode(
                    src_id=node_id,
                    rel="documented-in",
                    dst_id=f"doc/{doc_key}",
                    provenance=provenance.get(f"{node_id}|{doc_key}", []),
                )
            )
    return edges


# --- verify (S2.3): stamp every node asserted (Q2) -----------------------------------------------


def all_asserted(*node_lists: list) -> bool:
    """The verify invariant: every node carries a `verification` block at status `asserted`
    (corpus provenance). True when it holds for every node in every list (S2 has no live gating)."""
    return all(n.verification.status == "asserted" for nodes in node_lists for n in nodes)


def build_proposals(unresolved: list[tuple[str, str, str]]) -> list[dict]:
    """Aggregate recognized-but-unresolved mentions into a **curator queue** (S2.4, §10).

    Input is `(type, surface, doc_key)` triples. Output is one proposal per `(type, surface)` with
    its occurrence count and the docs it was seen in — `status: proposed`, grounded with provenance.
    This is the propose-only artifact: a human curates these into the registry seed before anything
    reaches `knowledge.db`. AI proposes (at scale), determinism resolves, the human authorizes — no
    unreviewed assertion is ever laundered into the authoritative store (proposal §10)."""
    agg: dict[tuple[str, str], set[str]] = {}
    counts: dict[tuple[str, str], int] = {}
    for etype, surface, doc_key in unresolved:
        key = (etype, surface)
        agg.setdefault(key, set()).add(doc_key)
        counts[key] = counts.get(key, 0) + 1
    out: list[dict] = []
    for (etype, surface), docs in sorted(agg.items(), key=lambda kv: (-counts[kv[0]], kv[0])):
        out.append(
            {
                "type": etype,
                "surface": surface,
                "status": "proposed",
                "occurrences": counts[(etype, surface)],
                "docs": sorted(docs),
            }
        )
    return out


def entities_from_resolution(
    idx: ResolutionIndex,
    resolved_node_ids: set[str],
    *,
    provenance: dict[str, list[Provenance]] | None = None,
) -> list[EntityNode]:
    """Build the EntityNodes for the entities that actually resolved in the corpus, from their seed
    identity (canonical name + synonyms) plus their accumulated provenance."""
    provenance = provenance or {}
    out: list[EntityNode] = []
    for node_id in sorted(resolved_node_ids):
        seed = idx.entities[node_id]
        out.append(
            EntityNode(
                type=seed.type,
                canonical=seed.canonical,
                canonical_name=seed.canonical_name,
                synonyms=list(seed.synonyms),
                provenance=provenance.get(node_id, []),
            )
        )
    return out
