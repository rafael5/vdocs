"""Unit tests for kernel.titles — display titles (strip version/patch noise)."""

import pytest

from vdocs.kernel import titles


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        # strip a leading NS*ver*patch token
        (
            "RMPR*3*59 Delayed Order Report (DOR) (GUI) User Manual",
            "Delayed Order Report (DOR) (GUI) User Manual",
        ),
        # strip "Version N.N"
        (
            "Accounts Receivable Version 4.5 User Manual - Title Page",
            "Accounts Receivable User Manual - Title Page",
        ),
        # inline patch parenthetical
        (
            "Consult/Request Tracking Technical Manual (GMRC*3.0*189)",
            "Consult/Request Tracking Technical Manual",
        ),
        # "(Updated NS*v*p)"
        (
            "National Drug File - User Manual (Updated PSN*4.0*575)",
            "National Drug File - User Manual",
        ),
        ("VistALink Version 1.5 Developer Guide", "VistALink Developer Guide"),
        ("QUASAR Version 3 User Manual (Updated ACKQ*3*21)", "QUASAR User Manual"),
        # multi-segment version
        (
            "Laboratory: VBECS Version 2.4.1 Admin User Guide",
            "Laboratory: VBECS Admin User Guide",
        ),
        # bare dotted version, no keyword
        (
            "VistA Scheduling Enhancement (VSE) GUI 1.7.2.1 User Guide Addendum",
            "VistA Scheduling Enhancement (VSE) GUI User Guide Addendum",
        ),
        # a patch-only title collapses to empty (display_title falls back to the app)
        ("PSO*7.0*123", ""),
    ],
)
def test_denoise_strips_version_patch_noise(raw: str, want: str) -> None:
    # _denoise is the shared strip pass behind display_title (clean_title, its
    # superseded consumer, was deleted — the strip rules remain load-bearing).
    assert titles._denoise(raw) == want


@pytest.mark.parametrize(
    "raw",
    [
        "CPRS User Manual: GUI Version",  # "Version" = a variant, not a number
        "CPRS Technical Manual: List Manager Version",
        "Laboratory Auto Verification/Auto Release User Guide",  # "Release" = a feature word
        "RA HL7 Interface Spec for Voice Recognition Release Notes",  # "Release Notes" = doc type
    ],
)
def test_denoise_preserves_word_senses(raw: str) -> None:
    # Version/Release are stripped only when followed by a number.
    assert titles._denoise(raw) == raw


def test_denoise_is_idempotent() -> None:
    for raw in [
        "Accounts Receivable Version 4.5 User Manual",
        "PSJ*5*279 Nurse's User Manual Change Pages",
        "CPRS User Manual: GUI Version",
    ]:
        once = titles._denoise(raw)
        assert titles._denoise(once) == once


# ── display_title (abbreviation-first, product-prefixed) ────────────────────

_PSO = [
    {
        "abbr": "IEP",
        "full": "Inbound ePrescribing",
        "match": [
            "Pharmacy Reengineering (PRE) Inbound ePrescribing (IEP)",
            "Inbound ePrescribing",
            "IEP",
        ],
    },
    {"abbr": "Outpatient Rx", "full": "Outpatient Pharmacy", "match": ["Outpatient Pharmacy"]},
]
_VSE = [
    {
        "abbr": "VSE",
        "full": "VistA Scheduling Enhancement",
        "match": ["VistA Scheduling Enhancement", "VSE"],
    }
]


def test_display_title_registry_product():
    title, abbr, full = titles.display_title(
        "Outpatient Pharmacy Manager's User Manual", "PSO", "Pharmacy: Outpatient Pharmacy", _PSO
    )
    assert title == "Outpatient Rx — Manager's User Manual"
    assert (abbr, full) == ("Outpatient Rx", "Outpatient Pharmacy")


def test_display_title_longest_alias_wins():
    title, abbr, _ = titles.display_title(
        "Pharmacy Reengineering (PRE) Inbound ePrescribing (IEP) User Manual (Unit 4, Part 1)",
        "PSO",
        "Pharmacy: Outpatient Pharmacy",
        _PSO,
    )
    assert abbr == "IEP"
    assert title == "IEP — User Manual (Unit 4, Part 1)"


def test_display_title_strips_leftover_abbr_paren():
    title, abbr, _ = titles.display_title(
        "VistA Scheduling Enhancement (VSE) GUI User Guide Addendum", "SD", "Scheduling", _VSE
    )
    assert title == "VSE — GUI User Guide Addendum"


def test_display_title_default_app_uses_app_code_and_heuristic_lead():
    # no registry entry → abbr is the app_code; the leading product name is dropped
    title, abbr, full = titles.display_title(
        "Radiology User Manual", "RA", "Radiology/Nuclear Medicine", []
    )
    assert (title, abbr, full) == ("RA — User Manual", "RA", "Radiology/Nuclear Medicine")


def test_display_title_default_keeps_distinguishing_module():
    # the app_name prefixes the title → only it is stripped, the module survives
    title, _, _ = titles.display_title(
        "Beneficiary Travel Dashboard User Manual", "DGBT", "Beneficiary Travel", []
    )
    assert title == "DGBT — Dashboard User Manual"
