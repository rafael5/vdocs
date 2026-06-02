"""fetch selection → input fingerprint / SKIP_IF_UNCHANGED (§5.6, §7.3).

The resolved selection is part of fetch's input fingerprint, so changing it re-runs the stage
while repeating it is a no-op — proven here at the fingerprint level (the end-to-end skip/re-run
is covered in test_bronze_dag).
"""

from __future__ import annotations

from vdocs.stages.fetch.fetch_pure import Selection
from vdocs.stages.fetch.stage import FetchStage


def test_default_fetch_selection_is_empty(ctx):
    stage = FetchStage()
    assert stage.selection.is_empty  # no blind download — the operator must opt in (§5.6)
    assert "selection" in stage._input_fps(ctx)


def test_selection_enters_fetch_inputs_fp(ctx):
    everything = FetchStage(selection=Selection(all_=True))._input_fps(ctx)
    just_adt = FetchStage(selection=Selection(apps=frozenset({"ADT"})))._input_fps(ctx)
    assert "selection" in everything
    # a different selection ⇒ a different input fingerprint ⇒ not skipped
    assert everything["selection"] != just_adt["selection"]
