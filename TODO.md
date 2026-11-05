# TODO

Lightweight backlog for this project. For longer-form planning, use `docs/`.

## Now

## Next

- **`convert` and `enrich` don't re-run when the registry files they read change.** `convert`
  reads `converter-routing/converter-routing.yaml` and `enrich` reads the profile registries
  (`app-profiles`, `function-domains`, `doc-user`), but neither puts them in its input fingerprint.
  An edit leaves the stage skipping as "inputs unchanged" until someone forces it. It's the same gap
  b9c6f6d closed for `catalog`/`consolidate` and a5b4363 for `index`. Fix it the way `fetch` already
  does in `extra_input_fps`, by fingerprinting just the files the stage reads, not the whole
  `registries` tree: declaring the tree would make `convert` redo its ~17-minute run after any
  registry edit. Test first: a registry edit must change the stage's input fingerprint. (Found
  2026-11-05; `fetch` checked and is already covered.)
- **Completeness reads COMPLETE while 219 admitted records have no gold document.** Measured
  2026-11-05: 152 archived sole survivors, 52 DOCX the doc-type policy keeps and 9 PDF-only
  documents were never fetched; 5 fetches failed and 1 was rejected as bad content. The verdict
  counts what is admitted, not what is held, and `fetch` downloads only its current selection, so
  re-running does not close the gap. Decide whether admitted-but-not-held should count against the
  verdict, and whether the fetch selection should cover the admitted set.

## Later

- **A few revision tables still lose their dates.** After 9f9df51, 64 revision-date cells stay
  unnormalized. Most aren't dates (23 are `REDACTED`), but two real problems remain:
  - three documents' tables put the change description in the date column:
    `SD/vse_gui_1_6_user_guide` (17 rows, so the document gets no revision date),
    `ACKQ/ackq3_0p13_tm` and `PSX/psx_2_p68_um_cp`;
  - numeric spans written with a dash (`04/12/2016 – 04/14/2016`, `03/14/2016- 03/15/2016`) and a
    few typos (`05/190/2026`, `07/28/2-22`, `04/082004`, `Dec2 004`).

## Done
