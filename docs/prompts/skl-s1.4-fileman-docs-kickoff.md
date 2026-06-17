# Kickoff — SKL S1.4: retire the `fileman-docs` casing workaround

**Repo: `fileman-docs`.** Start a fresh session and `cd ~/projects/fileman-docs` first (one session ↔
one repo). This is the *repo half* of SKL S1 — the integration proof. The **vdocs half is done**
(2026-06-17, commit on branch `fileman-integrated-master-proposal`): `vdocs build-termbase` now emits a
generated **`Casing.yml`** Vale style that enforces canonical capitalization for the safe set only
(624 terms; English-colliding acronyms auto-vetoed). See `~/projects/vdocs/docs/skl-implementation-plan.md`
S1 + Discoveries for the *why*.

## What this kills

`fileman-docs` worked around the casing bug by hand:

- `.vale.ini` has **`Vale.Terms = NO`** (disables blanket accept.txt case-enforcement), and
- `.vale/VistA/Brand.yml` — a **hand-maintained** ~7-term substitution (`Vista→VistA`, `Fileman→FileMan`,
  `Mumps→MUMPS`, …).

That is exactly the hand-curated parallel list (tenet #13 violation) SKL exists to delete. The generated
`Casing.yml` replaces it with 624 single-sourced terms.

## Steps

1. **Refresh the termbase from vdocs** (single-sourced; never hand-edit the artifacts):
   ```bash
   cd ~/projects/vdocs && .venv/bin/vdocs build-termbase \
     --out-dir ~/projects/fileman-docs/<the vocab/style out-dir `make termbase` already uses>
   ```
   Confirm `make termbase` (the fileman-docs target) is the canonical path and use it if present — it
   should now drop **four** artifacts: `accept.txt`, `VistA.yml`, **`Casing.yml`**, `typos-extend.toml`.
   `Casing.yml` lands beside `VistA.yml` (the `.vale/VistA/` style dir).

2. **Delete the workaround:**
   - `rm .vale/VistA/Brand.yml`
   - In `.vale.ini`: **remove the `Vale.Terms = NO` line** and its explanatory comment block, and add
     `Casing` is picked up automatically (it's in the `VistA` style dir already on `BasedOnStyles`).
     Leave `Vale.Terms` **unset/at default** — `Casing.yml` now does casing precisely, so the blanket
     accept.txt enforcement stays off-by-virtue-of-being-replaced. (If `Vale.Terms` defaults to ON and
     re-introduces the CAN problem, keep it `NO` — `Casing.yml` is the real enforcer either way. Verify
     empirically with step 4.)

3. **Wire the producer note:** the `.vale.ini` comment that says "FOLLOW-UP (vdocs L0c): have
   `build-termbase` split case-safe brand terms…" is now **done** — update or remove it.

4. **Prove the gate** (`make gate` stays green) and the invariants hold:
   - **Break-test still bites:** a doc containing `Vista` / `Fileman` → `VistA.Casing` error
     (`Use the curated capitalization 'VistA'`). Don't let it regress.
   - **No false positives:** ordinary prose `the user can run it on or off site; it is an option` →
     **zero** casing errors (the bug this fixes).
   - **Coverage jumped:** casing now spans ~624 terms, not ~7. Spot-check a few (`PIMS`, `CPRS`, `KIDS`).
   - **Behavior change to expect:** `MUMPS` is **no longer** force-cased (`mumps` is a real medical
     word — deliberately vetoed). If a `Mumps→MUMPS` enforcement is genuinely wanted, that's a
     `typo-corrections.yaml` entry in **vdocs**, not a hand-edit here.

## Done

`make gate` green; `Brand.yml` gone; `Vale.Terms = NO` removed (or justified); break-test bites; no
false positives on common words; casing coverage ≫ 6. Commit + push (house cadence). Then update
`~/projects/vdocs/docs/skl-implementation-plan.md` — flip **S1.4 → ✅** and the S1 master-tracker row to
done, with a one-line changelog entry.
