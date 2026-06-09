"""Unit tests for the Monograph → app-profiles parser (scripts/seed_app_profiles.py).

The parser is the risky part of the one-shot authoring script: it turns the VistA Monograph's
§4 "The VistA Modules" structured profile blocks into per-package records. TDD'd here against a
minimal but faithful two-entry fixture mirroring the real ``> **Field:** value`` shape.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.seed_app_profiles import (  # noqa: E402
    _FALLBACK_PROFILES,
    app_namespace,
    build_profiles,
    classify_scope,
    derive_audience,
    parent_package,
    parse_monograph_entries,
    resolve_audience,
    software_class,
)
from vdocs.models.catalog import EnrichedInventory, EnrichedRecord  # noqa: E402

_FIXTURE = """\
## 3. Resources

Filler that must not be parsed as an entry.

## 4. The VistA Modules

### Accounts Receivable (AR)

[↑ Back to Contents](#contents)

> **VistA Package Name:** ACCOUNTS RECEIVABLE
>
> **VASI System Status:** Production
>
> **Namespace:** PRCA
>
> **SPM Product Line:** VHA Finance
>
> **Brief Description:** The Accounts Receivable (AR) package is a system of accounting.
>
> **VDL link:** [Accounts Receivable (AR) (PRCA)](https://www.va.gov/vdl/application.asp?appid=29)
>
> **VHA Business Owner:** ACFO Finance Operations
>
> **Full Description and Features:** Some of the debts owed to a VA facility.
>
> Features:

- Provides a generic billing system

- Calculates interest and administrative charges

### Computerized Patient Record System (CPRS)

[↑ Back to Contents](#contents)

> **VistA Package Name:** ORDER ENTRY/RESULTS REPORTING
>
> **VASI System Status:** Production
>
> **Namespace:** OR
>
> **SPM Product Line:** Clinical Services
>
> **Brief Description:** CPRS is the GUI clinicians use to enter orders and review results.
>
> **VDL link:** [Computerized Patient Record System (CPRS) (OR)](https://www.va.gov/vdl/application.asp?appid=61)
>
> **VHA Business Owner:** Office of Clinical Informatics
>
> **Full Description and Features:** CPRS enables clinicians to write orders.

## Appendix

Trailing junk that must not be parsed.
"""


def test_parses_one_entry_per_module() -> None:
    entries = parse_monograph_entries(_FIXTURE)
    assert len(entries) == 2, "two ### modules between §4 and Appendix"


def test_extracts_structured_fields() -> None:
    ar = parse_monograph_entries(_FIXTURE)[0]
    assert ar["package_display"] == "Accounts Receivable (AR)"
    assert ar["namespace"] == "PRCA"
    assert ar["product_line"] == "VHA Finance"
    assert ar["brief_description"].startswith("The Accounts Receivable (AR) package")
    assert ar["business_owner"] == "ACFO Finance Operations"
    assert ar["appid"] == "29"


def test_collects_feature_bullets() -> None:
    ar = parse_monograph_entries(_FIXTURE)[0]
    assert ar["features"] == [
        "Provides a generic billing system",
        "Calculates interest and administrative charges",
    ]
    # CPRS has no Features: block -> empty list, not a crash
    assert parse_monograph_entries(_FIXTURE)[1]["features"] == []


def test_ignores_content_outside_section_4() -> None:
    displays = [e["package_display"] for e in parse_monograph_entries(_FIXTURE)]
    assert "Resources" not in " ".join(displays)
    assert all("Appendix" not in d for d in displays)


def test_derive_audience_from_product_line() -> None:
    assert derive_audience("Clinical Services", "") == "clinical"
    assert derive_audience("Patient Care Services", "") == "clinical"
    assert derive_audience("VHA Finance", "") == "business-admin"
    assert derive_audience("Telehealth and Scheduling", "") == "clinical-admin"
    assert derive_audience("VistA Office (VO) VistA Infrastructure", "") == "sysadmin"
    # unknown product line falls through to a review sentinel, never a guess
    assert derive_audience("Some New Line", "") == "needs-review"


def test_resolve_audience_applies_reviewed_overrides() -> None:
    # PCE -> clinical (with clinical-admin secondary); registries -> clinical-admin uniformly
    prim, sec, _ = resolve_audience("PX", "Health Informatics", "")
    assert (prim, sec) == ("clinical", "clinical-admin")
    for reg in ("ONC", "TBI", "ROR"):
        prim, sec, _ = resolve_audience(reg, "Health Informatics", "")
        assert prim == "clinical-admin", reg
    # KMPD's own purpose names IRM/sysadmins
    assert resolve_audience("KMPD", "Health Informatics", "")[0] == "sysadmin"


def test_resolve_audience_falls_through_to_product_line_map() -> None:
    # an app with no override uses the SPM product-line mapping
    prim, sec, basis = resolve_audience("PSO", "Clinical Services", "")
    assert (prim, sec) == ("clinical", None)
    assert "Clinical Services" in basis


def test_curated_fallback_emitted_for_in_scope_app_absent_from_monograph() -> None:
    # SRA is in-scope VistA, absent from the Monograph fixture, and has a curated fallback profile.
    inv = EnrichedInventory(
        records=[
            EnrichedRecord(
                app_name_abbrev="SRA",
                app_name_full="Surgery Risk Assessment",
                pkg_ns="SRA",
                system_type="VistA",
                app_status="archive",
                app_url="https://www.va.gov/vdl/application.asp?appid=999",
            )
        ]
    )
    draft = build_profiles(parse_monograph_entries(_FIXTURE), inv)
    assert "SRA" not in draft["profiles"], "no Monograph match -> not a monograph profile"
    fb = draft["fallback_profiles"]["SRA"]
    assert fb["source"] == "manual"
    assert fb["app_user_primary"] == _FALLBACK_PROFILES["SRA"]["audience_primary"]
    assert fb["purpose"]  # curated purpose text present
    assert draft["_needs_fallback"] == {}, "every fallback app is curated -> none left unhandled"


def test_software_class_default_national_with_explicit_iii_override() -> None:
    # default: VDL membership -> Class I (national)
    cls, basis = software_class("PSO")
    assert cls == "I" and "VDL" in basis
    # explicit app-level reclassification -> III (local)
    cls, basis = software_class("NUPA")
    assert cls == "III" and basis


def test_monograph_profile_carries_class_and_vasi_status() -> None:
    inv = EnrichedInventory(
        records=[
            EnrichedRecord(
                app_name_abbrev="PRCA",
                app_name_full="Accounts Receivable (AR)",
                pkg_ns="PRCA",
                system_type="VistA",
                app_status="archive",
                app_url="https://www.va.gov/vdl/application.asp?appid=29",
            )
        ]
    )
    prof = build_profiles(parse_monograph_entries(_FIXTURE), inv)["profiles"]["PRCA"]
    assert prof["software_class"] == "I"
    assert prof["vasi_status"] == "Production"


def test_namespace_enrichment_fills_onco() -> None:
    # ONCO (Registries) has no inventory namespace; enrich to the Oncology package (ONC)
    assert app_namespace("ONCO", "") == "ONC"
    # an app with a namespace keeps it
    assert app_namespace("PSO", "PSO") == "PSO"


def test_parent_package_for_sub_prefix_and_sub_product_apps() -> None:
    assert parent_package("KMPV") == "KMP"  # sub-product of Capacity Management
    assert parent_package("SSO/UC") == "XU"  # sub-prefix of Kernel
    assert parent_package("PRF") == "DG"  # sub-prefix of Registration
    assert parent_package("PSO") == ""  # standalone package -> no parent


def test_fallback_profile_carries_enrichments() -> None:
    inv = EnrichedInventory(
        records=[
            EnrichedRecord(
                app_name_abbrev="ONCO",
                app_name_full="Registries",
                pkg_ns="",
                system_type="VistA",
                app_status="archive",
                app_url="https://www.va.gov/vdl/application.asp?appid=998",
            )
        ]
    )
    fb = build_profiles(parse_monograph_entries(_FIXTURE), inv)["fallback_profiles"]["ONCO"]
    assert fb["namespace"] == "ONC"


def test_classify_scope_excludes_non_vista_and_decommissioned() -> None:
    assert classify_scope("VistA", "active", "Production") == (True, "")
    assert classify_scope("VistA + GUI", "archive", "Production") == (True, "")
    ok, reason = classify_scope("Web client", "active", "Production")
    assert ok is False and "non-vista" in reason
    ok, reason = classify_scope("COTS product", "active", "Production")
    assert ok is False and "non-vista" in reason
    ok, reason = classify_scope("VistA", "decommissioned", "Production")
    assert ok is False and "decommissioned" in reason
    ok, reason = classify_scope("VistA", "active", "Inactive")
    assert ok is False and "inactive" in reason
