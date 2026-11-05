#!/usr/bin/env python3
"""Inventory browser, step 0 — re-derive every figure in the proposal's §1, §3 and §4.

`docs/proposals/inventory-browser-proposal.md` quoted figures that ad-hoc scripts measured on the
2026-11-05 lake and that were never committed. This script measures each of them again, from the
lake and the registries, through the pipeline's own definitions — imported, never restated:

* the join key: ``kernel.ids.doc_id``;
* disposition, and what a VistA record is: ``load_gate_policy``, ``sole_survivors`` and
  ``classify``. A VistA record is a genuine (non-noise) record the gate's ``app_in_scope`` admits;
* profile tags: ``load_profile_maps`` and ``profile_tags``;
* fetch status: ``inventory_status`` over ``StateStore.all_acquisitions()``, the join behind
  ``vdocs inventory --status``, reported beside the acquisition row itself;
* the last-updated date: ``official_date`` from each ``history.yaml`` member under
  ``documents/gold/consolidated/``, matched to records by ``doc_id`` (never
  ``v_documents.published``, which is the title-page date only).

Each figure is reported beside the value the proposal printed before step 0. Read-only on the lake:
every SQLite file is opened ``mode=ro`` and nothing is written under ``--data-dir``. Writes a
markdown report and a sibling JSON; the same lake gives the same JSON apart from
``provenance.run_date``.

Usage:
    python scripts/inventory_measurements.py [--data-dir DIR] [--registries DIR]
        [--package-namespace TSV] [--out REPORT.md]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sqlite3
import statistics
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from vdocs.kernel import personas
from vdocs.kernel.ids import doc_id
from vdocs.kernel.registry import load_mapping
from vdocs.models.catalog import EnrichedInventory, EnrichedRecord
from vdocs.models.stage import Acquisition
from vdocs.orchestrator.state import StateStore
from vdocs.stages.fetch.fetch_pure import GatePolicy, sole_survivors
from vdocs.stages.fetch.policy import load_gate_policy
from vdocs.stages.serve_inventory.completeness_pure import (
    classify,
    completeness_report,
    docx_anchor_keys,
)
from vdocs.stages.serve_inventory.serve_pure import inventory_status

log = structlog.get_logger(__name__)

DEFAULT_PACKAGE_TSV = (
    Path.home() / "projects" / "vista-meta" / "vista" / "export" / "code-model"
) / "package-namespace.tsv"

# The four listing fields of the proposed row key (§3) and the gold columns this script reads.
ROW_KEY_FIELDS = ("app_url", "section_name", "doc_url", "patch_id")
GOLD_COLUMNS = (
    "doc_id",
    "app_code",
    "doc_type",
    "pkg_ns",
    "app_name",
    "app_user",
    "doc_user",
    "software_class",
    "function_category",
    "is_latest",
    "published",
)
# The registry files the measurements read, hashed into the provenance.
REGISTRY_FILES = (
    "scope-policy.yaml",
    "doctype-policy.yaml",
    "app-profiles.yaml",
    "doc-user.yaml",
    "function-domains.yaml",
)
# Facet name → (profile tag, v_documents column); Type is the doc-type code itself.
PROFILE_FACETS = (
    ("Domain", "function_category"),
    ("Audience", "doc_user"),
    ("App user", "app_user"),
)
APP_LEVEL_TAGS = ("app_user", "software_class", "function_category")
ISO_MONTH = re.compile(r"\d{4}-\d{2}")
NEVER_ATTEMPTED = "never-attempted"


# --- inputs ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Lake:
    """Everything the measurements read, loaded once."""

    records: list[EnrichedRecord]
    policy: GatePolicy
    profile_maps: personas.ProfileMaps
    app_profile_names: dict[str, str]  # app_code → name, from app-profiles.yaml
    acquisitions: dict[str, Acquisition]
    gold: list[dict[str, Any]]  # v_documents rows
    histories: list[dict[str, Any]]  # history.yaml mappings, in path order
    raw_documents: list[dict[str, Any]]  # the crawl's document links (for file_date)
    packages: list[dict[str, str]]  # vista-meta package-namespace.tsv rows


def _require(path: Path) -> Path:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return path


def _ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{_require(path)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _history_paths(data_dir: Path) -> list[Path]:
    root = _require(data_dir / "documents" / "gold" / "consolidated")
    return sorted(root.rglob("history.yaml"))


def load_lake(data_dir: Path, registries: Path, package_tsv: Path) -> Lake:
    """Read the lake (read-only), the registries and the vista-meta namespace export."""
    inv_json = _require(data_dir / "inventory" / "gold" / "inventory.json")
    records = EnrichedInventory.model_validate_json(inv_json.read_text(encoding="utf-8")).records

    conn = _ro(data_dir / "state.db")
    try:
        acquisitions = StateStore(conn).all_acquisitions()
    finally:
        conn.close()

    conn = _ro(data_dir / "index.db")
    try:
        gold = [
            dict(row)
            for row in conn.execute(
                f"SELECT {', '.join(GOLD_COLUMNS)} FROM v_documents ORDER BY doc_id"
            )
        ]
    finally:
        conn.close()

    raw = json.loads(
        _require(data_dir / "inventory" / "bronze" / "catalog.raw.json").read_text(encoding="utf-8")
    )
    raw_documents = [
        d
        for section in raw.get("sections") or []
        for app in section.get("applications") or []
        for d in app.get("documents") or []
    ]
    with _require(package_tsv).open(encoding="utf-8", newline="") as fh:
        packages = list(csv.DictReader(fh, delimiter="\t"))

    return Lake(
        records=records,
        policy=load_gate_policy(registries),
        profile_maps=personas.load_profile_maps(registries),
        app_profile_names=personas.app_names(registries),
        acquisitions=acquisitions,
        gold=gold,
        histories=[load_mapping(p) for p in _history_paths(data_dir)],
        raw_documents=raw_documents,
        packages=packages,
    )


# --- pure definitions -----------------------------------------------------------------------


def is_vista(rec: EnrichedRecord, policy: GatePolicy) -> bool:
    """A genuine record the gate's ``app_in_scope`` admits (VistA system type, status allowed)."""
    return not rec.noise_type and policy.app_in_scope(rec)


def _canonical(rec: EnrichedRecord) -> str:
    return json.dumps(rec.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)


def row_keys(records: list[EnrichedRecord]) -> list[str]:
    """The proposal's row key (§3): a hash of the four listing fields plus an ordinal among the
    records that share them, assigned by sorting those records on their full canonical content —
    so a key follows the listing's content, not the order VA's page happens to list it in."""
    groups: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(records):
        fields = "\x1f".join(str(getattr(rec, f)) for f in ROW_KEY_FIELDS)
        groups[hashlib.sha256(fields.encode("utf-8")).hexdigest()[:16]].append(i)
    keys = [""] * len(records)
    for base, idxs in groups.items():
        for ordinal, i in enumerate(sorted(idxs, key=lambda j: _canonical(records[j]))):
            keys[i] = f"{base}:{ordinal}"
    return keys


def fold_name(name: str) -> str:
    """The namespace-name agreement criterion: equal after folding case and dropping every
    character that is not a letter or digit. Nothing else is forgiven."""
    return re.sub(r"[^0-9a-z]", "", name.casefold())


def date_source(member: dict[str, Any]) -> str:
    """Where a ``history.yaml`` member's ``official_date`` came from: ``revision-history`` when it
    is one of the member's revision dates (``official_date`` is the newest of them), else
    ``title-page``; empty when the member carries no date."""
    date = str(member.get("official_date") or "")
    if not date:
        return ""
    revision_dates = {str(r.get("date") or "") for r in member.get("revisions") or []}
    return "revision-history" if date in revision_dates else "title-page"


def history_members(
    histories: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str], int]:
    """``doc_id`` → its ``history.yaml`` member; the ``doc_id``s found in more than one member
    (the first, in path order, is kept); and the count of ``superseded`` entries that name a
    ``doc_id`` other than their member's (by construction there are none)."""
    members: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    foreign = 0
    for hist in histories:
        for m in hist.get("members") or []:
            did = str(m["doc_id"])
            if did in members:
                duplicates.append(did)
            else:
                members[did] = m
            foreign += sum(1 for s in m.get("superseded") or [] if str(s.get("doc_id", did)) != did)
    return members, sorted(duplicates), foreign


def _months_between(earlier: str, later: str) -> int:
    return (int(later[:4]) - int(earlier[:4])) * 12 + int(later[5:7]) - int(earlier[5:7])


def _fig(
    fid: str, label: str, measured: Any, proposal: Any = None, tol: float = 0
) -> dict[str, Any]:
    """One figure, with the value the proposal printed before step 0 beside it."""
    if proposal is None:
        agrees = None
    elif isinstance(proposal, int | float) and isinstance(measured, int | float):
        agrees = abs(measured - proposal) <= tol
    else:
        agrees = measured == proposal
    return {
        "id": fid,
        "label": label,
        "proposal": proposal,
        "measured": measured,
        "agrees": agrees,
    }


def _pct(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def _top(counter: Counter[str], n: int) -> str:
    return ", ".join(
        f"{k} {v}" for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    )


# --- the join every section reads -----------------------------------------------------------


@dataclass(frozen=True)
class Joined:
    lake: Lake
    ids: list[str]  # doc_id per record
    vista: list[bool]  # is_vista per record
    status: list[str]  # disposition status per record
    reason: list[str]  # disposition reason per record
    gold: dict[str, dict[str, Any]]  # doc_id → v_documents row
    status_rows: dict[str, str]  # doc_id → inventory_status label
    members: dict[str, dict[str, Any]]  # doc_id → history.yaml member
    dated: dict[str, tuple[str, str]]  # gold doc_id → (official_date, source)

    def fetch(self, did: str) -> str:
        acq = self.lake.acquisitions.get(did)
        return acq.status if acq is not None else NEVER_ATTEMPTED


def join(lake: Lake) -> Joined:
    records, policy = lake.records, lake.policy
    soles = sole_survivors(records, policy)
    anchors = docx_anchor_keys(records)
    disp = [classify(r, policy, docx_anchors=anchors, sole_survivors=soles) for r in records]
    members, _, _ = history_members(lake.histories)
    gold = {str(g["doc_id"]): g for g in lake.gold}
    dated = {}
    for did in gold:
        m = members.get(did)
        if m is not None and date_source(m):
            dated[did] = (str(m["official_date"]), date_source(m))
    return Joined(
        lake=lake,
        ids=[doc_id(r) for r in records],
        vista=[is_vista(r, policy) for r in records],
        status=[d.status for d in disp],
        reason=[d.reason for d in disp],
        gold=gold,
        status_rows={s.doc_id: s.status for s in inventory_status(records, lake.acquisitions)},
        members=members,
        dated=dated,
    )


# --- §1 -------------------------------------------------------------------------------------


def measure_s1(j: Joined) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lake, records = j.lake, j.lake.records
    figs: list[dict[str, Any]] = []
    vista_ids = {d for d, v in zip(j.ids, j.vista, strict=True) if v}
    prefixes = lake.policy.allowed_system_prefixes
    prefix_ids = {
        d
        for d, r in zip(j.ids, records, strict=True)
        if not r.noise_type and r.system_type.startswith(prefixes)
    }
    figs += [
        _fig(
            "s1.status_total",
            "`vdocs inventory --status` total: distinct non-noise `doc_id`s, any system type",
            len(j.status_rows),
            3834,
        ),
        _fig(
            "s1.status_vista",
            "… of which VistA (the gate's `app_in_scope`)",
            sum(1 for d in j.status_rows if d in vista_ids),
            2941,
        ),
        _fig(
            "s1.status_vista_prefix_only",
            "… of which on a VistA system type, decommissioned applications included "
            "(the first measurement's definition)",
            sum(1 for d in j.status_rows if d in prefix_ids),
        ),
    ]
    report = completeness_report(
        records, lake.policy, sole_survivors=sole_survivors(records, lake.policy)
    )
    figs.append(_fig("s1.completeness_total", "`vdocs completeness` records", report.total, 9080))

    hng = [
        i
        for i, (st, did) in enumerate(zip(j.status, j.ids, strict=True))
        if st == "held" and did not in j.gold
    ]

    def count(reason: str | None, fetch: str) -> int:
        return sum(
            1
            for i in hng
            if (reason is None or j.reason[i] == reason) and j.fetch(j.ids[i]) == fetch
        )

    ids_with_docx = {d for d, r in zip(j.ids, records, strict=True) if r.doc_format == "docx"}
    unpaired = sorted(
        {j.ids[i] for i in hng if j.reason[i] == "sole-format" and j.ids[i] in ids_with_docx}
    )
    figs += [
        _fig("s1.held_not_in_gold", "Records held with no gold document", len(hng), 219),
        _fig(
            "s1.hng_sole_survivor_never_fetched",
            "… archived sole survivors, never fetched",
            count("sole-survivor", NEVER_ATTEMPTED),
            152,
        ),
        _fig(
            "s1.hng_docx_kept_never_fetched",
            "… DOCX the policy keeps, never fetched",
            count("", NEVER_ATTEMPTED),
            52,
        ),
        _fig(
            "s1.hng_pdf_sole_format_never_fetched",
            "… PDF records held as the only format (`sole-format`), never fetched",
            count("sole-format", NEVER_ATTEMPTED),
            9,
        ),
        _fig(
            "s1.hng_pdf_twins_unpaired",
            "… … of which the PDF twin of a DOCX with the same `doc_id` "
            "(neither row has an anchor key, so `classify()` cannot pair them)",
            sum(1 for i in hng if j.reason[i] == "sole-format" and j.ids[i] in unpaired),
        ),
        _fig("s1.hng_failed", "… fetch failed", count(None, "failed"), 5),
        _fig("s1.hng_bad_content", "… rejected as bad content", count(None, "bad_content"), 1),
        _fig("s1.hng_fetched", "… fetched, yet not in gold", count(None, "fetched")),
        _fig(
            "s1.hng_largest_apps",
            "… largest applications",
            _top(Counter(records[i].app_name_abbrev for i in hng), 5),
            "SD 40, VBECS 27, CPRS 25, ROR 24, PSO 17",
        ),
    ]

    inv_ids = set(j.ids)
    apps_by_slug: dict[str, set[str]] = defaultdict(set)
    for r in records:
        apps_by_slug[r.doc_slug].add(r.app_name_abbrev)
    gold_only: list[dict[str, Any]] = []
    for did in sorted(d for d in j.gold if d not in inv_ids):
        app, slug = did.split(":", 1)
        gold_only.append(
            {"doc_id": did, "listed_under": sorted(apps_by_slug.get(slug, set()) - {app})}
        )
    refiled = {str(g["doc_id"]) for g in gold_only if g["listed_under"]}
    refiled_slugs = {d.split(":", 1)[1]: d.split(":", 1)[0] for d in refiled}
    figs += [
        _fig("s1.gold_only", "Gold documents whose `doc_id` no record carries", len(gold_only), 15),
        _fig(
            "s1.gold_only_refiled",
            "… whose slug the inventory lists under another app code (re-filed)",
            len(refiled),
            14,
        ),
        _fig(
            "s1.gold_only_departed",
            "… whose slug is gone from the inventory",
            len(gold_only) - len(refiled),
            1,
        ),
        _fig(
            "s1.refiled_held_not_in_gold",
            "Records of the re-filed slugs, under the new app code, held but not in gold",
            sum(
                1
                for i in hng
                if refiled_slugs.get(records[i].doc_slug, records[i].app_name_abbrev)
                != records[i].app_name_abbrev
            ),
            14,
        ),
    ]

    split = Counter(
        (j.reason[i] or "(kept DOCX)", j.status_rows.get(j.ids[i], ""), j.fetch(j.ids[i]))
        for i in hng
    )
    details = {
        "status_counts": dict(sorted(Counter(j.status_rows.values()).items())),
        "dispositions": {
            "held": report.held,
            "not-vista": report.not_vista,
            "excluded": report.excluded_by_policy,
            "covered-by-other-format": report.covered_by_other_format,
            "unreachable": report.unreachable,
            "undecided": report.undecided,
        },
        "held_not_in_gold_split": [
            {"reason": k[0], "inventory_status": k[1], "acquisition": k[2], "records": n}
            for k, n in sorted(split.items())
        ],
        "unpaired_pdf_twins": unpaired,
        "gold_only": gold_only,
    }
    return figs, details


# --- §3 -------------------------------------------------------------------------------------


def _namespace_figures(j: Joined) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lake, records = j.lake, j.lake.records
    package_names: dict[str, set[str]] = defaultdict(set)
    for row in lake.packages:
        if row.get("namespace"):
            package_names[row["namespace"]].add(row["package_name"])
    package_name = {ns: sorted(names)[0] for ns, names in package_names.items()}
    app_full: dict[str, set[str]] = defaultdict(set)
    for r in records:
        app_full[r.app_name_abbrev].add(r.app_name_full)

    per_ns = Counter(r.pkg_ns for r in records)
    namespaces = sorted(ns for ns in per_ns if ns)
    named = [ns for ns in namespaces if ns in package_name]
    app_codes = [ns for ns in namespaces if ns not in package_name and ns in app_full]
    unnamed = [ns for ns in namespaces if ns not in package_name and ns not in app_full]
    both = [ns for ns in named if ns in app_full]
    inv_pairs = [
        {"namespace": ns, "package_file": package_name[ns], "application": sorted(app_full[ns])[0]}
        for ns in both
        if fold_name(package_name[ns]) != fold_name(sorted(app_full[ns])[0])
    ]

    latest = sorted({str(g["pkg_ns"]) for g in lake.gold if g["is_latest"] and g["pkg_ns"]})
    lib_name = {
        str(g["app_code"]): str(g["app_name"])
        for g in sorted(lake.gold, key=lambda g: (g["app_code"], g["app_name"] or ""))
        if g["app_name"]
    }
    named_today = [ns for ns in latest if ns in lib_name]
    named_after = [ns for ns in latest if ns in package_name or ns in lib_name]
    lib_pairs = [
        {"namespace": ns, "library_today": lib_name[ns], "package_file": package_name[ns]}
        for ns in named_today
        if ns in package_name and fold_name(lib_name[ns]) != fold_name(package_name[ns])
    ]

    figs = [
        _fig(
            "s3.namespaces",
            "Inventory namespaces (distinct non-empty `pkg_ns`)",
            len(namespaces),
            162,
        ),
        _fig("s3.ns_package_named", "… named by the PACKAGE file (#9.4)", len(named), 102),
        _fig("s3.ns_package_named_records", "… … records", sum(per_ns[n] for n in named), 6710),
        _fig(
            "s3.ns_app_code",
            "… not in the PACKAGE file but an application code",
            len(app_codes),
            56,
        ),
        _fig("s3.ns_app_code_records", "… … records", sum(per_ns[n] for n in app_codes), 1717),
        _fig("s3.ns_unnamed", "… named nowhere", unnamed, ["PREC", "PREN", "XUSC"]),
        _fig("s3.ns_unnamed_records", "… … records", sum(per_ns[n] for n in unnamed), 92),
        _fig("s3.no_namespace_records", "Records with no namespace", per_ns.get("", 0), 561),
        _fig(
            "s3.ns_both_named",
            "Namespaces named by both the PACKAGE file and a same-code application",
            len(both),
            94,
        ),
        _fig(
            "s3.ns_both_agree",
            "… whose two names are equal after folding case and punctuation",
            len(both) - len(inv_pairs),
            73,
        ),
        _fig(
            "s3.ns_registry_unnamed",
            "Inventory namespaces with no same-code application name in `app-profiles.yaml` "
            "(restated in D4)",
            sum(1 for ns in namespaces if ns not in lake.app_profile_names),
            60,
        ),
        _fig("s3.library_namespaces", "Library namespaces (latest documents)", len(latest), 96),
        _fig(
            "s3.library_named_today", "… named today (same-code application)", len(named_today), 92
        ),
        _fig(
            "s3.library_named_after",
            "… named with the PACKAGE file first, else the same-code application",
            len(named_after),
            96,
        ),
        _fig(
            "s3.library_newly_named",
            "… named for the first time",
            sorted(set(named_after) - set(named_today)),
            ["BPS", "DG", "PSGW", "USR"],
        ),
        _fig(
            "s3.library_renamed",
            "… whose name would change (folded comparison; the proposal read 15 substantive "
            "+ 32 reworded)",
            len(lib_pairs),
            47,
        ),
    ]
    multi = sorted(ns for ns, names in package_names.items() if len(names) > 1)
    return figs, {
        "namespace_pairs_inventory": inv_pairs,
        "namespace_pairs_library": lib_pairs,
        "package_namespaces_with_several_names": multi,
    }


def measure_s3(j: Joined) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lake, records = j.lake, j.lake.records
    per_id = Counter(j.ids)
    listings = Counter(r.doc_url for r in records)
    pages: dict[str, set[str]] = defaultdict(set)
    for r in records:
        pages[r.doc_url].add(r.app_url)
    multi_page = sorted(u for u, p in pages.items() if len(p) > 1)
    repeated = [u for u, n in listings.items() if n > 1]
    noise_by_url = {r.doc_url: r.noise_type for r in records}
    vba = [r for r in records if r.noise_type == "vba_form"]

    four = Counter(tuple(str(getattr(r, f)) for f in ROW_KEY_FIELDS) for r in records)
    dup_links = []
    for key, n in sorted(four.items()):
        if n < 2:
            continue
        group = [r for r in records if tuple(str(getattr(r, f)) for f in ROW_KEY_FIELDS) == key]
        dup_links.append(
            {
                "doc_url": key[2],
                "listings": n,
                "identical": len({_canonical(r) for r in group}) == 1,
                "titles": len({r.doc_title for r in group}),
                "doc_codes": len({r.doc_code for r in group}),
            }
        )
    app_pages: dict[str, set[str]] = defaultdict(set)
    for r in records:
        app_pages[r.app_name_abbrev].add(r.app_url)
    multi_app = Counter({a: len(p) for a, p in app_pages.items() if len(p) > 1})

    figs = [
        _fig("s3.records", "Records (listings)", len(records), 9080),
        _fig("s3.distinct_doc_id", "Distinct `doc_id`", len(per_id), 5032),
        _fig(
            "s3.max_records_per_doc_id",
            "Records sharing one `doc_id`, at most",
            max(per_id.values(), default=0),
            6,
        ),
        _fig(
            "s3.multi_page_links",
            "Links listed on more than one application page (the proposal: 18 benefits-form links)",
            len(multi_page),
            18,
        ),
        _fig(
            "s3.multi_page_link_records",
            "… records listing them",
            sum(listings[u] for u in multi_page),
            1334,
        ),
        _fig("s3.repeated_links", "Links listed more than once anywhere", len(repeated)),
        _fig(
            "s3.repeated_link_surplus",
            "… listings beyond the first of each",
            sum(listings[u] - 1 for u in repeated),
        ),
        _fig(
            "s3.vba_form_records",
            "Records classified `not-vista:vba-form` (restated in D2)",
            len(vba),
            1184,
        ),
        _fig(
            "s3.vba_form_files",
            "… distinct files (D2: 18)",
            len({r.doc_url for r in vba}),
            18,
        ),
        _fig(
            "s3.gold_match_records",
            "Records with a gold match on `doc_id`",
            sum(1 for d in j.ids if d in j.gold),
            2120,
        ),
        _fig(
            "s3.four_field_distinct",
            "Distinct (application page, section, file URL, patch id)",
            len(four),
            9073,
        ),
        _fig("s3.four_field_surplus", "… surplus records", len(records) - len(four), 7),
        _fig("s3.dup_links", "… links listed more than once on one page", len(dup_links), 5),
        _fig(
            "s3.dup_links_identical",
            "… … with every field identical",
            sum(1 for d in dup_links if d["identical"]),
            3,
        ),
        _fig(
            "s3.app_codes_multi_page",
            "App codes on more than one application page",
            len(multi_app),
            171,
        ),
        _fig("s3.app_code_most_pages", "… the most pages", _top(multi_app, 1), "LR 12"),
        _fig("s3.row_keys_distinct", "Distinct row keys", len(set(row_keys(records)))),
    ]

    maps = lake.profile_maps
    matched = [(r, j.gold[d]) for r, d in zip(records, j.ids, strict=True) if d in j.gold]
    mismatch: Counter[str] = Counter()
    ns_diff: dict[str, dict[str, Any]] = {}
    for rec, g in matched:
        tags = personas.profile_tags(rec.app_name_abbrev, rec.doc_code, maps)
        for facet, tag in PROFILE_FACETS:
            mismatch[facet] += tags.get(tag, "") != (g[tag] or "")
        mismatch["Type"] += rec.doc_code != g["doc_type"]
        if rec.pkg_ns != g["pkg_ns"]:
            entry = ns_diff.setdefault(
                str(g["doc_id"]), {"inventory": rec.pkg_ns, "gold": g["pkg_ns"], "records": 0}
            )
            entry["records"] += 1
    for facet in ("Domain", "Audience", "App user", "Type"):
        figs.append(
            _fig(
                f"s3.mismatch_{facet.lower().replace(' ', '_')}",
                f"Gold-matched records whose computed {facet} differs from `index.db`",
                mismatch[facet],
                0,
            )
        )
    figs.append(
        _fig("s3.namespace_differs", "… whose Namespace differs (documents)", len(ns_diff), 2)
    )

    def no_tag(rec: EnrichedRecord, tags: tuple[str, ...]) -> bool:
        got = personas.profile_tags(rec.app_name_abbrev, rec.doc_code, maps)
        return not any(got.get(t) for t in tags)

    no_profile = [i for i, r in enumerate(records) if no_tag(r, APP_LEVEL_TAGS)]
    figs += [
        _fig(
            "s3.no_profile_records",
            "Records with no application profile (no app user, software class or domain)",
            len(no_profile),
            2300,
            tol=50,
        ),
        _fig(
            "s3.no_profile_not_vista",
            "… of which not VistA",
            sum(1 for i in no_profile if not j.vista[i]),
            2298,
        ),
    ]
    ns_figs, ns_details = _namespace_figures(j)
    figs += ns_figs
    details = {
        "multi_page_links": [
            {
                "doc_url": u,
                "pages": len(pages[u]),
                "records": listings[u],
                "noise_type": noise_by_url[u],
            }
            for u in multi_page
        ],
        "dup_links": dup_links,
        "namespace_differs": [{"doc_id": d, **v} for d, v in sorted(ns_diff.items())],
        "facet_without_value": {
            facet: sum(1 for r in records if no_tag(r, (tag,))) for facet, tag in PROFILE_FACETS
        },
        **ns_details,
    }
    return figs, details


# --- §4 -------------------------------------------------------------------------------------


def measure_s4(j: Joined) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lake, records = j.lake, j.lake.records
    n = len(records)
    sources = Counter(src for _, src in j.dated.values())
    later = []
    for did, (date, src) in sorted(j.dated.items()):
        title = str(j.gold[did]["published"] or "")[:7]
        if src == "revision-history" and ISO_MONTH.fullmatch(title) and date > title:
            later.append({"doc_id": did, "title_page": title, "newest_revision": date})
    years = [_months_between(x["title_page"], x["newest_revision"]) / 12 for x in later]
    example = next((x for x in later if x["doc_id"].endswith(":xwb1_1p44um")), None)

    dated_rec = [d in j.dated for d in j.ids]
    undated_vista = [i for i in range(n) if not dated_rec[i] and j.vista[i]]
    with_gold = [i for i in undated_vista if j.ids[i] in j.gold]
    no_gold = [i for i in undated_vista if j.ids[i] not in j.gold]
    undated_ids = {j.ids[i] for i in undated_vista}
    ids_with_docx = {d for d, r in zip(j.ids, records, strict=True) if r.doc_format == "docx"}
    members, duplicates, foreign = history_members(lake.histories)
    n_dated = sum(dated_rec)
    figs = [
        _fig(
            "s4.posting_dates",
            "Crawled links that carry a VDL posting date",
            sum(1 for d in lake.raw_documents if d.get("file_date")),
            28,
        ),
        _fig("s4.crawled_links", "… of crawled links", len(lake.raw_documents), 9080),
        _fig("s4.gold_documents", "Gold documents (`v_documents`)", len(j.gold), 1040),
        _fig("s4.gold_dated", "… dated by `official_date`", len(j.dated), 990),
        _fig("s4.dated_revision", "… … from Revision History", sources["revision-history"], 856),
        _fig("s4.dated_title_page", "… … from the title page", sources["title-page"], 134),
        _fig("s4.gold_undated", "… carrying no date", len(j.gold) - len(j.dated), 50),
        _fig(
            "s4.gold_without_history",
            "… with no `history.yaml` member",
            sum(1 for d in j.gold if d not in members),
        ),
        _fig(
            "s4.history_duplicate_ids",
            "`doc_id`s in more than one `history.yaml` member",
            len(duplicates),
        ),
        _fig(
            "s4.superseded_other_id",
            "`superseded` entries naming another `doc_id`",
            foreign,
        ),
        _fig(
            "s4.revision_later_than_title",
            "Gold documents whose newest revision is later than the title page",
            len(later),
            332,
        ),
        _fig(
            "s4.median_years_later",
            "… median years later",
            round(statistics.median(years), 1) if years else None,
            14,
            tol=0.5,
        ),
        _fig(
            "s4.example_title_page",
            "`xwb1_1p44um` title page",
            example["title_page"] if example else None,
            "2005-01",
        ),
        _fig(
            "s4.example_newest_revision",
            "`xwb1_1p44um` newest revision",
            example["newest_revision"] if example else None,
            "2022-08",
        ),
        _fig("s4.records_dated", "Records dated through `doc_id`", n_dated, 2018),
        _fig(
            "s4.records_dated_by_published",
            "Records a title-page date (`v_documents.published`) alone would date",
            sum(1 for d in j.ids if d in j.gold and str(j.gold[d]["published"] or "").strip()),
        ),
        _fig("s4.records_undated", "Records undated", n - n_dated, 7062),
        _fig(
            "s4.undated_not_vista",
            "… not VistA",
            sum(1 for i in range(n) if not dated_rec[i] and not j.vista[i]),
            3228,
        ),
        _fig("s4.undated_vista", "… VistA (measured directly)", len(undated_vista), 3834),
        _fig(
            "s4.undated_vista_with_gold",
            "… … records of gold documents that carry no date",
            len(with_gold),
            100,
            tol=5,
        ),
        _fig(
            "s4.undated_gold_docs",
            "… … … those gold documents",
            len({j.ids[i] for i in with_gold}),
            50,
        ),
        _fig("s4.undated_vista_no_gold", "… … records with no gold document", len(no_gold), 3732),
        _fig(
            "s4.no_gold_never_fetched",
            "… … … never fetched (no acquisition row)",
            sum(1 for i in no_gold if j.fetch(j.ids[i]) == NEVER_ATTEMPTED),
            3732,
        ),
        _fig(
            "s4.undated_vista_no_gold_ids",
            "… … … distinct `doc_id`s",
            len({j.ids[i] for i in no_gold}),
            1861,
        ),
        _fig(
            "s4.undated_vista_no_gold_slugs",
            "… … … distinct slugs",
            len({records[i].doc_slug for i in no_gold}),
        ),
        _fig(
            "s4.undated_vista_ids",
            "Distinct `doc_id`s among undated VistA records (D6's 1,911 documents)",
            len(undated_ids),
            1911,
        ),
        _fig(
            "s4.undated_vista_ids_with_docx",
            "… with a DOCX record (D6: a Word version)",
            len(undated_ids & ids_with_docx),
            1903,
        ),
        _fig("s4.dated_share", "Share of records dated (%)", _pct(n_dated, n), 22, tol=0.5),
        _fig(
            "s4.dated_share_all_vista",
            "Share dated if every undated VistA record were dated (%, D6)",
            _pct(n_dated + len(undated_vista), n),
            64,
            tol=0.5,
        ),
        _fig(
            "s4.undated_share",
            "Share of records undated (%, D6)",
            _pct(n - n_dated, n),
            78,
            tol=0.5,
        ),
    ]
    details = {
        "revision_later_than_title": later,
        "undated_vista_no_gold_by_fetch": dict(
            sorted(Counter(j.fetch(j.ids[i]) for i in no_gold).items())
        ),
        "undated_vista_no_gold_by_inventory_status": dict(
            sorted(Counter(j.status_rows.get(j.ids[i], "") for i in no_gold).items())
        ),
        "undated_vista_no_gold_by_disposition": dict(
            sorted(Counter(j.status[i] for i in no_gold).items())
        ),
        "official_date_not_month": sorted(
            d for d, (date, _) in j.dated.items() if not ISO_MONTH.fullmatch(date)
        ),
    }
    return figs, details


def measure(lake: Lake) -> dict[str, Any]:
    """Every figure of §1, §3 and §4, with the details behind them."""
    j = join(lake)
    sections: dict[str, list[dict[str, Any]]] = {}
    details: dict[str, Any] = {}
    for name, fn in (("1", measure_s1), ("3", measure_s3), ("4", measure_s4)):
        figs, det = fn(j)
        sections[name] = figs
        details.update(det)
    return {"sections": sections, "details": details}


def measured(result: dict[str, Any]) -> dict[str, Any]:
    """``figure id → measured value`` across every section."""
    return {f["id"]: f["measured"] for figs in result["sections"].values() for f in figs}


# --- provenance -----------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(path: Path, *args: str) -> str:
    """A read-only git query; empty when ``path`` is not inside a checkout."""
    proc = subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def provenance(
    data_dir: Path, registries: Path, package_tsv: Path, lake: Lake, run_date: str
) -> dict[str, Any]:
    """What the measurements read — every field but ``run_date`` is fixed by the inputs."""
    inv_json = data_dir / "inventory" / "gold" / "inventory.json"
    raw_json = data_dir / "inventory" / "bronze" / "catalog.raw.json"
    conn = _ro(data_dir / "index.db")
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    finally:
        conn.close()
    consolidated = data_dir / "documents" / "gold" / "consolidated"
    hist_rows = [
        f"{p.relative_to(consolidated).as_posix()}\t{_sha256(p)}" for p in _history_paths(data_dir)
    ]
    acq_rows = sorted(f"{d}\t{a.status}" for d, a in lake.acquisitions.items())
    repo = Path(__file__).resolve().parents[1]
    reg_hash = hashlib.sha256()
    for name in REGISTRY_FILES:
        path = registries / "inventory" / name
        reg_hash.update(f"{name}\t{_sha256(path) if path.exists() else 'absent'}\n".encode())
    return {
        "run_date": run_date,
        "data_dir": str(data_dir),
        "inventory_json": {"sha256": _sha256(inv_json), "records": len(lake.records)},
        "crawl_raw_json": {"sha256": _sha256(raw_json), "documents": len(lake.raw_documents)},
        "index_db": {
            "read_schema_version": meta.get("read_schema_version", ""),
            "corpus_content_hash": meta.get("corpus_content_hash", ""),
        },
        "acquisitions": {
            "rows": len(acq_rows),
            "sha256": hashlib.sha256("\n".join(acq_rows).encode()).hexdigest(),
        },
        "history_yaml": {
            "files": len(hist_rows),
            "sha256": hashlib.sha256("\n".join(hist_rows).encode()).hexdigest(),
        },
        "registries": {"path": str(registries), "sha256": reg_hash.hexdigest()},
        "vdocs": {
            "commit": _git(repo, "rev-parse", "HEAD"),
            "clean": _git(repo, "status", "--porcelain", "--", "src", "registries", "scripts")
            == "",
        },
        "vista_meta": {
            "commit": _git(package_tsv.parent, "rev-parse", "HEAD"),
            "tsv_last_commit": _git(
                package_tsv.parent, "log", "-1", "--format=%H", "--", package_tsv.name
            ),
            "tsv_sha256": _sha256(package_tsv),
        },
    }


# --- report ---------------------------------------------------------------------------------

SECTION_TITLES = {
    "1": "§1 Why",
    "3": "§3 What a record is, and the facets",
    "4": "§4 Dates",
}


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "(none)"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _verdict(agrees: bool | None) -> str:
    return "" if agrees is None else ("same" if agrees else "**differs**")


def _table(head: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return out


def _notes(result: dict[str, Any]) -> list[str]:
    m, det = measured(result), result["details"]
    notes = []
    if m["s4.undated_vista"] == m["s1.status_total"]:
        notes.append(
            f"The undated VistA records (§4) and the `inventory --status` total (§1) are both "
            f"{m['s1.status_total']:,}, measured independently. They count different things — "
            "records, against distinct non-noise `doc_id`s of any system type — so the match "
            "is a coincidence."
        )
    masked = [
        r
        for r in det["held_not_in_gold_split"]
        if r["inventory_status"] == "out_of_scope" and r["acquisition"] != NEVER_ATTEMPTED
    ]
    if masked:
        notes.append(
            "`inventory_status` labels every PDF-only `doc_id` *out_of_scope* without reading its "
            "acquisition, although the gate admits sole-format PDFs and fetch attempts them: "
            + "; ".join(
                f"{r['records']} held record(s) with acquisition *{r['acquisition']}*"
                for r in masked
            )
            + ". The acquisition column is the fetch outcome."
        )
    if det["unpaired_pdf_twins"]:
        notes.append(
            "`classify()` holds a PDF as *sole-format* when its `anchor_key` is empty, even when a "
            "DOCX with the same `doc_id` exists, because `docx_anchor_keys` skips empty keys: "
            + ", ".join(f"`{d}`" for d in det["unpaired_pdf_twins"])
            + "."
        )
    return notes


def render_md(result: dict[str, Any]) -> str:
    p = result["provenance"]
    lines = [
        "# Inventory browser — step 0 measurements",
        "",
        "Every figure in §1, §3 and §4 of "
        "[the inventory browser proposal](../docs/proposals/inventory-browser-proposal.md), "
        "measured again by `scripts/inventory_measurements.py` through the pipeline's own "
        "definitions. *Proposal* is the value the proposal printed before step 0.",
        "",
        "## What this read",
        "",
        *_table(
            ["Input", "Identity"],
            [
                ["Lake", f"`{p['data_dir']}` (read-only)"],
                [
                    "`inventory.json`",
                    f"{p['inventory_json']['records']:,} records, sha256 "
                    f"`{p['inventory_json']['sha256']}`",
                ],
                [
                    "`index.db`",
                    f"read_schema_version {p['index_db']['read_schema_version']}, "
                    f"corpus_content_hash `{p['index_db']['corpus_content_hash']}`",
                ],
                [
                    "Crawl `catalog.raw.json`",
                    f"{p['crawl_raw_json']['documents']:,} links, sha256 "
                    f"`{p['crawl_raw_json']['sha256']}`",
                ],
                [
                    "`state.db` acquisitions",
                    f"{p['acquisitions']['rows']:,} rows, sha256 of (doc_id, status) "
                    f"`{p['acquisitions']['sha256']}`",
                ],
                [
                    "`history.yaml`",
                    f"{p['history_yaml']['files']:,} files, sha256 `{p['history_yaml']['sha256']}`",
                ],
                [
                    "Registries",
                    f"`{p['registries']['path']}`, sha256 `{p['registries']['sha256']}`",
                ],
                [
                    "vdocs",
                    f"commit `{p['vdocs']['commit'] or 'unknown'}` "
                    f"(src, registries, scripts {'clean' if p['vdocs']['clean'] else 'MODIFIED'})",
                ],
                [
                    "vista-meta",
                    f"commit `{p['vista_meta']['commit'] or 'unknown'}`; `package-namespace.tsv` "
                    f"sha256 `{p['vista_meta']['tsv_sha256']}`, last changed in "
                    f"`{p['vista_meta']['tsv_last_commit'] or 'unknown'}`",
                ],
                ["Run date", p["run_date"]],
            ],
        ),
    ]
    for name, figs in result["sections"].items():
        lines += [
            "",
            f"## {SECTION_TITLES[name]}",
            "",
            *_table(
                ["Figure", "Proposal", "Measured", ""],
                [[f["label"], f["proposal"], f["measured"], _verdict(f["agrees"])] for f in figs],
            ),
        ]
    det = result["details"]
    lines += [
        "",
        "## Details",
        "",
        "### Held records with no gold document, by reason and fetch outcome",
        "",
        *_table(
            ["Reason", "`inventory --status`", "Acquisition", "Records"],
            [
                [r["reason"], r["inventory_status"], r["acquisition"], r["records"]]
                for r in det["held_not_in_gold_split"]
            ],
        ),
        "",
        "### Gold documents no record carries",
        "",
        *_table(
            ["`doc_id`", "Slug listed under"],
            [[g["doc_id"], g["listed_under"]] for g in det["gold_only"]],
        ),
        "",
        "### Links listed on more than one application page",
        "",
        *_table(
            ["Link", "Pages", "Records", "Noise type"],
            [
                [x["doc_url"], x["pages"], x["records"], x["noise_type"]]
                for x in det["multi_page_links"]
            ],
        ),
        "",
        "### Links listed more than once on one page",
        "",
        *_table(
            ["Link", "Listings", "Every field identical", "Titles", "Doc codes"],
            [
                [
                    x["doc_url"],
                    x["listings"],
                    "yes" if x["identical"] else "no",
                    x["titles"],
                    x["doc_codes"],
                ]
                for x in det["dup_links"]
            ],
        ),
        "",
        "### Gold-matched documents whose namespace differs",
        "",
        *_table(
            ["`doc_id`", "Inventory", "Gold", "Records"],
            [
                [x["doc_id"], x["inventory"], x["gold"], x["records"]]
                for x in det["namespace_differs"]
            ],
        ),
        "",
        "### Library namespace names that would change",
        "",
        "Every Library namespace whose current name (the same-code application's) is not equal to "
        "its PACKAGE-file name after folding case and punctuation. Which of them change in "
        "substance and which are rewordings is a reading of this list, not a measurement.",
        "",
        *_table(
            ["Namespace", "Library today", "PACKAGE file (#9.4)"],
            [
                [x["namespace"], x["library_today"], x["package_file"]]
                for x in det["namespace_pairs_library"]
            ],
        ),
        "",
        "### Inventory namespaces whose two names differ",
        "",
        *_table(
            ["Namespace", "PACKAGE file (#9.4)", "Application"],
            [
                [x["namespace"], x["package_file"], x["application"]]
                for x in det["namespace_pairs_inventory"]
            ],
        ),
        "",
        "### Undated VistA records with no gold document",
        "",
        *_table(
            ["By acquisition", "Records"],
            [[k, v] for k, v in det["undated_vista_no_gold_by_fetch"].items()],
        ),
        "",
        *_table(
            ["By `inventory --status`", "Records"],
            [[k, v] for k, v in det["undated_vista_no_gold_by_inventory_status"].items()],
        ),
        "",
        *_table(
            ["By disposition", "Records"],
            [[k, v] for k, v in det["undated_vista_no_gold_by_disposition"].items()],
        ),
    ]
    notes = _notes(result)
    if notes:
        lines += ["", "## Notes", "", *[f"- {n}" for n in notes]]
    return "\n".join(lines) + "\n"


def main() -> None:
    from vdocs.config import Settings

    cfg = Settings()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data-dir", default=str(cfg.data_dir))
    ap.add_argument("--registries", default=str(cfg.registries))
    ap.add_argument("--package-namespace", default=str(DEFAULT_PACKAGE_TSV))
    ap.add_argument("--out", default="reports/inventory-browser-measurements.md")
    args = ap.parse_args()

    data_dir = Path(args.data_dir).expanduser()
    registries = Path(args.registries).expanduser()
    package_tsv = Path(args.package_namespace).expanduser()
    lake = load_lake(data_dir, registries, package_tsv)
    result = {
        "provenance": provenance(
            data_dir, registries, package_tsv, lake, dt.date.today().isoformat()
        ),
        **measure(lake),
    }
    out_md = Path(args.out)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_md(result), encoding="utf-8")
    out_json = out_md.with_suffix(".json")
    out_json.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    differs = [
        f["id"] for figs in result["sections"].values() for f in figs if f["agrees"] is False
    ]
    log.info("inventory measurements written", md=str(out_md), json=str(out_json), differs=differs)


if __name__ == "__main__":
    main()
