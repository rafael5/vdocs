# De-Novo Pipeline Run — Gated Full Corpus via Real VDL Fetch

> **Purpose:** rebuild the entire `~/data/vdocs` lake from scratch with **all current logic applied**
> — the admission gates (app-scope G3 + doc-type G4), the B1 anchor-key fix, and the persona bake —
> by **really fetching every gate-admitted document from the live VDL**. No `seed_from_v1` shortcut,
> no mocks, no offline gap: **all 1,036 gate-admitted docs** end up in the corpus.

**Requires network** (downloads from `https://www.va.gov/vdl/`).
**Shared-lake rule:** before running, confirm no operator run is live —
`pgrep -af "vdocs run"` and check `~/data/vdocs/reports/*.log`. This is the big destructive operation.

---

## What it produces

| | count | why |
|---|---|---|
| gate-admitted fetch targets | **1,036** | VistA apps only (G3) + Tier-A doc-types only (G4); `fetch --all` selects all of them |
| really downloaded | **1,036** | live VDL fetch, content-addressed into the bronze CAS (idempotent; re-runnable) |
| gold (is_latest) docs | ~800–900 | after B1 version-collapse (one anchor per logical doc) |
| persona coverage | **100%** of gold apps | `app_user`/`doc_user`/`software_class`/`function_category` baked into frontmatter + index |

`vdocs fetch --all --dry-run` prints `selection matches 1036 of 1036` — the gate is already wired in.

---

## 1. Wipe the lake (destructive)

```bash
cd ~/data/vdocs
rm -rf documents index.db index.db-* inventory.db reports
rm -f  inventory/silver/* inventory/gold/*
# keep inventory/bronze/catalog.raw.json (or re-crawl in step 2) and state.db
```
*(A re-fetch re-downloads bytes, so the old bronze CAS is not worth keeping — wipe `documents/` fully.)*

## 2. Rebuild the inventory (control plane)

Fresh crawl (most complete — picks up any new VDL docs), or reuse the saved `catalog.raw.json`:

```bash
cd ~/projects/vdocs
.venv/bin/vdocs crawl --force            # OPTION A: fresh VDL catalog (network). Skip to reuse catalog.raw.json.
.venv/bin/vdocs catalog --force          # catalog.raw → catalog.enriched (B1 anchor_key, doc_code, scope signals)
.venv/bin/vdocs serve-inventory --force  # → gold inventory.{json,csv,db} + the HARD GATE (the fetch gate)
```

## 3. Confirm registries are current (already committed)

```bash
.venv/bin/python scripts/seed_app_profiles.py   # → app-profiles.yaml (104 profiles, 100% gold coverage); no-op if unchanged
```

## 4. REAL fetch — every gate-admitted document (network)

```bash
.venv/bin/vdocs fetch --all
# select_fetch_targets applies the always-on gate (noise §9.5 + DOCX §1 + app-scope G3 + doc-type G4)
# → downloads all 1036 gated docx from the VDL into the content-addressed bronze CAS.
# Idempotent: re-run to retry any failures (recorded in state.db acquisitions as status='failed').
```

After it finishes, check for any failed downloads:
```bash
.venv/bin/python -c "import sqlite3; c=sqlite3.connect('$HOME/data/vdocs/state.db'); \
print('fetched:', c.execute(\"SELECT COUNT(*) FROM acquisitions WHERE status='fetched'\").fetchone()[0], \
'failed:', c.execute(\"SELECT COUNT(*) FROM acquisitions WHERE status='failed'\").fetchone()[0])"
# re-run 'vdocs fetch --all' to retry failures (CAS hits are skipped, only failures re-attempt).
```

## 5. Process the document plane → gold + index

```bash
.venv/bin/vdocs run --from convert --to index --force
# convert → discover → enrich (bakes personas) → normalize → consolidate (B1 grouping) → index (persona columns)
# add --to manifest for the full gold deliverable (relate + manifest)
```

## 6. Verify

```bash
.venv/bin/python - <<'PY'
import sqlite3, collections
c = sqlite3.connect("/home/rafael/data/vdocs/index.db")
n = c.execute("SELECT COUNT(*) FROM documents WHERE is_latest=1").fetchone()[0]
print("gold (is_latest) docs:", n)
for col in ("app_user","doc_user","software_class","function_category"):
    k = c.execute(f"SELECT COUNT(*) FROM documents WHERE is_latest=1 AND {col}<>''").fetchone()[0]
    print(f"  {col:18} {k}/{n}")
print("doc_type spread:", dict(collections.Counter(r[0] for r in
      c.execute("SELECT doc_type FROM documents WHERE is_latest=1"))))
print("XU:XU:UG distinct anchors:",
      c.execute("SELECT COUNT(DISTINCT anchor_key) FROM documents WHERE anchor_key LIKE 'XU:XU:UG%'").fetchone()[0])
PY
```

Expect: **only Tier-A doc_types** (UM/UG/TM/DG/API/INT/AG/SM/SG/QRG/TRG/REF/FAQ/TG) — no DIBR/IG/RN/SUP;
persona columns populated for ~100% of gold; many distinct XU:XU:UG anchors (B1 fix working).

---

## Notes

- **`vdocs run` won't fetch on its own** (no blind download — empty default selection). The corpus
  comes from the explicit `vdocs fetch --all` in step 4.
- **Idempotent + retryable:** the CAS dedupes by content hash, so re-running `vdocs fetch --all`
  only re-attempts `failed` acquisitions; successful ones are CAS hits. Run it until `failed: 0`.
- **`seed_from_v1.py --all`** remains as an *offline* alternative (now gate-aware too) for dev without
  network — but it caps at the ~929 docs the v1 tree happens to hold. This runbook uses the real
  fetch precisely to get all 1,036 with no omissions and no mocks.
- **Reversible gate:** to widen to the ungated ~2,778 (all doc-types) for stress-testing, flip the
  `doctype-policy.yaml` decisions to `keep` and re-run from `serve-inventory` → `fetch --all`.
