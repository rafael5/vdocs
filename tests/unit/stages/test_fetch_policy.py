"""Unit tests for the gate-policy loader — reads scope-policy + doctype-policy registries."""

from pathlib import Path

from vdocs.stages.fetch.policy import load_gate_policy

_REGISTRIES = Path(__file__).resolve().parents[3] / "registries"


def test_load_gate_policy_from_real_registries():
    g = load_gate_policy(_REGISTRIES)
    # app scope: VistA allowed, decommissioned denied
    assert "VistA" in g.allowed_system_prefixes
    assert "decommissioned" in g.denied_app_status
    # doctype policy: the omit-list carries the Tier B/C/D codes, not the kept reference core
    assert {"RN", "DIBR", "SUP", "WF"} <= g.omitted_doc_codes
    assert "UM" not in g.omitted_doc_codes
    assert "TM" not in g.omitted_doc_codes
