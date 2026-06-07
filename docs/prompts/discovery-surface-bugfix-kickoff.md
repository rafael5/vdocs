# Kickoff Prompt — Discovery-Surface & Gold-Gap-Fill Bugfixes

> Paste the block below into a **fresh session** to act on the discovery/processing
> bugs found while filling VistA-doc gaps from a consumer repo (2026-06-07).
> Report: [`../vdocs-discovery-processing-bugfix-report.md`](../vdocs-discovery-processing-bugfix-report.md) ·
> Plan to fold into: [`../vdocs-remediation-plan.md`](../vdocs-remediation-plan.md).

---

```
Act on docs/vdocs-discovery-processing-bugfix-report.md (the discovery-surface &
gold-gap-fill bug report, 2026-06-07). It catalogs bugs B1–B5 + discoveries D1–D4
found while a consumer (m-stdlib) used vdocs to "answer X from gold" and "fill the
gold gaps." The corpus had the answers, but reaching them took ~15 manual
rediscovery steps the tool should have answered in 1–2 commands.

READ FIRST, in order:
1. docs/vdocs-discovery-processing-bugfix-report.md — this report (TOC, master
   bug table §4, prioritized backlog §16, verified facts §17).
2. docs/vdocs-remediation-plan.md — FORWARD source of truth; fold §16's backlog in.
3. docs/vdocs-implementation-plan.md — execution tracker; add tasks there.

THE P1s (do these first):
- B1 (§5) — OVER-CONSOLIDATION. ~41 distinct Kernel-8.0 krn_8_0_{dg,sm}_*_ug
  feature guides share one XU:XU:UG anchor key; consolidate keeps one winner and
  demotes ~40 to is_latest=0, so they're excluded from gold/FTS search though
  fully processed to silver. Fix: per-document anchor key for granular feature
  guides (fold doc_subject/slug into the key, not just doc_code); add a
  consolidate guardrail that refuses to collapse a version group whose members
  have divergent titles; then backfill catalog→consolidate→index→relate→manifest.
  Same defect blocks VIAB/via_vip_user_guide (already fetched to bronze).
- B2 (§6) — FETCH-THEN-PROMOTE is broken. After `fetch --app VIAB`,
  `run --from convert [--force]` skips all stages as unchanged; the new doc never
  converts. Fix: key convert freshness on the bronze acquisition set; make --force
  actually force; add `vdocs promote <doc_id>` single-lineage incremental promote.
- B4 (§8) — `ask` SILENTLY HIDES fetched-but-not-gold content (FTS is is_latest=1
  only). Surface non-gold matches with a tier label; never let present content
  read as absent.

THEN P2/P3: B5/B3 (`vdocs gaps` join + `inventory --json/--topic/--status`),
card tier counts (§10), skill/CLAUDE.md updates (§14).

VERIFY BEFORE CODING (don't re-discover — §17 has the numbers):
- inventory status: total=3692 fetched=1465 not_acquired=2180 out_of_scope=42.
- ls ~/data/vdocs/documents/silver/text/03-normalized/XU/ | grep _ug | wc -l → 41.
- gold/consolidated/XU/xu_dg/history.yaml → XU:XU:DG member_count: 2.
- SHARED LAKE: before any stage, check for a live operator run
  (`pgrep -af "vdocs run"` + reports/*.log); run only uncovered stages.

HARD RULE: TDD — write the failing test first (the project's pytest/uv/ruff/mypy
toolchain), confirm red, implement, confirm green; design changes go in the design
doc before code. There is unrelated WIP on master (embed stage) — branch off and
don't touch it.
```
