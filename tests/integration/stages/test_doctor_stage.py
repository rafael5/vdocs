"""doctor integration — the soundness gate as a terminal DAG stage (P2.1, audit R‑6 / [S18]).

The audit's finding was placement, not logic: 19 checks that all passed, invoked only by
``build`` and by hand, so ``vdocs run`` could finish green over a RED-able ``index.db``. These
tests pin the fix — doctor sorts last in the real DAG, a RED corpus stops the run with a
non-zero exit, a GREEN one writes the computable report, and WARN/BY-DESIGN never fail (F6).
"""

from __future__ import annotations

import json

import pytest

from vdocs.kernel import cas, db
from vdocs.orchestrator.engine import Orchestrator
from vdocs.orchestrator.stage import PostflightError
from vdocs.stages.doctor.stage import DoctorStage
from vdocs.stages.index.stage import _SCHEMA

_DOC_COLS = (
    "doc_key, doc_id, app_code, doc_type, section, pkg_ns, version, patch_id, anchor_key, "
    "group_key, title, doc_label, app_user, doc_user, software_class, function_category, "
    "word_count, section_count, is_latest, template_id, source_sha256, source_url"
)


def _doc(conn, *, doc_key, doc_id, doc_type="UM", anchor_key="ADT:DG:UM:um",
         function_category="registration"):  # fmt: skip
    conn.execute(
        f"INSERT INTO documents ({_DOC_COLS}) VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (doc_key, doc_id, "ADT", doc_type, "CLIN", "DG", "5.3", "DG*5.3*1", anchor_key,
         "ADT:DG:5.3", "OR UM", "User Manual", "clinical", "developer", "vista",
         function_category, 100, 4, 1, "", "abc", "https://va.gov/d/x.docx"),
    )  # fmt: skip
    conn.execute(
        "INSERT INTO chunks_fts (chunk_id, section_id, doc_key, title, doc_title, section_path, "
        "body) VALUES (?,?,?,'Intro','OR UM','OR','registration text')",
        (f"{doc_key}/s", f"{doc_key}/s", doc_key),
    )


def _seed(ctx, **doc_kwargs):
    """A minimal *sound* lake: index.db with the published views + relations, and the
    contract-manifest `manifest` produces (the edge that sorts doctor terminal)."""
    from vdocs.kernel import read_contract as rc

    conn = db.connect(ctx.cfg.index_db)
    conn.executescript(_SCHEMA)
    spec = rc.load(rc.contract_path(base=ctx.cfg.read_contract_dir))
    conn.executescript(rc.view_ddl(spec))
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('read_schema_version', ?)", (rc.version(spec),)
    )
    conn.execute(
        "CREATE TABLE relations (src_type TEXT, src_id TEXT, rel TEXT, dst_type TEXT, "
        "dst_id TEXT, weight INTEGER)"
    )
    _doc(conn, doc_key="ADT/um1", doc_id="ADT:um1", anchor_key="ADT:DG:UM:um1", **doc_kwargs)
    conn.execute("INSERT INTO entities VALUES ('routine:XL','routine','XL',2)")
    conn.execute("INSERT INTO entity_mentions VALUES ('routine:XL','ADT/um1','ADT/um1/s')")
    conn.commit()
    conn.close()
    cas.atomic_write(ctx.cfg.contract_manifest, b'{"read_schema_version": "x"}\n')
    return conn


def test_doctor_sorts_last_in_the_real_dag(ctx):
    """The placement *is* the fix (R‑6): a run that reaches manifest now reaches the gate."""
    from vdocs.cli.app import build_stages

    order = [s.name for s in Orchestrator(build_stages()).order()]
    assert order[-1] == "doctor"
    assert order.index("manifest") < order.index("doctor")


def test_doctor_green_writes_the_report_artifact(ctx):
    _seed(ctx)
    (result,) = Orchestrator([DoctorStage()]).run(ctx)
    assert result.status == "ok"

    payload = json.loads(ctx.cfg.doctor_report.read_text())
    assert payload["verdict"] == "GREEN"
    assert payload["gold_count"] == 1
    assert payload["generated_at"]
    names = [c["name"] for c in payload["checks"]]
    assert "read contract" in names and "gate fidelity" in names
    assert all(c["health"] != "FAIL" for c in payload["checks"])
    assert result.counts["fail"] == 0 and result.counts["gold_documents"] == 1


def test_doctor_red_fails_the_run_and_still_writes_the_report(ctx):
    # an untyped gold doc → coverage:doc_type below the 100% floor → FAIL ⇒ RED
    _seed(ctx, doc_type="")
    with pytest.raises(PostflightError, match="RED"):
        Orchestrator([DoctorStage()]).run(ctx)
    # the report is written *before* the gate fires — a RED verdict must leave evidence
    payload = json.loads(ctx.cfg.doctor_report.read_text())
    assert payload["verdict"] == "RED"
    failed = [c["name"] for c in payload["checks"] if c["health"] == "FAIL"]
    assert "coverage:doc_type" in failed


def test_doctor_warn_only_passes(ctx):
    # F6 is deliberate: WARN and BY-DESIGN never flip the verdict. A non-4-part anchor_key
    # (not on the accepted list) is the WARN case — worth an eye, not a corruption.
    _seed(ctx)
    conn = db.connect(ctx.cfg.index_db)
    conn.execute("UPDATE documents SET anchor_key='ADT:um1' WHERE doc_key='ADT/um1'")
    conn.commit()
    conn.close()

    (result,) = Orchestrator([DoctorStage()]).run(ctx)
    assert result.status == "ok"
    payload = json.loads(ctx.cfg.doctor_report.read_text())
    assert payload["verdict"] == "GREEN"
    warns = [c for c in payload["checks"] if c["health"] == "WARN"]
    assert any(c["name"] == "anchor form" for c in warns)
    # a WARN is surfaced to the operator, not swallowed (degrade loud)
    assert result.counts["warn"] == len(warns)


def test_doctor_always_reruns(ctx):
    """A gate re-checks every time — an unchanged lake must not skip the verdict."""
    _seed(ctx)
    Orchestrator([DoctorStage()]).run(ctx)
    (second,) = Orchestrator([DoctorStage()]).run(ctx)
    assert second is not None and second.status == "ok"
