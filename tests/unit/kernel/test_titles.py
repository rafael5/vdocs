"""Unit tests for kernel.titles — clean display title (strip version/patch tokens)."""

import pytest

from vdocs.kernel import titles


@pytest.mark.parametrize(
    ("raw", "app_name", "want"),
    [
        # strip a leading NS*ver*patch token
        (
            "RMPR*3*59 Delayed Order Report (DOR) (GUI) User Manual",
            "Prosthetics",
            "Delayed Order Report (DOR) (GUI) User Manual",
        ),
        # strip "Version N.N"
        (
            "Accounts Receivable Version 4.5 User Manual - Title Page",
            "Accounts Receivable",
            "Accounts Receivable User Manual - Title Page",
        ),
        # inline patch parenthetical
        (
            "Consult/Request Tracking Technical Manual (GMRC*3.0*189)",
            "Consult/Request Tracking",
            "Consult/Request Tracking Technical Manual",
        ),
        # "(Updated NS*v*p)"
        (
            "National Drug File - User Manual (Updated PSN*4.0*575)",
            "National Drug File",
            "National Drug File - User Manual",
        ),
        ("VistALink Version 1.5 Developer Guide", "VistALink", "VistALink Developer Guide"),
        ("QUASAR Version 3 User Manual (Updated ACKQ*3*21)", "QUASAR", "QUASAR User Manual"),
        # multi-segment version
        (
            "Laboratory: VBECS Version 2.4.1 Admin User Guide",
            "VBECS",
            "Laboratory: VBECS Admin User Guide",
        ),
        # bare dotted version, no keyword
        (
            "VistA Scheduling Enhancement (VSE) GUI 1.7.2.1 User Guide Addendum",
            "VistA Scheduling Enhancement",
            "VistA Scheduling Enhancement (VSE) GUI User Guide Addendum",
        ),
        # app-name fallback: title was only NS*v*p + a doc-type label
        ("XWB*1.1*73 User Guide", "RPC Broker", "RPC Broker — User Guide"),
        (
            "PSJ*5*279 Nurse's User Manual Change Pages",
            "Inpatient Medications",
            "Inpatient Medications — Nurse's User Manual Change Pages",
        ),
    ],
)
def test_clean_title(raw: str, app_name: str, want: str) -> None:
    assert titles.clean_title(raw, app_name) == want


@pytest.mark.parametrize(
    "raw",
    [
        "CPRS User Manual: GUI Version",  # "Version" = a variant, not a number
        "CPRS Technical Manual: List Manager Version",
        "Laboratory Auto Verification/Auto Release User Guide",  # "Release" = a feature word
        "RA HL7 Interface Spec for Voice Recognition Release Notes",  # "Release Notes" = doc type
    ],
)
def test_clean_title_preserves_word_senses(raw: str) -> None:
    # Version/Release are stripped only when followed by a number.
    assert titles.clean_title(raw, "CPRS") == raw


def test_clean_title_never_empty() -> None:
    # A patch-only title collapses → falls back to the app name.
    assert titles.clean_title("PSO*7.0*123", "Outpatient Pharmacy") == "Outpatient Pharmacy"
    # No app name and label-only → keep the label rather than vanish.
    assert titles.clean_title("XWB*1.1*73 User Guide", "") == "User Guide"


def test_clean_title_is_idempotent() -> None:
    for raw in [
        "Accounts Receivable Version 4.5 User Manual",
        "PSJ*5*279 Nurse's User Manual Change Pages",
        "CPRS User Manual: GUI Version",
    ]:
        once = titles.clean_title(raw, "App Name")
        assert titles.clean_title(once, "App Name") == once
