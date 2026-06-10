# De-Novo Pipeline Run — Gated Full Corpus (offline)

> **Purpose:** rebuild the entire `~/data/vdocs` lake from scratch with **all current logic applied**
> — the admission gates (app-scope G3 + doc-type G4), the B1 anchor-key fix, and the persona bake —
> producing the **gated full corpus (~929 docs)** that the search/TUI will serve. Offline: bytes come
> from the v1 raw tree; no live VDL fetch.

**Shared-lake rule:** before running, confirm no operator run is live —
`pgrep -af "vdocs run"` and check `~/data/vdocs/reports/*.log`. This is the big destructive operation.

---

## What it produces

| | count | why |
|---|---|---|
| gated DOCX seeded | **~929** | admission gate: VistA apps only, Tier-A doc-types only (omit B/C/D) |
| gold (is_latest) docs | ~800–900 | after B1 version-collapse (one anchor per logical doc) |
| persona coverage | **100%** of gold apps | `app_user`/`doc_user`/`software_class`/`function_category` baked into frontmatter + index |

---

## Preserve (do NOT delete)

- `~/data/vista-docs/raw` — **3.6 G**, the v1 docx byte source the seed reads.
- `~/data/vdocs/inventory/bronze/catalog.raw.json` — the VDL crawl output (lets `catalog` rebuild
  the inventory offline; otherwise you'd need a live `vdocs crawl`).
- `~/data/vdocs/state.db` — keep it (the recorded `crawl` run satisfies `catalog`'s preflight;
  `--force` re-runs everything else anyway).

## 1. Wipe the derived lake (destructive)

```bash
cd ~/data/vdocs
rm -rf documents index.db index.db-* inventory.db reports
rm -f  inventory/silver/* inventory/gold/*          # KEEP inventory/bronze/catalog.raw.json
# (state.db and inventory/bronze/catalog.raw.json stay)
```

## 2. Rebuild the inventory (control plane) — offline, with current code

```bash
cd ~/projects/vdocs
.venv/bin/vdocs catalog --force          # catalog.raw → catalog.enriched (B1 anchor_key, doc_code, scope signals)
.venv/bin/vdocs serve-inventory --force  # → gold inventory.{json,csv,db} + the HARD GATE
```
*(For fresh VDL data instead of the saved catalog.raw: run `.venv/bin/vdocs crawl` first — needs network.)*

## 3. Confirm the registries are current (already committed this session)

```bash
.venv/bin/python scripts/seed_app_profiles.py   # → registries/inventory/app-profiles.yaml (104 profiles, 100% gold coverage)
```
*(No-op if unchanged; safe to re-run. The doc-user / scope / doctype policies are already in `registries/`.)*

## 4. Seed the gated document corpus (offline, applies the admission gate)

```bash
.venv/bin/python scripts/seed_from_v1.py --all
# → ~929 gate-admitted docx into bronze CAS + raw/index.json + acquisitions + a 'fetch' run record
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
# B1 sanity: distinct XU:XU:UG anchors should be many (not 1)
print("XU:XU:UG distinct anchors:",
      c.execute("SELECT COUNT(DISTINCT anchor_key) FROM documents WHERE anchor_key LIKE 'XU:XU:UG%'").fetchone()[0])
PY
```

Expect: **only Tier-A doc_types** (UM/UG/TM/DG/API/INT/AG/SM/SG/QRG/TRG/REF/FAQ/TG) — no DIBR/IG/RN/SUP;
persona columns populated for ~100% of gold; many distinct XU:XU:UG anchors (B1 fix working).

---

## Notes

- **`vdocs run` fetches nothing on its own** (no blind download — empty default selection). The gated
  corpus comes from `seed_from_v1.py --all` (offline) or, for live data, `vdocs fetch --all` (which
  applies the same gate but downloads from the VDL).
- **The 107-doc gap** between the gate-admitted set (1,036) and the offline-seedable set (929) is gated
  docs the v1 tree never fetched — only a live `vdocs fetch --all` would pull those.
- **Reversible gate:** to widen to the ungated ~2,778 (all doc-types) for stress-testing, flip the
  `doctype-policy.yaml` decisions to `keep` (or add a `--no-gate` seed flag) and re-seed.
