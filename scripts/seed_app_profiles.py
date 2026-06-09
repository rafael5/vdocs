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


def build_profiles(entries: list[dict], inv: EnrichedInventory) -> dict:
    """Assemble the draft registry: in-scope matched profiles + _needs_fallback + _excluded."""
    by_appid = {e["appid"]: e for e in entries if e["appid"]}
    by_ns = {e["namespace"]: e for e in entries if e["namespace"]}
    apps = _distinct_apps(inv)

    profiles: dict[str, dict] = {}
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
            needs_fallback[abbrev] = (
                f"{app['name']} — not in Monograph 2023 (needs manual extraction)"
            )
            continue
        # re-check scope now that we know the Monograph VASI status
        ok, reason = classify_scope(app["system_type"], app["app_status"], entry["vasi_status"])
        if not ok:
            excluded[abbrev] = f"{app['name']} — {reason}"
            continue
        profiles[abbrev] = {
            "name": app["name"],
            "purpose": entry["brief_description"],
            "purpose_long": entry["full_description"],
            "function_category": entry["product_line"],
            "business_owner": entry["business_owner"],
            "audience_primary": derive_audience(entry["product_line"], entry["business_owner"]),
            "features": entry["features"],
            "namespace": entry["namespace"],
            "source": "monograph",
            "evidence": {"doc": _MON_DOC, "line": entry["line"], "match": method},
            "confidence": "high" if method == "appid" else "medium",
        }

    return {
        "profiles": profiles,
        "_needs_fallback": needs_fallback,
        "_excluded": excluded,
    }


_HEADER = (
    "# registries/inventory/app-profiles.yaml — DRAFT (auto-generated, review before use).\n"
    "# Per-application purpose / function category / operator audience, transcribed from the\n"
    "# VistA Monograph July 2023 §4 and joined to the gold inventory. Regenerate with\n"
    "#   python scripts/seed_app_profiles.py\n"
    "# Every 'profiles' entry cites its Monograph source line. 'audience_primary: needs-review'\n"
    "# and medium-confidence/namespace matches need a human pass. '_needs_fallback' = in-scope\n"
    "# VistA apps absent from the 2023 Monograph (manual-extraction path). '_excluded' = out of\n"
    "# scope (COTS/web/non-VistA or decommissioned/inactive) — not fetched, analysed, or in gold.\n"
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

    p, fb, ex = draft["profiles"], draft["_needs_fallback"], draft["_excluded"]
    needs_review = sum(1 for v in p.values() if v["audience_primary"] == "needs-review")
    print(f"Monograph §4 entries parsed: {len(entries)}")
    print(f"  in-scope profiles:   {len(p)}  (audience needs-review: {needs_review})")
    print(f"  _needs_fallback:     {len(fb)}  (in-scope, not in Monograph)")
    print(f"  _excluded:           {len(ex)}  (COTS/web/non-VistA or decommissioned)")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
