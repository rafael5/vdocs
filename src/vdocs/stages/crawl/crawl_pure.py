"""Pure HTML → catalog parsing for the VA VDL (§8 crawl; ported from v1 §16).

The VDL is a 3-level site:
  1. index page (``va.gov/vdl/``)  — ``section.asp`` links → sections
  2. section page                  — ``application.asp`` links → applications
  3. application page              — tables of file links → documents

All functions are pure: an HTML string in, Pydantic catalog records out. No I/O —
the thin ``stage.py`` driver supplies the HTML by fetching it.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from vdocs.models.catalog import CatalogApplication, CatalogDocument, CatalogSection

_VDL_BASE = "https://www.va.gov/vdl/"
_DOC_BASE = "https://www.va.gov/"

_ARCHIVE_RE = re.compile(r"\s*-\s*ARCHIVE\s*$", re.I)
_DECOMM_RE = re.compile(r"\s*-\s*DECOMMISSIONED\s*(.*?)\s*$", re.I)
_APP_CODE_RE = re.compile(r"\(([A-Z0-9+/ ]{1,20})\)\s*$")

_FILE_EXTS = (".pdf", ".doc", ".docx", ".zip", ".txt")
_FORMAT_LABELS = {"DOCX", "PDF", "DOC", "ZIP", "TXT", "WORD"}
_DATE_RE = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}/\d{4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})",
    re.I,
)


def _parse_app_name(raw: str) -> tuple[str, str, str]:
    """Return (clean_name, status, decommission_date) from a raw VDL app-name string."""
    m = _ARCHIVE_RE.search(raw)
    if m:
        return raw[: m.start()].strip(), "archive", ""
    m = _DECOMM_RE.search(raw)
    if m:
        return raw[: m.start()].strip(), "decommissioned", m.group(1).strip()
    return raw.strip(), "active", ""


def _extract_app_code(name: str) -> str:
    """Extract 'NUR' from 'Nursing (NUR)'."""
    m = _APP_CODE_RE.search(name)
    return m.group(1).strip() if m else ""


def parse_index(html: str, base_url: str = _VDL_BASE) -> list[CatalogSection]:
    """Parse the VDL index page → sections (``section.asp?secid=N`` links, de-duplicated)."""
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    sections: list[CatalogSection] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if "section.asp" not in href:
            continue
        full_url = urljoin(base_url, href)
        sec_id = parse_qs(urlparse(full_url).query).get("secid", [""])[0]
        if sec_id in seen:
            continue
        seen.add(sec_id)
        name = a.get_text(strip=True)
        if name:
            sections.append(CatalogSection(name=name, url=full_url))
    return sections


def parse_section_page(html: str, base_url: str = _VDL_BASE) -> list[CatalogApplication]:
    """Parse a section page → applications (``application.asp?appid=N`` links, de-duplicated)."""
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    apps: list[CatalogApplication] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if "application.asp" not in href:
            continue
        full_url = urljoin(base_url, href)
        app_id = parse_qs(urlparse(full_url).query).get("appid", [""])[0]
        if app_id in seen:
            continue
        seen.add(app_id)
        clean_name, status, decomm = _parse_app_name(a.get_text(strip=True))
        apps.append(
            CatalogApplication(
                name=clean_name,
                app_code=_extract_app_code(clean_name),
                url=full_url,
                status=status,
                decommission_date=decomm,
            )
        )
    return apps


def _file_link(href: str) -> bool:
    return any(href.lower().endswith(ext) for ext in _FILE_EXTS)


def _make_document(href: str, title: str, label: str, date: str, base_url: str) -> CatalogDocument:
    full_url = urljoin(base_url, href)
    filename = urlparse(href).path.rsplit("/", 1)[-1]
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return CatalogDocument(
        title=title,
        url=full_url,
        filename=filename,
        file_ext=ext,
        doc_type_label=label,
        file_date=date,
    )


def parse_application_page(html: str, base_url: str = _DOC_BASE) -> list[CatalogDocument]:
    """Parse an application page → documents. Table-based scan, with a broad-link fallback."""
    soup = BeautifulSoup(html, "html.parser")
    docs: list[CatalogDocument] = []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            cell_texts = [c.get_text(strip=True) for c in cells]
            date = next((m.group(1) for ct in cell_texts if (m := _DATE_RE.search(ct))), "")
            for a in row.find_all("a", href=True):
                href = str(a["href"])
                if not _file_link(href):
                    continue
                link_text = a.get_text(strip=True)
                if link_text.upper() in _FORMAT_LABELS:
                    label = link_text.upper()
                    title = next(
                        (t for t in cell_texts if t and t.upper() not in _FORMAT_LABELS),
                        _make_document(href, "", "", "", base_url).filename,
                    )
                else:
                    title = link_text or (cell_texts[1] if len(cell_texts) > 1 else "")
                    label = cell_texts[0] if cell_texts else ""
                docs.append(_make_document(href, title, label, date, base_url))

    if not docs:
        for a in soup.find_all("a", href=True):
            href = str(a["href"])
            if _file_link(href):
                docs.append(_make_document(href, a.get_text(strip=True), "", "", base_url))

    return docs
