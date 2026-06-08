# Offline Lexical Search — Plan & Tracker

> **The *how/status* execution tracker lives in**
> [`offline-lexical-search-implementation-plan.md`](offline-lexical-search-implementation-plan.md)
> (detailed L0–L4 steps, per-phase changelog/discoveries/risks/remediations/recommendations). This
> document is the *what/why*.

> **Successor to** [`vdocs-implementation-plan.md`](vdocs-implementation-plan.md), which is now
> **closed/frozen** (see its 🏁 Closure section). That effort was a spike; its decisive finding —
> *the all-or-nothing embedding/vector path is not worth its cost on this corpus* — set the
> direction this plan executes. The remediation audit
> ([`vdocs-remediation-plan.md`](vdocs-remediation-plan.md)) remains useful as background; where it
> assumes a semantic/MCP finish, this plan supersedes it.

## Goal — one outcome

**Best-possible offline, human, no-AI search over the VistA doc corpus, packaged so any developer
can run it with zero ML dependencies.** The consumer is a human developer searching technical VistA
documentation locally — no agent, no server, no model. The deliverable is therefore portable by
construction: a self-contained `index.db` (SQLite + FTS5) plus a tiny query tool that opens it
anywhere stock `sqlite3` exists.

**Why lexical (the closure finding, in one line):** lexical is lighter, more portable, faster to
rebuild on every upstream doc change, and faster to iterate than vector search — and the residual
quality gap on an expert/exact-token corpus is closable cheaply at *query time*. Full rationale +
numbers: the implementation plan's 🏁 Closure section and Phase C Discoveries (2026-06-08).

## Inherited from the spike — done, do not redo

These stand and are the foundation; this plan builds *on* them, not over them:
- **The pipeline** (crawl → … → index → relate → manifest) produces a clean, latest-only,
  structure-aware `index.db` with stable IDs (`doc_key`, `section_id = doc_key/slug`,
  `chunk_id = section_id[#pN]`) and FTS5 over searchable chunks. **Lexical search is live**
  (`server/search.py`, `vdocs ask`).
- **Denoising applied to prod** (Phase B): boilerplate single-sourced, `gold/glossary.md`
  materialized, tables re-introduced as searchable chunks — all of which sharpen *lexical* hits.
- **The evaluation harness** (`scripts/baseline_golden.py` + `registries/golden-queries.yaml`):
  nDCG@10 · MRR · recall@k · redundancy@k over graded judgements. **Baseline (dev lake, 2026-06-07):
  mean nDCG@10 = 0.395, MRR = 0.517, recall@10 = 0.50, redundancy@10 = 0.017** (5 labeled / 6 queries).
  This is the number every change below must beat.

## Non-goals (explicit)

- **No semantic / vector search** (`embed`, `vectors.db`, ANN, RRF). Parked; see the closure finding.
- **No MCP / agent surface** (`server/mcp.py`, `serve-mcp`). Descoped — the consumer is a human, offline.
- Not a server. Search must work as a local file + small binary/script, not a running service.

## Definition of done

1. A developer can be handed **one `index.db` + one small runner** and search the corpus offline with
   no Python/ML install required of them.
2. **Lexical quality beats the 0.395 baseline** on the golden set, and the canonical
   vocabulary-mismatch failure (`kaajee-install-procedure`, currently **nDCG@10 = 0.0**) is fixed.
3. The **human-browsable markdown corpus** is published (so search results resolve to readable docs).
4. A **quality gate** runs the golden-query metrics in CI and the published claim is reproducible.

---

## Phases

Lean and sequenced. Each is a shippable increment with a gate. Status legend: ✅ done · 🟡 in
progress · ⬜ not started.

### L1 — Lexical quality (highest leverage, zero/low rebuild cost)
The known gap is vocabulary mismatch on terse, generically-titled sections (the KAAJEE case: the
doc-defining token lives in the **document title**, which is *not* in the FTS index — only
`section_path` is). All three levers are cheap; two are query-time (zero rebuild).

| ID | Step | Detail | Gate |
|----|------|--------|------|
| L1.1 | Field-weighted BM25 | `bm25(chunks_fts, …)` weighting title/section_path/doc_title above body in `server/search.py` (currently unweighted) | nDCG@10 ↑ vs 0.395; no regression on labeled queries |
| L1.2 | Index doc title (+breadcrumb) in FTS | Add `doc_title` to `chunks_fts` in `stages/index/stage.py` (build-time; `section_path` already indexed). Makes "KAAJEE" findable for every chunk of that doc | `kaajee-install-procedure` nDCG@10 > 0; full re-index of dev lake stays seconds |
| L1.3 | Glossary query expansion | Query-time synonym/acronym expansion in `search_pure.fts_match_query`, data-driven from `registries/glossary` (today: empty → seed minimal known cases, e.g. KAAJEE ↔ expansion) | expansion is data-driven + unit-tested; measured lift where applicable |

*TDD: pure-function tests first (`fts_match_query`, weight construction); integration test on a seeded
`index.db`. Measure each lever independently via `baseline_golden.py` and record before/after.*

### L2 — Distributable offline search tool (the portability deliverable)
A zero-ML-dependency way for a developer to search a handed-over `index.db`.

> **Decision (2026-06-08) — build the search CLI in Go, not Python.** The tool is a thin shell around
> SQLite/FTS5, and Go packages that for distribution better than Python on every axis that matters
> here: a **single static binary** (no runtime to install), **cross-compiled** to mac/win/linux ×
> amd64/arm64 from one machine, and — decisively — **FTS5 compiled *in*** via **`modernc.org/sqlite`**
> (pure-Go, cgo-free, FTS5 included) rather than depending on whatever the recipient's system
> `sqlite3`/Python was built against (where FTS5 is usually-but-not-guaranteed present). Rust +
> `rusqlite` (bundled) is equivalent; choose Go on familiarity. **The index builder (`vdocs`) stays
> Python** — `index.db` is the language-neutral distribution contract between them.
>
> *Cost, and how it's contained:* a two-language split means the ranker is reimplemented in Go. The
> surface is small and mostly declarative (field weights live in the `bm25(...)` SQL; expansion is a
> few dozen lines), and drift is prevented by **gating the Go binary against `golden-queries.yaml` in
> CI** (L2.3) so it must reproduce the Python ranker's results.

| ID | Step | Detail | Gate |
|----|------|--------|------|
| L2.1 | Go search CLI | Go + `modernc.org/sqlite` (FTS5), opens `index.db` read-only, runs the L1 ranker (field-weighted `bm25` + glossary expansion). No cgo, no ML deps anywhere in the closure | single static binary; same top-k as `vdocs ask` on the golden queries |
| L2.2 | Cross-compile + handoff | `GOOS`/`GOARCH` matrix → per-platform binaries; document the "give a dev the corpus" path (`index.db` + binary, no rebuild). Decide whether to ship full prod `index.db` (167 MB) or a curated subset | a fresh machine (no Python, no ML) searches with documented steps |
| L2.3 | Ranker-parity gate | Run the Go binary against `golden-queries.yaml` in CI; assert it reproduces the Python ranker's nDCG/ordering within tolerance | Go ↔ Python parity enforced; divergence fails CI |

**Binary shape (sketch):**
```
vdocs-search <query>                          # ranked, pre-cited hits to stdout
  --db PATH        index.db (default: ./index.db)
  --k N            results (default 10)
  --app XU,PSO     structured pre-filter (documents.app_code)
  --doc-type ...   structured pre-filter (documents.doc_type)
  --json           machine-readable output (else: human table w/ snippet + citation)

  read-only SQLite (modernc.org/sqlite, FTS5) · query = fts_match(expand(input)) ·
  ORDER BY bm25(chunks_fts, w_title, w_path, w_doctitle, w_body) · JOIN documents for citation.
  ~one Go pkg: `query` (build MATCH + weights, mirrors search_pure) + `cli` (flags, format).
  glossary expansion table embedded at build time (go:embed) from registries/glossary.
```
A browser-zero-install **static-HTML + SQLite-WASM** page over the same `index.db` is a *possible*
companion for the dev-lake-size corpus, but the 167 MB prod index is heavy for a browser tab — out of
scope unless an audience asks for it.

### L3 — Human corpus deliverable (publish)
Search hits must resolve to a readable doc; ship the browsable corpus.

| ID | Step | Detail | Gate |
|----|------|--------|------|
| L3.1 | `publish` | Markdown-only tree + INDEX + materialized glossary from `consolidated/` | publish tree builds; links/anchors resolve |
| L3.2 | `push` | Commit to the public docs repo | corpus live + browsable |

### L4 — Quality gate
| ID | Step | Detail | Gate |
|----|------|--------|------|
| L4.1 | Gate the metrics | Run `baseline_golden.py` in CI against a committed expected floor; expand `golden-queries.yaml` toward ~20–30 queries | metrics reproduce; regressions fail CI |
| L4.2 | Publish the claim | Record the final lexical nDCG@10 / redundancy@k as the documented quality statement | claim reproducible from the committed harness |

---

## Master tracker

| Phase | ID | Step | Status |
|-------|----|------|--------|
| **L1 — Lexical quality** | L1.1 | Field-weighted BM25 | ⬜ |
| | L1.2 | Doc title (+breadcrumb) in FTS | ⬜ |
| | L1.3 | Glossary query expansion | ⬜ |
| **L2 — Distributable tool** | L2.1 | Go search CLI (`modernc.org/sqlite`, FTS5) | ⬜ |
| | L2.2 | Cross-compile + handoff | ⬜ |
| | L2.3 | Ranker-parity gate (Go ↔ Python on golden set) | ⬜ |
| **L3 — Human corpus** | L3.1 | `publish` | ⬜ |
| | L3.2 | `push` | ⬜ |
| **L4 — Quality gate** | L4.1 | Gate the metrics in CI | ⬜ |
| | L4.2 | Publish the quality claim | ⬜ |

**Suggested order:** L1 first (it defines the quality ceiling and is mostly query-time), then L2
(portability — the headline deliverable), with L3/L4 parallelizable.

---

## Risks

- **Field weights overfit the 6-query golden set.** *Mitigation:* expand the set (L4.1) before
  trusting weight tuning; keep changes that help the *class* of query (title-bearing tokens), not
  individual labels.
- **Glossary is empty.** Expansion has no data until curated. *Mitigation:* seed the known
  high-value cases first; treat full curation as incremental, data-driven (`registries/glossary`).
- **Re-index is still a full `index.db` rebuild** (cheap, but not yet incremental). *Mitigation:*
  acceptable for now (seconds–minutes, no model); revisit per-doc incremental indexing only if the
  rebuild time becomes a real iteration drag.

## Discoveries

- *(none yet — this plan opens 2026-06-08 at closure of the spike)*

## Changelog

- 2026-06-08 — **Plan opened.** Successor to the frozen `vdocs-implementation-plan.md`. Scope reframed
  to offline, human, no-AI lexical search distributed to developers; semantic/vector (Phase C) parked
  and MCP/agent (Phase D) descoped per the spike's closure finding. Baseline carried forward:
  lexical nDCG@10 = 0.395.
- 2026-06-08 — **L2 language decision: Go (not Python) for the search CLI.** Single static binary,
  cross-compiled, FTS5 compiled in via `modernc.org/sqlite` (no recipient-environment SQLite/FTS5
  dependency). `vdocs` index builder stays Python; `index.db` is the contract; added L2.3 ranker-parity
  gate against `golden-queries.yaml` to prevent Go↔Python drift. See L2's Decision note.
