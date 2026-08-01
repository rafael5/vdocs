"""Pure acquisition-chain reconciliation — the join no gate performed (P1.2, audit R-3).

Every seam from the admission gate to the silver tree *self*-reports: ``fetch`` counts what it
downloaded, ``convert`` counts what it converted, ``doctor`` inspects only ``index.db``. Nothing
ever **joined** them, so a document could be recorded ``fetched``, be missing from
``raw/index.json``, have no bundle anywhere downstream, and raise a finding nowhere — which is
exactly what six documents did on the live lake (the sha-keyed index collapse, [S4]).

This module is that join, as one pure function over five ``doc_id`` sets:

    admitted ⊇ fetched == raw_index == converted == normalized

Each disagreement is reported **per doc_id** (not as a count): "the chain lost 6" is a fact about
arithmetic, "the chain lost ``PSJ:psj_5_tm``" is a fact you can act on. The driver
(``validate/stage.py``) builds the sets from the real artifacts and blocks on any finding.
"""

from __future__ import annotations

from dataclasses import dataclass

#: A doc reached the corpus but the admission gate no longer admits it (a withdrawn/renamed
#: document, or a policy edit that narrowed scope): the corpus over-states the live library.
FETCHED_NOT_ADMITTED = "fetched-not-admitted"
#: Recorded ``fetched`` but absent from ``raw/index.json`` — the measured six. No bundle is ever
#: produced, yet ``inventory --status`` reports the document as present.
FETCHED_NOT_INDEXED = "fetched-not-indexed"
#: In the index with no ``fetched`` acquisition to account for it (a hand-edited or stale file).
INDEXED_NOT_FETCHED = "indexed-not-fetched"
#: In the index but no ``01-converted`` bundle — conversion dropped the document.
INDEXED_NOT_CONVERTED = "indexed-not-converted"
#: Converted but not normalized — the silver trees disagree (normalize dropped it).
CONVERTED_NOT_NORMALIZED = "converted-not-normalized"
#: Normalized with no converted source — a ghost bundle a prune failed to remove.
NORMALIZED_NOT_CONVERTED = "normalized-not-converted"


@dataclass(frozen=True, order=True)
class ChainFinding:
    """One broken link, named by the document it lost."""

    kind: str
    doc_id: str
    detail: str


_DETAIL = {
    FETCHED_NOT_ADMITTED: "fetched but no longer an admitted target (withdrawn, or policy "
    "narrowed) — reconcile: re-run fetch, then convert",
    FETCHED_NOT_INDEXED: "recorded fetched but absent from raw/index.json — no bundle will be "
    "produced; re-run: vdocs fetch --all",
    INDEXED_NOT_FETCHED: "in raw/index.json with no fetched acquisition — the index does not "
    "match state.db; re-run: vdocs fetch --all",
    INDEXED_NOT_CONVERTED: "in raw/index.json but no converted bundle — conversion dropped it; "
    "check the convert run's errors",
    CONVERTED_NOT_NORMALIZED: "converted but not normalized — check the normalize run's errors",
    NORMALIZED_NOT_CONVERTED: "normalized with no converted source — a stale bundle survived "
    "pruning; re-run convert",
}


def reconcile_chain(
    *,
    admitted: set[str],
    fetched: set[str],
    raw_index: set[str],
    converted: set[str],
    normalized: set[str],
) -> list[ChainFinding]:
    """Every broken link in the acquisition chain, one finding per ``doc_id`` (sorted).

    All five arguments are ``doc_id`` sets: the gate-admitted targets, the ``fetched``
    acquisitions, the ``raw/index.json`` keys, and the two silver bundle trees (mapped back to
    doc_ids through the index). An empty result means the chain is intact end-to-end — the
    guarantee no single stage's counts can give.
    """
    broken: list[ChainFinding] = []
    for kind, missing in (
        (FETCHED_NOT_ADMITTED, fetched - admitted),
        (FETCHED_NOT_INDEXED, fetched - raw_index),
        (INDEXED_NOT_FETCHED, raw_index - fetched),
        (INDEXED_NOT_CONVERTED, raw_index - converted),
        (CONVERTED_NOT_NORMALIZED, converted - normalized),
        (NORMALIZED_NOT_CONVERTED, normalized - converted),
    ):
        broken.extend(ChainFinding(kind, doc_id, _DETAIL[kind]) for doc_id in missing)
    return sorted(broken)


__all__ = [
    "CONVERTED_NOT_NORMALIZED",
    "FETCHED_NOT_ADMITTED",
    "FETCHED_NOT_INDEXED",
    "INDEXED_NOT_CONVERTED",
    "INDEXED_NOT_FETCHED",
    "NORMALIZED_NOT_CONVERTED",
    "ChainFinding",
    "reconcile_chain",
]
