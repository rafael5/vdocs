"""The `resolve` stage — consolidated gold + registries + DD seed → gold/knowledge.db (SKL §6, S2).

`resolve` is the named DAG layer that builds the Semantic Knowledge Layer: it runs after
`consolidate` and emits `knowledge.db` (the SKL's own gold store, Q4). It promotes today's scattered
entity work into one governed transform — **recognize → resolve → classify → relate → verify** —
each a pure core in `resolve_pure` (the recognizer is *shared* with `index`, not forked).

For the S2 pilot it resolves the **FileMan (DI) gold**: every surface of a FileMan file
(`file #200`, `the NEW PERSON file`, `^VA(200,`) resolves to one canonical entity id
(`fileman_file/200`), seeded from the authoritative live-DD export (`registries/entities/
dd-seed.di.yaml`, Q6). Recognized-but-unresolved mentions are written to a propose-only curator
queue (§10) — **never** asserted into `knowledge.db`. Every asserted node carries provenance + a
`verification` block at status `asserted` (Q2 defers live verification to S5).
"""

from __future__ import annotations

import json
import re

import structlog

from vdocs.contracts.registry import (
    CONSOLIDATED,
    KNOWLEDGE_ENTITIES,
    KNOWLEDGE_RELATIONSHIPS,
    KNOWLEDGE_TERMS,
    REGISTRIES,
)
from vdocs.kernel import frontmatter, knowledge_db, termbase
from vdocs.kernel import products as kproducts
from vdocs.kernel import registry as kregistry
from vdocs.models.knowledge import Provenance
from vdocs.models.stage import Idempotency, PostflightResult, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.index import entities_pure as ent
from vdocs.stages.resolve import resolve_pure as rp

log = structlog.get_logger(__name__)

# The S2 pilot package: the FileMan gold lives under `gold/consolidated/DI/` (proposal §12 S2).
PILOT_APP = "DI"


class ResolveStage(Stage):
    name = "resolve"
    description = "build the SKL (knowledge.db): resolve FileMan gold entities/terms/relationships"
    requires = [CONSOLIDATED, REGISTRIES]
    produces = [KNOWLEDGE_ENTITIES, KNOWLEDGE_TERMS, KNOWLEDGE_RELATIONSHIPS]
    idempotency = Idempotency.SKIP_IF_UNCHANGED
    contract_ver = 1  # bump when the knowledge.db node shape changes (re-runs downstream consumers)

    def __init__(self) -> None:
        # the verify invariant (every node asserted) — checked in deep_gate
        self._asserted_ok = True

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        cfg = ctx.cfg
        rules = _load_rules(cfg)
        idx = rp.resolution_index(_load_dd_seed(cfg))
        registered = _load_edge_types(cfg)
        products = kproducts.load_products(cfg.registries)
        english = termbase.load_english_words(cfg.registries)
        term_re = _term_regex(products)

        # accumulators across the pilot's gold bodies
        entity_prov: dict[str, list[Provenance]] = {}
        resolved_by_doc: dict[str, set[str]] = {}
        edge_prov: dict[str, list[Provenance]] = {}
        term_appears: set[str] = set()
        term_prov: dict[str, list[Provenance]] = {}
        unresolved: list[tuple[str, str, str]] = []

        pilot_root = cfg.gold_consolidated / PILOT_APP
        for body_path in sorted(pilot_root.rglob("body.md")):
            doc_key = body_path.parent.relative_to(cfg.gold_consolidated).as_posix()
            meta, body = frontmatter.parse(body_path.read_text(encoding="utf-8"))
            sha = str(meta.get("source_sha256", ""))
            prov = Provenance(source_sha256=sha, doc=doc_key)

            result = rp.resolve(body, rules, idx)
            for node_id in result.resolved:
                entity_prov.setdefault(node_id, []).append(prov)
                resolved_by_doc.setdefault(doc_key, set()).add(node_id)
                edge_prov.setdefault(f"{node_id}|{doc_key}", []).append(prov)
            for etype, surface in result.unresolved:
                unresolved.append((etype, surface, doc_key))

            if term_re is not None:
                for m in term_re.finditer(body):
                    surface = _canonical_term(products, m.group(0))
                    term_appears.add(surface)
                    term_prov.setdefault(surface, []).append(prov)

        # --- assemble the SKL nodes (S2.2/S2.3) ---
        resolved_ids = {nid for ids in resolved_by_doc.values() for nid in ids}
        entities = rp.entities_from_resolution(idx, resolved_ids, provenance=entity_prov)
        terms = rp.classify_terms(
            products, english_words=english, appears=term_appears, provenance=term_prov
        )
        candidate_edges = rp.documented_in_edges(resolved_by_doc, provenance=edge_prov)
        edges, rejected = rp.partition_edges(candidate_edges, registered)

        # verify (S2.3, Q2): every node asserted — corpus provenance, no live gating in S2
        self._asserted_ok = rp.all_asserted(entities, terms, edges)

        knowledge_db.write_atomic(
            cfg.knowledge_db, entities=entities, terms=terms, relationships=edges
        )
        _write_proposals(cfg, rp.build_proposals(unresolved))

        warnings: list[str] = []
        if rejected:
            warnings.append(
                f"{len(rejected)} edge(s) dropped — unregistered rel type(s) "
                f"{sorted({e.rel for e in rejected})} (gated by edge-types.yaml, Q3)"
            )
        return RunResult(
            counts={
                "entities": len(entities),
                "terms": len(terms),
                "relationships": len(edges),
                "rejected_edges": len(rejected),
                "proposals": len(unresolved),
            },
            warnings=warnings,
        )

    def deep_gate(self, ctx: StageContext) -> PostflightResult:
        """Fail if the verify invariant broke — a node reached the store without an `asserted`
        verification block (Q2 / §10: no node escapes provenance + lifecycle)."""
        if not self._asserted_ok:
            return PostflightResult(ok=False, reason="a knowledge.db node is not asserted (verify)")
        return PostflightResult(ok=True)


def _load_dd_seed(cfg) -> list[dict]:  # type: ignore[no-untyped-def]
    """The FileMan DD spine (`registries/entities/dd-seed.di.yaml` `files`). Absent → empty (no
    resolution; the store is still well-formed)."""
    data = kregistry.load_mapping(cfg.registries / "entities" / "dd-seed.di.yaml", missing_ok=True)
    return list(data.get("files") or [])


def _load_edge_types(cfg) -> frozenset[str]:  # type: ignore[no-untyped-def]
    """The closed registered `rel` set (`registries/relationships/edge-types.yaml`, Q3)."""
    data = kregistry.load_mapping(
        cfg.registries / "relationships" / "edge-types.yaml", missing_ok=True
    )
    return frozenset(str(e["rel"]) for e in (data.get("edge_types") or []) if e.get("rel"))


def _load_rules(cfg) -> list[ent.EntityRule]:  # type: ignore[no-untyped-def]
    """The shared registry-driven recognizers (same source `index` compiles — no fork)."""
    data = kregistry.load_mapping(cfg.registries / "entities" / "entities.yaml", missing_ok=True)
    return ent.compile_rules(data.get("entities") or [])


def _term_regex(products: dict[str, list[dict]]) -> re.Pattern[str] | None:
    """A whole-word alternation over the curated product/brand abbreviations — used to detect which
    terms *appear* in the gold (the `classify` input). None when no products are configured."""
    abbrs = sorted({str(e["abbr"]) for entries in products.values() for e in entries}, key=len,
                   reverse=True)  # fmt: skip
    if not abbrs:
        return None
    alt = "|".join(re.escape(a) for a in abbrs)
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alt})(?![A-Za-z0-9])")


def _canonical_term(products: dict[str, list[dict]], matched: str) -> str:
    """Map a matched surface back to its canonical abbr (case-insensitive), so casing variants
    (`vista`/`VISTA`) classify under the one canonical Term node."""
    for entries in products.values():
        for e in entries:
            if str(e["abbr"]).lower() == matched.lower():
                return str(e["abbr"])
    return matched


def _write_proposals(cfg, proposals: list[dict]) -> None:  # type: ignore[no-untyped-def]
    """Write the propose-only curator queue (§10) — the reproducible proposal→review artifact."""
    cfg.knowledge_proposals.parent.mkdir(parents=True, exist_ok=True)
    cfg.knowledge_proposals.write_text(
        json.dumps({"proposals": proposals}, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
