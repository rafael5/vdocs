"""Pure cores of the `merge` stage — SKL (`knowledge.db`) → entity-keyed `index.db` (SKL S3.3).

`merge` is the post-`resolve` join (D-S3.3a): it augments `index.db` from the SKL **additively**
(D-S3.3b), reconciling the two id schemes and projecting the SKL surfaces into `index.db` so the
shipped one file carries entity identity. Like `relate`, it adds only *derived* tables — no new
extraction. Every function here is pure: SKL nodes + index rows in, sorted unique tuples out; the
thin `stage.py` driver does the I/O.

* **reconcile** — `index` keys an entity `fileman_file:200` (colon, its own recognition pass); the
  SKL keys it `fileman_file/200` (slash). The two reconcile on `(type, canonical)`: the index id is
  `f"{type}:{canonical}"`, so an SKL entity maps to the index row of the same `(type, canonical)`
  when that row exists. Carries the SKL id + identity onto the index side.
* **synonym_rows** — every surface (canonical name + synonyms) per SKL entity — the synonym catalog
  the shipped index carries (and the seed the S3.4 search expansion derives from).
* **tag_chunks** — chunk → entity tags: a chunk is *about* an entity when one of its
  **distinctive** surfaces occurs in the chunk text. Distinctive-only is the load-bearing safety
  rule — the real SKL has common-word names (`fileman_file/1` = "FILE", `/19` = "OPTION") that would
  tag the whole corpus if matched bare.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

from vdocs.kernel.text import bounded_branch

# (entity_id, node_id, type, canonical, canonical_name) — the colon↔slash reconciliation row.
EntitySklRow = tuple[str, str, str, str, str]
# (node_id, surface, kind) — kind ∈ {canonical_name, synonym}.
SynonymRow = tuple[str, str, str]
# (chunk_id, node_id) — a chunk-level entity tag.
ChunkTag = tuple[str, str]


@dataclass(frozen=True)
class SklEntity:
    """One SKL entity, as `merge` consumes it (a thin read of `knowledge.db:entities`)."""

    node_id: str
    type: str
    canonical: str
    canonical_name: str
    synonyms: tuple[str, ...]


def index_entity_id(etype: str, canonical: str) -> str:
    """The colon-style id `index` keys entities by — MUST mirror `stages/index/stage.py`
    (`eid = f"{etype}:{canon}"`). The single point the two schemes are reconciled."""
    return f"{etype}:{canonical}"


def reconcile(entities: list[SklEntity], index_entity_ids: set[str]) -> list[EntitySklRow]:
    """The colon↔slash join map: one row per SKL entity whose `(type, canonical)` is also an `index`
    entity (so the SKL id attaches to a real index row). SKL entities absent from `index` are
    dropped — `merge` augments where both DBs agree, never inventing index rows (friction #3)."""
    rows = [
        (index_entity_id(e.type, e.canonical), e.node_id, e.type, e.canonical, e.canonical_name)
        for e in entities
        if index_entity_id(e.type, e.canonical) in index_entity_ids
    ]
    return sorted(rows)


def synonym_rows(entities: list[SklEntity]) -> list[SynonymRow]:
    """Every surface of every SKL entity: the canonical name (kind `canonical_name`) then each
    distinct synonym (kind `synonym`). De-duplicated per entity (the SKL `synonyms` list usually
    repeats the canonical name); sorted, stable."""
    rows: list[SynonymRow] = []
    for e in entities:
        seen: set[str] = set()
        if e.canonical_name:
            rows.append((e.node_id, e.canonical_name, "canonical_name"))
            seen.add(e.canonical_name)
        for s in e.synonyms:
            if s and s not in seen:
                rows.append((e.node_id, s, "synonym"))
                seen.add(s)
    return sorted(rows)


def is_distinctive(surface: str) -> bool:
    """True when a surface is specific enough to tag/expand on — never a bare common word. A surface
    is distinctive iff it carries a digit (a file number / numbered global), is a global (`^…`), or
    is multi-word. So "200"/"^VA(200,"/"NEW PERSON" qualify; "FILE"/"OPTION" do not."""
    s = surface.strip()
    if not s:
        return False
    if any(ch.isdigit() for ch in s) or s.startswith("^"):
        return True
    return len(s.split()) >= 2


def distinctive_surfaces(entity: SklEntity) -> list[str]:
    """The entity's tag-worthy surfaces (canonical name + synonyms, distinctive only), de-duped in
    first-seen order. Empty when the entity has only bare common-word surfaces."""
    out: list[str] = []
    seen: set[str] = set()
    for s in (entity.canonical_name, *entity.synonyms):
        if s and s not in seen and is_distinctive(s):
            out.append(s)
            seen.add(s)
    return out


def _norm(surface: str) -> str:
    """Match key: upper-cased, internal whitespace collapsed (globals keep their punctuation)."""
    return re.sub(r"\s+", " ", surface.strip()).upper()


def tag_chunks(chunks: list[tuple[str, str]], entities: list[SklEntity]) -> list[ChunkTag]:
    """`(chunk_id, node_id)` tags: a chunk is tagged with an entity when any of that entity's
    *distinctive* surfaces occurs in the chunk text (case-insensitive, alnum-boundary-guarded).
    `chunks` is `(chunk_id, text)`. Sorted, de-duplicated (one tag per chunk/entity however many
    surface hits). Non-matching chunks (incl. non-DI chunks) simply get no tags (friction #3)."""
    surf_to_nodes: dict[str, set[str]] = {}
    for e in entities:
        for s in distinctive_surfaces(e):
            surf_to_nodes.setdefault(_norm(s), set()).add(e.node_id)
    if not surf_to_nodes:
        return []
    # longest-first so the most specific surface anchors the alternation (compile once).
    branches = [bounded_branch(s) for s in sorted(surf_to_nodes, key=len, reverse=True)]
    rx = re.compile("|".join(branches), re.IGNORECASE)

    out: set[ChunkTag] = set()
    for chunk_id, text in chunks:
        for m in rx.finditer(text):
            for node_id in surf_to_nodes[_norm(m.group(0))]:
                out.add((chunk_id, node_id))
    return sorted(out)


# --- search synonyms (keyword-search proposal, fix 3) ---------------------------------------------
# One table of term → alternatives that every search front door applies (rules and cases:
# contracts/query/v1.json, `synonyms`). Written from the hand-written registry
# (registries/search-synonyms.yaml), the documents' application codes and namespaces with their
# names, and the SKL's file names (file 200 → NEW PERSON), so there is one expansion mechanism.
# Measured 2026-11-06 (reports/mcp-review-synonyms.json): a name expanding to its codes and a
# product abbreviation expanding to its name each cost a judged question its place and found
# nothing the code → name rows did not, so neither is written.

# (seq, term, alternative, match_case, source); match_case 1 = the term matches only as written.
SearchSynonymRow = tuple[int, str, str, int, str]

_OPERATOR_WORDS = frozenset({"and", "or", "not"})
_RUNS = re.compile(r"[^\W_]+")


@dataclass(frozen=True)
class AppNames:
    """One application of the latest corpus, as the documents (and package master) name it."""

    code: str
    name: str  # documents.app_name, raw ("Pharmacy: Automatic Replenish / Ward Stock")
    namespaces: tuple[str, ...]


@dataclass(frozen=True)
class HandSynonyms:
    """The parsed registry: package code → plain names; Kernel parts; judged terms."""

    packages: dict[str, tuple[str, ...]]
    kernel_parts: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]  # (names, alternatives)
    terms: tuple[tuple[str, tuple[str, ...], int], ...]  # (term, alternatives, match_case)


def parse_search_synonyms(text: str) -> HandSynonyms:
    """Parse `registries/search-synonyms.yaml`. A term without the judged query it fixes is refused:
    hand-written terms go in only with a judged question (fix 4)."""
    raw = yaml.safe_load(text) or {}
    packages = {str(k): tuple(v or ()) for k, v in (raw.get("packages") or {}).items()}
    parts = tuple(
        (tuple(p["names"]), tuple(p["alternatives"])) for p in raw.get("kernel_parts") or ()
    )
    terms = []
    for t in raw.get("terms") or ():
        if not t.get("fixes"):
            raise ValueError(f"search-synonyms: term {t.get('term')!r} names no judged query")
        terms.append((str(t["term"]), tuple(t["alternatives"]), int(t.get("match_case", 0))))
    return HandSynonyms(packages, parts, tuple(terms))


def clean_app_name(name: str) -> str:
    """'Pharmacy: Automatic Replenish / Ward Stock' → 'Automatic Replenish / Ward Stock';
    'Visual Impairment Service Team (VIST)' → 'Visual Impairment Service Team'."""
    name = re.sub(r"\s*\([^)]*\)", "", name or "")
    return re.sub(r"^[^:]{1,20}:\s*", "", name).strip()


def search_synonym_rows(
    apps: list[AppNames], hand: HandSynonyms, skl_names: list[tuple[str, str]]
) -> tuple[list[SearchSynonymRow], list[str]]:
    """The search synonym table, in order, and the registry's package codes that have no documents
    (reported, never guessed). `skl_names` is the SKL's `(canonical, canonical_name)` pairs."""
    rows: list[SearchSynonymRow] = []
    seen: set[tuple[str, int, str]] = set()

    def add(term: str, alternatives: list[str], match_case: int, source: str) -> None:
        key = _fold(term)
        if len(key) < 2 or key in _OPERATOR_WORDS:
            return
        for alt in alternatives:
            folded = _fold(alt)
            if len(folded) < 2 or folded in _OPERATOR_WORDS or folded == key:
                continue
            if (key, match_case, folded) not in seen:
                seen.add((key, match_case, folded))
                rows.append((len(rows), term, alt, match_case, source))

    by_code = {a.code: a for a in apps}
    missing = sorted(c for c in hand.packages if c not in by_code)
    for code, names in hand.packages.items():
        if code in by_code:
            for n in names:
                add(n, _targets(by_code[code]), 0, "package_name")
    for names, alternatives in hand.kernel_parts:
        for n in names:
            add(n, list(alternatives), 0, "kernel_part")
    for a in apps:
        for code in dict.fromkeys((a.code, *a.namespaces)):
            add(code, [clean_app_name(a.name)], 1, "application")
    for term, alternatives, match_case in hand.terms:
        add(term, list(alternatives), match_case, "term")
    for canonical, name in skl_names:
        key = canonical.strip()
        if len(key) >= 3 and key.isalnum() and len((name or "").split()) >= 2:
            add(key, [name], 0, "skl")
    return rows, missing


def _targets(app: AppNames) -> list[str]:
    """What a plain-English package name expands to: the package name, code and namespaces."""
    return list(dict.fromkeys((clean_app_name(app.name), app.code, *app.namespaces)))


def _fold(text: str) -> str:
    return " ".join(_RUNS.findall(text)).lower()
