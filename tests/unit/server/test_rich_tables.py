"""Unit tests for the rich-reading table distribution planner/driver (P3)."""

from __future__ import annotations

import hashlib
import json

from vdocs.server import rich_tables as rt


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_plan_tables_lists_sorted_entries_with_sha_and_doc_count():
    files = {
        "DI/fm22_2dg/tables/table-02.csv": b"b,c\n",
        "DI/fm22_2dg/tables/table-01.csv": b"a\n",
        "CPRS/cprsguitm/tables/table-01.csv": b"x,y\n",
    }
    plan = rt.plan_tables(files)
    # sorted by bundle-relative path
    assert [e.path for e in plan.tables] == [
        "CPRS/cprsguitm/tables/table-01.csv",
        "DI/fm22_2dg/tables/table-01.csv",
        "DI/fm22_2dg/tables/table-02.csv",
    ]
    assert plan.tables[1].sha256 == _sha(b"a\n") and plan.tables[1].bytes == 2
    assert plan.total_bytes == sum(len(b) for b in files.values())
    assert plan.doc_count == 2  # two distinct bundle dirs


def test_build_tables_bundle_copies_structure_prunes_and_writes_manifest(tmp_path):
    # a fake gold tree with two docs' tables + an unrelated file (not under tables/)
    gold = tmp_path / "gold"
    (gold / "DI/fm22_2dg/tables").mkdir(parents=True)
    (gold / "DI/fm22_2dg/tables/table-01.csv").write_bytes(b"Var,Default\nDT,$H\n")
    (gold / "CPRS/cprsguitm/tables").mkdir(parents=True)
    (gold / "CPRS/cprsguitm/tables/table-01.csv").write_bytes(b"a,b\n")
    (gold / "DI/fm22_2dg/body.md").write_text("not a table")  # must be ignored

    out = tmp_path / "rich-tables"
    # a stale CSV from a prior, larger run must be pruned (and its emptied dir dropped)
    (out / "OLD/gone/tables").mkdir(parents=True)
    (out / "OLD/gone/tables/table-09.csv").write_bytes(b"stale\n")

    cfg = _Cfg(gold, out)
    plan = rt.build_tables_bundle(cfg)

    assert len(plan.tables) == 2 and plan.doc_count == 2
    assert (out / "DI/fm22_2dg/tables/table-01.csv").read_bytes() == b"Var,Default\nDT,$H\n"
    assert not (out / "OLD/gone/tables/table-09.csv").exists()  # stale pruned
    assert not (out / "OLD").exists()  # emptied dir dropped
    assert not (out / "DI/fm22_2dg/body.md").exists()  # non-table never copied

    m = json.loads((out / "manifest.json").read_text())
    assert m["contract_ver"] == rt.MANIFEST_VER and m["table_count"] == 2
    paths = {t["path"]: t for t in m["tables"]}
    assert "DI/fm22_2dg/tables/table-01.csv" in paths
    assert paths["CPRS/cprsguitm/tables/table-01.csv"]["sha256"] == _sha(b"a,b\n")


class _Cfg:
    """Minimal config stand-in exposing the two paths the driver reads."""

    def __init__(self, gold, out):
        self.gold_consolidated = gold
        self.rich_tables = out
        self.rich_tables_manifest = out / "manifest.json"
