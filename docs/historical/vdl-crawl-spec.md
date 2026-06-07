# VDL Crawl & Inventory-Enrichment Specification

**Status:** Replication-grade spec (derived from the v1 `vista-docs` implementation). **Date:** 2026-06-01.
**Purpose:** define, exactly, how to crawl the VA VistA Document Library (VDL) website and enrich the
result into the canonical **inventory**, so the vdocs `crawl` + `catalog` stages reproduce **everything
v1 derived** and may improve on it.

> **Contract — superset, not identity (decided 2026-06-01).** vdocs does **not** have to emit a
> byte-identical `vdl_inventory_enriched.csv`. The binding requirement is **no information loss**: every
> signal v1 derived (every column's meaning in §5) must be present and at least as correct. vdocs is
> **free to add columns, finer fields, extra signals, or richer structure** wherever that makes the
> enrichment better — and free to choose its own column order, types, and on-disk shape (JSON is the
> primary artifact; CSV is a convenience view). v1's exact columns and the §7 distributions are the
> **reference floor and sanity targets**, not a diff gate.
>
> This document is reverse-engineered from the authoritative v1 sources:
> `src/vista_docs/crawl/{parser,crawler,session}.py`, `scripts/enrich_inventory.py` (1,448 lines),
> `scripts/classify_vista_type.py`, `src/vista_docs/enrich/{doc_labels,package_master,text_fixers}.py`,
> the `data/*.yaml` vocabularies, and validated against the live output
> `~/data/vista-docs/inventory/vdl_inventory_enriched.csv` (8,834 rows × 34→36 columns). Where vdocs
> should *implement* this rather than copy it, §9 maps each piece onto the vdocs `crawl`/`catalog` stage
> contracts (design §8). **Inventory is metadata only — no documents are downloaded.** Selecting and
> fetching a subset is a separate, later step (§9.5).

---

## Contents

1. [Pipeline overview](#1-pipeline-overview)
2. [The VDL website structure](#2-the-vdl-website-structure)
3. [Stage A — crawl (site → raw inventory)](#3-stage-a--crawl-site--raw-inventory)
4. [Stage B — enrich (raw → enriched inventory)](#4-stage-b--enrich-raw--enriched-inventory)
5. [Column reference (all 34 columns)](#5-column-reference-all-34-columns)
6. [Vocabularies & regexes](#6-vocabularies--regexes)
7. [Invariants & acceptance test (identical CSV)](#7-invariants--acceptance-test-identical-csv)
8. [Lessons learned (the trial and error)](#8-lessons-learned-the-trial-and-error)
9. [Mapping onto the vdocs architecture](#9-mapping-onto-the-vdocs-architecture)
10. [Appendix — external vocabulary files](#10-appendix--external-vocabulary-files)

---

## 1. Pipeline overview

```
VDL website (va.gov/vdl/)
   │  crawl  (HTTP + HTML parse; 3-level walk; polite session)
   ▼
raw inventory   vdl_inventory.csv      (12 columns, one row per document LINK)
   │  enrich (5 deterministic passes; pure transforms + curated vocabularies)
   ▼
enriched inventory   vdl_inventory_enriched.csv   (34 columns, 1:1 with raw rows)
                     + vdl_inventory_schema.json   (per-field type manifest)
   │  classify (system_type) — scripts/classify_vista_type.py
   ▼
final inventory      vdl_inventory_enriched.csv   (36 columns: + system_type, cots_dependent)
```

> **Two scripts, two column counts.** `enrich_inventory.py` emits **34** columns; `classify_vista_type.py`
> then *inserts* `system_type` and `cots_dependent` immediately after `app_status`, yielding **36**. It
> is idempotent (inserts only if absent; overwrites values; writes a `.csv.bak`). The on-disk reference
> file verified 2026-06-01 is the **34-column** state (classify not last-run on it). Reproduce both
> stages; treat 36 columns as the complete inventory. **Note:** the v1 narrative docs say "29 columns"
> with a different idealized list — that is stale; the **as-built 34/36 columns here are authoritative.**

Two properties define correctness:

- **1:1 rows.** Enrichment never adds or drops rows. 8,834 raw rows → 8,834 enriched rows. Every
  document *link* on every application page becomes exactly one row (a DOCX and its companion PDF are
  two rows that share a `doc_slug`).
- **Determinism.** Given the same raw inventory + the same curated vocabularies, enrichment is a pure
  function. No network, no randomness, no time dependence (the only dated value is the build stamp in
  the schema JSON).

---

## 2. The VDL website structure

The VDL is a classic 3-level ASP site rooted at `https://www.va.gov/vdl/`:

| Level | Page | Links to find | Yields |
|---|---|---|---|
| 1 | index (`vdl/`) | `<a href="…section.asp?secid=N">` | **Sections** (name + url) |
| 2 | section (`section.asp?secid=N`) | `<a href="…application.asp?appid=N">` | **Applications** (name, status, url) |
| 3 | application (`application.asp?appid=N`) | doc-file `<a>` inside content tables | **Documents** (title, url, file, date) |

Today's live site (verified 2026-06-01): **5 sections** — Clinical (`secid=1`), Infrastructure
(`secid=2`), Financial-Administrative (`secid=3`), VistA/GUI Hybrids (`secid=4`), Monograph
(`secid=6`). Infrastructure alone lists ~69 applications (including archived/decommissioned).

**Critical real-world facts (see §8 for why each matters):**
- Document links are served as **relative** hrefs (`documents/<Section>/<App>/<file>.docx`) and **must
  be resolved against the application page's *final* URL** (after redirects), i.e. `…/vdl/documents/…`
  — *not* the host root.
- Application pages also contain **chrome links** repeated across many pages — VBA benefit forms
  (`vba.va.gov`, `benefits.va.gov`) and non-VDL VA references (paths without `/vdl/`). These are
  **not documents**; they are detected and flagged as noise in enrichment (§4.2), never hard-deleted.
- The site responds differently to anonymous/abusive clients — a **descriptive User-Agent**, a
  **delay between requests**, and **retry on 5xx** are required for a clean, complete crawl.

---

## 3. Stage A — crawl (site → raw inventory)

### 3.1 HTTP session (v1 `session.py` + `config.py`)

A single configured session, reused for every request:

| Setting | v1 value | Notes |
|---|---|---|
| `User-Agent` | `vista-docs/0.1 (hobbyist research; contact: see github.com/rferrisx/vista-docs)` | **Mandatory.** VA infra returns **HTTP 403 to the default `python-requests`/client UA**; any non-default UA works (the fetch docs used a `Mozilla/5.0…` UA, the crawl config a custom one — either is fine). vdocs sends e.g. `vdocs/<ver> (+github.com/rafael5/vdocs)`. |
| inter-request delay | **1.5 s** after every GET | politeness; avoids throttling on a `.gov`. |
| timeout | 30 s per request | |
| retries | total **3**, `backoff_factor=2.0`, `status_forcelist=[500,502,503,504]`, `raise_on_status=False` | transient 5xx are retried with exponential backoff. |
| redirects | followed, `max_redirects=5` | the **final** URL is used as the parse base (below); cap redirects to avoid loops on legacy URLs. |
| HTTP 429 | exponential backoff 2→4→8 s | bulk requests without delay risk 429 + IP block on this `.gov`. |

### 3.2 Level 1 — `parse_index(html, base_url) -> [Section]`

- Scan every `<a href>`; keep those whose href contains `section.asp`.
- Resolve href against `base_url` (`urljoin`); extract `secid` from the query.
- **De-duplicate by `secid`** (the index repeats links); skip links with empty visible text.
- Emit `Section(name=<link text>, url=<resolved url>)`.

### 3.3 Level 2 — `parse_section_page(html, base_url) -> [Application]`

- Keep `<a href>` containing `application.asp`; resolve; extract `appid`; **de-dup by `appid`**.
- Parse the **status suffix** from the link text:
  - `… - ARCHIVE` → `status="archive"`, strip suffix from name.
  - `… - DECOMMISSIONED <rest>` → `status="decommissioned"`, `decommission_date=<rest>`, strip.
  - otherwise → `status="active"`.
- Extract the **app code** from a trailing parenthesis: `Nursing (NUR)` → `NUR`
  (regex `\(([A-Z0-9+/ ]{1,20})\)\s*$` on the cleaned name). May be empty (handled in enrichment).
- Emit `Application(name, app_code, url, status, decommission_date)`.

### 3.4 Level 3 — `parse_application_page(html, base_url) -> [Document]`

`base_url` **must be the final response URL** of the application page (post-redirect).

1. **Table-first scan.** For each `<table>`/`<tr>` with ≥2 cells, collect the row's cell texts; for
   each `<a href>` in the row whose href ends in a known extension (`.pdf .doc .docx .zip .txt`):
   - resolve the href against `base_url`; derive `filename` (last path segment) and `file_ext`.
   - **Title/label resolution:** VDL renders the *format* as the link text (`DOCX`/`PDF`/…) and the
     *title* in a sibling cell. So: if the link text ∈ {DOCX, PDF, DOC, ZIP, TXT, WORD}, the
     `doc_type_label` = that link text and the `title` = the first non-format cell text; otherwise the
     link text *is* the title and the label = the first cell text.
   - **Date:** first cell text matching `\d{1,2}/\d{1,2}/\d{4}` | `\d{1,2}/\d{4}` | `Mon YYYY`.
2. **Fallback link scan.** *Only if the table scan found zero docs*, scan all `<a href>` ending in a
   known extension (no titles/dates). This is what scoops chrome/noise links on table-less pages — it
   is deliberately last-resort, and the noise it admits is caught in enrichment (§4.2).

### 3.5 Raw inventory output contract — `vdl_inventory.csv` (12 columns)

One row per `(section, application, document)` triple, in crawl order:

```
section_name, app_name, app_code, app_status, decommission_date,
doc_title, doc_type, filename, file_ext, doc_date, doc_url, app_url
```

(`doc_type` here is the *raw VDL label* e.g. "DOCX"; `app_code` is the parens code from level 2.) Also
emit the hierarchical `vdl_inventory.json` (Section→Application→Document) for browsing. Enrichment
reads the **CSV**.

### 3.6 Crawl lessons (summary; full list §8)

- Use the response's **final URL** as the level-3 base (relative links + redirects).
- Descriptive UA + 1.5 s delay + 5xx retry are not optional for a complete crawl.
- Skip a section/app that returns non-200 with a WARN; do not abort the whole crawl.
- De-dup sections by `secid` and apps by `appid` (the nav repeats them).

---

## 4. Stage B — enrich (raw → enriched inventory)

`enrich_inventory.py` is a **5-pass** transform. Passes 1 and the global half of 2 are per-row; pass 2's
setup, pass 3, and passes 4–5 require the whole corpus. Order is load-bearing — do not reorder.

### 4.0 Inputs & curated data

- Input: `vdl_inventory.csv` (§3.5).
- Curated vocabularies (in-repo `data/`): `doc_labels.yaml`, `package_master.yaml`,
  `typo_corrections.yaml` (see §6 / §10).
- Optional: `publish/url_map.json` (for the two `github_md_*` columns; absent → those columns blank).
- Text fixers: `fix_mojibake`, `apply_typo_corrections` (v1 `enrich/text_fixers.py`).

### 4.1 Pass 1 — per-row rename, repair, parse

For each raw row:

1. **Rename** source columns: `filename→doc_filename`, `file_ext→doc_file_ext`. (`app_name` is
   renamed to `app_name_full` after abbrev extraction below.) Source columns `doc_type`, `doc_date`,
   `app_code` are **dropped** (not carried into the enriched output).
2. **Mojibake repair** on `doc_title`, `doc_subject`, `app_name` — *before* abbrev extraction so the
   regex sees clean text. v1 `fix_mojibake` is exactly **`ftfy.fix_text(text, normalization="NFC")`**
   (empty→`""`). The NFC + ftfy pass also normalizes/strips Unicode whitespace such as ` `
   (non-breaking space), which was breaking `\bPOM\b` on ~31 JLV titles. **Fidelity note:** vdocs'
   `kernel/text.repair_mojibake` is now `ftfy.fix_text(text, normalization="NFC")` (the two mojibake
   fixers were unified onto ftfy — §9.2), so `catalog` delegates to it directly and reproduces the
   identical CSV; the field pass adds nbsp stripping. (`doc_filename`/URLs are never touched — literal
   va.gov identifiers.)
3. **App abbrev extraction:** `app_name_abbrev` = trailing-parens code via `\s*\(([A-Z0-9/+\-]{1,10})\)\s*$`;
   strip it from `app_name`; then `app_name_full = app_name`.
4. **Typo corrections** (`apply_typo_corrections`) on `doc_title`, `doc_subject`, `app_name_full`;
   every original spelling that was changed is collected into **`doc_search_aliases`**
   (pipe-joined, de-duplicated) so search can still match the original.
5. **`parse_row`** (the heart — patch identity + doc type + subject):
   - **Multi-namespace:** if the title matches `…NS*V*P/NS*V*P…` (`MULTI_NS_RE`), set `multi_ns="1"`
     and capture the whole slash-joined prefix into `patch_id_full` (`PATCH_FULL`).
   - **Patch identity — Pattern A** (`PATCH_A`): `^(optional prefix )NS*V*P(/extra)? remainder`. On
     match: `pkg_ns=NS`, `patch_ver=V`, `patch_num=int(P)`, and `remainder` → doc-type classification.
   - **Else Pattern B** (`PATCH_B`): non-VistA version forms (`Version X.Y`, `vX.Y`, `Release N`, or a
     bare `X.Y[.Z]`). On match `patch_ver=that`, `pkg_ns=app_code`. If still no version, try the
     **filename** version `^app_(major)_(minor)` (`FNAME_VER`). If still no patch number, try the
     filename patch `_p?NNNN_` (`FNAME_PATCH`).
   - **Doc-type classification (title first, filename second):** run `classify_doc_type(remainder/title)`
     against the ordered `DOC_TYPE_PATTERNS` (§6); if empty, fall back to `classify_by_filename(doc_filename, app_abbrev)`
     using the filename-suffix map `_SLUG_SUFFIX_MAP` (+ `_APP_SPECIFIC_SUFFIX` overrides). Title always
     wins over filename.
   - **`doc_subject`** = `extract_subject(remainder, …, doc_label)` — strip the patch prefix, the
     matched doc-label text, and any residual DIBR phrase; trim leading/trailing punctuation.
   - **VBA-form override:** if the title starts with `\d{2}[–-]\d+` or the filename starts with
     `(VBA|SF)\d`, force `doc_code="FORM"`, `doc_label="VBA Form"`, clear `pkg_ns/patch_ver/patch_num`.
   - Returns `pkg_ns, patch_ver, patch_num, doc_code, doc_label, doc_subject, patch_id_full, multi_ns`.

### 4.2 Pass 2 — corpus-global enrichment

First compute two corpus-wide structures:

- **Shared-URL set:** `Counter(doc_url)`; any URL with count > 1 is a **shared** (chrome) URL.
- **Companion map:** group every `doc_url` by its base (URL minus extension) → `{ext: url}`.

Then per row, derive (in this order):

1. **`app_name_abbrev` fallback:** if empty, use `APP_ABBREV_FALLBACK[app_name_full]`, else `pkg_ns`.
2. **Package-master canonicalization** (`package_master.yaml`): look up the abbrev. If found, overwrite
   `app_name_full` with the master `canonical_name`, set `canonical_pkg`, and fill `pkg_ns` *only if
   blank* (per-row patch-derived `pkg_ns` is trusted over the master). The original `app_name_full`,
   when it differed, is preserved in **`doc_subject_raw`**. If not found, `canonical_pkg = app_name_abbrev`,
   `doc_subject_raw = ""`.
3. **`doc_subject` cleaning** (`clean_doc_subject`): clear the subject if it is a redundant echo
   (== abbrev / title / label), a multi-NS continuation (`/…`), a bare year, a bare version, pure
   punctuation, a patch artifact (`*NNN`), a full patch-id, or ≤2 chars with no letters.
4. **`section_code`** = `SECTION_CODE[section_name]` (CLI/FIN/GUI/INF/MON).
5. **`decommission_date`** normalized `MMM YYYY` → `YYYY-MM`.
6. **`patch_ver_major` / `patch_ver_minor`** = `split_patch_ver(patch_ver)` (ints as strings; minor 0
   when major-only).
7. **`doc_layer`:** `anchor` if version-but-no-patch-number; `patch` if a patch number; else `plain`.
8. **`patch_id`:** `NS*V*P` when ns+ver+num; `NS*V` when ns+ver (anchor); else `""`.
9. **`github_md_url` / `github_md_raw_url`:** from `url_map.json` keyed by `doc_url` first, then
   `patch_id`; blank if no map or no hit.
10. **`doc_format`** = `doc_file_ext` without the dot (`pdf`/`docx`/`doc`).
11. **`group_key`:** `app_name_abbrev:pkg_ns:patch_ver` **only when `patch_ver` is set**, else `""`.
    *(This is v1's key — note it retains the version; see §9.4 for the vdocs design's version-free
    variant and the decision to make.)*
12. **`noise_type`:** if `doc_url` ∈ shared-URLs → `classify_noise(url)` (`vba_form` for VBA/benefits
    domains, `va_ref` for non-`/vdl/` paths, else `""`); non-shared → `""`.
13. **`companion_url`:** the paired-format URL from the companion map (PDF↔DOCX), else `""`.
14. **`doc_slug`:** `make_doc_slug(doc_filename)` = filename stem, lowercased, non-alnum→`_`, trimmed.
    PDF/DOCX pairs therefore share a slug.

### 4.3 Pass 3 — group-key peer inference

For rows still missing `doc_code`: among the *labelled, non-noise* peers in the same `group_key`
(excluding the row's own slug), if they **unanimously** agree on a single `doc_code`, adopt it (and its
label). Only 100% consensus assigns — any disagreement leaves it blank.

### 4.4 Pass 4 — manual overrides (human-reviewed residuals)

Applied after all automation so explicit human decisions win:
- `doc_slug ∈ MANUAL_NOISE` → `noise_type="test_document"`, clear code/label.
- `doc_slug ∈ MANUAL_OVERRIDES` → set `(doc_code, doc_label)` to the reviewed value (overrides any
  wrong auto-code).

### 4.5 Pass 5 — canonical label + provenance

- **Canonical `doc_label`** (`apply_canonical_label` + `doc_labels.yaml`): collapse label drift so each
  `doc_code` maps to one canonical `doc_label`; the original per-row label, when it differed, is kept
  in **`doc_subtitle`**.
- **`doc_labelling`:** `"manual"` if `doc_slug ∈ MANUAL_SLUGS` (the 154 human-reviewed slugs), else
  `"code"`.

Finally write the 34 columns in the fixed order (§5) with `csv.DictWriter(extrasaction="ignore")`, plus
`vdl_inventory_schema.json` (per-field type manifest).

### 4.6 Stage C — system classification (`classify_vista_type.py`)

A second script re-reads the enriched CSV and **inserts two columns immediately after `app_status`**:
`system_type` and `cots_dependent`. Both are pure dict lookups keyed on `app_name_abbrev`:

- **`system_type`** = `SYSTEM_TYPE[app_name_abbrev]` — a curated 196-app map into **11 categories**
  (e.g. `VistA`, `VistA + GUI`, `VistA + COTS`, `VistA + middleware`, `Data patch`, non-VistA buckets).
  Unmapped → `"unclassified"` (should be empty given full coverage).
- **`cots_dependent`** = membership in `COTS_DEPENDENCY = {MD, YS, ROI, CPT, DRG, PREM}`.

Idempotent: inserts only if the columns are absent, overwrites values on re-run, writes a `.csv.bak`.
Result = the **36-column** final inventory. The classification *criterion* (the KIDS test) and its
edge cases are in §8(d); the 196-app map is reference data → vdocs `registries/system-types` (§9.3).

---

## 5. Column reference (v1's 34 + 2 Stage C = 36 — the information floor; vdocs may add more)

Output order is **fixed** (this is part of the contract):

| # | Column | Type | Null? | Derivation / values |
|---|---|---|---|---|
| 1 | `section_name` | str | no | from crawl |
| 2 | `section_code` | str | no | `SECTION_CODE[section_name]` ∈ {CLI,FIN,GUI,INF,MON} |
| 3 | `app_name_full` | str | no | crawl app name (parens stripped) → package-master canonical_name |
| 4 | `app_name_abbrev` | str | no | parens code → `APP_ABBREV_FALLBACK` → `pkg_ns` |
| 5 | `canonical_pkg` | str | no | package-master canonical_pkg (consolidated identity), else abbrev |
| 6 | `doc_subject_raw` | str | yes | original `app_name_full` when it differed from canonical |
| 7 | `doc_search_aliases` | str | yes | `|`-joined original spellings corrected by typo fixer |
| 8 | `app_status` | str | no | active / archive / decommissioned |
| 9 | `decommission_date` | str | yes | `YYYY-MM` |
| 10 | `pkg_ns` | str | yes | VistA namespace from patch parse (or master fill / app_code) |
| 11 | `patch_ver` | str | yes | version string; **do not string-sort** — use major/minor |
| 12 | `patch_ver_major` | int | yes | |
| 13 | `patch_ver_minor` | int | yes | 0 when major-only |
| 14 | `patch_num` | int | yes | |
| 15 | `patch_id` | str | yes | `NS*V*P` (patch) or `NS*V` (anchor) |
| 16 | `patch_id_full` | str | yes | full multi-NS prefix; set only when `multi_ns=1` |
| 17 | `multi_ns` | bool | no | `"0"`/`"1"` in CSV |
| 18 | `group_key` | str | yes | `app_name_abbrev:pkg_ns:patch_ver` (when ver known) |
| 19 | `doc_code` | str | yes | normalized doc-type abbreviation (RN, TM, DIBR, …) |
| 20 | `doc_label` | str | yes | canonical full label from `doc_labels.yaml` |
| 21 | `doc_subtitle` | str | yes | original label when it differed from canonical |
| 22 | `doc_layer` | str | no | anchor / patch / plain |
| 23 | `doc_labelling` | str | no | code / manual |
| 24 | `doc_title` | str | no | mojibake- and typo-corrected title |
| 25 | `doc_filename` | str | no | web filename (not a FileMan file) |
| 26 | `doc_slug` | str | no | URL-safe stem; PDF/DOCX pairs share it |
| 27 | `doc_format` | str | no | pdf / docx / doc |
| 28 | `doc_subject` | str | yes | qualifier stripped from title (best-effort) |
| 29 | `noise_type` | str | no | "" / vba_form / va_ref / test_document |
| 30 | `app_url` | str | no | from crawl |
| 31 | `doc_url` | str | no | from crawl (resolved) |
| 32 | `companion_url` | str | yes | paired-format URL |
| 33 | `github_md_url` | str | yes | blob URL of the markdown counterpart |
| 34 | `github_md_raw_url` | str | yes | raw.githubusercontent URL |

**+2 from Stage C (§4.6), inserted after `app_status` → 36-column final order:**

| pos | Column | Type | Null? | Derivation / values |
|---|---|---|---|---|
| 8a | `system_type` | str | no | `SYSTEM_TYPE[app_name_abbrev]`; 11 categories; `"unclassified"` if unmapped |
| 8b | `cots_dependent` | bool | no | `app_name_abbrev ∈ {MD, YS, ROI, CPT, DRG, PREM}` |

**+ vdocs-native column(s) (§9.4 decision); column order is free under the superset contract:**

| Column | Type | Null? | Derivation / values |
|---|---|---|---|
| `anchor_key` | str | yes | `app_name_abbrev:pkg_ns:doc_code` (version-free, §6.6); the design's anchor-document identity, consumed by `consolidate`. A vdocs addition beyond v1 — add more such fields freely where they improve enrichment. |

---

## 6. Vocabularies & regexes

These are reproduced verbatim from v1; they are *data*, and in vdocs they belong in version-controlled
`registries/` (design §9.6/§9.7), not inline in code.

### 6.1 `SECTION_CODE`
```
Clinical → CLI ; Financial-Administrative → FIN ;
VistA/GUI Hybrids (formerly HealtheVet) → GUI ; Infrastructure → INF ; Monograph → MON
```

### 6.2 Patch-identity regexes
```python
PATCH_A    = ^(?:[A-Za-z ]+\s)?([A-Z][A-Z0-9]+)\*([\d]+(?:\.[\d]+)?)\*(\d+)(?:/\d+)*\s*(.*)   # NS*V*P remainder
PATCH_FULL = ^(?:[A-Za-z ]+\s)?([A-Z][A-Z0-9]+\*[\d.]+\*\d+(?:/[A-Z][A-Z0-9]+\*[\d.]+\*\d+)*)  # multi-NS prefix
MULTI_NS_RE= [A-Z][A-Z0-9]+\*[\d.]+\*\d+/[A-Z][A-Z0-9]+\*                                       # multi-NS detector
PATCH_B    = (?:[Vv]ersion\s+|[Vv](?=\d)|Release\s+)(\d+(?:\.\d+)*)|\b(\d+\.\d+(?:\.\d+)?)\b    # non-VistA version
FNAME_VER  = ^[a-z0-9]+_(\d+)_(\d+)                                                             # filename version
FNAME_PATCH= _p?(\d{3,5})_                                                                      # filename patch
ABBR_RE    = \s*\(([A-Z0-9/+\-]{1,10})\)\s*$                                                    # app parens code
```

### 6.3 `DOC_TYPE_PATTERNS` (title classifier — **order is the priority**, most-specific first)
Reproduced verbatim from v1 (`enrich_inventory.py` lines 242–337); each entry is `(regex, doc_code, canonical_label)`.
The full ordered list is in [Appendix §10.4](#104-doc_type_patterns-verbatim). Key ordering rules:
DIBR before Installation; Setup/Config and Quick-Reference before generic "Guide"; User Manual before
User Guide; possessive/plural variants (`User.?s?`, `Administrator.?s?`); the VDL typo `Productions
Operations Manual`; numeric lab series `^\d{3}:` → Supplement; VBA-form patterns last.

### 6.4 `_SLUG_SUFFIX_MAP` + `_APP_SPECIFIC_SUFFIX` (filename fallback classifier)
Used only when the title classifier returns nothing. Suffix = last `[_-]([a-z]{2,8})` of the stem.
Full map in [Appendix §10.5](#105-_slug_suffix_map-verbatim). Notable: `_tg → Training Guide` (NOT
Technical Guide — 100% of corpus); `_manual → Technical Manual`; `_pm → API/Programmer Manual`;
app-specific `(PRC,signed)→POM`, `(TMP,signed)→RS`.

### 6.5 `APP_ABBREV_FALLBACK`, `MANUAL_OVERRIDES`, `MANUAL_NOISE`, `MANUAL_SLUGS`
Curated maps (~44 abbrev fallbacks; ~90 manual overrides; 2 manual-noise slugs; 154 manual slugs).
Verbatim in [Appendix §10.6](#106-curated-override-maps-verbatim). These encode human review of the
residual label-gap cases (v1 `vdl_inventory_label_gaps_residual.md`, 2026-03-30).

### 6.6 External YAML vocabularies
`doc_labels.yaml`, `package_master.yaml`, `typo_corrections.yaml` — see [§10.1–§10.3](#10-appendix--external-vocabulary-files).

---

## 7. Acceptance — no information loss + reference distributions

The contract is **superset, not identity** (see header). Correctness has two parts:

1. **No information loss (binding).** Every v1 signal in §5 is present in the vdocs output with at least
   v1's correctness: `noise_type`, `doc_layer`, `doc_code`/`doc_label`, patch identity (incl.
   `multi_ns`/`patch_id_full`), `companion_url`, `doc_slug`, `group_key`, `system_type`, etc. vdocs may
   add more columns/fields/structure; it may **not** drop or weaken any of these.
2. **Reference distributions (sanity targets, not a diff gate).** Run against the same crawl, the
   vdocs output should land **at or above** these figures (more-correct enrichment may legitimately
   shift them — e.g. fewer blank `doc_code`). Investigate large regressions; small improvements are fine.

**All figures below were measured directly from the on-disk `vdl_inventory_enriched.csv` on
2026-06-01** and supersede any differing tallies in the v1 narrative docs (which are stale — e.g. the
docs state `anchor 1,918 / plain 3,332`; the actual file is `anchor 3,466 / plain 1,784`).

- **Rows:** 8,834 (1:1 with raw — enrichment never adds/drops rows). **Columns:** at least the v1
  signals of §5 (34 enrich / 36 with Stage C); vdocs adds `anchor_key` and may add more. Column order
  and on-disk shape are vdocs's choice.
- **`noise_type`:** `""`=7,491 · `vba_form`=1,192 · `va_ref`=149 · `test_document`=2.
- **`doc_layer`:** anchor=3,466 · patch=3,584 · plain=1,784.
- **`doc_format`:** pdf=5,097 · docx=3,730 · doc=7.
- **`doc_labelling`:** code=8,526 · manual=308.
- **`section_code`:** CLI=5,790 · FIN=1,485 · GUI=780 · INF=777 · MON=2.
- **`patch_id` filled:** 6,902. **`companion_url` filled:** 7,422.
- **`doc_code` leaders:** RN=1,598 · DIBR=1,342 · FORM=1,192 · UG=884 · UM=880 · IG=821 · TM=723 ·
  CRU=336 · (blank)=151 · VDD=145.
- **Stage C:** `system_type` 100% filled, **0 `unclassified`** (the 196-app map covers every abbrev);
  `cots_dependent` true only for {MD, YS, ROI, CPT, DRG, PREM}.

A diff against the committed reference CSV (modulo crawl-date drift in `doc_url`/new docs) is the gate.
Recommended: pin a captured raw `vdl_inventory.csv` fixture so enrichment is testable offline and the
distributions above become exact unit assertions.

---

## 8. Lessons learned (the trial and error)

### Crawling
- **Relative links + redirects:** resolve level-3 doc hrefs against the application page's **final**
  response URL, giving `…/vdl/documents/…`. Resolving against the host root 404s every document.
- **Descriptive User-Agent is required**; bare clients get inconsistent/blocked responses.
- **Politeness/robustness:** 1.5 s delay + retry on 500/502/503/504 with backoff; a non-200 section/app
  is skipped with a WARN, never aborts the crawl.
- **De-dup nav repetition** by `secid`/`appid`.
- **Format-as-link-text:** the document title lives in a sibling table cell, not the anchor text (the
  anchor text is "DOCX"/"PDF").

### Inventory / noise
- **Chrome links pollute a naive crawl.** The same VBA benefit forms and non-VDL VA references appear
  on hundreds of pages. The robust, corpus-global signal is **shared URL = appears on >1 page → noise**;
  domain/path rules then classify it `vba_form` (VBA/benefits hosts) or `va_ref` (path lacks `/vdl/`).
  ~1,343 of 8,834 rows are noise. Noise is **flagged, never deleted**.
- **Companion pairing:** DOCX and PDF of one document are separate rows; group by URL-minus-extension to
  fill `companion_url` and share `doc_slug`.

### Patch identity
- **Multi-namespace titles** (`SD*5.3*603/WEBP*1*1`) are real: take the first NS for `patch_id`, keep
  the full slash-joined prefix in `patch_id_full`, set `multi_ns=1`.
- **Anchor vs patch vs plain:** version-without-patch = `anchor` (the consolidation target); with patch
  number = `patch`; neither = `plain` (forms, undated refs).
- **Fallback chain for version/patch:** title → filename `app_major_minor` → filename `_pNNNN_`.
- Re-derive the app code from the app-name parens (+ fallback map); the raw `app_code` column is **not**
  trusted/carried.

### Doc-type classification
- **Title before filename**, and **specificity ordering matters** (DIBR before Installation; Setup/
  Config & Quick-Ref before generic Guide; User Manual before User Guide). Wrong order mislabels en masse.
- **Filename suffixes are ~80%-validated, not certain** — some suffixes mean different things per app
  (`_signed`, `_tg`), hence `_APP_SPECIFIC_SUFFIX` and the manual residual layer.
- **Group-key peer inference** rescues unlabelled docs only on unanimous peer agreement.
- **Manual residual layer** (154 reviewed slugs → 308 `manual`-labelled rows) is unavoidable at this
  scale; it must be applied *after* automation and recorded (`doc_labelling`) for auditability.
- **Canonical label collapse** (`doc_labels.yaml`) removes wording drift per `doc_code`; the original
  wording is preserved in `doc_subtitle`.

### Text quality
- **Mojibake repair first** (before abbrev/parse), then **typo corrections**, preserving original
  spellings in `doc_search_aliases` so search still matches.

### Package identity
- **Package master** canonicalizes `app_name_full`/`pkg_ns` and records post-consolidation identity
  (`canonical_pkg`, e.g. `RUM → KMPR`); per-row divergence kept in `doc_subject_raw`.
- **App display code ≠ M namespace** (diverge in 27 apps / 16%: ADT↔DG, CPRS↔OR). Keep both:
  `app_name_abbrev` (VDL display) and `pkg_ns` (M namespace).
- **Slash/`+` in app codes** (`SSO/UC`, `AR/WS`, `DRM+`) — the parens regex permits them; **sanitize
  slashes → `_` before any filesystem path** (`AR/WS` → `ar_ws`).
- **Non-breaking space (` `/U+00A0)** in titles defeated `\bPOM\b` on ~31 JLV titles — strip Unicode
  whitespace (the NFC/ftfy pass does this), not just ASCII.
- **Possessive forms:** `User's Guide` broke a bare `User\s+Guide` regex → `User.?s?\s+Guide`.

### Acquisition URL (validates the vdocs fix)
- v1 hit a **`/documents/` vs `/vdl/documents/`** URL-pattern bug that caused **6,935 failed fetch
  attempts** before adding a URL-probe (HEAD) step. This is the *same* relative-base bug vdocs caught
  in its real-fetch test (commit `209361a`); the spec mandates resolving against the final page URL.

### System classification (Stage C — the KIDS test)
- **The sole criterion is the KIDS test:** an app is `VistA` iff it is an M package, KIDS-deployed, and
  runs server-side on the M VistA server. Connecting to VistA, carrying a `pkg_ns`, or appearing in the
  VDL does **not** make it VistA.
- **Phantom namespaces:** non-VistA apps carry a `pkg_ns` for catalog tracking (MED→TIU because it
  *calls* TIU; PECS→PREC). Classify by Technical-Manual content, not by namespace.
- **VDL bundling forces hybrid categories:** `VistA + GUI` (CPRS, MAG), `VistA + COTS` (MD, YS, ROI),
  `VistA + middleware` (XOBV/VistALink). The M side passes KIDS; the other side does not.
- **Data-only KIDS patches** (CPT, ICD, DRG, LEX) ship via KIDS but carry data/licensed terminology,
  not M code → `Data patch`.
- **Interface-package traps:** DVBA (AMIE) is VistA, not VBA (CAPRI is the separate VBA client); IVMB
  (HEC interface) is VistA. Name alone is never sufficient — read the TM.

### Output shape
- **As-built ≠ narrative.** The docs say "29 columns"; the scripts emit **34** (enrich) → **36** (after
  classify). Trust the code. Column order is fixed and canonical (§5).
- **Never string-sort `patch_ver`** (`"5.3" < "10"` lexically) — sort by
  `(patch_ver_major, patch_ver_minor, patch_num)` integers.

---

## 9. Mapping onto the vdocs architecture

This spec *is* the **inventory medallion** — its own bronze→silver→gold track, independent of the
document medallion and gating it at `fetch` (vdocs design §4, §8): **inv-bronze** = `crawl` →
`catalog.raw`; **inv-silver** = `catalog` → `catalog.enriched` (this spec's enrichment); **inv-gold** =
`serve-inventory` → the **gold inventory** (curated/validated/queryable selection surface + the fetch
gate, joined with `state.db:acquisitions`, §9.5). The lake path is `inventory/{bronze,silver,gold}/…`,
*not* `documents/bronze/…`. Required changes to the current vdocs stages so they implement this from the
outset:

### 9.1 `kernel/http`
Add a descriptive **User-Agent**, **retry/backoff on 5xx**, follow redirects, and **return the final
URL**. Expose an inter-request **delay** (config). (Design §9.2 already lists `kernel/http`.)

### 9.2 `crawl` stage
- Resolve level-3 links against the **final** application-page URL (already fixed: commit `209361a`).
- Honor the config delay; skip non-200 pages with a WARN; de-dup by secid/appid (already done).
- Output `inventory/bronze/catalog.raw.{json,csv}` = the §3.5 raw inventory (inv-bronze).

### 9.3 `catalog` stage = the enrichment
Implement passes 1–5 **and Stage C** as **pure functions** (`catalog_pure.py`) + a thin driver,
producing the §5 **36-column** enriched inventory as `inventory/silver/catalog.enriched.{json,csv}`
(inv-silver, plus the schema JSON); `serve-inventory` then promotes it to the gold inventory (inv-gold)
behind the fetch gate. The current vdocs `catalog` is a thin subset (patch id, doc_type, group_key, drift) — it
must be extended to the full column set, the 5-pass ordering, noise classification, companion pairing,
canonical labels, the manual/peer layers, and `system_type`/`cots_dependent`. **Vocabularies live in
`registries/`** (the discovery-is-data tenet): `registries/doc-types` (DOC_TYPE_PATTERNS + suffix map),
`registries/packages` (package_master + abbrev fallback), `registries/doc-labels`,
`registries/typo-corrections`, `registries/manual-labels` (overrides/noise/slugs),
`registries/noise-domains` (VBA/benefits hosts), `registries/system-types` (SYSTEM_TYPE + COTS). `catalog`
`requires` them.
- **Mojibake fidelity — DECIDED: adopt ftfy for the inventory text pass, now unified in the kernel.** The
  `doc_title`/`doc_subject`/`app_name(_full)` repair uses **`ftfy.fix_text(text, normalization="NFC")` +
  nbsp-strip** (§4.1) — `ftfy` is a dependency. The two mojibake fixers were unified onto ftfy (§9.2):
  `kernel/text.repair_mojibake` *is* now that exact ftfy call, so `catalog` delegates to it (no separate
  custom path remains to diverge). The inventory pass adds nbsp-stripping on top.

### 9.4 Decisions (resolved 2026-06-01)
- **`group_key` granularity — DECIDED: keep both keys.** Provide v1's `group_key = app:pkg:patch_ver`
  (clusters patches within one version) **and** the design §6.6 version-free `anchor_key =
  app:pkg:doc_code` (clusters every version of a logical document under one living anchor, consumed by
  `consolidate`). Both carry distinct, useful signal, so vdocs keeps both rather than choosing. With the
  superset contract (§7) there is no byte-diff to preserve, so column order is free — place `anchor_key`
  wherever is clearest (e.g. beside `group_key`).
- **`noise_type` vs. `drift_status` — DECIDED: two separate columns.** Noise classification stays in
  `catalog` enrichment (§4.2) as `noise_type` (a static property: genuine doc vs. chrome/form). It is
  orthogonal to and kept separate from the §7.6 `drift_status` (a temporal property: changed since last
  crawl). Neither is folded into the other.

### 9.5 Selection, fetch & acquisition status (separate, later)
`fetch` consumes the enriched inventory and downloads **only a selected subset** (never blind/all). The
genuine candidate set = rows with `noise_type==""`; selection (by app/section/doc_type/group, or a
curated list) is applied before fetch. This spec's inventory is the basis for *deciding* what to fetch.

**The inventory is the gatekeeper; fetch status is a separate system of record.** Per-document fetch
status (fetched-or-not, last-attempt/fetched dates, success/failure, http status, retries, resulting
`sha256`, error) is mutable, action-derived state — **not** written back into `catalog.enriched` (that
would break `catalog` idempotency and churn the artifact). It lives in a dedicated **`acquisitions`**
table in `state.db`, keyed by the inventory **stable `doc_id` = `app_code:doc_slug`** (vdocs design §5.5,
where the full schema lives). The inventory stays the gatekeeper in three senses: (1) nothing is fetched
that isn't a green `noise_type==''` row; (2) `doc_id` is the join key; (3) the operational "inventory +
fetch status" an operator inspects is the **join** `enriched ⋈ acquisitions` (`vdocs fetch --status` / an
`inventory_status` view), not status baked into the inventory. `raw/index.json` is a derived projection
of `acquisitions`. Fetch is naturally incremental (skip `status==fetched` unless stale) and is where
`CHANGED_IN_PLACE` drift is decided (stored `acquisitions.sha256` vs. a fresh fetch — design §7.6).

### 9.6 Suggested build order
1. `kernel/http` hardening (UA/retry/redirect/final-URL/delay) + tests.
2. `crawl` → raw inventory (verify against live VDL: section/app/doc counts).
3. Port vocabularies into `registries/`.
4. `catalog` passes 1–5 as pure functions, TDD'd against a pinned raw-inventory fixture, asserting the
   §7 distributions.
5. Validate the enriched CSV diffs clean against v1's reference.

---

## 10. Appendix — external vocabulary files

Authoritative sources (copy into vdocs `registries/` rather than inlining in code):
`~/projects/vista-docs/data/{doc_labels,package_master,typo_corrections}.yaml`,
`scripts/enrich_inventory.py` (the inline maps), `scripts/classify_vista_type.py` (system map).

### 10.1 `doc_labels.yaml` — canonical label per doc_code (31 entries, verbatim)

`apply_canonical_label(code, current, table)` returns `(canonical, subtitle)`: unknown/empty code →
pass current through; known + current differs → `(canonical, current)`; matches → `(canonical, "")`.
The `# §3.5 drift` markers are the 5 codes whose most-frequent label was deliberately overridden.

```yaml
labels:
  AG:     "Administrator's Guide"
  API:    "API Manual"
  APX:    "Appendix"
  CFG:    "Configuration Guide"               # §3.5 drift: drop "Setup and "
  CRU:    "Clinical Reminder Update"
  CVG:    "Conversion Guide"
  DESC:   "Description Document"
  DG:     "Developer Guide"
  DIBR:   "Deployment, Installation, Back-Out, and Rollback Guide"
  FAQ:    "Frequently Asked Questions"
  FORM:   "VBA Form"
  IG:     "Installation Guide"
  IG-IMP: "Implementation Guide"
  INT:    "Interface Specification"           # §3.5 drift: not "Interface Feed Guide"
  PDD:    "Patch Description Document"
  POM:    "Production Operations Manual"
  QRG:    "Quick Reference Guide"
  REF:    "Reference"                          # §3.5 drift: not "Interface Toolkit"
  RN:     "Release Notes"
  RS:     "Requirements Specification"
  SG:     "Security Guide"
  SG-SET: "Setup Guide"
  SM:     "Site Manual / Systems Management Guide"
  SUP:    "Supplement"
  TG:     "Technical Guide"
  TM:     "Technical Manual"
  TRG:    "Training Guide"
  UG:     "User Guide"                         # §3.5 drift: not "Manager/ADPAC Guide"
  UM:     "User Manual"                         # §3.5 drift: not "Clinical Coordinator Manual"
  VDD:    "Version Description Document"
  WF:     "Workflow Guide"
```

### 10.2 `package_master.yaml` — abbrev → canonical identity (168 entries)

`PackageEntry(abbrev, canonical_name, pkg_ns, canonical_pkg, aliases, notes)`. Aliases each register as
their own `by_abbrev` key (so a legacy abbrev resolves to the survivor). **Three consolidations:**
`RUM→KMPR`, `SAGG→KMPS`, `SSO/UC→SSO`. Schema + the consequential entries (verbatim):

```yaml
<abbrev>:
  canonical_name: <str, required>
  pkg_ns: <M namespace, may be "">
  canonical_pkg: <surviving abbrev; = self unless consolidated>
  aliases: [<other abbrevs resolving here>]
  notes: <optional>
# --- representative / divergent entries ---
ADT:   {canonical_name: "Admission Discharge Transfer", pkg_ns: "DG", canonical_pkg: "ADT"}
AR/WS: {canonical_name: "Pharmacy: Automatic Replenish / Ward Stock", pkg_ns: "PSGW", canonical_pkg: "AR/WS"}
CPRS:  {canonical_name: "Computerized Patient Record System", pkg_ns: "OR", canonical_pkg: "CPRS"}
DRG:   {canonical_name: "Diagnostic Related Group (DRG) Grouper", pkg_ns: "ICD", canonical_pkg: "DRG"}
DRM+:  {canonical_name: "Dentistry", pkg_ns: "DENT", canonical_pkg: "DRM+"}
KMPR:  {canonical_name: "Resource Usage Monitor", pkg_ns: "KMPR", canonical_pkg: "KMPR", aliases: ["RUM"]}
KMPS:  {canonical_name: "Statistical Analysis of Global Growth", pkg_ns: "KMPS", canonical_pkg: "KMPS", aliases: ["SAGG"]}
MED:   {canonical_name: "Mobile Electronic Documentation", pkg_ns: "TIU", canonical_pkg: "MED"}  # phantom ns (calls TIU)
PECS:  {canonical_name: "Pharmacy ...Enterprise Customization System", pkg_ns: "PREC", canonical_pkg: "PECS"}
SSO:   {canonical_name: "Single Signon/User Context", pkg_ns: "XUSC", canonical_pkg: "SSO", aliases: ["SSO/UC"]}
```
`scripts/seed_package_master.py` produces a *starting guess* (`package_master.seed.yaml`, most-frequent
name/ns + `⚠` divergence comments); the hand-curated `.yaml` is authoritative. **`app_name_abbrev`
(VDL display code) ≠ `pkg_ns` (M namespace) in 27 apps (16%)** — e.g. ADT/DG, CPRS/OR.

### 10.3 `typo_corrections.yaml` — field-scoped spelling fixes (3 entries, verbatim)

`apply_typo_corrections(text, field, corrections)`: for each correction whose `fields` include this
field and whose `source` is a substring, replace; return text + the replaced sources (→ `doc_search_aliases`).

```yaml
corrections:
  - {source: "Staph Aurerus",            corrected: "Staph Aureus",            fields: [doc_title, doc_subject, app_name_full]}  # MRSA, 25 rows
  - {source: "DIBORG",                   corrected: "DIBRG",                   fields: [doc_title, doc_subject]}                 # 16 HTRE/DHT rows; filename EXCLUDED
  - {source: "Health Data  Informatics", corrected: "Health Data Informatics", fields: [app_name_full, doc_title, doc_subject]}  # HDI double-space
```

### 10.4 `DOC_TYPE_PATTERNS` (47 entries, verbatim)
`enrich_inventory.py` lines 242–337 — copy verbatim. Ordered most-specific first, case-insensitive,
**first match wins**. Ordering invariants in §6.3 / §8.

### 10.5 `_SLUG_SUFFIX_MAP` (~55 entries) + `_APP_SPECIFIC_SUFFIX` (verbatim)
`enrich_inventory.py` lines 409–485 — copy verbatim. `_tg→TRG` (Training, **not** Technical);
`_manual→TM`; `_pm→API`; app-specific `(PRC,signed)→POM`, `(TMP,signed)→RS`.

### 10.6 Curated override maps (verbatim)
`APP_ABBREV_FALLBACK` (lines 125–169), `MANUAL_NOISE` (2 slugs), `MANUAL_OVERRIDES` (~90 slug→code,
lines 509–634), `MANUAL_SLUGS` (the 154 reviewed slugs = overrides ∪ noise ∪ ~60 more) — copy verbatim.

### 10.7 `classify_vista_type.py` — `SYSTEM_TYPE` (196 apps) + `COTS_DEPENDENCY` (6)
`SYSTEM_TYPE[app_name_abbrev]` → one of 11 categories (with `(M)` rationale comments per app);
`COTS_DEPENDENCY` = {MD, YS, ROI, CPT, DRG, PREM}. Copy verbatim from `scripts/classify_vista_type.py`.
See §4.6 / §8(d) for the classification *rules* (the KIDS test).
