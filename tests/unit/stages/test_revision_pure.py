"""Unit tests for revision-history extraction — HTML + GFM-pipe dialects (§6.6)."""

from __future__ import annotations

from vdocs.stages.normalize import revision_pure as rev

_HTML = """## Revision History

The most recent entries are linked.

<table>
<thead><tr>
  <th>Date</th><th>Version</th><th>Page</th><th>Change</th><th>Project Manager</th>
</tr></thead>
<tbody>
<tr>
  <td>03/2024</td><td>5.3</td><td>12</td>
  <td>Updated <a href="#_Toc9">install</a> steps</td><td>REDACTED</td>
</tr>
<tr>
  <td>1/15/20</td><td>5.2</td><td>3, 5</td><td>Initial release</td><td>REDACTED</td>
</tr>
</tbody>
</table>

## Installation
"""

_PIPE = """## Revision History

| Date | Version | Page | Change |
|------|---------|------|--------|
| 03/2024 | 5.3 | [12](#p12) | Updated [steps](#s) |
| 01/2020 | 5.2 | 3 | Initial |

## Next
"""


def test_norm_date():
    assert rev._norm_date("3/2024") == "2024-03"
    assert rev._norm_date("1/15/20") == "2020-01"  # 2-digit year < 50 → 20xx
    assert rev._norm_date("Feb 2009") == "Feb 2009"  # unrecognised passes through


def test_parse_html_revision_table():
    found = rev.find_revision_table(_HTML)
    assert found is not None
    records = rev.parse_revision_table(found[2])
    assert [(r.date, r.version, r.pages, r.change) for r in records] == [
        ("2024-03", "5.3", [12], "Updated install steps"),
        ("2020-01", "5.2", [3, 5], "Initial release"),
    ]
    assert records[0].refs == ["#_Toc9"]  # the PM "REDACTED" column is dropped


def test_parse_pipe_revision_table_docling_dialect():
    found = rev.find_revision_table(_PIPE)
    assert found is not None
    records = rev.parse_revision_table(found[2])
    assert (records[0].date, records[0].version, records[0].pages) == ("2024-03", "5.3", [12])
    assert records[0].change == "Updated steps"  # link text kept, anchor stripped
    assert records[0].refs == ["#p12", "#s"]


def test_extract_revision_history_removes_table_and_returns_records():
    cleaned, records = rev.extract_revision_history(_HTML)
    assert len(records) == 2
    assert "<table" not in cleaned and "Updated" not in cleaned  # table gone from the body
    assert "## Installation" in cleaned  # the rest of the doc is kept


def test_extract_no_revision_table_is_noop():
    body = "# Doc\n\nNo revision table here.\n"
    assert rev.extract_revision_history(body) == (body, [])


def test_parse_edge_cases():
    assert rev.parse_revision_table("<table>\n</table>") == []  # no rows
    assert rev.parse_revision_table("| Date | Version | Change |") == []  # single pipe line
    # an HTML revision table with an empty <tr></tr> data row → that row is skipped
    html = (
        "<table><tr><th>Date</th><th>Version</th><th>Change</th></tr>"
        "<tr></tr><tr><td>03/2024</td><td>5.3</td><td>x</td></tr></table>"
    )
    assert len(rev.parse_revision_table(html)) == 1
    # a pipe revision table with a stray separator row in the data is ignored
    pipe = "| Date | Version | Change |\n|---|---|---|\n|---|---|---|\n| 03/2024 | 5.3 | y |"
    recs = rev.parse_revision_table(pipe)
    assert [r.change for r in recs] == ["y"]


def test_find_revision_table_ignores_non_revision_pipe_table():
    body = "Intro\n\n| Name | Value |\n|------|-------|\n| a | b |\n\nmore\n"
    assert rev.find_revision_table(body) is None  # header lacks date/change → not a revision table


def test_revision_sidecar_summary_and_records():
    _, records = rev.extract_revision_history(_HTML)
    side = rev.revision_sidecar(records)
    assert side["revision_count"] == 2
    assert side["revision_newest"] == "2024-03" and side["revision_oldest"] == "2020-01"
    assert side["revisions"][0]["change"] == "Updated install steps"
