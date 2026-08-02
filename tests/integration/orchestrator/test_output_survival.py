"""The OUTPUT half of the skip decision (audit R‑1, second half — closed 2026-08-02).

P4 fixed the *input* half: a consumer's fingerprints are content hashes, so a change upstream
reaches it. This is the other half, and it bit twice on the live lake **after** P4:

    `index` rebuilds `index.db` from scratch, which recreates `entity_skl` as an empty shell.
    `merge` fills that table. `merge`'s own inputs (`index.db:chunks`/`entities`) are rebuilt
    **content-identically**, so its preflight correctly says "inputs unchanged" and skips — over
    an output that no longer exists. `doctor` then goes RED on the SKL-projections check.

Nothing in the skip decision asked the one question that matters here: *is what I produced last
time still there?* `produces_ok` only checks that the artifact **validates** (a table that exists,
even an emptied one), never that it still matches what this stage recorded producing.
"""

from __future__ import annotations

import sqlite3

from vdocs.models.artifact import ArtifactContract, Kind, StorageClass
from vdocs.models.stage import Decision, RunResult
from vdocs.orchestrator.engine import Orchestrator
from vdocs.orchestrator.stage import Stage

SOURCE = ArtifactContract(
    key="x.db:src",
    kind=Kind.SQLITE_TABLE,
    storage_class=StorageClass.STATE,
    produced_by="producer",
    db="x.db",
    table="src",
)
PROJECTION = ArtifactContract(
    key="x.db:proj",
    kind=Kind.SQLITE_TABLE,
    storage_class=StorageClass.STATE,
    produced_by="projector",
    db="x.db",
    table="proj",
)


def _conn(ctx):
    return sqlite3.connect(ctx.cfg.lake / "x.db")


def _write(ctx, table, rows):
    conn = _conn(ctx)
    conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute(f"DELETE FROM {table}")
    conn.executemany(f"INSERT INTO {table} (id, v) VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


class Producer(Stage):
    """Stands in for `index`: rebuilds its own table, and (below) can wipe the projection."""

    name = "producer"
    produces = [SOURCE]

    def run(self, ctx, force):
        _write(ctx, "src", [(1, "a"), (2, "b")])
        return RunResult()


class Projector(Stage):
    """Stands in for `merge`: reads SOURCE, fills PROJECTION."""

    name = "projector"
    requires = [SOURCE]
    produces = [PROJECTION]

    def __init__(self) -> None:
        self.run_count = 0

    def run(self, ctx, force):
        self.run_count += 1
        _write(ctx, "proj", [(1, "projected")])
        return RunResult()


def _wipe_projection(ctx):
    """What `index`'s rebuild does to `entity_skl`: the table survives, its contents don't."""
    conn = _conn(ctx)
    conn.execute("DELETE FROM proj")
    conn.commit()
    conn.close()


def test_a_stage_reruns_when_its_own_output_was_wiped_by_another_writer(ctx):
    projector = Projector()
    Orchestrator([Producer(), projector]).run(ctx)
    assert projector.run_count == 1
    assert Projector().preflight(ctx, force=False).decision is Decision.SKIP  # steady state

    _wipe_projection(ctx)  # inputs untouched — only the OUTPUT is gone

    pf = Projector().preflight(ctx, force=False)
    assert pf.decision is Decision.PROCEED, pf.reason
    assert "proj" in pf.reason  # names the artifact that changed under it


def test_the_rerun_actually_restores_the_output(ctx):
    projector = Projector()
    orch = Orchestrator([Producer(), projector])
    orch.run(ctx)
    _wipe_projection(ctx)

    Orchestrator([Projector()]).run(ctx)  # no --force needed: the gap repairs itself
    conn = _conn(ctx)
    assert conn.execute("SELECT count(*) FROM proj").fetchone()[0] == 1
    conn.close()


def test_an_untouched_output_still_skips(ctx):
    """The check must not defeat skipping — that would re-run the whole DAG every time."""
    Orchestrator([Producer(), Projector()]).run(ctx)
    assert Projector().preflight(ctx, force=False).decision is Decision.SKIP
    assert Projector().preflight(ctx, force=False).decision is Decision.SKIP


def test_a_modified_output_also_reruns(ctx):
    """Not only deletion: any drift in what this stage produced means the record is not true."""
    Orchestrator([Producer(), Projector()]).run(ctx)
    _write(ctx, "proj", [(1, "TAMPERED")])  # same row count, different content

    assert Projector().preflight(ctx, force=False).decision is Decision.PROCEED
