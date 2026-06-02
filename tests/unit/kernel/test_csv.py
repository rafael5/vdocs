"""Unit tests for kernel.csv — the single shared CSV-table serialiser (§9.2/§11).

A primitive used by ``crawl``/``catalog``/``serve-inventory`` to emit their human-browsable
flat tables lives in the kernel, not copy-pasted per stage.
"""

from vdocs.kernel import csv as kcsv


def test_to_csv_writes_header_then_rows_in_column_order():
    out = kcsv.to_csv(
        ["b", "a"],
        [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}],
    )
    assert out.splitlines() == ["b,a", "2,1", "4,3"]


def test_to_csv_ignores_extra_keys_by_default():
    # model_dump() carries fields beyond the published columns — they must be dropped, not raise.
    out = kcsv.to_csv(["a"], [{"a": "1", "extra": "x"}])
    assert out.splitlines() == ["a", "1"]


def test_to_csv_empty_rows_is_header_only():
    assert kcsv.to_csv(["a", "b"], []) == "a,b\r\n"


def test_to_csv_missing_key_is_blank_cell():
    out = kcsv.to_csv(["a", "b"], [{"a": "1"}])
    assert out.splitlines() == ["a,b", "1,"]


def test_to_csv_strict_raises_on_extra_keys():
    import pytest

    with pytest.raises(ValueError):
        kcsv.to_csv(["a"], [{"a": "1", "extra": "x"}], strict=True)
