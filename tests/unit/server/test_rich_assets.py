"""Tests for the rich-publication subset image-bundle builder (server/rich_assets.py).

The pure planner (``plan_bundle``) takes already-read bodies so it is unit-tested without the lake;
``build_bundle`` is the thin driver that reads gold bodies + copies the union of assets into the
bundle dir. Rich-publication proposal §3/§7 (P1 substrate).
"""

from __future__ import annotations

import json

from vdocs.config import Settings
from vdocs.server import rich_assets


def _asset(assets, name, data):
    assets.mkdir(parents=True, exist_ok=True)
    (assets / name).write_bytes(data)


def test_load_subset_reads_rich_key(tmp_path):
    reg = tmp_path / "registries"
    reg.mkdir()
    (reg / "rich-publication.yaml").write_text("rich:\n  - CPRS/cprsguium\n  - DI/scrn_tut\n")
    assert rich_assets.load_subset(reg) == ["CPRS/cprsguium", "DI/scrn_tut"]


def test_load_subset_absent_registry_is_empty(tmp_path):
    assert rich_assets.load_subset(tmp_path) == []


def test_plan_bundle_unions_assets_across_docs_deduped(tmp_path):
    assets = tmp_path / "assets"
    _asset(assets, "a.png", b"12345")  # 5 — shared by both docs
    _asset(assets, "b.png", b"678")  # 3 — doc one only
    _asset(assets, "c.png", b"90")  # 2 — doc two only
    bodies = {
        "APP/one": "![x](a.png)\n![y](b.png)\n",
        "APP/two": "![x](a.png)\n![z](c.png)\n",
    }
    plan = rich_assets.plan_bundle(["APP/one", "APP/two"], bodies, assets)

    # the union counts a shared asset once: a + b + c = 5 + 3 + 2
    assert [p.name for p in plan.assets] == ["a.png", "b.png", "c.png"]  # sorted by name
    assert plan.total_bytes == 10
    assert {d.doc_key: (d.present, d.image_count, d.missing) for d in plan.docs} == {
        "APP/one": (True, 2, 0),
        "APP/two": (True, 2, 0),
    }


def test_plan_bundle_records_missing_refs_and_absent_bodies(tmp_path):
    assets = tmp_path / "assets"
    _asset(assets, "present.png", b"here")
    bodies = {
        "APP/one": "![ok](present.png)\n![gone](missing.png)\n",  # 1 resolves, 1 missing
        "APP/two": None,  # no gold body on disk
    }
    plan = rich_assets.plan_bundle(["APP/one", "APP/two"], bodies, assets)

    docs = {d.doc_key: d for d in plan.docs}
    assert docs["APP/one"].present is True
    assert docs["APP/one"].image_count == 1
    assert docs["APP/one"].missing == 1
    assert docs["APP/two"].present is False
    assert [p.name for p in plan.assets] == ["present.png"]


def test_build_bundle_copies_union_and_writes_manifest(tmp_path):
    cfg = Settings(data_dir=tmp_path)
    cfg.lake.mkdir(parents=True, exist_ok=True)
    # registry naming two docs
    (cfg.registries).mkdir(parents=True, exist_ok=True) if not cfg.registries.exists() else None
    # gold bodies
    for dk, body in {
        "CPRS/cprsguium": "# UM\n\n![f1](sha1.png)\n![f2](sha2.png)\n",
        "DI/scrn_tut": "# Tut\n\n![f1](sha1.png)\n",  # shares sha1 with the UM
    }.items():
        bp = cfg.gold_consolidated / dk / "body.md"
        bp.parent.mkdir(parents=True, exist_ok=True)
        bp.write_text(body)
    _asset(cfg.assets, "sha1.png", b"AAAA")  # 4
    _asset(cfg.assets, "sha2.png", b"BB")  # 2

    plan = rich_assets.build_bundle(cfg, subset=["CPRS/cprsguium", "DI/scrn_tut"])

    # union copied into the bundle dir (content-addressed, shared asset once)
    assert sorted(p.name for p in cfg.rich_assets.glob("*.png")) == ["sha1.png", "sha2.png"]
    assert (cfg.rich_assets / "sha1.png").read_bytes() == b"AAAA"
    assert plan.total_bytes == 6

    manifest = json.loads(cfg.rich_assets_manifest.read_text())
    assert manifest["doc_count"] == 2
    assert manifest["asset_count"] == 2
    assert manifest["total_bytes"] == 6
    assert sorted(manifest["assets"]) == ["sha1.png", "sha2.png"]
    assert {d["doc_key"] for d in manifest["docs"]} == {"CPRS/cprsguium", "DI/scrn_tut"}


def test_build_bundle_is_idempotent_skips_existing_copy(tmp_path):
    cfg = Settings(data_dir=tmp_path)
    cfg.lake.mkdir(parents=True, exist_ok=True)
    bp = cfg.gold_consolidated / "CPRS/cprsguium" / "body.md"
    bp.parent.mkdir(parents=True, exist_ok=True)
    bp.write_text("# UM\n\n![f1](sha1.png)\n")
    _asset(cfg.assets, "sha1.png", b"AAAA")

    rich_assets.build_bundle(cfg, subset=["CPRS/cprsguium"])
    dst = cfg.rich_assets / "sha1.png"
    first_mtime = dst.stat().st_mtime_ns
    # a second build must leave the already-present (content-addressed) copy untouched
    rich_assets.build_bundle(cfg, subset=["CPRS/cprsguium"])
    assert dst.stat().st_mtime_ns == first_mtime


def test_build_bundle_prunes_assets_no_longer_selected(tmp_path):
    cfg = Settings(data_dir=tmp_path)
    cfg.lake.mkdir(parents=True, exist_ok=True)
    bp = cfg.gold_consolidated / "CPRS/cprsguium" / "body.md"
    bp.parent.mkdir(parents=True, exist_ok=True)
    bp.write_text("# UM\n\n![f1](sha1.png)\n")
    _asset(cfg.assets, "sha1.png", b"AAAA")
    # a stale asset from a prior, larger bundle
    cfg.rich_assets.mkdir(parents=True, exist_ok=True)
    (cfg.rich_assets / "stale.png").write_bytes(b"old")

    rich_assets.build_bundle(cfg, subset=["CPRS/cprsguium"])

    assert (cfg.rich_assets / "sha1.png").is_file()
    assert not (cfg.rich_assets / "stale.png").exists()  # pruned — no longer in the union
