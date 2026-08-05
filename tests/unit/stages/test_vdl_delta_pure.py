"""The snapshot-to-snapshot delta (VO.3) and the parser tripwire (VO.4a) — pure, no I/O.

Two rules earn their tests here:

* **Identity is the VDL's own numeric id** (``appid``/``secid``, carried in every crawled URL),
  never a parsed name. VA renaming an application must read as a rename, not as one application
  dying and another being born — the whole point of a timeline is that the same thing is
  recognisable across it.
* **``app_status`` is a regex over the application's displayed name suffix**, not a field VA
  serves us. A cosmetic change to how VA writes " - ARCHIVE" would present as every application
  changing lifecycle at once. That reads as history; it is a parser break, and the delta must say
  so instead of publishing it.
"""

from __future__ import annotations

from vdocs.models.catalog import (
    Catalog,
    CatalogApplication,
    CatalogDocument,
    CatalogSection,
)
from vdocs.stages.crawl.delta_pure import render_delta, vdl_delta


def _docs(n: int) -> list[CatalogDocument]:
    return [
        CatalogDocument(
            title=f"Doc {i}", url=f"http://x/d{i}.docx", filename=f"d{i}.docx", file_ext=".docx"
        )
        for i in range(n)
    ]


def _app(appid: int, name: str, *, status: str = "active", docs: int = 1) -> CatalogApplication:
    return CatalogApplication(
        name=name,
        app_code=name[:3].upper(),
        url=f"https://www.va.gov/vdl/application.asp?appid={appid}",
        status=status,
        documents=_docs(docs),
    )


def _catalog(*sections: CatalogSection) -> Catalog:
    return Catalog(sections=list(sections))


def _section(secid: int, name: str, *apps: CatalogApplication) -> CatalogSection:
    return CatalogSection(
        name=name,
        url=f"https://www.va.gov/vdl/section.asp?secid={secid}",
        applications=list(apps),
    )


def test_unchanged_section_reports_zero_rather_than_being_absent() -> None:
    """'No row' and 'no change' must not look the same — absence is how a regression hides."""
    before = _catalog(_section(1, "Clinical", _app(10, "Nursing")))
    after = _catalog(_section(1, "Clinical", _app(10, "Nursing")))

    delta = vdl_delta(before, after)

    (section,) = delta.sections
    assert section.name == "Clinical"
    assert section.documents_before == section.documents_after == 1
    assert section.documents_change == 0


def test_section_counts_are_broken_down_by_lifecycle_label() -> None:
    before = _catalog(_section(1, "Clinical", _app(10, "Nursing"), _app(11, "Lab")))
    after = _catalog(
        _section(1, "Clinical", _app(10, "Nursing"), _app(11, "Lab", status="archive"))
    )

    (section,) = vdl_delta(before, after).sections

    assert section.status_before == {"active": 2}
    assert section.status_after == {"active": 1, "archive": 1}


def test_a_renamed_application_is_a_rename_not_a_departure_and_an_arrival() -> None:
    """Keyed on ``appid``: VA re-titling a package must not read as retirement plus rebirth."""
    before = _catalog(_section(1, "Clinical", _app(10, "Nursing")))
    after = _catalog(_section(1, "Clinical", _app(10, "Nursing Service")))

    delta = vdl_delta(before, after)

    assert delta.departures == [] and delta.arrivals == []
    (rename,) = delta.renames
    assert rename.appid == "10"
    assert (rename.name_before, rename.name_after) == ("Nursing", "Nursing Service")


def test_arrivals_and_departures_are_reported_by_appid() -> None:
    before = _catalog(_section(1, "Clinical", _app(10, "Nursing"), _app(11, "Lab")))
    after = _catalog(_section(1, "Clinical", _app(10, "Nursing"), _app(12, "Pharmacy")))

    delta = vdl_delta(before, after)

    assert [d.appid for d in delta.departures] == ["11"]
    assert [a.appid for a in delta.arrivals] == ["12"]


def test_a_single_genuine_transition_is_one_row_and_no_flag() -> None:
    apps_before = [_app(i, f"App{i}") for i in range(20)]
    apps_after = [_app(i, f"App{i}") for i in range(20)]
    apps_after[3] = _app(3, "App3", status="archive")

    delta = vdl_delta(
        _catalog(_section(1, "Clinical", *apps_before)),
        _catalog(_section(1, "Clinical", *apps_after)),
    )

    assert delta.suspect_parser is False
    (transition,) = delta.transitions
    assert transition.appid == "3"
    assert (transition.status_before, transition.status_after) == ("active", "archive")


def test_a_corpus_wide_status_change_is_a_suspected_parser_break_not_history() -> None:
    """The VO.4a tripwire: mass lifecycle change is a broken regex until proven otherwise."""
    apps_before = [_app(i, f"App{i}") for i in range(20)]
    apps_after = [_app(i, f"App{i}", status="archive") for i in range(20)]

    delta = vdl_delta(
        _catalog(_section(1, "Clinical", *apps_before)),
        _catalog(_section(1, "Clinical", *apps_after)),
    )

    assert delta.suspect_parser is True
    assert delta.transitions == []  # suppressed: not published as if it were history
    assert "20" in delta.suspect_reason and "app_status" in delta.suspect_reason


def test_the_tripwire_does_not_fire_on_a_tiny_corpus() -> None:
    """One change out of three is 33% but only one application — a floor keeps fixtures sane."""
    before = _catalog(_section(1, "Clinical", _app(10, "A"), _app(11, "B"), _app(12, "C")))
    after = _catalog(
        _section(1, "Clinical", _app(10, "A", status="archive"), _app(11, "B"), _app(12, "C"))
    )

    delta = vdl_delta(before, after)

    assert delta.suspect_parser is False
    assert len(delta.transitions) == 1


def test_a_section_present_in_only_one_snapshot_still_reports() -> None:
    before = _catalog(_section(1, "Clinical", _app(10, "Nursing")))
    after = _catalog(
        _section(1, "Clinical", _app(10, "Nursing")), _section(2, "Infrastructure", _app(20, "XU"))
    )

    sections = {s.name: s for s in vdl_delta(before, after).sections}

    assert sections["Infrastructure"].documents_before == 0
    assert sections["Infrastructure"].documents_after == 1


def test_render_names_both_states_of_a_transition() -> None:
    before = _catalog(_section(1, "Clinical", *[_app(i, f"App{i}") for i in range(20)]))
    apps_after = [_app(i, f"App{i}") for i in range(20)]
    apps_after[3] = _app(3, "App3", status="archive")
    after = _catalog(_section(1, "Clinical", *apps_after))

    text = render_delta(vdl_delta(before, after), before_name="2026-06-10", after_name="2026-09-01")

    assert "2026-06-10" in text and "2026-09-01" in text
    assert "active" in text and "archive" in text
    assert "SUSPECT-PARSER" not in text


def test_render_leads_with_the_suspect_flag_when_it_fires() -> None:
    before = _catalog(_section(1, "Clinical", *[_app(i, f"App{i}") for i in range(20)]))
    after = _catalog(
        _section(1, "Clinical", *[_app(i, f"App{i}", status="archive") for i in range(20)])
    )

    text = render_delta(vdl_delta(before, after), before_name="a", after_name="b")

    assert "SUSPECT-PARSER" in text
