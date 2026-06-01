"""Unit tests for crawl pure parsers — VDL HTML → catalog records (§8 crawl, §16)."""

from vdocs.stages.crawl import crawl_pure as cp

INDEX_HTML = """
<html><body>
  <a href="section.asp?secid=1">Clinical</a>
  <a href="section.asp?secid=2">Infrastructure</a>
  <a href="section.asp?secid=1">Clinical (dup)</a>
  <a href="https://external.example/other">Not a section</a>
</body></html>
"""

SECTION_HTML = """
<html><body>
  <a href="help.asp">Help (not an application link)</a>
  <a href="application.asp?appid=55">Admission Discharge Transfer (ADT)</a>
  <a href="application.asp?appid=70">Social Work (SOW) - DECOMMISSIONED JUL 2020</a>
  <a href="application.asp?appid=80">CPRS: Problem List (GMPL) - ARCHIVE</a>
  <a href="application.asp?appid=55">ADT again (dup)</a>
</body></html>
"""

APP_HTML = """
<html><body>
<table>
  <tr><th>Document</th><th>Format</th><th>Date</th></tr>
  <tr>
    <td>DG*5.3*1057 Deployment, Installation, Back-Out, and Rollback Guide</td>
    <td><a href="/documents/Clinical/ADT/dg_5_3_1057_dibr.docx">DOCX</a></td>
    <td>03/2024</td>
  </tr>
  <tr>
    <td>DG*5.3*1057 Deployment, Installation, Back-Out, and Rollback Guide</td>
    <td><a href="/documents/Clinical/ADT/dg_5_3_1057_dibr.pdf">PDF</a></td>
    <td>03/2024</td>
  </tr>
</table>
</body></html>
"""

# A fallback page: bare file links, no table structure.
APP_HTML_FALLBACK = """
<html><body>
  <a href="/documents/x/readme.docx">Some Readme Guide</a>
  <a href="page.asp?id=9">not a file</a>
</body></html>
"""


def test_parse_index_extracts_unique_sections():
    sections = cp.parse_index(INDEX_HTML)
    assert [s.name for s in sections] == ["Clinical", "Infrastructure"]
    assert sections[0].url.endswith("section.asp?secid=1")
    assert sections[0].url.startswith("https://www.va.gov/")


def test_parse_section_page_extracts_apps_with_status():
    apps = cp.parse_section_page(SECTION_HTML)
    by_code = {a.app_code: a for a in apps}
    assert by_code["ADT"].status == "active"
    assert by_code["SOW"].status == "decommissioned"
    assert by_code["SOW"].decommission_date == "JUL 2020"
    assert by_code["GMPL"].status == "archive"
    # the duplicate appid=55 collapses to one entry
    assert sum(1 for a in apps if a.app_code == "ADT") == 1


def test_parse_application_page_table_rows():
    docs = cp.parse_application_page(APP_HTML)
    assert len(docs) == 2
    docx = next(d for d in docs if d.file_ext == ".docx")
    assert docx.filename == "dg_5_3_1057_dibr.docx"
    assert docx.title.startswith("DG*5.3*1057 Deployment")
    assert docx.doc_type_label == "DOCX"
    assert docx.file_date == "03/2024"
    assert docx.url.startswith("https://www.va.gov/")


def test_parse_application_page_fallback_link_scan():
    docs = cp.parse_application_page(APP_HTML_FALLBACK)
    assert len(docs) == 1
    assert docs[0].filename == "readme.docx"
    assert docs[0].title == "Some Readme Guide"


def test_parse_application_page_empty_when_no_file_links():
    assert cp.parse_application_page("<html><body><p>nothing</p></body></html>") == []


def test_parse_application_page_resolves_relative_href_against_page_url():
    # Live VDL serves RELATIVE doc links ("documents/…") that must resolve against the
    # application-page URL — not the host root. Regression guard for the crawl base bug.
    html = (
        "<table><tr><td>NPM Operational Summary</td>"
        '<td><a href="documents/Infrastructure/NPM/pmuser.docx">DOCX</a></td></tr></table>'
    )
    docs = cp.parse_application_page(
        html, base_url="https://www.va.gov/vdl/application.asp?appid=20"
    )
    assert docs[0].url == "https://www.va.gov/vdl/documents/Infrastructure/NPM/pmuser.docx"


def test_parse_index_skips_empty_section_text():
    # a section.asp link with no visible text is skipped (no name)
    html = '<a href="section.asp?secid=9"></a><a href="section.asp?secid=1">Clinical</a>'
    assert [s.name for s in cp.parse_index(html)] == ["Clinical"]


def test_parse_application_page_title_in_link_text_and_skips_noise_rows():
    # link text is the title itself (not a "DOCX" format label) → title/label fallback;
    # a header-only short row and a non-file link in a data row are both ignored.
    html = """
    <table>
      <tr><th>only one cell</th></tr>
      <tr>
        <td>Installation Guide</td>
        <td><a href="help.asp?id=2">not a file</a>
            <a href="/d/tiuig.docx">TIU Installation Guide</a></td>
      </tr>
    </table>
    """
    docs = cp.parse_application_page(html)
    assert len(docs) == 1
    assert docs[0].title == "TIU Installation Guide"  # link text used as title
    assert docs[0].doc_type_label == "Installation Guide"  # first cell used as label
