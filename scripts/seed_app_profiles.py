#!/usr/bin/env python3
"""Seed a draft ``registries/inventory/app-profiles.yaml`` from the VistA Monograph.

The Monograph (``MON/vista_monograph_0723_r``) §4 "The VistA Modules" is the VA's own
structured, per-package profile: ``> **Field:** value`` blocks carrying a one-line *Brief
Description* (purpose), a *Full Description and Features* list, an authoritative *SPM Product
Line* functional category, and the *VHA Business Owner* — plus join keys (*Namespace* and a
*VDL link* ``appid``). This script parses those blocks, joins them to the gold inventory, derives
an operator-audience persona from the product line, applies the in-scope rule (active VistA only;
COTS/web/decommissioned excluded), and emits a *draft* registry for human review.

Derivation, not invention: every profile field is transcribed from the Monograph with a line-level
evidence pointer. Apps in scope but absent from the 2023 Monograph are listed under
``_needs_fallback`` for the manual-extraction path; out-of-scope apps under ``_excluded`` with a
reason.

Usage:
    python scripts/seed_app_profiles.py [--data-dir PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

from vdocs.models.catalog import EnrichedInventory

_MON_REL = "documents/silver/text/03-normalized/MON/vista_monograph_0723_r/body.md"
_MON_DOC = "vista_monograph_0723_r"

_SECTION_4 = re.compile(r"^##\s*4\.\s*The VistA Modules\s*$", re.MULTILINE)
_SECTION_END = re.compile(r"^##\s+Appendix\b", re.MULTILINE)
_ENTRY = re.compile(r"^###\s+(.*\S)\s*$")
_FIELD = re.compile(r"^>\s*\*\*(?P<label>.+?):\*\*\s*(?P<value>.*)$")
_BULLET = re.compile(r"^-\s+(.*\S)\s*$")
_APPID = re.compile(r"appid=(\d+)")

# SPM Product Line -> operator-audience persona. One reviewed decision per VA product line
# (~19 lines) instead of per-app guessing. Genuinely mixed lines map to "needs-review" rather
# than a guess, so the human pass resolves them via Business Owner + Brief Description.
_PRODUCT_LINE_AUDIENCE: dict[str, str] = {
    "Patient Care Services": "clinical",
    "Clinical Services": "clinical",
    "VHA Finance": "business-admin",
    "Financial Management": "business-admin",
    "Compensation and Pension": "business-admin",
    "Community Care": "business-admin",
    "Telehealth and Scheduling": "clinical-admin",
    "Eligibility and Enrollment": "clinical-admin",
    "VHA Front Office": "clinical-admin",
    "Healthcare Environment and Logistics": "clinical-admin",
    "Veteran Relationship Management": "clinical-admin",
    "VistA Office (VO) VistA Infrastructure": "sysadmin",
    "IT Infrastructure Operations and Services": "sysadmin",
    "Identity Access Management": "sysadmin",
    "Customer Master Data Management": "sysadmin",
    "VistA Office (VO) Technical Reference": "developer",
    "Data and Analytics": "developer",
    # deliberately review-only (mixed audiences under one SPM management grouping):
    "Health Informatics": "needs-review",
    "Digital Experience": "needs-review",
}


def parse_monograph_entries(text: str) -> list[dict]:
    """Parse the §4 "The VistA Modules" blocks into one record per package.

    Each record carries the package display heading, its 1-based line number, every
    ``> **Field:** value`` pair, the feature bullets, and the convenience keys used downstream
    (namespace / product_line / brief_description / business_owner / full_description / appid).
    Content outside §4 (before the heading or at/after the Appendix) is ignored.
    """
    start = _SECTION_4.search(text)
    if start is None:
        return []
    end = _SECTION_END.search(text, start.end())
    body = text[start.end() : end.start() if end else len(text)]
    base_line = text[: start.end()].count("\n") + 1

    entries: list[dict] = []
    current: dict | None = None
    for offset, line in enumerate(body.splitlines()):
        m = _ENTRY.match(line)
        if m:
            current = {
                "package_display": m.group(1).strip(),
                "line": base_line + offset,
                "fields": {},
                "features": [],
            }
            entries.append(current)
            continue
        if current is None:
            continue
        fm = _FIELD.match(line)
        if fm:
            current["fields"][fm.group("label").strip().lower()] = fm.group("value").strip()
            continue
        bm = _BULLET.match(line)
        if bm:
            current["features"].append(bm.group(1).strip())

    for e in entries:
        f = e["fields"]
        e["namespace"] = f.get("namespace", "")
        e["product_line"] = f.get("spm product line", "")
        e["brief_description"] = f.get("brief description", "")
        e["business_owner"] = f.get("vha business owner", "")
        e["full_description"] = f.get("full description and features", "")
        e["vasi_status"] = f.get("vasi system status", "")
        am = _APPID.search(f.get("vdl link", ""))
        e["appid"] = am.group(1) if am else ""
    return entries


def derive_audience(product_line: str, business_owner: str) -> str:
    """Operator-audience persona from the SPM Product Line. Unknown lines -> 'needs-review'."""
    return _PRODUCT_LINE_AUDIENCE.get(product_line.strip(), "needs-review")


# Reviewed per-app overrides (2026-06-09). All 15 were SPM "Health Informatics" — a mixed
# management bucket that the product-line map deliberately leaves as 'needs-review'. Resolved from
# each app's Brief Description + VHA Business Owner. Rulings: registries -> clinical-admin applied
# uniformly; PCE -> clinical. Value = (primary, secondary | None, basis).
_APP_AUDIENCE_OVERRIDE: dict[str, tuple[str, str | None, str]] = {
    "ADT": ("clinical-admin", None, "registration/MAS clerks (administrative ADT functions)"),
    "DGJ": ("clinical-admin", None, "HIM incomplete-records tracking"),
    "DI": ("developer", None, "VistA DBMS (FileMan) — programmers"),
    "SQLI": ("developer", None, "FileMan SQL access — programmers"),
    "HL7": ("developer", None, "messaging/interface engine — interface engineers"),
    "KMPD": ("sysadmin", None, "purpose names 'IRM and system administrators'"),
    "IBD": ("clinical-admin", None, "encounter-form printing / data entry — clinic clerks"),
    "ONC": ("clinical-admin", None, "Cancer Registrars (registry abstraction)"),
    "ROI": ("clinical-admin", None, "HIM Release-of-Information clerks"),
    "RT": ("clinical-admin", None, "chart/film file-room tracking — HIM"),
    "TBI": ("clinical-admin", None, "registry (registries rule applied uniformly)"),
    "ROR": ("clinical-admin", None, "registry (registries rule applied uniformly)"),
    "PX": ("clinical", "clinical-admin", "clinical encounter documentation; workload entry 2nd"),
    "XM": ("sysadmin", None, "messaging infrastructure (MailMan) — OIT/IRM"),
    "XU": ("sysadmin", "developer", "system/user/menu/TaskMan mgmt; developer APIs 2nd"),
}


def resolve_audience(
    abbrev: str, product_line: str, business_owner: str
) -> tuple[str, str | None, str]:
    """(primary, secondary, basis). A reviewed per-app override wins over the product-line map."""
    if abbrev in _APP_AUDIENCE_OVERRIDE:
        return _APP_AUDIENCE_OVERRIDE[abbrev]
    return derive_audience(product_line, business_owner), None, f"SPM product line: {product_line}"


# VistA software class (SAC I/II/III). Deterministic, traceable derivation:
#  - default "I": every in-scope app is documented in the VDL, which only publishes *nationally
#    released* software. (VDL membership establishes national distribution = Class I or II; II is
#    not separable from this corpus without the VA SAC/NPM PACKAGE #9.4 list, so we default to I.)
#  - "III" override: apps whose OWN docs carry an explicit app-level reclassification statement.
#    Component-level "Class III tool/option" mentions are deliberately NOT used (too noisy).
#  - "II" (field-developed, nationally distributed but optional) is NOT assigned — needs SAC list.
_CLASS_III_APPS: dict[str, str] = {
    "NUPA": "own doc: 'package status changed to Class 3 Software… no longer supported nationally'",
}


def software_class(abbrev: str) -> tuple[str, str]:
    """(class, basis). Default 'I' from VDL national-catalog membership; explicit 'III' override."""
    if abbrev in _CLASS_III_APPS:
        return "III", _CLASS_III_APPS[abbrev]
    return "I", "VDL national catalog membership (nationally released)"


def classify_scope(system_type: str, app_status: str, vasi_status: str) -> tuple[bool, str]:
    """In-scope = active VistA (M-based) app. COTS/web/non-VistA and decommissioned/inactive out."""
    if not system_type.startswith("VistA"):
        return False, f"non-vista (system_type={system_type})"
    if app_status == "decommissioned":
        return False, "decommissioned (inventory app_status)"
    if vasi_status.strip().lower() == "inactive":
        return False, "inactive (VASI status)"
    return True, ""


def _distinct_apps(inv: EnrichedInventory) -> dict[str, dict]:
    """One row per canonical abbrev with the fields needed to join + scope."""
    apps: dict[str, dict] = {}
    for r in inv.records:
        ab = r.app_name_abbrev
        if not ab or ab in apps:
            continue
        am = _APPID.search(r.app_url)
        apps[ab] = {
            "name": r.app_name_full,
            "pkg_ns": r.pkg_ns,
            "appid": am.group(1) if am else "",
            "system_type": r.system_type,
            "app_status": r.app_status,
        }
    return apps


def _match(app: dict, by_appid: dict[str, dict], by_ns: dict[str, dict]) -> tuple[dict | None, str]:
    """Join an inventory app to a Monograph entry: appid -> namespace, recording the method."""
    if app["appid"] and app["appid"] in by_appid:
        return by_appid[app["appid"]], "appid"
    if app["pkg_ns"] and app["pkg_ns"] in by_ns:
        return by_ns[app["pkg_ns"]], "namespace"
    return None, ""


# Curated fallback profiles (2026-06-09) for in-scope VistA apps absent from the 2023 Monograph.
# `purpose` is transcribed/condensed from the app's OWN docs in the gold corpus (evidence.doc);
# `audience` is reasoned from package function (registries -> clinical-admin applied uniformly).
# status "have-docs" = purpose curated from corpus; "pending-fetch" = no docs in corpus yet, so
# purpose is "" and audience is a low-confidence prior to confirm once the docs are fetched.
_FALLBACK_PROFILES: dict[str, dict] = {
    "ASCD": {
        "purpose": "Automatically determines and assigns Service Connected (SC) / Non-Service "
        "Connected (NSC) status for patient encounters in the PCE and Scheduling packages, from "
        "available disability-rating information.",
        "audience_primary": "clinical-admin",
        "audience_basis": "encounter SC/NSC classification — eligibility/MAS",
        "status": "have-docs",
        "doc": "ascd_um",
    },
    "CHDS": {
        "purpose": "The Clinical Data Repository/Health Data Repository (CHDR) exchanges "
        "standards-based, computable electronic health record data between VA (VistA) and DoD.",
        "audience_primary": "developer",
        "audience_basis": "VA/DoD health-data exchange infrastructure",
        "status": "have-docs",
        "doc": "chds_dibr",
    },
    "EFR": {
        "purpose": "The Embedded Fragment Registry (EFRA) maintains local and national registries "
        "for clinical and resource tracking of care for Veterans with embedded-fragment injuries.",
        "audience_primary": "clinical-admin",
        "audience_basis": "registry (registries rule)",
        "status": "have-docs",
        "doc": "efr_um",
    },
    "GEN": {
        "purpose": "The Generic Code Sheet (GCS) package provides a generic facility to define, "
        "build, and transmit code sheets (electronic data records) to external systems such as "
        "the Austin Information Technology Center.",
        "audience_primary": "sysadmin",
        "audience_basis": "IRM data-transmission utility (low confidence; could be business-admin)",
        "status": "have-docs",
        "doc": "gen_ig",
    },
    "IVMB": {
        "purpose": "Supports the Health Eligibility Center (HEC): income-verification / means-test "
        "processing using HUD geographic income thresholds to determine Veteran eligibility.",
        "audience_primary": "clinical-admin",
        "audience_basis": "eligibility/means-test processing",
        "status": "have-docs",
        "doc": "ivmb_ig",
    },
    "KMPV": {
        "purpose": "VistA System Monitor (VSM) collects Cache and VistA metrics on system capacity "
        "and business usage via timed and event collectors, for capacity planning and monitoring.",
        "audience_primary": "sysadmin",
        "audience_basis": "capacity monitoring — IRM",
        "status": "have-docs",
        "doc": "kmpv_um",
    },
    "NCR": {
        "purpose": "National Clozapine Coordination registry support within VistA Mental Health: "
        "implements VistA clozapine monitoring logic (lab-result-gated dispensing).",
        "audience_primary": "clinical-admin",
        "audience_basis": "registry (registries rule)",
        "status": "have-docs",
        "doc": "ncr_tm",
    },
    "NUPA": {
        "purpose": "Patient Assessment Documentation Package (PADP) provides nursing "
        "assessment/reassessment documentation templates. (Class 3 software, no longer nationally "
        "supported.)",
        "audience_primary": "clinical",
        "audience_basis": "nursing assessment documentation",
        "status": "have-docs",
        "doc": "nupa_um",
    },
    "PAIT": {
        "purpose": "Patient Appointment Information Transmission (PAIT) extracts and transmits "
        "VistA patient appointment data (released in patch SD*5.3).",
        "audience_primary": "clinical-admin",
        "audience_basis": "scheduling/appointment data transmission",
        "status": "have-docs",
        "doc": "pait_um",
    },
    "PREA": {
        "purpose": "The Advanced Medication Platform (AMPL GUI) gives pharmacists a single point "
        "of access to a patient's medical data across all VistA Pharmacy packages.",
        "audience_primary": "clinical",
        "audience_basis": "pharmacists (purpose names them)",
        "status": "have-docs",
        "doc": "prea_ug",
    },
    "PRPF": {
        "purpose": "The Patient Funds (PFOP) system manages the private/personal finances of VA "
        "patients hospitalized at VA facilities (electronic equivalent of VA Form 10-1083).",
        "audience_primary": "business-admin",
        "audience_basis": "agent cashier / patient-funds accounting",
        "status": "have-docs",
        "doc": "prpf_um",
    },
    "ROEV": {
        "purpose": "VA Eye Injury Data Store (VA EIDS, formerly MEVIR) transfers Veteran "
        "eye-injury data into the joint DoD/VA Eye Injury and Vision Registry (DVEIVR).",
        "audience_primary": "clinical-admin",
        "audience_basis": "registry (registries rule)",
        "status": "have-docs",
        "doc": "roev_ug",
    },
    "SRA": {
        "purpose": "The Surgery Risk Assessment package collects non-cardiac surgical "
        "risk-assessment and case data from VA medical centers (VASQIP/NSQIP) to document, "
        "organize, and transmit surgery case data for quality reporting.",
        "audience_primary": "clinical",
        "audience_basis": "surgical clinical nurse reviewers (VASQIP)",
        "status": "have-docs",
        "doc": "sra_um",
    },
    # pending-fetch: in-scope VistA, but no docs in the corpus yet -> purpose pending; audience is
    # a low-confidence prior from package function, to confirm on fetch.
    "HL": {
        "purpose": "",
        "audience_primary": "developer",
        "audience_basis": "HL7 standard files/tables — infrastructure (prior)",
        "status": "pending-fetch",
        "doc": None,
    },
    "MJCF": {
        "purpose": "",
        "audience_primary": "needs-review",
        "audience_basis": "Bar Code Expansion — function unclear without docs",
        "status": "pending-fetch",
        "doc": None,
    },
    "ONCO": {
        "purpose": "",
        "audience_primary": "clinical-admin",
        "audience_basis": "registry platform (registries rule, prior)",
        "status": "pending-fetch",
        "doc": None,
    },
    "PPP": {
        "purpose": "",
        "audience_primary": "clinical",
        "audience_basis": "pharmacy (prior)",
        "status": "pending-fetch",
        "doc": None,
    },
    "ROEB": {
        "purpose": "",
        "audience_primary": "clinical-admin",
        "audience_basis": "breast cancer registry (registries rule, prior)",
        "status": "pending-fetch",
        "doc": None,
    },
    "ROEG": {
        "purpose": "",
        "audience_primary": "clinical-admin",
        "audience_basis": "MS surveillance registry (registries rule, prior)",
        "status": "pending-fetch",
        "doc": None,
    },
    "SSO/UC": {
        "purpose": "",
        "audience_primary": "sysadmin",
        "audience_basis": "single sign-on / user context — authentication infra (prior)",
        "status": "pending-fetch",
        "doc": None,
    },
    "XOB": {
        "purpose": "",
        "audience_primary": "developer",
        "audience_basis": "Name Standardization — HealtheVet identity infra (prior)",
        "status": "pending-fetch",
        "doc": None,
    },
}


def _fallback_profile(abbrev: str, app: dict) -> dict:
    """A curated fallback profile (manual/corpus-derived) for an app absent from the Monograph."""
    c = _FALLBACK_PROFILES[abbrev]
    cls, cls_basis = software_class(abbrev)
    return {
        "name": app["name"],
        "purpose": c["purpose"],
        "function_category": "",  # no SPM product line off-Monograph
        "audience_primary": c["audience_primary"],
        "audience_basis": c["audience_basis"],
        "software_class": cls,
        "software_class_basis": cls_basis,
        "vasi_status": "unknown",  # not in the Monograph
        "namespace": app["pkg_ns"],
        "source": "manual",
        "status": c["status"],
        "reviewed": True,
        "needs_review": True,
        "evidence": {"doc": c["doc"]} if c["doc"] else {},
        "confidence": "low",
    }


def build_profiles(entries: list[dict], inv: EnrichedInventory) -> dict:
    """Assemble the draft registry: Monograph profiles + curated fallback_profiles + _excluded."""
    by_appid = {e["appid"]: e for e in entries if e["appid"]}
    by_ns = {e["namespace"]: e for e in entries if e["namespace"]}
    apps = _distinct_apps(inv)

    profiles: dict[str, dict] = {}
    fallback_profiles: dict[str, dict] = {}
    needs_fallback: dict[str, str] = {}
    excluded: dict[str, str] = {}

    for abbrev in sorted(apps):
        app = apps[abbrev]
        ok, reason = classify_scope(app["system_type"], app["app_status"], "")
        if not ok:
            excluded[abbrev] = f"{app['name']} — {reason}"
            continue
        entry, method = _match(app, by_appid, by_ns)
        if entry is None:
            if abbrev in _FALLBACK_PROFILES:
                fallback_profiles[abbrev] = _fallback_profile(abbrev, app)
            else:
                needs_fallback[abbrev] = (
                    f"{app['name']} — not in Monograph 2023 (needs manual extraction)"
                )
            continue
        # re-check scope now that we know the Monograph VASI status
        ok, reason = classify_scope(app["system_type"], app["app_status"], entry["vasi_status"])
        if not ok:
            excluded[abbrev] = f"{app['name']} — {reason}"
            continue
        primary, secondary, basis = resolve_audience(
            abbrev, entry["product_line"], entry["business_owner"]
        )
        cls, cls_basis = software_class(abbrev)
        profile = {
            "name": app["name"],
            "purpose": entry["brief_description"],
            "purpose_long": entry["full_description"],
            "function_category": entry["product_line"],
            "business_owner": entry["business_owner"],
            "audience_primary": primary,
            "audience_basis": basis,
            "software_class": cls,
            "software_class_basis": cls_basis,
            "vasi_status": entry["vasi_status"],
            "features": entry["features"],
            "namespace": entry["namespace"],
            "source": "monograph",
            "reviewed": abbrev in _APP_AUDIENCE_OVERRIDE,
            "evidence": {"doc": _MON_DOC, "line": entry["line"], "match": method},
            "confidence": "high" if method == "appid" else "medium",
        }
        if secondary:
            profile["audience_secondary"] = secondary
        profiles[abbrev] = profile

    return {
        "profiles": profiles,
        "fallback_profiles": fallback_profiles,
        "_needs_fallback": needs_fallback,
        "_excluded": excluded,
    }


_HEADER = (
    "# registries/inventory/app-profiles.yaml — DRAFT (auto-generated, review before use).\n"
    "# Per-application purpose / function category / operator audience, transcribed from the\n"
    "# VistA Monograph July 2023 §4 and joined to the gold inventory. Regenerate with\n"
    "#   python scripts/seed_app_profiles.py\n"
    "# 'software_class': I (national) by default — the VDL only catalogs nationally-released\n"
    "# software; III only on an explicit app-level reclassification in the app's docs; II needs\n"
    "# the VA SAC list (not assigned). 'vasi_status' (Production / Technical Reference Only / Not\n"
    "# A System …) is the Monograph's per-app importance gradient ('unknown' for fallback apps).\n"
    "# Every 'profiles' entry cites its Monograph source line. 'audience_primary: needs-review'\n"
    "# and medium-confidence/namespace matches need a human pass. 'fallback_profiles' = in-scope\n"
    "# VistA apps absent from the 2023 Monograph, curated from their own docs (source: manual,\n"
    "# confidence: low) — status 'have-docs' carries a purpose from the corpus; 'pending-fetch'\n"
    "# has no docs yet (empty purpose, audience a prior). '_excluded' = out of scope (COTS/web/\n"
    "# non-VistA or decommissioned/inactive) — not fetched, analysed, or included in gold.\n"
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=Path.home() / "data" / "vdocs")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent.parent / "registries" / "inventory" / "app-profiles.yaml",
    )
    args = ap.parse_args()

    mon = (args.data_dir / _MON_REL).read_text()
    inv_path = args.data_dir / "inventory" / "silver" / "catalog.enriched.json"
    inv = EnrichedInventory.model_validate_json(inv_path.read_text())

    entries = parse_monograph_entries(mon)
    draft = build_profiles(entries, inv)

    args.out.write_text(
        _HEADER + yaml.safe_dump(draft, sort_keys=False, allow_unicode=True, width=100)
    )

    p, fbp = draft["profiles"], draft["fallback_profiles"]
    fb, ex = draft["_needs_fallback"], draft["_excluded"]
    needs_review = sum(1 for v in p.values() if v["audience_primary"] == "needs-review")
    have_docs = sum(1 for v in fbp.values() if v["status"] == "have-docs")
    print(f"Monograph §4 entries parsed: {len(entries)}")
    print(f"  in-scope profiles:   {len(p)}  (audience needs-review: {needs_review})")
    print(
        f"  fallback_profiles:   {len(fbp)}  (curated; have-docs {have_docs}, "
        f"pending-fetch {len(fbp) - have_docs})"
    )
    print(f"  _needs_fallback:     {len(fb)}  (still unhandled)")
    print(f"  _excluded:           {len(ex)}  (COTS/web/non-VistA or decommissioned)")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
