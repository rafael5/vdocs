"""P4.2 — migrating the recorded ``rows:<count>`` SQLite fingerprints (audit R‑1).

P4.1 made ``sqlite_fingerprint`` a content hash, so every fingerprint recorded by an earlier run
is in a format the new one cannot equal. Left alone, a consumer's preflight reads that mismatch as
**upstream drift → FAIL** — 13 of them on the live lake, on the first run after the change. This
migration accepts a legacy value once and lets the run re-record it.

The line it must not cross: accepting the *format* must never accept a genuinely changed table.
"""

from __future__ import annotations

import sqlite3

from vdocs.models.artifact import ArtifactContract, Kind, StorageClass
from vdocs.models.stage import Decision, RunResult, StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.orchestrator.stage import Stage

TABLE = ArtifactContract(
    key="x.db:t",
    kind=Kind.SQLITE_TABLE,
    storage_class=StorageClass.STATE,
    produced_by="producer",
    db="x.db",
    table="t",
)


class Producer(Stage):
    name = "producer"
    produces = [TABLE]

    def run(self, ctx, force):
        _write(ctx, [(1, "a"), (2, "b")])
        return RunResult()


class Consumer(Stage):
    name = "consumer"
    requires = [TABLE]

    def __init__(self) -> None:
        self.run_count = 0

    def run(self, ctx, force):
        self.run_count += 1
        return RunResult()


def _write(ctx, rows):
    path = ctx.cfg.lake / "x.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("DELETE FROM t")
    conn.executemany("INSERT INTO t (id, v) VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


def _record_legacy(ctx, rows):
    """A producer completion record in the pre-P4.1 format — what every live lake carries."""
    ctx.state.record(
        StageRun(
            stage="producer",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={TABLE.key: f"rows:{rows}"},
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )  # fmt: skip
    )


def test_legacy_fingerprint_is_accepted_not_read_as_drift(ctx):
    _write(ctx, [(1, "a"), (2, "b")])
    _record_legacy(ctx, 2)

    pf = Consumer().preflight(ctx, force=False)
    assert pf.decision is not Decision.FAIL, pf.reason


def test_legacy_fingerprint_is_re_recorded_in_the_new_format(ctx):
    _write(ctx, [(1, "a"), (2, "b")])
    _record_legacy(ctx, 2)

    Orchestrator([Producer(), Consumer()]).run(ctx)

    recorded = ctx.state.get("producer", "")
    assert not recorded.outputs_fp[TABLE.key].startswith("rows:")  # migrated, not sticky
    assert Consumer().preflight(ctx, force=False).decision is not Decision.FAIL


def test_legacy_fingerprint_does_not_swallow_a_real_change(ctx):
    """The line the migration must not cross.

    A legacy record whose row COUNT no longer matches the table is a change the old format could
    see — accepting it because the format is old would trade a false alarm for a silent one."""
    _write(ctx, [(1, "a"), (2, "b"), (3, "c")])
    _record_legacy(ctx, 2)  # the table has grown since this was recorded

    pf = Consumer().preflight(ctx, force=False)
    assert pf.decision is Decision.FAIL
    assert "changed since producer" in pf.reason


def test_a_same_rowcount_cell_change_re_runs_the_consumer(ctx):
    """The regression the whole phase exists for (finding 5a).

    Under `rows:<count>` this consumer skipped: the row count was unchanged, so its input
    fingerprint was unchanged, so the preflight said "inputs unchanged" over a table whose
    content had changed. That is how `merge`'s SKL projection was wiped on the live lake."""
    consumer = Consumer()
    orch = Orchestrator([Producer(), Consumer()])
    orch.run(ctx)
    assert Consumer().preflight(ctx, force=False).decision is Decision.SKIP

    _write(ctx, [(1, "a"), (2, "CHANGED")])  # same row count, different content
    ctx.state.record(
        StageRun(
            stage="producer",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={TABLE.key: TABLE.fingerprint(ctx.cfg)},
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )  # fmt: skip
    )

    assert consumer.preflight(ctx, force=False).decision is Decision.PROCEED


def test_a_stage_with_a_legacy_record_reruns_once_then_skips(ctx):
    """ "Accept once" has to be literally once.

    A producer whose own record is in the retired format must re-run and re-record — otherwise it
    skips, the legacy value stays on disk forever, and every consumer keeps taking the tolerant
    path. One run of leniency is a migration; every run is a hole."""
    producer = Producer()
    _write(ctx, [(1, "a"), (2, "b")])
    _record_legacy(ctx, 2)

    assert producer.preflight(ctx, force=False).decision is Decision.PROCEED
    Orchestrator([producer]).run(ctx)
    assert not ctx.state.get("producer", "").outputs_fp[TABLE.key].startswith("rows:")

    # migrated — back to the normal skip behaviour, no lingering leniency
    assert producer.preflight(ctx, force=False).decision is Decision.SKIP
