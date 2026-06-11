"""The `index` stage — text@normalized (+ consolidated grouping) → index.db (§5.5, §14.6).

Builds the derived corpus index: `documents`, `doc_sections` (ALL headings = the anchor/structure
map, each carrying `is_latest`/`kind`/`searchable`/`section_path`), `chunks` (the retrieval units
derived from sections — containers + hollow excluded, oversized split into `#pN`; §5.5/§14.6)
**+ FTS5 over the `is_latest` searchable chunks — the search surface**, and the
`entities` / `entity_mentions` tables from a generic, registry-driven recognition pass
(`entities_pure`, no patterns in code). Every unit is keyed by a **stable id**: the section id is
`refs.yaml`'s `<doc_key>/<slug>` (the URL-safe bundle-path form `normalize` already emits and MCP
URIs use); `documents.doc_id` keeps the inventory join key `app_code:doc_slug` alongside (§5.5, D4).

`is_latest` is taken from `consolidated` (the version-group rollup): the anchor — the latest member
of each group — is current; prior versions are evidence, indexed but **excluded** from FTS and
entity extraction so one query never returns competing patch versions (§14.6).

Built with `kernel.db.build_atomic` (the hardened temp+rename DB build). Because a fresh rebuild
would otherwise wipe `enrich`'s `doc_meta_staged` (it lives in this same file and `index` *consumes*
it), the build **carries that table forward verbatim** — so the rebuilt store is self-contained and
a forced re-run still finds its input. `index` therefore `requires` `doc_meta_staged` explicitly
(the real dependency, made a contract edge rather than a hidden read).
"""

from __future__ import annotations

import sqlite3
from collections import Counter

import structlog

from vdocs.contracts.registry import (
    CONSOLIDATED,
    DOC_META_STAGED,
    INDEX_CHUNKS,
    INDEX_DOCUMENTS,
    INDEX_ENTITIES,
    INDEX_SECTIONS,
    TEXT_NORMALIZED,
)
from vdocs.kernel import db, frontmatter, personas, titles
from vdocs.kernel import products as kproducts
from vdocs.kernel import registry as kregistry
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.enrich import enrich_pure as ep
from vdocs.stages.index import entities_pure as ent
from vdocs.stages.index import index_pure as ip

log = structlog.get_logger(__name__)

_SCHEMA = """
CREATE TABLE documents (
  doc_key       TEXT PRIMARY KEY,
  doc_id        TEXT NOT NULL,
  app_code      TEXT, doc_type TEXT, section TEXT, pkg_ns TEXT,
  version       TEXT, patch_id TEXT, anchor_key TEXT, group_key TEXT,
  title         TEXT, title_source TEXT, app_name TEXT,
  product_abbr  TEXT, product_full TEXT, doc_label TEXT,
  app_user      TEXT, doc_user TEXT, software_class TEXT, function_category TEXT,
  word_count    INTEGER, section_count INTEGER, is_latest INTEGER NOT NULL,
  template_id   TEXT, source_sha256 TEXT, source_url TEXT,
  published     TEXT, pub_year TEXT
);
CREATE TABLE doc_sections (
  section_id TEXT PRIMARY KEY,
  doc_key    TEXT NOT NULL REFERENCES documents(doc_key),
  slug TEXT, title TEXT, level INTEGER, toc_level INTEGER, is_latest INTEGER NOT NULL,
  kind TEXT NOT NULL, searchable INTEGER NOT NULL, section_path TEXT
);
CREATE TABLE chunks (
  chunk_id   TEXT PRIMARY KEY,
  section_id TEXT NOT NULL REFERENCES doc_sections(section_id),
  doc_key    TEXT NOT NULL REFERENCES documents(doc_key),
  part       INTEGER NOT NULL,
  text       TEXT NOT NULL
);
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  chunk_id UNINDEXED, section_id UNINDEXED, doc_key UNINDEXED, title, doc_title, section_path, body
);
CREATE TABLE entities (
  entity_id TEXT PRIMARY KEY, type TEXT, canonical_name TEXT, mention_count INTEGER
);
CREATE TABLE entity_mentions (
  entity_id TEXT NOT NULL REFERENCES entities(entity_id),
  doc_key   TEXT NOT NULL REFERENCES documents(doc_key),
  section_id TEXT NOT NULL
);
-- facet indices (LF.5): instant narrow-by-facet for focused search (perf only, no shape change)
CREATE INDEX idx_documents_facets ON documents(is_latest, doc_type, app_code, pkg_ns);
CREATE INDEX idx_documents_persona ON documents(is_latest, app_user, doc_user);
CREATE INDEX idx_entity_mentions_eid ON entity_mentions(entity_id);
CREATE VIEW quality AS
  SELECT d.doc_key, d.doc_id, d.is_latest, d.word_count, d.section_count,
         (SELECT count(*) FROM entity_mentions em WHERE em.doc_key = d.doc_key) AS entity_mentions
  FROM documents d;
"""

_DOC_COLUMNS = (
    "doc_key", "doc_id", "app_code", "doc_type", "section", "pkg_ns", "version", "patch_id",
    "anchor_key", "group_key", "title", "title_source", "app_name",
    "product_abbr", "product_full", "doc_label",
    "app_user", "doc_user", "software_class", "function_category",
    "word_count", "section_count", "is_latest", "template_id", "source_sha256", "source_url",
    "published", "pub_year",
)  # fmt: skip


class IndexStage(Stage):
    name = "index"
    description = "build index.db: documents, sections (anchors), chunks+FTS5 (search), entities"
    requires = [TEXT_NORMALIZED, CONSOLIDATED, DOC_META_STAGED]
    produces = [INDEX_DOCUMENTS, INDEX_SECTIONS, INDEX_CHUNKS, INDEX_ENTITIES]
    idempotency = Idempotency.SKIP_IF_UNCHANGED
    # v2 (L1.2): chunks_fts gained a `doc_title` column (the doc-defining-token search fix).
    # v3 (§7 bake): documents gained app_user/doc_user/software_class/function_category columns +
    # the persona facet index. v4 (title de-noise): documents gained `title_source` (raw title) +
    # `app_name`, and `title` is now the version/patch-stripped display name (kernel.titles).
    # v5 (abbreviation-first titles): documents gained `product_abbr`/`product_full`, and `title`
    # is now "<product abbr> — <suffix>" (kernel.titles.display_title + product-names.yaml).
    # v6 (date facet): documents gained `published` (YYYY-MM) + `pub_year` from the gold FM.
    # The bump folds into consumers' inputs_fp so a re-run rebuilds.
    contract_ver = 6

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        cfg = ctx.cfg
        staged_cols, staged_rows = _read_staged(cfg.index_db)
        by_path = {str(r["bundle_path"]): r for r in staged_rows}
        latest_ids = _latest_doc_ids(cfg.gold_consolidated)
        app_name_map = personas.app_names(cfg.registries)  # app_code → name (title fallback)
        products = kproducts.load_products(cfg.registries)  # app_code → [product] (abbr titles)
        rules = ent.compile_rules(
            _load_entity_entries(cfg.registries / "entities" / "entities.yaml")
        )

        documents: list[tuple] = []
        sections: list[tuple] = []  # one row per heading — the anchor/structure map
        chunks: list[tuple] = []  # (chunk_id, section_id, doc_key, part, text) — search units
        # fts cols: (chunk_id, section_id, doc_key, title, doc_title, section_path, body)
        fts: list[tuple] = []
        ent_count: Counter = Counter()  # (entity_id, type, canonical) → mentions
        mentions: list[tuple] = []

        for body_path in sorted(cfg.silver_normalized.rglob("body.md")):
            doc_key = body_path.parent.relative_to(cfg.silver_normalized).as_posix()
            meta, body = frontmatter.parse(body_path.read_text(encoding="utf-8"))
            staged = by_path.get(doc_key, {})
            doc_id = str(
                staged.get("doc_id") or f"{meta.get('app_code', '')}:{doc_key.split('/')[-1]}"
            )
            is_latest = doc_id in latest_ids
            # The document title is an FTS column (L1.2) so a doc-defining token (e.g. "KAAJEE")
            # is findable on every chunk of the doc even when section titles/bodies are generic.
            doc_title = str(meta.get("title", "") or staged.get("doc_title") or "")
            toc_depth = _toc_depth(body_path.parent / "refs.yaml")
            secs = ip.shred_sections(body, doc_key, toc_depth)
            word_count = int(staged.get("word_count") or ep.word_count(body))
            documents.append(
                _doc_row(
                    doc_key,
                    doc_id,
                    meta,
                    staged,
                    is_latest,
                    word_count,
                    len(secs),
                    app_name_map,
                    products,
                )
            )
            for s in secs:
                sections.append(
                    (
                        s.section_id,
                        doc_key,
                        s.slug,
                        s.title,
                        s.level,
                        int(s.toc_level),
                        int(is_latest),
                        s.kind,
                        int(s.searchable),
                        s.section_path,
                    )
                )
                # entities stay a section-level signal (mentions cite the anchor section_id)
                if is_latest:  # the search surface + entity graph are anchor-only (§14.6)
                    for etype, canon in ent.extract(s.text, rules):
                        eid = f"{etype}:{canon}"
                        ent_count[(eid, etype, canon)] += 1
                        mentions.append((eid, doc_key, s.section_id))
            # Chunks are the retrieval units (A2b): small adjacent leaves under one parent merge
            # into a coherent unit, oversized leaves split (#pN); containers/hollow yield none. The
            # merged unit cites its first leaf (`unit.section_id`); the FTS title/path are that
            # anchor's.
            if is_latest:
                for unit in ip.chunk_units(secs):
                    for c in ip.chunks_for_unit(unit):
                        chunks.append((c.chunk_id, c.section_id, doc_key, c.part, c.text))
                        fts.append(
                            (
                                c.chunk_id,
                                c.section_id,
                                doc_key,
                                unit.title,
                                doc_title,
                                unit.section_path,
                                c.text,
                            )
                        )
                # B3b (§8.4): re-introduce each extracted `tables/*.csv` as a searchable chunk
                # (caption + flattened rows) citing the section that referenced it, so a table
                # lifted out of prose for fidelity is still findable.
                tables_dir = body_path.parent / "tables"
                for s in secs:
                    for name, caption in ip.find_table_refs(s.text):
                        rows = _read_table_csv(tables_dir / name)
                        # oversized tables are windowed by rows (#pN) so no chunk blows the
                        # embedder token budget that `embed` asserts.
                        base = f"{s.section_id}#{name}"
                        for i, text in enumerate(ip.table_chunk_texts(caption, rows)):
                            tid = base if i == 0 else f"{base}#p{i + 1}"
                            chunks.append((tid, s.section_id, doc_key, i, text))
                            fts.append(
                                (tid, s.section_id, doc_key, caption, doc_title,
                                 s.section_path, text)
                            )  # fmt: skip

        def build(conn: sqlite3.Connection) -> None:
            conn.executescript(_SCHEMA)
            _carry_staged(conn, staged_cols, staged_rows)
            conn.executemany(
                f"INSERT INTO documents ({', '.join(_DOC_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in _DOC_COLUMNS)})",
                documents,
            )
            conn.executemany(
                "INSERT INTO doc_sections "
                "(section_id, doc_key, slug, title, level, toc_level, is_latest, "
                "kind, searchable, section_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                sections,
            )
            conn.executemany(
                "INSERT INTO chunks (chunk_id, section_id, doc_key, part, text) "
                "VALUES (?, ?, ?, ?, ?)",
                chunks,
            )
            conn.executemany(
                "INSERT INTO chunks_fts "
                "(chunk_id, section_id, doc_key, title, doc_title, section_path, body) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                fts,
            )
            conn.executemany(
                "INSERT INTO entities (entity_id, type, canonical_name, mention_count) "
                "VALUES (?, ?, ?, ?)",
                [(eid, t, c, n) for (eid, t, c), n in sorted(ent_count.items())],
            )
            conn.executemany(
                "INSERT INTO entity_mentions (entity_id, doc_key, section_id) VALUES (?, ?, ?)",
                mentions,
            )

        db.build_atomic(cfg.index_db, build)
        return RunResult(
            counts={
                "documents": len(documents),
                "sections": len(sections),
                "chunks": len(chunks),
                "table_chunks": sum(1 for c in chunks if "#table-" in c[0]),
                "entities": len(ent_count),
                "mentions": len(mentions),
            }
        )


def _read_table_csv(path):  # type: ignore[no-untyped-def]
    """Read an extracted `tables/*.csv` sidecar into rows (B3b); `[]` if missing/unreadable."""
    import csv

    if not path.is_file():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.reader(fh))
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def _doc_row(  # type: ignore[no-untyped-def]
    doc_key, doc_id, meta, staged, is_latest, word_count, section_count, app_names, products
):
    """One `documents` row — inventory identity from the staged table, title/template/provenance
    from the bundle FM (the keys `doc_meta_staged` doesn't carry).

    The display `title` is abbreviation-first — `"<product abbr> — <suffix>"`, version/patch
    stripped (`kernel.titles.display_title`); `title_source` preserves the raw; `product_abbr`/
    `product_full` and `app_name` drive the faceted browser + explainer."""

    def s(key: str) -> str:
        return str(staged.get(key, "") or "")

    app_code = s("app_code") or str(meta.get("app_code", ""))
    raw_title = str(meta.get("title", "") or s("doc_title"))
    app_name = app_names.get(app_code, "")
    published = str(meta.get("published", ""))  # gold FM publication date (YYYY-MM)
    pub_year = published[:4] if published[:4].isdigit() else ""
    disp_title, product_abbr, product_full = titles.display_title(
        raw_title, app_code, app_name, products.get(app_code, [])
    )
    return (
        doc_key,
        doc_id,
        app_code,
        s("doc_code") or str(meta.get("doc_type", "")),
        s("section_code") or str(meta.get("section", "")),
        s("pkg_ns") or str(meta.get("pkg_ns", "")),
        s("patch_ver") or str(meta.get("version", "")),
        s("patch_id") or str(meta.get("patch_id", "")),
        s("anchor_key"),
        s("group_key"),
        disp_title,
        raw_title,
        app_name,
        product_abbr,
        product_full,
        s("doc_label"),
        # §7 profile tags: baked into the body FM by `enrich`, read straight off `meta`
        str(meta.get("app_user", "")),
        str(meta.get("doc_user", "")),
        str(meta.get("software_class", "")),
        str(meta.get("function_category", "")),
        word_count,
        section_count,
        int(is_latest),
        str(meta.get("template_id", "")),
        str(meta.get("source_sha256", "")),
        s("source_url") or str(meta.get("source_url", "")),
        published,
        pub_year,
    )


def _read_staged(index_db):  # type: ignore[no-untyped-def]
    """Read `enrich`'s `doc_meta_staged` (columns + rows-as-dicts). Preflight guarantees it exists
    (index `requires` it), so this is a plain read."""
    conn = db.connect(index_db, read_only=True)
    try:
        cur = conn.execute("SELECT * FROM doc_meta_staged")
        cols = [c[0] for c in cur.description]
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return cols, rows


def _carry_staged(conn, cols, rows):  # type: ignore[no-untyped-def]
    """Recreate `doc_meta_staged` verbatim in the rebuilt store (same schema as `enrich`), so the
    table `index` consumed survives its own rebuild (self-contained, re-runnable)."""
    ddl_cols = ", ".join(f"{c} INTEGER" if c == "word_count" else f"{c} TEXT" for c in cols)
    conn.execute(f"CREATE TABLE doc_meta_staged ({ddl_cols}, PRIMARY KEY (doc_id))")
    if rows:
        conn.executemany(
            f"INSERT INTO doc_meta_staged ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})",
            [[r[c] for c in cols] for r in rows],
        )


def _latest_doc_ids(consolidated_root):  # type: ignore[no-untyped-def]
    """The `doc_id`s flagged `is_latest` across every group's `history.yaml` (the anchors)."""
    latest: set[str] = set()
    for hist_path in consolidated_root.rglob("history.yaml"):
        data = kregistry.load_mapping(hist_path)
        for m in data.get("members") or []:
            if m.get("is_latest"):
                latest.add(str(m["doc_id"]))
    return latest


def _toc_depth(refs_path):  # type: ignore[no-untyped-def]
    """The doc's chosen TOC depth from `refs.yaml`, or the H2–H3 default (heading-less docs)."""
    data = kregistry.load_mapping(refs_path, missing_ok=True)
    depth = data.get("toc_depth")
    return (depth[0], depth[1]) if depth else ip.DEFAULT_TOC_DEPTH


def _load_entity_entries(path):  # type: ignore[no-untyped-def]
    """The curated `registries/entities` recognizers (empty if absent — no extraction, a no-op)."""
    data = kregistry.load_mapping(path, missing_ok=True)
    return data.get("entities") or []
