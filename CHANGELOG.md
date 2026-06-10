# Changelog

All notable user-facing changes to this project will be documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is for **what shipped**. For the *why* behind decisions
(refactors, design choices, abandoned approaches), use `CHANGES.md` instead.

## [Unreleased]

### Added

- **Gold library validated `GREEN`** (`docs/gold-validation-report.md`). First end-to-end de-novo
  gated build from a real VDL fetch (no mocks): fresh crawl (8907 docs) → admission gate (1044) →
  fetched 1040/1044 → **615 `is_latest` gold docs**. B1–B5 quality/fidelity checks pass — gate
  fidelity (only Tier-A doc-types), persona columns (`app_user`/`software_class` 100%), FTS, all 9
  entity types, faceted + pre-cited search. GREEN authorizes the TUI build.

### Changed

### Fixed

- **doc-type classification**: titles using the bare abbreviation **"TM"** (e.g. *"SD PIMS Version
  5.3 TM ADDENDUM 941"*) are now classified as Technical Manual. Previously only the spelled-out
  "Technical Manual" matched, leaving such docs untyped → empty `anchor_key` → mis-collapsed in gold.
  A last-resort `\bTM\b` pattern (ordered last so full-phrase patterns win) fixes it; the 3 affected
  SD PIMS docs now anchor and version-collapse correctly.
- **`embed`**: stop OOM-killing the box on the full corpus. Batches are now bounded by their
  *padded* token footprint (`items × longest member`) instead of a fixed 256-item count — one long
  8k-context chunk no longer drags a whole batch up to its length (the cause of the ~20–25 GB
  spikes). Vectors also stream into `vectors.db` batch-by-batch rather than accumulating every
  vector in memory first.
