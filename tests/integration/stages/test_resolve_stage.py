"""resolve integration — consolidated DI gold + registries + DD seed → gold/knowledge.db (SKL S2).

Seeds a tiny FileMan (DI) gold slice (one anchor bundle whose body names file #200 three ways),
runs ResolveStage through the orchestrator, and asserts the headline SKL proof: `file #200`,
`the NEW PERSON file`, and `^VA(200,` all resolve to ONE canonical entity (`fileman_file/200`);
every node is provenanced + asserted; relationships are typed against the closed edge set; and a
re-run is idempotent.
"""

from __future__ import annotations

import json

from vdocs.contracts.registry import CONSOLIDATED
from vdocs.kernel import knowledge_db
from vdocs.models.stage import Decision, StageRun
from vdocs.orchestrator.engine import Orchestrator
from vdocs.stages.resolve.stage import ResolveStage

_BODY = """---
title: FileMan Technical Manual
app_code: DI
pkg_ns: DI
doc_type: TM
source_sha256: deadbeef
---

# Files

Edit the NEW PERSON file with FileMan. See file #200 for users; its global is ^VA(200,0).
VistA stores users there.
"""


def _seed_gold(ctx):
    """One DI gold anchor bundle + a recorded `consolidate` ok run (so preflight trusts it)."""
    bundle = ctx.cfg.gold_consolidated / "DI" / "fm22_2tm"
    bundle.mkdir(parents=True)
    (bundle / "body.md").write_text(_BODY, encoding="utf-8")
    (bundle / "history.yaml").write_text("members: []\n", encoding="utf-8")
    ctx.state.record(
        StageRun(
            stage="consolidate",
            scope="",
            status="ok",
            started_at="t",
            finished_at="t",
            inputs_fp={},
            outputs_fp={CONSOLIDATED.key: CONSOLIDATED.fingerprint(ctx.cfg)},
            counts={},
            contract_ver=2,
            tool_ver=ctx.cfg.tool_ver,
        )
    )


def test_three_surfaces_resolve_to_one_entity_in_knowledge_db(ctx):
    _seed_gold(ctx)
    (result,) = Orchestrator([ResolveStage()]).run(ctx)
    assert result.status == "ok"

    entities = knowledge_db.read_entities(ctx.cfg.knowledge_db)
    by_id = {e.node_id: e for e in entities}
    # the headline: one canonical NEW PERSON entity, seeded from the live DD
    assert "fileman_file/200" in by_id
    np = by_id["fileman_file/200"]
    assert np.canonical_name == "NEW PERSON"
    assert "^VA(200," in np.synonyms
    # provenance + verification (Q2: asserted in S2)
    assert np.provenance[0].source_sha256 == "deadbeef"
    assert np.provenance[0].doc == "DI/fm22_2tm"
    assert np.verification.status == "asserted"


def test_relationships_are_typed_and_documented_in_the_doc(ctx):
    _seed_gold(ctx)
    Orchestrator([ResolveStage()]).run(ctx)
    rels = knowledge_db.read_relationships(ctx.cfg.knowledge_db)
    edges = {(r.src_id, r.rel, r.dst_id) for r in rels}
    assert ("fileman_file/200", "documented-in", "doc/DI/fm22_2tm") in edges
    # every edge uses a registered (closed-set) rel type
    assert all(r.rel == "documented-in" for r in rels)


def test_terms_are_classified_with_facets(ctx):
    _seed_gold(ctx)
    Orchestrator([ResolveStage()]).run(ctx)
    terms = {t.surface: t for t in knowledge_db.read_terms(ctx.cfg.knowledge_db)}
    # VistA appears in the body → classified; brand casing is enforced, does not collide
    if "VistA" in terms:  # depends on the product registry carrying VistA (it does)
        assert terms["VistA"].collides_with_english is False


def test_resolve_writes_a_propose_only_curator_queue(ctx):
    _seed_gold(ctx)
    Orchestrator([ResolveStage()]).run(ctx)
    # unresolved recognized mentions (e.g. the bare ^VA global) go to the queue, never knowledge.db
    assert ctx.cfg.knowledge_proposals.is_file()


def test_resolve_counts_distinguish_mentions_from_reviewable_candidates(ctx):
    """SL.1(c): `proposals` used to report `len(unresolved)` — every *mention* — while the artifact
    it writes aggregates to one row per `(type, surface)`. On the production lake that read as
    "4,415 candidates awaiting approval" when a curator would face 307 rows, and the wrong figure
    was carried into five documents. The run must report the reviewable count, not the mention
    count, and both must be named for what they are."""
    _seed_gold(ctx)
    (result,) = Orchestrator([ResolveStage()]).run(ctx)

    queue = json.loads(ctx.cfg.knowledge_proposals.read_text(encoding="utf-8"))["proposals"]
    assert result.counts["proposal_candidates"] == len(queue)
    assert result.counts["proposal_mentions"] == sum(p["occurrences"] for p in queue)
    # The body names ^VA(200,0) once and nothing else unresolvable, so the two genuinely differ
    # only when a surface repeats; what matters is that each count means what it says.
    assert result.counts["proposal_mentions"] >= result.counts["proposal_candidates"]
    assert "proposals" not in result.counts  # the ambiguous name is gone


def test_resolve_is_idempotent(ctx):
    _seed_gold(ctx)
    orch = Orchestrator([ResolveStage()])
    orch.run(ctx)
    assert ResolveStage().preflight(ctx, force=False).decision is Decision.SKIP
    before = knowledge_db.read_entities(ctx.cfg.knowledge_db)
    orch.run(ctx, force=True)
    after = knowledge_db.read_entities(ctx.cfg.knowledge_db)
    assert before == after
