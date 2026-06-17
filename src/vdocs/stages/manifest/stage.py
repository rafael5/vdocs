"""The `manifest` stage — consolidated + index.db → corpus-manifest.json + discovery.json (§14.4).

The agent front door: corpus counts, the stable-ID scheme, and the capability manifest, assembled
from the derived stores. The corpus is lexical-first and offline, so the capability manifest
advertises lexical/structured/graph only — the semantic/vector path was descoped.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import structlog

from vdocs.contracts.registry import (
    AI_MANIFEST,
    CONSOLIDATED,
    CORPUS_CARD,
    CORPUS_MANIFEST,
    DISCOVERY_JSON,
    INDEX_DOCUMENTS,
    INDEX_ENTITIES,
    KNOWLEDGE_ENTITIES,
    KNOWLEDGE_RELATIONSHIPS,
    REGISTRIES,
    RELATIONS,
)
from vdocs.kernel import cas, db, knowledge_db, read_contract
from vdocs.kernel import csv as kcsv
from vdocs.kernel import registry as kregistry
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.manifest import manifest_pure as mp

log = structlog.get_logger(__name__)


class ManifestStage(Stage):
    name = "manifest"
    description = "assemble corpus-manifest.json + discovery.json + the AI corpus card"
    requires = [
        CONSOLIDATED,
        INDEX_DOCUMENTS,
        INDEX_ENTITIES,
        RELATIONS,
        REGISTRIES,
        KNOWLEDGE_ENTITIES,
        KNOWLEDGE_RELATIONSHIPS,
    ]
    produces = [CORPUS_MANIFEST, DISCOVERY_JSON, AI_MANIFEST, CORPUS_CARD]
    idempotency = Idempotency.SKIP_IF_UNCHANGED
    # v2 (S3.2): gold/glossary.md gains an Entities section projected from the SKL (knowledge.db) —
    # canonical names + aliases + documented-in cross-links; manifest now requires KNOWLEDGE_* (runs
    # after resolve). Bump re-runs so the glossary regenerates from the SKL.
    contract_ver = 2  # bump when the published manifest JSON / glossary shape changes

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        cfg = ctx.cfg
        counts = _gather_counts(cfg.index_db)
        coverage = _gather_coverage(cfg.index_db)
        generated_at = ctx.clock()

        # the read-contract version + capabilities the published DB satisfies — consumers negotiate
        # against this (ADR-0001 P2.4); coverage feeds consumer staleness/quality (P2.3).
        spec = read_contract.load(read_contract.contract_path(base=cfg.read_contract_dir))
        rc_block = {
            "version": read_contract.version(spec),
            "capabilities": read_contract.capabilities(spec),
        }
        manifest = mp.corpus_manifest(
            counts,
            tool_ver=cfg.tool_ver,
            generated_at=generated_at,
            coverage=coverage,
            read_contract=rc_block,
            characterization=_gather_characterization(cfg.index_db),
        )
        discovery = mp.discovery_descriptor(counts, tool_ver=cfg.tool_ver)
        cas.atomic_write(cfg.corpus_manifest, _dumps(manifest))
        cas.atomic_write(cfg.discovery_json, _dumps(discovery))

        # The AI corpus card (§14.7): the always-fresh catalog + entity index + query recipe an
        # agent reads to answer "based on the vdocs gold corpus, …" without re-discovering it.
        catalog = mp.build_catalog(_gather_catalog(cfg.index_db))
        entity_index = mp.build_entity_index(_gather_entity_rows(cfg.index_db))
        card = mp.ai_manifest(
            counts,
            catalog,
            entity_index,
            tool_ver=cfg.tool_ver,
            generated_at=generated_at,
            index_fingerprint=_index_fingerprint(cfg.index_db),
        )
        cas.atomic_write(cfg.ai_manifest, _dumps(card))
        cas.atomic_write(cfg.corpus_card, (mp.corpus_card(card)).encode("utf-8"))

        # B1 (§9.6/§9.7): materialise the curated boilerplate canonical copies so `normalize`'s
        # `_shared/boilerplate/<id>.md` REFERENCE links resolve (single-sourced, de-duplicated).
        shared = mp.shared_boilerplate_files(_load_boilerplate_entries(cfg))
        bp_dir = cfg.gold_shared / "boilerplate"
        for name, text in shared.items():
            cas.atomic_write(bp_dir / name, text.encode("utf-8"))

        # `gold/glossary.md`: an **Entities** section projected from the SKL (canonical names +
        # aliases + documented-in cross-links, S3.2) then the **Acronyms** section harvested from
        # the per-doc acronym tables (B2, §9.6 PROMOTE). Both generated, no hand-maintained list.
        skl_entities = knowledge_db.read_entities(cfg.knowledge_db)
        documented_in = mp.documented_in_map(knowledge_db.read_relationships(cfg.knowledge_db))
        glossary = mp.build_glossary(
            _harvest_glossary_pairs(cfg),
            skl_entities=skl_entities,
            documented_in=documented_in,
        )
        cas.atomic_write(cfg.glossary, glossary.encode("utf-8"))

        return RunResult(
            counts={
                "documents": counts["documents"],
                "version_groups": counts["version_groups"],
                "entities": counts["entities"],
                "relations": counts["relations"],
                "catalog_docs": len(catalog),
                "shared_boilerplate": len(shared),
                "glossary_terms": glossary.count("\n**"),
            }
        )


def _harvest_glossary_pairs(cfg) -> list:  # type: ignore[no-untyped-def]
    """Scan every `tables/*.csv` sidecar under silver-normalized and collect `(term, definition)`
    pairs from those that are acronym glossaries (B2). Non-glossary tables yield none."""
    pairs: list = []
    for csv_path in cfg.silver_normalized.rglob("tables/*.csv"):
        pairs.extend(mp.acronym_table_pairs(kcsv.read_rows(csv_path)))
    return pairs


def _load_boilerplate_entries(cfg) -> list:  # type: ignore[no-untyped-def]
    """The curated boilerplate registry rows (empty if absent) — source of the canonical copies."""
    data = kregistry.load_mapping(
        cfg.registries / "boilerplate" / "boilerplate.yaml", missing_ok=True
    )
    return data.get("boilerplate") or []


def _dumps(obj) -> bytes:  # type: ignore[no-untyped-def]
    """Deterministic JSON bytes (sorted keys) so a no-op re-run is byte-identical (content-skip)."""
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _gather_counts(index_db):  # type: ignore[no-untyped-def]
    """Corpus counts off the derived index — documents/sections/entities/relations + breakdowns."""
    conn = db.connect(index_db, read_only=True)
    try:
        one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "documents": one("SELECT count(*) FROM documents"),
            "documents_latest": one("SELECT count(*) FROM documents WHERE is_latest=1"),
            # each version group has exactly one is_latest anchor → latest count == group count
            "version_groups": one("SELECT count(*) FROM documents WHERE is_latest=1"),
            "sections": one("SELECT count(*) FROM doc_sections"),
            # the search surface is the chunks table (containers + hollow excluded, oversized split)
            "sections_searchable": one("SELECT count(*) FROM chunks"),
            "entities": one("SELECT count(*) FROM entities"),
            "entities_by_type": dict(
                conn.execute("SELECT type, count(*) FROM entities GROUP BY type").fetchall()
            ),
            "relations": one("SELECT count(*) FROM relations"),
            "relations_by_type": dict(
                conn.execute("SELECT rel, count(*) FROM relations GROUP BY rel").fetchall()
            ),
        }
    finally:
        conn.close()


def _gather_coverage(index_db):  # type: ignore[no-untyped-def]
    """Per-facet coverage over the is_latest gold (ADR-0001 P2.3): populated/total/pct + distinct
    value count. Lets a consumer surface staleness/quality (e.g. '12% lack function_category')."""
    conn = db.connect(index_db, read_only=True)
    try:
        total = conn.execute("SELECT count(*) FROM documents WHERE is_latest=1").fetchone()[0]
        have = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
        fields = ("function_category", "doc_type", "section", "app_user", "doc_user", "pkg_ns")
        cov: dict[str, dict] = {}
        for f in (f for f in fields if f in have):  # defensive: cover only columns that exist
            pop = conn.execute(
                f"SELECT count(*) FROM documents WHERE is_latest=1 AND {f}<>''"  # noqa: S608
            ).fetchone()[0]
            distinct = conn.execute(
                f"SELECT count(DISTINCT {f}) FROM documents WHERE is_latest=1 AND {f}<>''"  # noqa: S608
            ).fetchone()[0]
            cov[f] = {
                "populated": pop,
                "total": total,
                "pct": round(100 * pop / total, 1) if total else 0.0,
                "distinct": distinct,
            }
        return cov
    finally:
        conn.close()


def _gather_characterization(index_db):  # type: ignore[no-untyped-def]
    """Per-facet distinct-value distribution over is_latest gold (ADR-0001 P2.5) — the data-shape
    snapshot. Covers the vocab-gated facets; defensive over which columns exist."""
    conn = db.connect(index_db, read_only=True)
    try:
        have = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
        fields = tuple(
            f
            for f in ("function_category", "doc_type", "section", "app_user", "doc_user")
            if f in have
        )
        if not fields:
            return {}
        rows = [
            dict(r)
            for r in conn.execute(
                f"SELECT {', '.join(fields)} FROM documents WHERE is_latest=1"  # noqa: S608
            ).fetchall()
        ]
        return mp.facet_distribution(rows, fields)
    finally:
        conn.close()


def _gather_catalog(index_db):  # type: ignore[no-untyped-def]
    """The `is_latest` anchor documents (catalog rows for the AI card), ordered for stable order."""
    conn = db.connect(index_db, read_only=True)
    try:
        rows = conn.execute(
            "SELECT doc_key, doc_id, title, app_code, doc_type, pkg_ns, patch_id, version, "
            "section_count, word_count FROM documents WHERE is_latest=1 "
            "ORDER BY app_code, title, doc_key"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _gather_entity_rows(index_db):  # type: ignore[no-untyped-def]
    """Every entity (type, canonical name, mention count) — grouped/trimmed by the pure builder."""
    conn = db.connect(index_db, read_only=True)
    try:
        rows = conn.execute("SELECT type, canonical_name, mention_count FROM entities").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _index_fingerprint(index_db: Path) -> str:
    """A content fingerprint of `index.db` (streamed sha256) — the staleness stamp the AI card
    records so a consumer can tell whether the card still matches the live index."""
    h = hashlib.sha256()
    with index_db.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
