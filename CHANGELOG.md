# Changelog

All notable user-facing changes to this project will be documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is for **what shipped**. For the *why* behind decisions
(refactors, design choices, abandoned approaches), use `CHANGES.md` instead.

## [Unreleased]

### Added

### Changed

### Fixed

- **`embed`**: stop OOM-killing the box on the full corpus. Batches are now bounded by their
  *padded* token footprint (`items × longest member`) instead of a fixed 256-item count — one long
  8k-context chunk no longer drags a whole batch up to its length (the cause of the ~20–25 GB
  spikes). Vectors also stream into `vectors.db` batch-by-batch rather than accumulating every
  vector in memory first.
