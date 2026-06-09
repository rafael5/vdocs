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
    classify_scope,
    derive_audience,
    parse_monograph_entries,
)

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
