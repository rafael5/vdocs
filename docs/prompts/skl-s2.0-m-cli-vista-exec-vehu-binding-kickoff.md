# Kickoff — wire `m vista exec`/`status` to the live `vehu`/`foia-t12` containers (m-cli)

**Repo: `m-cli` (in `~/vista-cloud-dev/`).** Start a fresh session and `cd ~/vista-cloud-dev/m-cli`
first (one session ↔ one repo). Read `~/vista-cloud-dev/CLAUDE.md` (the **Engine access** + **Increment
Protocol** sections are mandatory), then `m-cli/CLAUDE.md`, then the driver-contract memory
(`~/vista-cloud-dev/docs/memory/m-driver-conformance.md` + `m-cli/docs/memory/MEMORY.md`). Follow the M
skills + the vista-cloud-dev Increment Protocol (persist→commit→push at every verified increment) and
the **driver-stack-only** rule — the whole point is to exercise the stack, never sidestep to raw
`docker exec`.

## Why this matters (the originating need)

The `vdocs` SKL program's S2.2 (`docs/prompts/skl-s2-kickoff.md` in the `vdocs` repo) needs to read the
live FileMan **Data Dictionary** — `file #200 → "NEW PERSON"`, field/global maps — to seed the entity
catalog (decision Q6: live DD spine). The systems are up and the DD is populated (verified 2026-06-17:
`vehu` YDB-VistA + `foia-t12` IRIS-VistA, both healthy; `^DIC(200,0)` piece 1 = `NEW PERSON`). The
sanctioned read path is `m vista exec` — **but it doesn't reach the container.** Fixing that unblocks
the SKL DD seam (and ad-hoc live-VistA inspection generally).

## The bug (reproduce)

```
m vista exec --engine ydb --transport docker 'W $ZV' -o json     # → ok:true, "stdout":"" (empty!)
m vista status --engine ydb --transport docker                   # → running:false, healthy:false
```
…even though `docker ps` shows `vehu` Up/healthy. Same empty result for the real target
`'W $P($G(^DIC(200,0)),"^",1)'`. The command "succeeds" but never touches `vehu`.

## Root cause (already traced — confirm, don't re-derive from scratch)

`m-cli/vista_cmd.go` → `vistaConn.build()` calls:
```go
cl := mdriver.NewClient(bin, v.Engine, v.Transport, nil, nil)   // connArgs = nil
```
The connection target (**which container**) is *not* passed — by design the comment says it "is read by
the driver from its `M_<ENGINE>_*` environment." The **m-ydb driver already supports it**:
`m-ydb/internal/config/config.go` → `Transport env:"M_YDB_TRANSPORT"` and
`Container env:"M_YDB_CONTAINER"` (docker transport: the container to exec into). The m-iris driver has
the analogous `M_IRIS_TRANSPORT` / `M_IRIS_CONTAINER`.

**But nothing sets `M_YDB_CONTAINER=vehu` / `M_IRIS_CONTAINER=foia-t12`** — not `.envrc`, not an m-cli
profile, and `vista_cmd.go` passes `nil` connArgs. So the docker transport has no target → no-op. This
is the inconsistency with `m test`, which targets the container via an explicit `--docker vehu` flag;
`m vista exec`/`status` has **no such flag** and relies on ambient env that is never populated.

## The fix — leaf-first, smallest thing that works first

**Step 0 — confirm the driver is fine (m-ydb leaf; likely no change).** Prove the m-ydb driver reaches
`vehu` when the env IS set — a one-liner through the stack:
```
M_YDB_TRANSPORT=docker M_YDB_CONTAINER=vehu m vista exec --engine ydb 'W $P($G(^DIC(200,0)),"^",1)'
```
Expect `NEW PERSON`. If that works, the driver needs **no change** — the gap is purely m-cli wiring.
(If it does *not* work, the bug is deeper in m-ydb's docker transport — fix the leaf repo first in its
own session, then return here.)

**Step 1 — decide the m-cli wiring (this is the real fix; pick per the maintainers' taste, TDD):**
- **(A) Explicit flag parity (recommended):** add `--container`/`--docker` (and consider `--instance`)
  to `vistaConn` in `m-cli/vista_cmd.go`, and pass it to the driver — either via `mdriver.NewClient`'s
  `connArgs`, or by exporting `M_<ENGINE>_CONTAINER` for the driver process. Mirrors `m test --docker
  vehu` so the two engine-access surfaces are consistent and the target is explicit/discoverable.
- **(B) Instance-profile resolution:** if/when m-cli grows an `[instance]` profile (driver-contract §3:
  "m-cli passes the active instance profile as `M_<ENGINE>_*` env"), have `vista exec`/`status` resolve
  the active profile (e.g. `vehu`, `foia-t12`) into the driver env. Cleaner long-term; bigger change.
- **(C) Documented env (fast unblock, not a real fix):** just document that the caller exports
  `M_YDB_TRANSPORT=docker M_YDB_CONTAINER=vehu` (IRIS analog). Acceptable as a stopgap the vdocs S2.2
  seam can use immediately (vdocs sets the env when it shells out), but the flag/profile is the durable
  fix — don't stop at (C) if the maintainers want parity.

TDD: write the failing test first (a `vista_cmd` unit test asserting the container reaches the driver
client / the env is emitted), implement, then the live integration check below. `make check` /
`make gates` green before commit (incl. the engine-access scan — the fix must keep using the driver
stack, not hand-rolled `docker exec`).

## Acceptance / done

- `m vista exec --engine ydb --transport docker '<cmd>'` (with the chosen targeting: flag, profile, or
  env) returns real output: `W $ZV` → a YottaDB version string; `W $P($G(^DIC(200,0)),"^",1)` →
  `NEW PERSON`.
- `m vista status --engine ydb …` → `running:true healthy:true version:<…>`.
- The **IRIS** path works too: `m vista exec --engine iris --transport docker 'W $ZV'` against
  `foia-t12` (and `^DIC(200,0)` → `NEW PERSON`).
- `--help` for `vista exec`/`status` documents how to target a container (if a flag was added).
- `make check` + `make gates` green; TDD test committed. Persist→commit→push per the Increment Protocol;
  route the finding to the in-org memory (`docs/memory/`, e.g. update/extend
  `engine-access-through-driver-stack`).

## Handback to the SKL/vdocs side

When green, update the **vdocs** repo's SKL tracker (`docs/skl-implementation-plan.md`, the S2 section
"Live-DD seam" note) and `docs/prompts/skl-s2-kickoff.md` (the DD-seam options): **option (a) is now
unblocked** — `vdocs` can shell out to `m vista exec --engine ydb …` for the one-shot DD export into
`registries/entities/dd-seed.<pkg>.yaml`. Note the exact targeting invocation that works (flag vs env)
so the vdocs S2.2 step copies it verbatim. (That tracker edit is a separate one-line `vdocs`-repo
session — one session ↔ one repo.)
