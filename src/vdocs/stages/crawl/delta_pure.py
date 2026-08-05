"""The snapshot-to-snapshot delta (VO.3) and the parser tripwire (VO.4a) — pure, no I/O.

What changed on the VDL between two crawls, answered as a query instead of an archaeology
project. Two constraints shape it:

**Identity is the VDL's own numeric id.** Every crawled URL carries ``section.asp?secid=N`` and
``application.asp?appid=N``. Names are display strings — VA re-titling a package would otherwise
read as one application dying and another being born, which is precisely the change a timeline
exists to *not* invent. Where an id is missing, the URL itself is the key; a name never is.

**``app_status`` is parsed, not served.** It comes from a regex over the application's displayed
name suffix (``" - ARCHIVE"``, ``" - DECOMMISSIONED <date>"`` — see ``crawl_pure``). A cosmetic
change to how VA writes that suffix would present as every application changing lifecycle on the
same day. Published as-is it would read as history, so the delta flags it and suppresses the rows
instead (VO.4a). The same break would also show as mass renames; the flag is a verdict on the
whole delta, not just the transition list.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

from vdocs.models.catalog import Catalog

# A corpus-wide lifecycle change is a broken parser until proven otherwise. The ratio is what
# fires in production (396 applications → ~20); the floor keeps the rule from calling a small
# crawl suspect when a single genuine transition happens to be a large share of it.
SUSPECT_RATIO = 0.05
SUSPECT_FLOOR = 10


@dataclass(frozen=True)
class SectionDelta:
    """One library section's composition in both snapshots (present in either, or both)."""

    secid: str
    name: str
    documents_before: int
    documents_after: int
    applications_before: int
    applications_after: int
    status_before: dict[str, int] = field(default_factory=dict)
    status_after: dict[str, int] = field(default_factory=dict)

    @property
    def documents_change(self) -> int:
        return self.documents_after - self.documents_before


@dataclass(frozen=True)
class AppRef:
    appid: str
    name: str
    section: str


@dataclass(frozen=True)
class AppRename:
    appid: str
    name_before: str
    name_after: str


@dataclass(frozen=True)
class StatusTransition:
    appid: str
    name: str
    status_before: str
    status_after: str


@dataclass(frozen=True)
class Delta:
    """What changed between two snapshots. ``transitions`` is empty when ``suspect_parser``."""

    sections: list[SectionDelta]
    arrivals: list[AppRef]
    departures: list[AppRef]
    renames: list[AppRename]
    transitions: list[StatusTransition]
    suspect_parser: bool = False
    suspect_reason: str = ""


@dataclass(frozen=True)
class _App:
    appid: str
    name: str
    status: str
    section: str


def _id_from(url: str, param: str) -> str:
    """The VDL's own id for this page, or the URL when it carries none — never a name."""
    return parse_qs(urlparse(url).query).get(param, [""])[0] or url


def _apps(catalog: Catalog) -> dict[str, _App]:
    return {
        _id_from(app.url, "appid"): _App(
            appid=_id_from(app.url, "appid"),
            name=app.name,
            status=app.status,
            section=section.name,
        )
        for section in catalog.sections
        for app in section.applications
    }


@dataclass(frozen=True)
class _SectionFacts:
    name: str
    documents: int
    applications: int
    statuses: dict[str, int]


def _sections(catalog: Catalog) -> dict[str, _SectionFacts]:
    return {
        _id_from(section.url, "secid"): _SectionFacts(
            name=section.name,
            documents=sum(len(a.documents) for a in section.applications),
            applications=len(section.applications),
            statuses=dict(Counter(a.status for a in section.applications)),
        )
        for section in catalog.sections
    }


_EMPTY = _SectionFacts(name="", documents=0, applications=0, statuses={})


def vdl_delta(
    before: Catalog,
    after: Catalog,
    *,
    suspect_ratio: float = SUSPECT_RATIO,
    suspect_floor: int = SUSPECT_FLOOR,
) -> Delta:
    """Compare two crawl snapshots — composition per section, and what happened to each app."""
    sec_b, sec_a = _sections(before), _sections(after)
    sections = [
        SectionDelta(
            secid=secid,
            name=(sec_a.get(secid) or sec_b[secid]).name,
            documents_before=sec_b.get(secid, _EMPTY).documents,
            documents_after=sec_a.get(secid, _EMPTY).documents,
            applications_before=sec_b.get(secid, _EMPTY).applications,
            applications_after=sec_a.get(secid, _EMPTY).applications,
            status_before=sec_b.get(secid, _EMPTY).statuses,
            status_after=sec_a.get(secid, _EMPTY).statuses,
        )
        for secid in sorted(set(sec_b) | set(sec_a), key=lambda k: (sec_a.get(k) or sec_b[k]).name)
    ]

    apps_b, apps_a = _apps(before), _apps(after)
    common = sorted(set(apps_b) & set(apps_a))
    arrivals = [
        AppRef(appid=k, name=apps_a[k].name, section=apps_a[k].section)
        for k in sorted(set(apps_a) - set(apps_b))
    ]
    departures = [
        AppRef(appid=k, name=apps_b[k].name, section=apps_b[k].section)
        for k in sorted(set(apps_b) - set(apps_a))
    ]
    renames = [
        AppRename(appid=k, name_before=apps_b[k].name, name_after=apps_a[k].name)
        for k in common
        if apps_b[k].name != apps_a[k].name
    ]
    transitions = [
        StatusTransition(
            appid=k,
            name=apps_a[k].name,
            status_before=apps_b[k].status,
            status_after=apps_a[k].status,
        )
        for k in common
        if apps_b[k].status != apps_a[k].status
    ]

    changed = len(transitions)
    suspect = changed >= suspect_floor and changed > suspect_ratio * len(common)
    reason = ""
    if suspect:
        share = changed / len(common)
        reason = (
            f"{changed} of {len(common)} applications changed app_status in one delta "
            f"({share:.0%}) — app_status is parsed from the application name suffix, so a "
            "corpus-wide change is a parser break until proven otherwise. Transitions are "
            "suppressed; check crawl_pure's status regex against a live VDL page before "
            "reading anything here as history."
        )

    return Delta(
        sections=sections,
        arrivals=arrivals,
        departures=departures,
        renames=renames,
        transitions=[] if suspect else transitions,
        suspect_parser=suspect,
        suspect_reason=reason,
    )


def _counts(statuses: dict[str, int]) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())) or "-"


def render_delta(delta: Delta, *, before_name: str, after_name: str) -> str:
    """The delta as a report. Leads with the tripwire when it fired — that is the headline."""
    out: list[str] = [f"=== VDL delta: {before_name} → {after_name} ==="]
    if delta.suspect_parser:
        out += ["", f"⚠️  SUSPECT-PARSER: {delta.suspect_reason}"]

    out += ["", "-- sections (documents, applications, lifecycle labels) --"]
    for s in delta.sections:
        sign = f"{s.documents_change:+d}" if s.documents_change else "0"
        out.append(
            f"  {s.name}: {s.documents_before} → {s.documents_after} documents ({sign}), "
            f"{s.applications_before} → {s.applications_after} applications"
        )
        out.append(f"      before: {_counts(s.status_before)}   after: {_counts(s.status_after)}")

    out += ["", f"-- applications: {len(delta.arrivals)} arrived, {len(delta.departures)} left --"]
    for a in delta.arrivals:
        out.append(f"  + appid={a.appid} {a.name} ({a.section})")
    for d in delta.departures:
        out.append(f"  - appid={d.appid} {d.name} ({d.section})")

    out += ["", f"-- renames: {len(delta.renames)} --"]
    for r in delta.renames:
        out.append(f"  appid={r.appid}: {r.name_before!r} → {r.name_after!r}")

    if delta.suspect_parser:
        out += ["", "-- lifecycle transitions: SUPPRESSED (see SUSPECT-PARSER above) --"]
    else:
        out += ["", f"-- lifecycle transitions: {len(delta.transitions)} --"]
        for t in delta.transitions:
            out.append(f"  appid={t.appid} {t.name}: {t.status_before} → {t.status_after}")
    return "\n".join(out)
