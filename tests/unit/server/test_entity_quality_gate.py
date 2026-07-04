"""Unit: the D2.5 floor-verification gate — measured join rates vs declared floors.

Floors are numbers, not adjectives: each floor-verified type's canonical names are
joined against the named vista-meta data-v1 vocabulary; rate < floor fails the
release gate. Measured at gate time against the corpus being released (F1).
"""

from __future__ import annotations

from vdocs.kernel.entity_quality import EntityQuality, EntityTypePolicy
from vdocs.server import entity_quality_gate as eq

_QUALITY = EntityQuality(
    types={
        "routine": EntityTypePolicy(
            status="floor-verified", floor=0.5, vocabulary="code-model/routines.tsv:routine_name"
        ),
        "option": EntityTypePolicy(status="excluded", reason="noise"),
        "build": EntityTypePolicy(status="no-authoritative-vocabulary"),
    },
    peer_vocabulary={"content_hash": "23d0"},
)


def test_load_vocab_reads_the_named_tsv_column(tmp_path):
    d = tmp_path / "code-model"
    d.mkdir()
    (d / "routines.tsv").write_text(
        "routine_name\tpackage\nXQOR\tKernel\norwu\tOE/RR\n", encoding="utf-8"
    )
    vocab = eq.load_vocab(tmp_path, "code-model/routines.tsv:routine_name")
    assert vocab == {"XQOR", "ORWU"}  # normalized upper


def test_measure_rates_and_floor_verdicts():
    rows = eq.measure(
        {"routine": ["XQOR", "orwu", "ZZNOPE", "ZZNADA"], "build": ["OR*3.0*1"]},
        {"routine": {"XQOR", "ORWU"}},
        _QUALITY,
    )
    by_type = {r.type: r for r in rows}
    r = by_type["routine"]
    assert (r.count, r.joined) == (4, 2)
    assert r.rate == 0.5 and r.floor == 0.5 and r.ok  # rate >= floor passes
    assert by_type["build"].status == "no-authoritative-vocabulary"
    assert by_type["build"].ok  # unverifiable types never block
    assert by_type["option"].status == "excluded" and by_type["option"].ok


def test_measure_fails_below_floor():
    rows = eq.measure({"routine": ["XQOR", "ZZ1", "ZZ2", "ZZ3"]}, {"routine": {"XQOR"}}, _QUALITY)
    r = next(x for x in rows if x.type == "routine")
    assert r.rate == 0.25 and not r.ok


def test_measure_flags_undeclared_shipping_type():
    rows = eq.measure({"mystery": ["A"]}, {}, _QUALITY)
    r = next(x for x in rows if x.type == "mystery")
    assert r.status == "UNDECLARED" and not r.ok


def test_gate_verdict():
    ok_rows = eq.measure({"routine": ["XQOR", "ORWU"]}, {"routine": {"XQOR", "ORWU"}}, _QUALITY)
    assert eq.verdict(ok_rows) == "PASS"
    bad_rows = eq.measure({"routine": ["ZZ1"]}, {"routine": {"XQOR"}}, _QUALITY)
    assert eq.verdict(bad_rows) == "FAIL"
