"""consolidate integration — normalized bundles → one anchor document per version group (§6.6).

Seeds normalized bundles that are *patches of one logical document* (same app/pkg/doc_type, distinct
``patch_id``), each with its own ``revisions.yaml``, blesses the upstreams (normalize → text@
normalized, convert → assets), runs ConsolidateStage through the orchestrator, and asserts: one
anchor bundle at a stable version-free path whose ``body.md`` is the latest member's body; an
ordered ``history.yaml`` folding both members' revisions + CAS refs to each retained body, with
``is_latest`` on the newest; the prior body retained in the content-addressed store; idempotent
re-run skips; and a later patch **appends** to the lineage without rewriting prior entries.
"""

from __future__ import annotations

import hashlib

import yaml

from vdocs.contracts.registry import ASSETS, TEXT_NORMALIZED
from vdocs.kernel import cas, frontmatter
from vdocs.models.stage import Decision, StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.consolidate.stage import ConsolidateStage


def _bless(ctx, stage, art):
    ctx.state.record(
        StageRun(
            stage=stage,
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={art.key: art.fingerprint(ctx.cfg)},
            counts={},
            contract_ver=1,
            tool_ver=ctx.cfg.tool_ver,
        )  # fmt: skip
    )


def _seed_member(
    ctx, *, slug, patch_id, body, date, doc_type="IG", app="CPRS", pkg="OR", with_revisions=True
):
    """Write one normalized bundle (identity FM + body + an optional one-row revisions.yaml)."""
    sha = hashlib.sha256(f"{slug}-source".encode()).hexdigest()
    text = frontmatter.emit(
        {
            "title": "Install Guide",
            "doc_type": doc_type,
            "app_code": app,
            "pkg_ns": pkg,
            "version": "3.0",
            "patch_id": patch_id,
            "source_sha256": sha,
            "tool_ver": "0.1.0",
        },
        body,
    )
    bundle = ctx.cfg.silver_normalized / app / slug
    cas.atomic_write(bundle / "body.md", text.encode())
    if with_revisions:
        cas.atomic_write(
            bundle / "revisions.yaml",
            yaml.safe_dump(
                {
                    "revision_count": 1,
                    "revision_newest": date,
                    "revision_oldest": date,
                    "revisions": [{"date": date, "version": patch_id, "change": f"rev {slug}"}],
                },
                sort_keys=False,
            ).encode(),
        )
    return sha


def _seed_assets(ctx):
    # a non-empty asset CAS so the (optional) ASSETS input validates; convert is the producer
    cas.atomic_write(ctx.cfg.assets / "deadbeef.png", b"img")
    _bless(ctx, "convert", ASSETS)


def _seed_two_patches(ctx):
    _seed_member(
        ctx, slug="or_3_190_ig", patch_id="OR*3*190", body="# IG\n\nv190 body\n", date="2018-01"
    )
    _seed_member(
        ctx, slug="or_3_566_ig", patch_id="OR*3.0*566", body="# IG\n\nv566 latest\n", date="2022-06"
    )
    _seed_assets(ctx)
    _bless(ctx, "normalize", TEXT_NORMALIZED)


def test_consolidate_builds_one_anchor_with_ordered_lineage(ctx):
    _seed_two_patches(ctx)
    (result,) = Orchestrator([ConsolidateStage()]).run(ctx)
    assert result.status == "ok"
    assert result.counts["groups"] == 1
    assert result.counts["documents"] == 2

    # one anchor bundle at the stable version-free path; its body is the LATEST member's body
    anchor = ctx.cfg.gold_consolidated / "CPRS" / "or_ig"
    assert anchor.is_dir()
    _, body = frontmatter.parse((anchor / "body.md").read_text())
    assert "v566 latest" in body and "v190 body" not in body

    # ordered history.yaml: both members oldest→newest, is_latest on the newest only
    hist = yaml.safe_load((anchor / "history.yaml").read_text())
    assert hist["anchor_key"] == "CPRS:OR:IG:or_ig" and hist["member_count"] == 2
    assert [m["patch_id"] for m in hist["members"]] == ["OR*3*190", "OR*3.0*566"]
    assert [m["is_latest"] for m in hist["members"]] == [False, True]
    # each member folds its own revisions.yaml + carries a CAS ref to its retained body
    assert hist["members"][0]["revisions"][0]["change"] == "rev or_3_190_ig"
    for m in hist["members"]:
        assert (ctx.cfg.history_bodies / f"{m['body_sha256']}.md").is_file()

    # the prior (superseded) body is retained in the CAS — evidence, not republished
    prior_sha = hist["members"][0]["body_sha256"]
    assert "v190 body" in (ctx.cfg.history_bodies / f"{prior_sha}.md").read_text()
    # the anchor body.md is exactly the newest retained body
    newest_sha = hist["members"][1]["body_sha256"]
    assert (anchor / "body.md").read_bytes() == (
        ctx.cfg.history_bodies / f"{newest_sha}.md"
    ).read_bytes()


def test_consolidate_skips_on_unchanged_rerun(ctx):
    _seed_two_patches(ctx)
    orch = Orchestrator([ConsolidateStage()])
    orch.run(ctx)
    # a no-force re-run with unchanged inputs is skipped by the generic SKIP_IF_UNCHANGED preflight
    stage = ConsolidateStage()
    assert stage.preflight(ctx, force=False).decision is Decision.SKIP


def test_consolidate_is_idempotent_under_force(ctx):
    _seed_two_patches(ctx)
    orch = Orchestrator([ConsolidateStage()])
    orch.run(ctx)
    anchor = ctx.cfg.gold_consolidated / "CPRS" / "or_ig"
    first_body = (anchor / "body.md").read_bytes()
    first_hist = (anchor / "history.yaml").read_bytes()
    orch.run(ctx, force=True)
    assert (anchor / "body.md").read_bytes() == first_body
    assert (
        anchor / "history.yaml"
    ).read_bytes() == first_hist  # append-only no-op → byte-identical


def test_consolidate_appends_a_later_patch(ctx):
    _seed_two_patches(ctx)
    orch = Orchestrator([ConsolidateStage()])
    orch.run(ctx)

    # a new VDL patch lands as the latest body; re-run should APPEND one entry, rewrite nothing
    _seed_member(
        ctx, slug="or_3_588_ig", patch_id="OR*3.0*588", body="# IG\n\nv588 newest\n", date="2023-09"
    )
    _bless(ctx, "normalize", TEXT_NORMALIZED)  # the input tree changed → re-fingerprint
    orch.run(ctx, force=True)

    anchor = ctx.cfg.gold_consolidated / "CPRS" / "or_ig"
    hist = yaml.safe_load((anchor / "history.yaml").read_text())
    assert hist["member_count"] == 3
    assert [m["patch_id"] for m in hist["members"]] == ["OR*3*190", "OR*3.0*566", "OR*3.0*588"]
    assert [m["is_latest"] for m in hist["members"]] == [False, False, True]
    # the anchor body is now the newest; the prior bodies remain retained in the CAS
    _, body = frontmatter.parse((anchor / "body.md").read_text())
    assert "v588 newest" in body
    assert (ctx.cfg.history_bodies / f"{hist['members'][0]['body_sha256']}.md").is_file()


def test_consolidate_member_without_revisions_sidecar(ctx):
    # a heading-less doc gets no revisions.yaml — it still consolidates (revisions=[], no date)
    _seed_member(
        ctx,
        slug="flat_um",
        patch_id="WV*1.0*5",
        body="# UM\n\nflat body\n",
        date="",
        with_revisions=False,
    )
    _seed_assets(ctx)
    _bless(ctx, "normalize", TEXT_NORMALIZED)

    (result,) = Orchestrator([ConsolidateStage()]).run(ctx)
    assert result.status == "ok" and result.counts["documents"] == 1
    # anchor path now follows the logical-doc stem of the slug (B1 fix), not <pkg>_<doc_code>
    anchor = ctx.cfg.gold_consolidated / "CPRS" / "flat_um"
    hist = yaml.safe_load((anchor / "history.yaml").read_text())
    assert hist["members"][0]["revisions"] == [] and hist["members"][0]["official_date"] == ""


def test_consolidate_isolates_a_single_doc_failure(ctx, monkeypatch):
    # R6: one bundle that fails to build a Member is logged + counted + skipped; the rest proceed
    _seed_member(
        ctx, slug="or_3_190_ig", patch_id="OR*3*190", body="# IG\n\nv190\n", date="2018-01"
    )
    _seed_member(ctx, slug="bad_um", patch_id="WV*1.0*9", body="# UM\n\nbad\n", date="2019-01")
    _seed_assets(ctx)
    _bless(ctx, "normalize", TEXT_NORMALIZED)
    from vdocs.stages.consolidate import stage as cs

    real = cs._member_from

    def flaky(meta, slug, raw, bodies, bundle_dir):
        if slug == "bad_um":
            raise ValueError("boom")
        return real(meta, slug, raw, bodies, bundle_dir)

    monkeypatch.setattr(cs, "_member_from", flaky)
    (result,) = Orchestrator([ConsolidateStage()]).run(ctx)
    assert result.status == "ok"
    assert result.counts["errors"] == 1 and result.counts["documents"] == 1
    assert (ctx.cfg.gold_consolidated / "CPRS" / "or_ig").is_dir()


def test_consolidate_fails_when_error_rate_is_systemic(ctx, monkeypatch):
    import pytest

    from vdocs.orchestrator.stage import PostflightError

    _seed_member(ctx, slug="a_ig", patch_id="OR*3*1", body="# A\n\na\n", date="2018-01")
    _seed_member(ctx, slug="b_ig", patch_id="OR*3*2", body="# B\n\nb\n", date="2019-01")
    _seed_assets(ctx)
    _bless(ctx, "normalize", TEXT_NORMALIZED)
    from vdocs.stages.consolidate import stage as cs

    def boom(*a, **k):
        raise ValueError("boom")

    monkeypatch.setattr(cs, "_member_from", boom)  # every doc fails → systemic → stage fails
    with pytest.raises(PostflightError):
        Orchestrator([ConsolidateStage()]).run(ctx)


def test_consolidate_propagates_latest_capture_manifest(ctx):
    # §8/§6.4: the latest member's capture.yaml (typed capture-attempt records) travels with the
    # anchor, like flags.yaml/toc.yaml — so the gold grain carries the completeness manifest too.
    def _capture(slug):
        return yaml.safe_dump(
            {"doc_id": f"CPRS/{slug}", "captures": {"refs": {"outcome": "captured"}}}
        ).encode()

    _seed_member(
        ctx, slug="or_3_190_ig", patch_id="OR*3*190", body="# IG\n\nv190\n", date="2018-01"
    )
    cas.atomic_write(
        ctx.cfg.silver_normalized / "CPRS" / "or_3_190_ig" / "capture.yaml", _capture("or_3_190_ig")
    )
    _seed_member(
        ctx, slug="or_3_566_ig", patch_id="OR*3.0*566", body="# IG\n\nv566\n", date="2022-06"
    )
    cas.atomic_write(
        ctx.cfg.silver_normalized / "CPRS" / "or_3_566_ig" / "capture.yaml", _capture("or_3_566_ig")
    )
    _seed_assets(ctx)
    _bless(ctx, "normalize", TEXT_NORMALIZED)

    Orchestrator([ConsolidateStage()]).run(ctx)

    anchor = ctx.cfg.gold_consolidated / "CPRS" / "or_ig"
    manifest = yaml.safe_load((anchor / "capture.yaml").read_text())
    assert manifest["doc_id"] == "CPRS/or_3_566_ig"  # the LATEST member's manifest, not the prior


def test_consolidate_writes_verifiable_bundle_manifest(ctx):
    # §5.3/§6.6: consolidate writes a bundle.yaml signed manifest enumerating every other part with
    # its sha256 + a bundle_digest, so the anchor bundle is a verifiable unit (validate recomputes).
    import hashlib

    from vdocs.kernel import bundle as kbundle

    _seed_two_patches(ctx)
    Orchestrator([ConsolidateStage()]).run(ctx)

    anchor = ctx.cfg.gold_consolidated / "CPRS" / "or_ig"
    manifest = yaml.safe_load((anchor / "bundle.yaml").read_text())
    assert manifest["anchor_key"] == "CPRS:OR:IG:or_ig"
    assert manifest["bundle_digest"] and manifest["source_sha256"]
    listed = {e["path"]: e for e in manifest["parts"]}
    assert "body.md" in listed and "history.yaml" in listed
    assert "bundle.yaml" not in listed  # the manifest never lists itself
    # every listed hash matches the file on disk
    for path, entry in listed.items():
        assert hashlib.sha256((anchor / path).read_bytes()).hexdigest() == entry["sha256"]
    # the manifest verifies clean against the on-disk parts (the validate gate's check)
    on_disk = {
        p.name: p.read_bytes() for p in anchor.iterdir() if p.is_file() and p.name != "bundle.yaml"
    }
    assert kbundle.verify_manifest(manifest, on_disk) == []


def test_consolidate_bundle_manifest_detects_tampering(ctx):
    from vdocs.kernel import bundle as kbundle

    _seed_two_patches(ctx)
    Orchestrator([ConsolidateStage()]).run(ctx)
    anchor = ctx.cfg.gold_consolidated / "CPRS" / "or_ig"
    manifest = yaml.safe_load((anchor / "bundle.yaml").read_text())
    # someone edits the published body after the fact → integrity check catches it
    (anchor / "body.md").write_text("# Tampered\n")
    on_disk = {
        p.name: p.read_bytes() for p in anchor.iterdir() if p.is_file() and p.name != "bundle.yaml"
    }
    finds = kbundle.verify_manifest(manifest, on_disk)
    assert any(f.kind == kbundle.HASH_MISMATCH and f.path == "body.md" for f in finds)


def test_consolidate_prunes_stale_sidecar_within_a_kept_bundle(ctx):
    # R4 hygiene caught by the bundle-integrity gate: a prior run's flags.yaml lingering in a still-
    # kept bundle whose current latest member has none must be removed, so the bundle matches its
    # bundle.yaml manifest exactly (no extra part).
    from vdocs.kernel import bundle as kbundle

    _seed_member(ctx, slug="or_3_1_ig", patch_id="OR*3*1", body="# IG\n\nv1\n", date="2020-01")
    _seed_assets(ctx)
    _bless(ctx, "normalize", TEXT_NORMALIZED)
    anchor = ctx.cfg.gold_consolidated / "CPRS" / "or_ig"
    cas.atomic_write(anchor / "flags.yaml", b"doc_id: stale\nflags: [stale]\n")  # prior-run residue

    Orchestrator([ConsolidateStage()]).run(ctx)

    assert not (anchor / "flags.yaml").exists()  # stale sidecar pruned
    manifest = yaml.safe_load((anchor / "bundle.yaml").read_text())
    on_disk = {
        p.name: p.read_bytes() for p in anchor.iterdir() if p.is_file() and p.name != "bundle.yaml"
    }
    assert kbundle.verify_manifest(manifest, on_disk) == []  # bundle matches its manifest exactly
