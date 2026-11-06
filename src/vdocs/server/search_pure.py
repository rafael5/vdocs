"""Pure helpers for the lexical search slice (§14.7) — no I/O, just query shaping.

The load-bearing piece is `read_query`: typed keywords → a **safe** FTS5 MATCH expression, by the
rules in `contracts/query/v1.json` (keyword-search proposal, fix 2), which every front door shares.
Every term is emitted as a double-quoted phrase, so stray punctuation (`*`, `:`, `^`) is never read
as FTS5 syntax; only AND, OR and NOT typed in capitals are operators.

`bm25_weights`/`bm25_expr` build the **field-weighted** ranking expression (L1.1): a doc-defining
token in a heading should outrank the same token buried in prose, so `title`/`section_path` carry
more weight than `body`. The column order here is the single source of truth and **must match the
`chunks_fts` schema in `stages/index/stage.py`** (a mismatch silently mis-weights columns).
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple

_TOKEN = re.compile(r"[A-Za-z0-9_]+")

# FTS5 column order of `chunks_fts` — MUST match the schema in `stages/index/stage.py`.
# (The first three are UNINDEXED, so their weight is inert; kept for positional correctness since
# FTS5 bm25() takes one weight per column in declaration order.)
FTS_COLUMNS: tuple[str, ...] = (
    "chunk_id", "section_id", "doc_key", "title", "doc_title", "section_path", "body",
)  # fmt: skip

# Per-column bm25 weights (higher = more influence on rank).
# L1.1 finding: weighting *section* headings (`title`/`section_path`) gives no lift here — VistA
# section titles are generic and the answer is in the body — so those stay a mild neutral prior.
# L1.2 adds `doc_title` (the document title), which carries the doc-defining token (e.g. "KAAJEE").
# Sweep on the dev golden set picked doc_title=2.5: KAAJEE 0.0→0.43, mean nDCG@10 0.387→0.469;
# heavier (≥4) over-promotes common title tokens ("VistA") and tanks `hwsc-rest`. Re-tune at L4.2.
FTS_WEIGHTS: dict[str, float] = {
    "doc_title": 2.5, "title": 2.0, "section_path": 1.5, "body": 1.0,
}  # fmt: skip


def skl_expansion_map(entities: list[tuple[str, str]]) -> dict[str, str]:
    """Build the query-expansion map from SKL entity identity rows `(canonical, canonical_name)` —
    the S3.3 `entity_skl` projection (`merge`). A distinctive identifier token (a FileMan file
    *number*) maps to its spelled-out canonical name, so a query that names an entity by its number
    expands to the precise name phrase the matching doc actually spells (`file #200` → `NEW PERSON`,
    the vocabulary-mismatch fix, S3.4). Replaces the hand-seeded `registries/glossary/expansions`
    (L1.3) with SKL-grounded data.

    Guarded so a bare common word never becomes an expansion: the key is kept only when it is a
    single alphanumeric token of ≥3 chars (`acronym_phrase_clauses` matches one `token.upper()`,
    and FTS tokenisation splits on `.`, so a decimal file number like `1.2` can never match and is
    dropped); the value only when it is a ≥2-word phrase (so `1 → FILE` / `19 → OPTION` drop while
    `200 → NEW PERSON` survives). Keyed upper-case to match the `acronym_phrase_clauses` lookup.
    """
    out: dict[str, str] = {}
    for canonical, name in entities:
        key = canonical.strip().upper()
        if len(key) >= 3 and key.isalnum() and len((name or "").split()) >= 2:
            out[key] = name
    return out


# --- fix 2: one query reader (contracts/query/v1.json) --------------------------------------------
_RUN = re.compile(r"[^\W_]+")  # letter-and-digit runs; FTS5's unicode61 index splits the same way
_ID_CHARS = frozenset("*^#.$%/")  # a word holding one of these keeps a lone single character
_OPERATORS = frozenset({"AND", "OR", "NOT"})


class QueryMatch(NamedTuple):
    """The two MATCH expressions for one query: `all` is searched first; `any` is the fallback,
    searched only when `all` matches nothing, and is `""` when there is no fallback."""

    all: str
    any: str


def read_query(text: str, expansions: dict[str, str] | None = None) -> QueryMatch:
    """Typed keywords → FTS5 MATCH expressions, by the shared rules in `contracts/query/v1.json`.

    Quoted text is one exact phrase (an open quote runs to the end); AND, OR and NOT in capitals
    are operators; every other word becomes one phrase of its letter-and-digit runs, so an
    identifier like DG*5.3*1029 stays whole. Bare terms are joined by AND. `any` OR-joins the
    terms, and exists only when no operator was typed and there are at least two terms.

    `expansions` (upper-case token → name) is today's SKL expansion (file 200 → NEW PERSON): an
    unquoted single-run term of three or more characters that is a key gains its name as an OR'd
    phrase, `("200" OR "new person")`. Fix 3's synonym table will replace it."""
    terms: list[str] = []
    joins: list[str] = []
    typed_operator = False
    pending = "AND"
    for i, piece in enumerate((text or "").split('"')):
        quoted = i % 2 == 1
        for word in [piece] if quoted else piece.split():
            if not quoted and word in _OPERATORS:
                pending, typed_operator = word, True
                continue
            term = _term(word, quoted, expansions or {})
            if term is None:
                continue
            if terms:
                joins.append(pending)
            terms.append(term)
            pending = "AND"
    if not terms:
        return QueryMatch("", "")
    all_ = terms[0] + "".join(f" {op} {t}" for op, t in zip(joins, terms[1:], strict=True))
    any_ = " OR ".join(terms) if not typed_operator and len(terms) >= 2 else ""
    return QueryMatch(all_, any_)


def _term(word: str, quoted: bool, expansions: dict[str, str]) -> str | None:
    """One word or quoted piece as a quoted FTS5 phrase, or None when it is skipped."""
    runs = _RUN.findall(word)
    if not runs:
        return None
    lone = len(runs) == 1 and len(runs[0]) == 1
    if not quoted and lone and not _ID_CHARS & set(word):
        return None  # a single-character bare word (I, a) carries no signal
    phrase = " ".join(runs)
    clause = f'"{phrase}"'
    if not quoted and len(runs) == 1 and len(phrase) >= 3:
        name = _RUN.findall(expansions.get(phrase.upper(), ""))
        if len(name) >= 2:
            clause = f'({clause} OR "{" ".join(name).lower()}")'
    return clause


def bm25_weights(
    columns: tuple[str, ...] = FTS_COLUMNS, weights: dict[str, float] | None = None
) -> list[float]:
    """One bm25 weight per column, in column order; columns absent from `weights` default to 1.0."""
    w = FTS_WEIGHTS if weights is None else weights
    return [float(w.get(c, 1.0)) for c in columns]


def bm25_expr(
    table: str, columns: tuple[str, ...] = FTS_COLUMNS, weights: dict[str, float] | None = None
) -> str:
    """The `bm25(<table>, w0, w1, …)` SQL expression with per-column weights (floats we control —
    no user input — so they are safe to inline as literals)."""
    args = ", ".join(repr(x) for x in bm25_weights(columns, weights))
    return f"bm25({table}, {args})"


# --- RR.3: a parent heading must not occupy the slot its child's content earned -------------------
# MEASURED on the production collection (2026-08-03) before this existed: 784 parent/child pairs
# whose titles are prefix-twins ("Accept Orders: Cancel a Pending Order UC_61" above "Accept Orders:
# Cancel a Pending Order"); 120 where the parent is searchable, its whole indexed text is under 300
# characters, and the child carries at least 3× more; and probing each with the child's own heading,
# **68 returned the parent AHEAD of the child** — the child as far down as rank 15 while the parent
# held rank 1. VBECS contributes 71 of the structural pairs (use-case-numbered headings).
#
# To REPRODUCE those counts: a top-level parent has an EMPTY `section_path`, so the parent key must
# be built with `(path + ' > ' + title).strip(' >')` — stripping whitespace alone yields "> Title",
# which no child's path ever matches. A first pass here did exactly that and reported 486/109
# instead of 784/120; the gap was precisely the 11 top-level parents (LA, MAG, …). The rule below
# handles them because `strip(' >')` is applied on both sides.
#
# Why it happens: bm25 normalises by field length, so a 118-character container whose entire text
# restates its child's heading looks like a perfect, dense match, while the child's 1,769 characters
# of actual procedure dilute the same terms.
#
# This REORDERS; it never excludes. Making parent lead-ins unsearchable is what made 6,779 sections
# findable (P6.1b), and a parent that matches with no child present is still the answer.
RESTATEMENT_MAX_CHARS = 300


def _twin_titles(a: str, b: str) -> bool:
    """True when one title is the other plus a suffix — the shape a numbered heading takes."""
    na, nb = _norm_title(a), _norm_title(b)
    return bool(na) and bool(nb) and (na.startswith(nb) or nb.startswith(na))


def _norm_title(t: str) -> str:
    return " ".join(_TOKEN.findall((t or "").lower()))


def demote_restating_parents(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reorder ranked hits so a restating parent follows its own child instead of preceding it.

    A hit is demoted only when all three hold: another hit is its **direct child** (that hit's
    `section_path` is this one's path plus its own title), the two titles are prefix-twins, and this
    hit's matched text is under :data:`RESTATEMENT_MAX_CHARS` — i.e. it says nothing its child does
    not. The child moves into the parent's position and the parent sits immediately behind it, so
    the pair keeps its rank while the substance leads. Order is otherwise preserved exactly."""
    by_parent_path: dict[str, list[int]] = {}
    for i, h in enumerate(hits):
        path = str(h.get("section_path") or "").strip(" >")
        by_parent_path.setdefault(path, []).append(i)

    demoted: dict[int, int] = {}  # parent index → its child's index
    for i, h in enumerate(hits):
        if int(h.get("body_len") or 0) >= RESTATEMENT_MAX_CHARS:
            continue
        own_path = str(h.get("section_path") or "").strip(" >")
        title = str(h.get("section_title") or "")
        child_path = f"{own_path} > {title}".strip(" >")
        for j in by_parent_path.get(child_path, []):
            if j != i and _twin_titles(title, str(hits[j].get("section_title") or "")):
                demoted[i] = j
                break

    if not demoted:
        return list(hits)
    children = set(demoted.values())
    out: list[dict[str, Any]] = []
    for i, h in enumerate(hits):
        if i in children and i not in demoted:
            continue  # already emitted beside its parent (or waiting to be)
        if i in demoted:
            out.append(hits[demoted[i]])  # the child takes the slot…
            out.append(h)  # …and its parent follows it
        elif i not in children:
            out.append(h)
    return out
