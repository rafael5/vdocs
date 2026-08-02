# Session summaries — the narrative record

One file per Claude session that did `vdocs` work, newest first:
`YYYY-MM-DD-<slug>.md`.

**What these are.** The human-readable story of a working session — what was attempted, what
actually happened, what was learned, and **what was got wrong and corrected**. Written to be
read back months later by a person, not parsed by a gate. They carry the connective tissue that
proposals, trackers, and commit messages deliberately leave out: why a question was asked, which
alternative was rejected, where a diagnosis went sideways.

**What these are not.** Not a source of truth. Decisions live in `proposals/` and `adr/`, live
status in the trackers, durable lessons in `memory/`, and what actually shipped in git history.
A summary cites those freely; nothing should cite a summary as authority.

**The folder is frozen.** A point-in-time record must not be rewritten to keep its links live —
that would falsify it. If a file it mentions later moves, or a claim in it turns out wrong, the
correction goes in a **later entry**, never by editing an earlier one.

*(Convention adopted from the vista-forge org's `docs/session-summaries/`, which is scoped to
that org's work; this is the same practice applied to this repo.)*

## Log

| Date | Session |
|---|---|
| 2026-08-01 | [The pipeline audit, and P1: a corpus that had been quietly six documents short](2026-08-01-pipeline-audit-and-p1.md) — an end-to-end adversarial audit read from the executed code (not the docs) produced a per-stage table, an artifact ledger, a Go-port reference, an MCP accuracy method and a 16-row risk register; its one *measured* defect was that `raw/index.json` is sha-keyed, so six documents with byte-identical siblings had collapsed out of the corpus while still reporting `fetched`. P1 re-derived the index by `doc_id` from acquisitions ⋈ admitted targets, added the acquisition-chain gate no stage had ever performed, and refused non-DOCX payloads at the CAS door. Three things went wrong worth reading: the audit had **named the wrong six doc_ids** (the survivors of each pair, eyeballed rather than derived); my group-count prediction was wrong; and the live acceptance run — not the audit, not the 1,132 tests — found a **WAL corruption bug** in a shared kernel primitive that had been silently reachable by three stages. |
