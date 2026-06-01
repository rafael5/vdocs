"""The orchestration state store — ``state.db:stage_runs`` (§7.2, §5.5).

This is the one store that is *not* rebuildable: it is the pipeline's history. Each
``postflight`` writes one completion record per ``(stage, scope)``; the next stage's
preflight reads it to decide whether its inputs are present, current, and blessed.
"""

from __future__ import annotations

import json
from pathlib import Path

from vdocs.kernel import db
from vdocs.models.stage import StageRun

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stage_runs (
    stage         TEXT NOT NULL,
    scope         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT NOT NULL,
    inputs_fp     TEXT NOT NULL,
    outputs_fp    TEXT NOT NULL,
    counts        TEXT NOT NULL,
    contract_ver  INTEGER NOT NULL,
    tool_ver      TEXT NOT NULL,
    PRIMARY KEY (stage, scope)
);
"""


class StateStore:
    """Read/write access to ``stage_runs``, keyed on ``(stage, scope)``."""

    def __init__(self, conn) -> None:
        self._conn = conn
        db.apply_schema(self._conn, _SCHEMA)

    @classmethod
    def open(cls, path: Path) -> StateStore:
        return cls(db.connect(path))

    def record(self, run: StageRun) -> None:
        """Insert-or-replace the completion record for ``(run.stage, run.scope)``."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO stage_runs
              (stage, scope, status, started_at, finished_at,
               inputs_fp, outputs_fp, counts, contract_ver, tool_ver)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.stage,
                run.scope,
                run.status,
                run.started_at,
                run.finished_at,
                json.dumps(run.inputs_fp),
                json.dumps(run.outputs_fp),
                json.dumps(run.counts),
                run.contract_ver,
                run.tool_ver,
            ),
        )
        self._conn.commit()

    def get(self, stage: str, scope: str = "") -> StageRun | None:
        row = self._conn.execute(
            "SELECT * FROM stage_runs WHERE stage = ? AND scope = ?",
            (stage, scope),
        ).fetchone()
        if row is None:
            return None
        return StageRun(
            stage=row["stage"],
            scope=row["scope"],
            status=row["status"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            inputs_fp=json.loads(row["inputs_fp"]),
            outputs_fp=json.loads(row["outputs_fp"]),
            counts=json.loads(row["counts"]),
            contract_ver=row["contract_ver"],
            tool_ver=row["tool_ver"],
        )

    def close(self) -> None:
        self._conn.close()
