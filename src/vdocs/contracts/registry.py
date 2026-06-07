"""The artifact registry — one place where every ArtifactContract is declared (§7.1, §11).

Stages reference artifacts by ``key``; the registry is the single lookup so a key is
defined exactly once. As stages land per phase, their produced/consumed contracts are
added here — never redeclared inline. Phase 1 seeds only the external ``vdl`` source;
bronze→gold artifacts arrive with their stages.
"""

from __future__ import annotations

from vdocs.models.artifact import ArtifactContract, Kind, Root, StorageClass


class ArtifactRegistry:
    """A name→contract map enforcing one definition per artifact key."""

    def __init__(self) -> None:
        self._by_key: dict[str, ArtifactContract] = {}

    def register(self, contract: ArtifactContract) -> ArtifactContract:
        if contract.key in self._by_key:
            raise ValueError(f"artifact {contract.key!r} already registered")
        self._by_key[contract.key] = contract
        return contract

    def get(self, key: str) -> ArtifactContract:
        return self._by_key[key]

    def all(self) -> list[ArtifactContract]:
        return list(self._by_key.values())

    def __contains__(self, key: object) -> bool:
        return key in self._by_key


# The canonical external source: the VDL website (§8, the `crawl` input). It is the one
# artifact with no producer and no lake location.
VDL = ArtifactContract(
    key="vdl",
    kind=Kind.EXTERNAL,
    storage_class=StorageClass.EXTERNAL,
    produced_by=None,
)


# The curated pattern registries (§9.6/§9.7): version-controlled repo config, never lake data,
# so it has no producer (a curated input like VDL) and resolves against `cfg.registries`. But
# unlike VDL it is a *real* fingerprintable tree — that is the point: a curation edit must change
# the input fingerprint of every consumer (`normalize`), so SKIP_IF_UNCHANGED re-runs the affected
# scopes instead of skipping on stale curation (§7.3; §8 treats a registry change like a
# contract-version bump for normalize).
REGISTRIES = ArtifactContract(
    key="registries",
    kind=Kind.TREE_TEXT,
    storage_class=StorageClass.EXTERNAL,
    produced_by=None,
    root=Root.REGISTRIES,
)


# --- inventory medallion (§4, §5.3, §8) ---
# The inventory catalog manifests are control-plane bookkeeping describing what exists
# upstream — regenerated each crawl, so STATE-class (not content-addressed evidence, not
# versioned text). They live on the inventory track's own bronze/silver, separate from the
# document medallion's content-addressed `raw` tree.
CATALOG_RAW = ArtifactContract(
    key="inventory/catalog.raw",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="crawl",
    relpath="inventory/bronze/catalog.raw.json",
)
CATALOG_ENRICHED = ArtifactContract(
    key="inventory/catalog.enriched",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="catalog",
    relpath="inventory/silver/catalog.enriched.json",
)
# inv-gold: the GOLD INVENTORY — the curated, queryable selection surface + the fetch gate.
# A portable JSON view and a queryable SQLite table, both produced by serve-inventory.
GOLD_INVENTORY = ArtifactContract(
    key="inventory/gold.json",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="serve-inventory",
    relpath="inventory/gold/inventory.json",
)
GOLD_INVENTORY_DB = ArtifactContract(
    key="inventory/gold.db",
    kind=Kind.SQLITE_TABLE,
    storage_class=StorageClass.STATE,
    produced_by="serve-inventory",
    db="inventory/gold/inventory.db",
    table="inventory",
)
RAW_TREE = ArtifactContract(
    key="bronze/raw",
    kind=Kind.TREE_ASSET_CAS,
    storage_class=StorageClass.ASSET_WRITE_ONCE,
    produced_by="fetch",
    relpath="documents/bronze/raw",
)
RAW_INDEX = ArtifactContract(
    key="bronze/raw/index.json",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="fetch",
    relpath="documents/bronze/raw/index.json",
)


# --- document silver (§5.2, §8) ---
# Per-document markdown bundles (trees of bundles); a new immutable tree per conforming stage.
# `convert` writes the first (raw conversion, pre-identity-FM) + the shared image asset CAS.
TEXT_CONVERTED = ArtifactContract(
    key="silver/text@converted",
    kind=Kind.TREE_TEXT,
    storage_class=StorageClass.TEXT_VERSIONED,
    produced_by="convert",
    relpath="documents/silver/text/01-converted",
)
ASSETS = ArtifactContract(
    key="assets",
    kind=Kind.TREE_ASSET_CAS,
    storage_class=StorageClass.ASSET_WRITE_ONCE,
    produced_by="convert",
    relpath="documents/assets",
    optional=True,  # a corpus slice with no images yields an empty asset store — still valid
)
# `discover` candidate patterns (pre-curation, §9.6): proposes registries/ updates, mutates nothing.
PATTERNS = ArtifactContract(
    key="reports/patterns",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="discover",
    relpath="reports/patterns/patterns.json",
)
# `enrich`: bundles with identity frontmatter baked in + the staged doc-meta table for `index`.
TEXT_ENRICHED = ArtifactContract(
    key="silver/text@enriched",
    kind=Kind.TREE_TEXT,
    storage_class=StorageClass.TEXT_VERSIONED,
    produced_by="enrich",
    relpath="documents/silver/text/02-enriched",
)
DOC_META_STAGED = ArtifactContract(
    key="index.db:doc_meta_staged",
    kind=Kind.SQLITE_TABLE,
    storage_class=StorageClass.STATE,
    produced_by="enrich",
    db="index.db",
    table="doc_meta_staged",
)
# `normalize`: gold-quality normalized bodies (artifacts stripped, phrases subtracted, TOC regen).
TEXT_NORMALIZED = ArtifactContract(
    key="silver/text@normalized",
    kind=Kind.TREE_TEXT,
    storage_class=StorageClass.TEXT_VERSIONED,
    produced_by="normalize",
    relpath="documents/silver/text/03-normalized",
)


# --- document gold (§4, §5.5, §6.6, §8) ---
# `consolidate`: one anchor document per version group at a stable, version-free path, with the
# ordered `history.yaml` lineage + retained prior bodies (content-addressed under gold/_shared/
# history). A TREE_TEXT over the whole gold anchor bundle — the sidecars need no separate contract.
CONSOLIDATED = ArtifactContract(
    key="gold/consolidated",
    kind=Kind.TREE_TEXT,
    storage_class=StorageClass.TEXT_VERSIONED,
    produced_by="consolidate",
    relpath="documents/gold/consolidated",
)
# `index`: the derived corpus index — documents + doc_sections (+ FTS5 over is_latest only) +
# entities, all keyed by stable IDs (§5.5/§14.6). Built fresh with `kernel.db.build_atomic`, which
# also carries forward `enrich`'s `doc_meta_staged` (index consumes + preserves it, so a forced
# re-run is self-contained). One SQLITE_TABLE contract per table `relate`/`manifest` reference.
INDEX_DOCUMENTS = ArtifactContract(
    key="index.db:documents",
    kind=Kind.SQLITE_TABLE,
    storage_class=StorageClass.STATE,
    produced_by="index",
    db="index.db",
    table="documents",
)
INDEX_SECTIONS = ArtifactContract(
    key="index.db:doc_sections",
    kind=Kind.SQLITE_TABLE,
    storage_class=StorageClass.STATE,
    produced_by="index",
    db="index.db",
    table="doc_sections",
)
INDEX_ENTITIES = ArtifactContract(
    key="index.db:entities",
    kind=Kind.SQLITE_TABLE,
    storage_class=StorageClass.STATE,
    produced_by="index",
    db="index.db",
    table="entities",
)
# the retrieval units derived from sections (§5.5, A1) — the search surface `embed` consumes.
INDEX_CHUNKS = ArtifactContract(
    key="index.db:chunks",
    kind=Kind.SQLITE_TABLE,
    storage_class=StorageClass.STATE,
    produced_by="index",
    db="index.db",
    table="chunks",
)
# `relate`: the knowledge-graph edges, appended to index.db over the entities `index` extracted
# (doc↔entity, entity↔entity, doc↔doc — §8). Added via `kernel.db.replace_table_atomic`, so it never
# touches `index`'s tables in the same file.
RELATIONS = ArtifactContract(
    key="index.db:relations",
    kind=Kind.SQLITE_TABLE,
    storage_class=StorageClass.STATE,
    produced_by="relate",
    db="index.db",
    table="relations",
)
# `manifest`: the agent front door — corpus schema/counts/ID-scheme/capabilities (§14.4).
# `vectors.db` is an OPTIONAL input (Phase 6); absent ⇒ semantic search marked unavailable (D3).
CORPUS_MANIFEST = ArtifactContract(
    key="gold/corpus-manifest.json",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="manifest",
    relpath="documents/gold/corpus-manifest.json",
)
DISCOVERY_JSON = ArtifactContract(
    key="gold/discovery.json",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="manifest",
    relpath="documents/gold/discovery.json",
)
# `manifest`: the AI corpus card (§14.7) — the always-fresh, denormalized catalog + entity index +
# the `vdocs ask` query recipe + the index.db fingerprint for staleness. `ai-manifest.json` is the
# machine rendering; `CORPUS.md` is the same content rendered for direct context loading.
AI_MANIFEST = ArtifactContract(
    key="gold/ai-manifest.json",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="manifest",
    relpath="documents/gold/ai-manifest.json",
)
CORPUS_CARD = ArtifactContract(
    key="gold/CORPUS.md",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="manifest",
    relpath="documents/gold/CORPUS.md",
)


# `embed` (Phase 6, §14.6): per-chunk embeddings + ANN index over the searchable is_latest chunks,
# in `vectors.db` (sqlite-vec). The `embedding_model` meta row (model/version/dim) is what
# `manifest` reads to flip semantic search on. produced_by="embed"; keyed by `chunk_id`.
VECTORS_DB = ArtifactContract(
    key="vectors.db:embedding_model",
    kind=Kind.SQLITE_TABLE,
    storage_class=StorageClass.STATE,
    produced_by="embed",
    db="vectors.db",
    table="embedding_model",
)


# `validate`: the sidecar-verification gate's findings report (§8 — Phase-5 slice). A FILE the gate
# always (re)writes; its recorded counts are the cross-run baseline for the §5.2 drop check.
VALIDATION_REPORT = ArtifactContract(
    key="reports/validation",
    kind=Kind.FILE,
    storage_class=StorageClass.STATE,
    produced_by="validate",
    relpath="reports/validation/verification.json",
)


def foundational_registry() -> ArtifactRegistry:
    """Build a registry seeded with the artifacts that exist before any stage runs."""
    reg = ArtifactRegistry()
    reg.register(VDL)
    return reg


def default_registry() -> ArtifactRegistry:
    """The registry of every artifact declared so far (foundational + bronze)."""
    reg = foundational_registry()
    for contract in (
        REGISTRIES,
        CATALOG_RAW,
        CATALOG_ENRICHED,
        GOLD_INVENTORY,
        GOLD_INVENTORY_DB,
        RAW_TREE,
        RAW_INDEX,
        TEXT_CONVERTED,
        ASSETS,
        PATTERNS,
        TEXT_ENRICHED,
        DOC_META_STAGED,
        TEXT_NORMALIZED,
        CONSOLIDATED,
        INDEX_DOCUMENTS,
        INDEX_SECTIONS,
        INDEX_ENTITIES,
        INDEX_CHUNKS,
        RELATIONS,
        VECTORS_DB,
        CORPUS_MANIFEST,
        DISCOVERY_JSON,
        AI_MANIFEST,
        CORPUS_CARD,
        VALIDATION_REPORT,
    ):
        reg.register(contract)
    return reg
