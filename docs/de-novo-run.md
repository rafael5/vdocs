# De-Novo Pipeline Run — the operator runbook

> **This is the canonical, accurate runbook** (rewritten 2026-06-10 after the operability-hardening
> work). It supersedes the pre-hardening copy archived under `docs/historical/`, which **misstated**
> fetch idempotence and the retry loop — do not follow that one.
>
> **The whole build is three commands:**
> ```bash
> vdocs gate                 # 1. PREVIEW — see exactly what will be fetched/promoted (no run)
> vdocs build --fresh --yes  # 2. BUILD   — crawl → … → manifest → doctor, one command
> vdocs doctor               # 3. TRUST   — re-check the corpus → GOLD LIBRARY: GREEN|RED
> ```
> (`vdocs build` already runs `doctor` at the end; step 3 is for re-checking later.)

The pipeline narrates itself: every stage prints a `[k/N] stage — …` banner, a live
`GREEN/WARN/ERROR` result line with counts + elapsed, progress heartbeats for the long stages
(`fetch`/`convert`), and an end-of-run summary table with an overall verdict and exit code. You do
**not** need to read `state.db` or write validation scripts — the tool reports what happened.

---

## 0. Prerequisites

- **Invoking `vdocs`.** After `make install` the CLI lives in the project `.venv`, **not** on your
  `PATH`. Every `vdocs …` command below means **`uv run vdocs …`** (or `source .venv/bin/activate`
  once, then plain `vdocs …`).
- **Check the environment first:** `vdocs preflight` → `PREFLIGHT: GO|NO-GO`. It verifies the things
  that strand a run before stage 1 — the converter binaries (Pandoc, + Docling if a doc is routed
  to it), a writable `$DATA_DIR`, free disk, and VDL reachability — each OK/WARN/FAIL with a fix.
  Exit 1 on NO-GO. (The prereqs below are exactly what it checks.)
- **Network** is needed for `crawl` + `fetch` (they pull from `https://www.va.gov/vdl/`). Everything
  after `fetch` runs **offline** (see §6 for the airgapped split).
- **Converters (system binaries — not pip deps).** `convert` shells out to **Pandoc** (required for
  every DOCX) and, for the one curated heavy-cross-reference doc (`CPRS/cprsguium`, see
  `registries/converter-routing/`), the **Docling** CLI. Install both before running:
  ```bash
  sudo apt install pandoc                      # or: brew install pandoc
  uv tool install 'docling-slim[standard]'     # Docling CLI, isolated env
  ```
  `convert` preflight-checks these and **fails up front with the exact install command** if either
  is missing — so you won't see a misleading "N documents failed to convert."
- **Shared lake.** `~/data/vdocs` (`$DATA_DIR`) is shared. `vdocs build` **refuses to start if another
  vdocs pipeline process is active** (it would race `state.db`/`index.db`/the CAS). If you see that
  message, wait for the other run (check `reports/*.log`) — don't force past it.
- No ML / vector dependencies, no `embed` stage — the corpus is lexical-first and offline.

## 1. Preview the gate (no run, no network)

```bash
vdocs gate
```
Prints the effective admission policy — allowed app system-types, denied statuses, the **KEPT** vs
**OMITTED** doc-types, and the untyped fail-safe — plus, if a gold inventory already exists, how many
documents are **ADMITTED** vs excluded (with a per-doc-type breakdown). To change what's admitted,
edit the registries and re-preview; see [`gate-reference.md`](gate-reference.md).

## 2. Build the corpus

```bash
vdocs build --fresh --yes
```
- `--fresh` does the from-scratch wipe of **derived** lake data — `documents/` (incl. the bronze CAS),
  `index.db`, **`state.db`**, `reports/`, and the inventory silver+gold. It **keeps**
  `inventory/bronze/catalog.raw.json` (so `--skip-crawl` can reuse it) and the repo registries. The
  wipe **refuses without `--yes`**.
  - *Why state.db is wiped:* `fetch` is now idempotent (it skips documents already in the CAS). If the
    CAS is wiped but `state.db` is kept, fetch would "skip" documents whose bytes are gone. A clean
    build wipes both so every gate-admitted document is re-downloaded.
- Without `--fresh` it builds in place (re-running is cheap — unchanged stages skip, and `fetch` only
  re-attempts what's missing).
- `--skip-crawl` reuses the saved `catalog.raw.json` instead of re-crawling (faster; skip a fresh VDL
  scrape). `catalog` runs off the on-disk `catalog.raw.json` even with no crawl record — a wiped
  `state.db` no longer forces a re-crawl.

`build` runs, in one orchestrated pass: `crawl → catalog → serve-inventory → fetch (--all) → convert →
discover → enrich → normalize → consolidate → index → validate → relate → manifest`, then `doctor`. It
exits **non-zero** if any stage ERRORs or the corpus comes out **RED**.

## 3. Trust the result

`build` ends with the `doctor` table + verdict. To re-check any time:
```bash
vdocs doctor
```
It reads `index.db` and reports each check as **PASS / BY-DESIGN / WARN / FAIL**, then
`GOLD LIBRARY: GREEN|RED` (exit 1 on RED). **BY-DESIGN** and **WARN** never make it RED — only a real
**FAIL** does. See §5 for what each bucket means.

---

## 4. Reading the run output (status + exit codes)

| Token | Meaning | Blocks? |
|---|---|---|
| `GREEN` | the stage did its work, no caveats | no |
| `WARN`  | completed, but look — e.g. some documents are permanently unavailable upstream, or a doc failed to convert and was isolated | **no** |
| `ERROR` | a preflight/postflight gate failed; the run stopped here | **yes** |

**Exit codes:** `0` = all GREEN (or WARN, by default) · `1` = an ERROR stopped the run, or `doctor`
is RED · `10` = `vdocs run --strict` and there were WARNs (opt-in; lets CI treat WARNs as failures).

## 5. The two non-defects you'll see (and why they're fine)

- **"N documents permanently unavailable" (a fetch WARN).** A few VDL documents return a persistent
  HTTP 500/404 upstream. `fetch` retries each across runs and, after the attempt cap, marks it
  `permanent_missing` and **stops re-attempting it**, listing the URLs in a WARN. This is an upstream
  availability gap, **not** a pipeline defect — the build proceeds GREEN/WARN. (The old runbook told you
  to "re-run until `failed=0`"; that's **unreachable** for these and would loop forever. Don't.)
- **`function_category` below 100% (a doctor BY-DESIGN row).** The fallback-profile apps carry no
  Monograph SPM line, so they legitimately have no `function_category`. `doctor-policy.yaml` encodes
  the expected floor, so this shows as **BY-DESIGN**, not a FAIL.

## 6. Retrying / resuming (idempotent — this is the big change)

`fetch` is a cheap, honest resume: re-running **does not** re-download what's already in the CAS.

```bash
vdocs fetch --all --force      # re-attempt ONLY the docs that failed last time (CAS hits are skipped)
vdocs fetch --all --refetch    # force a full re-download (ignore the CAS) — rarely needed
```
- A transient failure is retried on the next `--force` run; after the attempt cap it becomes
  `permanent_missing` and is no longer attempted (so the loop terminates).
- After topping up fetches, finish the document plane: `vdocs run --from convert --to manifest` then
  `vdocs doctor`.

## 7. Airgapped build (network only at the fetch boundary)

`fetch` is the only step past `crawl` that needs the network. To build offline:

1. **On a connected box:** `vdocs crawl && vdocs catalog && vdocs serve-inventory && vdocs fetch --all`
   (downloads every gate-admitted document into the bronze CAS).
2. **Copy the lake** (`~/data/vdocs` — at minimum `documents/bronze/`, `inventory/`, and `state.db`)
   to the airgapped box.
3. **On the airgapped box (offline):** `vdocs run --from convert --to manifest && vdocs doctor`.

Everything from `convert` onward is pure local computation — no network, no ML.

## 8. Verify (optional manual cross-check)

`vdocs doctor` is the shipped check, but you can spot-check the index directly:
```bash
vdocs ask "how to add a new patient" --k 5    # ranked, pre-cited gold hits
vdocs inventory --status                       # per-document fetch status (fetched/permanent_missing/…)
```

---

## What changed from the pre-hardening runbook

The archived `docs/historical/de-novo-run.md` is **wrong** on these points (now fixed):
- it claimed re-running `fetch` "skips CAS hits, only failures re-attempt" — that was false then
  (every run re-GET everything); it is **true now** (idempotent resume).
- it said loop "until `failed=0`" — unreachable for the persistent upstream 500s; now they become
  `permanent_missing` and the run completes with a WARN.
- it had you hand-sequence `--only` stages and dodge the OOM-prone `embed` stage; `embed` is **gone**
  and `vdocs build` sequences everything for you.
- wiping `state.db` used to force a cryptic re-crawl; `catalog` now runs off `catalog.raw.json`.
