"""Unit tests for kernel.personas — the shared two-axis persona / profile resolver (§7).

One vocabulary (clinical · clinical-admin · business-admin · developer · sysadmin), two axes:
app_user (who operates the app, app-profiles.yaml) and doc_user (who reads the doc, doc-user.yaml
with `operator` doc-types delegating to the app's app_user). This is the ONE place the four baked
tags are derived — enrich bakes them into gold frontmatter, the facets reader queries the columns.
"""

from __future__ import annotations

from vdocs.config import Settings
from vdocs.kernel import personas

# --- pure resolution --------------------------------------------------------
_DOC_USER = {"UM": "operator", "TM": "developer", "AG": "sysadmin"}
_APP_USER = {"SD": "clinical-admin", "OR": "clinical"}


def test_resolve_doc_user_role_fixed_ignores_app():
    # a Technical Manual is read by developers whatever the app
    assert personas.resolve_doc_user("TM", "OR", _DOC_USER, _APP_USER) == "developer"
    assert personas.resolve_doc_user("AG", "SD", _DOC_USER, _APP_USER) == "sysadmin"


def test_resolve_doc_user_operator_delegates_to_app_user():
    # a User Manual delegates to whoever operates the app
    assert personas.resolve_doc_user("UM", "SD", _DOC_USER, _APP_USER) == "clinical-admin"
    assert personas.resolve_doc_user("UM", "OR", _DOC_USER, _APP_USER) == "clinical"


def test_resolve_doc_user_empty_when_unknown():
    assert personas.resolve_doc_user("ZZ", "SD", _DOC_USER, _APP_USER) == ""  # unknown doc_type
    assert personas.resolve_doc_user("UM", "XX", _DOC_USER, _APP_USER) == ""  # app not operated


def test_profile_tags_resolves_four_and_drops_empties():
    maps = personas.ProfileMaps(
        app_user={"SD": "clinical-admin"},
        software_class={"SD": "I"},
        function_category={"SD": "Health Informatics"},
        doc_user={"UM": "operator"},
    )
    assert personas.profile_tags("SD", "UM", maps) == {
        "app_user": "clinical-admin",
        "doc_user": "clinical-admin",  # operator UM delegates to SD's app_user
        "software_class": "I",
        "function_category": "Health Informatics",
    }
    # an app with no profile yields no tags (all four empty → dropped)
    assert personas.profile_tags("XX", "UM", maps) == {}


def test_profile_tags_keys_are_the_canonical_four():
    assert personas.PROFILE_TAGS == ("app_user", "doc_user", "software_class", "function_category")


# --- registry loading (real in-repo registries) -----------------------------
def test_load_profile_maps_from_real_registries():
    maps = personas.load_profile_maps(Settings().registries)
    # doc-user.yaml: role-fixed + operator delegation
    assert maps.doc_user["TM"] == "developer" and maps.doc_user["UM"] == "operator"
    # app-profiles.yaml: ADT is a clinical-admin, Class I app
    assert maps.app_user["ADT"] == "clinical-admin"
    assert maps.software_class["ADT"] == "I"
    # function_category now comes from function-domains.yaml (the functional taxonomy),
    # NOT the Monograph SPM line: ADT (registration) → "Registration & scheduling".
    assert maps.function_category["ADT"] == "Registration & scheduling"
    assert maps.function_category["LR"] == "Laboratory"  # lab is its own domain
    assert maps.function_category["RA"] == "Radiology & imaging"
    assert maps.function_category["SR"] == "Specialty care"  # surgery → specialty
    # the needs-review sentinel is never surfaced as an app_user value
    assert "needs-review" not in set(maps.app_user.values())


def test_load_profile_maps_missing_registries_is_empty(tmp_path):
    maps = personas.load_profile_maps(tmp_path)  # no inventory/*.yaml present
    assert maps.app_user == {} and maps.doc_user == {}
    assert maps.software_class == {} and maps.function_category == {}


def test_load_profile_maps_skips_malformed_profile_entries(tmp_path):
    # a non-dict profile entry (e.g. a stray null) is ignored, not crashed on
    inv = tmp_path / "inventory"
    inv.mkdir()
    (inv / "app-profiles.yaml").write_text(
        "profiles:\n  GOOD: {app_user_primary: clinical, software_class: I}\n  BROKEN: null\n",
        encoding="utf-8",
    )
    (inv / "doc-user.yaml").write_text("doc_user: {UM: operator}\n", encoding="utf-8")
    maps = personas.load_profile_maps(tmp_path)
    assert maps.app_user == {"GOOD": "clinical"} and "BROKEN" not in maps.app_user
    assert maps.doc_user == {"UM": "operator"}
