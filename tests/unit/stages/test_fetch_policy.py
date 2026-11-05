"""Unit tests for the gate-policy loader — reads scope-policy + doctype-policy registries."""

from pathlib import Path

import yaml

from vdocs.stages.fetch.policy import load_gate_config, load_gate_policy

_REGISTRIES = Path(__file__).resolve().parents[3] / "registries"
_DOCTYPE_FIELDS = {"tier", "decision", "label", "reason"}


def test_load_gate_policy_from_real_registries():
    g = load_gate_policy(_REGISTRIES)
    # app scope: VistA allowed, decommissioned denied
    assert "VistA" in g.allowed_system_prefixes
    assert "decommissioned" in g.denied_app_status
    # doctype policy: the omit-list carries the Tier B/C/D codes, not the kept reference core
    assert {"RN", "DIBR", "SUP", "WF"} <= g.omitted_doc_codes
    assert "UM" not in g.omitted_doc_codes
    assert "TM" not in g.omitted_doc_codes


def test_every_doctype_entry_parses_to_exactly_its_four_fields():
    # An unquoted comma inside a YAML flow mapping ends the value: `reason: a, b` parses as
    # reason "a" plus a stray key "b". Nine reasons were cut that way, and `vdocs gate` printed
    # them truncated ("ephemeral version-delta changelog (largest single type").
    raw = yaml.safe_load((_REGISTRIES / "inventory" / "doctype-policy.yaml").read_text())
    malformed = {
        code: sorted(set(spec) ^ _DOCTYPE_FIELDS)
        for code, spec in raw["doctypes"].items()
        if set(spec) != _DOCTYPE_FIELDS
    }
    assert malformed == {}
    reasons = {d.code: d.reason for d in load_gate_config(_REGISTRIES).doctypes}
    assert reasons["RN"] == "ephemeral version-delta changelog (largest single type, 796 docs)"
