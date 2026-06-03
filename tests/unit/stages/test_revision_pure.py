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
    assert rev._norm_date("Feb 2009") == "2009-02"  # month-name form normalised (§6.4)
    assert rev._norm_date("April 2015") == "2015-04"
    assert rev._norm_date("sometime soon") == "sometime soon"  # unrecognised passes through


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
    cleaned, records, flag = rev.extract_revision_history(_HTML)
    assert len(records) == 2 and flag is None
    assert "<table" not in cleaned and "Updated" not in cleaned  # table gone from the body
    assert "## Revision History" not in cleaned  # the heading goes too (§6.4 apparatus strip)
    assert "## Installation" in cleaned  # the rest of the doc is kept


def test_extract_no_revision_table_is_noop():
    body = "# Doc\n\nNo revision table here.\n"
    assert rev.extract_revision_history(body) == (body, [], None)


def test_extract_strips_plain_heading_and_descriptive_boilerplate():
    body = (
        "Revision History\n\n"
        "The following table displays the revision history for this document.\n\n"
        "| Date | Description | Author |\n|------|-------------|--------|\n"
        "| Feb 2018 | Patch OR*3.0*447 | redacted |\n\n"
        "# Introduction\n\nReal content.\n"
    )
    cleaned, records, flag = rev.extract_revision_history(body)
    assert flag is None and len(records) == 1
    assert "Revision History" not in cleaned  # plain heading removed
    assert "displays the revision history" not in cleaned  # descriptive boilerplate removed
    assert "| Date |" not in cleaned  # table removed
    assert "# Introduction" in cleaned and "Real content." in cleaned


def test_extract_removes_all_revision_tables_in_a_doc():
    # DIBR-template docs carry two revision tables (Revision History + Documentation Revisions);
    # both must be lifted, not just the first (§6.4)
    body = (
        "Revision History\n\n"
        "| Date | Description | Author |\n|------|-------------|--------|\n"
        "| Feb 2018 | first table | a |\n\n"
        "# Overview\n\nprose\n\n"
        "Documentation Revisions\n\n"
        "| Date | Revision | Description |\n|------|----------|-------------|\n"
        "| Mar 2019 | 1.1 | second table | \n\n"
        "# Introduction\n\nx\n"
    )
    cleaned, records, flag = rev.extract_revision_history(body)
    assert flag is None and len(records) == 2  # both tables captured
    assert "first table" not in cleaned and "second table" not in cleaned
    assert "Revision History" not in cleaned and "Documentation Revisions" not in cleaned
    assert "# Overview" in cleaned and "prose" in cleaned and "# Introduction" in cleaned


def test_extract_revision_heading_without_table_is_retained_and_flagged():
    # capture-before-strip: a revision-history heading with no parseable table is LEFT + FLAGGED
    body = "## Revision History\n\nSee git history for changes.\n\n# Introduction\n\nx\n"
    cleaned, records, flag = rev.extract_revision_history(body)
    assert records == []
    assert flag == rev.REVISION_UNPARSED_FLAG
    assert "## Revision History" in cleaned  # never deleted blind


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


# --- §6.4 corrected detection contract: the real VA dialects (Description, not Change) ----------
# Each is the column header + a plain/bold/blockquote `Revision History` heading above it (the
# proximity guard). The v1 predicate required `change` AND (`version`|`patch`) → matched 0 of these.
_DESC_AUTHOR = """Revision History

| Date | Revision | Description | Author |
|------|----------|-------------|--------|
| Feb 2018 | 1.2 | Patch OR*3.0*447 – 2FA | redacted |
| Mar 2010 | 1.0 | Initial Release | redacted |

# Introduction
"""

_VERSION_DESC = """> **Revision History**

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 10/6/2020 | 1.2 | Updates for WEBB*2*17 | David Horn |

# Introduction
"""

_DATE_DESC = """Documentation Revisions

| Date | Description of Change | Authors |
|------|----------------------|---------|
| Feb 2018 | Patch OR*3.0*447 | redacted |

# Introduction
"""

_PM_TW = """Revision History

| Date | Description (Patch # if applic.) | Project Manager | Technical Writer |
|------|----------------------------------|-----------------|------------------|
| 09/2015 | Initial | redacted | redacted |

# Introduction
"""


def test_detects_date_revision_description_author_dialect():
    found = rev.find_revision_table(_DESC_AUTHOR)
    assert found is not None
    recs = rev.parse_revision_table(found[2])
    assert [(r.date, r.change) for r in recs] == [
        ("2018-02", "Patch OR*3.0*447 – 2FA"),
        ("2010-03", "Initial Release"),
    ]


def test_detects_version_description_author_blockquote_bold_dialect():
    found = rev.find_revision_table(_VERSION_DESC)
    assert found is not None
    recs = rev.parse_revision_table(found[2])
    assert recs[0].version == "1.2"
    assert recs[0].change == "Updates for WEBB*2*17"


def test_detects_date_description_author_dialect_under_documentation_revisions():
    found = rev.find_revision_table(_DATE_DESC)
    assert found is not None
    recs = rev.parse_revision_table(found[2])
    assert recs[0].change == "Patch OR*3.0*447"


def test_detects_pm_techwriter_dialect():
    assert rev.find_revision_table(_PM_TW) is not None


def test_detects_pipe_table_with_empty_leading_header_row():
    # Docling/Pandoc emit a leading empty header row; the real Date|Version|Description columns are
    # in the first *data* row (the ANRV/ASCD DIBR dialect) — detect + parse from there (§6.4)
    body = (
        "Revision History\n\n"
        "|   |   |   |\n"
        "|---|---|---|\n"
        "| **Date** | **Version** | **Description** |\n"
        "| Mar 2019 | 1.1 | Updated screens |\n\n"
        "# Introduction\n\nx\n"
    )
    found = rev.find_revision_table(body)
    assert found is not None
    recs = rev.parse_revision_table(found[2])
    assert [(r.date, r.version, r.change) for r in recs] == [("2019-03", "1.1", "Updated screens")]
    cleaned, records, flag = rev.extract_revision_history(body)
    assert flag is None and len(records) == 1
    assert "Revision History" not in cleaned and "Updated screens" not in cleaned


def test_proximity_guard_rejects_date_description_table_without_revision_heading():
    # a date/description table that is NOT under a revision-history heading must not be stripped
    body = (
        "## Audit Log\n\n"
        "| Date | Description | Owner |\n|------|-------------|-------|\n"
        "| 2020 | something happened | x |\n\n# Next\n"
    )
    assert rev.find_revision_table(body) is None


def test_revision_sidecar_summary_and_records():
    _, records, _ = rev.extract_revision_history(_HTML)
    side = rev.revision_sidecar(records)
    assert side["revision_count"] == 2
    assert side["revision_newest"] == "2024-03" and side["revision_oldest"] == "2020-01"
    assert side["revisions"][0]["change"] == "Updated install steps"
