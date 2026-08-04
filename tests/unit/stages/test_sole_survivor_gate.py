"""VO.7 — the sole-survivor exception to the doc-type policy.

The doc-type policy omits release notes, install guides and similar because they are version-bound
and go stale. That is right in general and wrong for one case: when the omitted document is the
*last surviving documentation of its kind* for a package whose code is still installed and running
in VistA. Nothing newer supersedes it, so omitting it does not defer the content to a better
version — it discards it.

The exception is deliberately narrow. A blanket doc-type flip admits 1,766 documents and rebuilds
the flood the policy exists to prevent; this rule admits ~159. It is computed corpus-wide (does
anything supersede this?), so it lives in `select_fetch_targets`, which sees every record — not in
`GatePolicy.admits`, which sees one at a time.
"""

from vdocs.models.catalog import EnrichedRecord
from vdocs.stages.fetch.fetch_pure import (
    GatePolicy,
    Selection,
    select_fetch_targets,
    sole_survivors,
)

POLICY = GatePolicy(
    allowed_system_prefixes=("VistA",),
    denied_app_status=frozenset({"decommissioned"}),
    omitted_doc_codes=frozenset({"RN"}),
)


def rec(slug: str, **kw) -> EnrichedRecord:
    base = dict(
        app_name_abbrev="XU",
        doc_slug=slug,
        doc_code="UM",
        doc_format="docx",
        system_type="VistA",
        app_status="active",
        anchor_key=f"XU:XU:{kw.get('doc_code', 'UM')}",
    )
    return EnrichedRecord(**{**base, **kw})


class TestSoleSurvivors:
    def test_an_archived_document_with_nothing_newer_is_a_sole_survivor(self) -> None:
        records = [rec("old-rn", doc_code="RN", app_status="archive")]
        assert sole_survivors(records, POLICY) == {"XU:XU:RN"}

    def test_an_archived_document_an_active_one_supersedes_is_not(self) -> None:
        records = [
            rec("old-rn", doc_code="RN", app_status="archive"),
            rec("new-rn", doc_code="RN", app_status="active"),
        ]
        assert sole_survivors(records, POLICY) == set()

    def test_an_active_document_is_never_a_sole_survivor(self) -> None:
        """The rule is an exception for *superseded* material, not a doctype-policy escape hatch
        for current documents — those are the 1,766 the policy deliberately omits."""
        assert sole_survivors([rec("rn", doc_code="RN")], POLICY) == set()

    def test_out_of_scope_apps_never_qualify(self) -> None:
        records = [rec("rn", doc_code="RN", app_status="archive", system_type="Web client")]
        assert sole_survivors(records, POLICY) == set()

    def test_noise_never_qualifies(self) -> None:
        records = [rec("f", doc_code="RN", app_status="archive", noise_type="vba_form")]
        assert sole_survivors(records, POLICY) == set()

    def test_a_kept_doctype_is_not_reported(self) -> None:
        """A kept type needs no exception — it is admitted by the policy already."""
        records = [rec("um", app_status="archive")]
        assert sole_survivors(records, POLICY) == set()


class TestGateIntegration:
    def test_a_sole_survivor_is_fetched_despite_its_omitted_doctype(self) -> None:
        records = [rec("old-rn", doc_code="RN", app_status="archive")]
        targets = select_fetch_targets(records, Selection(all_=True), POLICY)
        assert [t.doc_slug for t in targets] == ["old-rn"]

    def test_a_superseded_omitted_document_is_still_excluded(self) -> None:
        records = [
            rec("old-rn", doc_code="RN", app_status="archive"),
            rec("new-rn", doc_code="RN", app_status="active"),
        ]
        assert select_fetch_targets(records, Selection(all_=True), POLICY) == []

    def test_the_exception_does_not_widen_app_scope(self) -> None:
        """A narrowing invariant must stay a narrowing — the sole-survivor rule relaxes the
        doc-type axis only, never the app-scope or noise ones."""
        records = [
            rec("a", doc_code="RN", app_status="archive", system_type="COTS product"),
            rec("b", doc_code="RN", app_status="archive", noise_type="vba_form"),
        ]
        assert select_fetch_targets(records, Selection(all_=True), POLICY) == []

    def test_ordinary_admission_is_unchanged(self) -> None:
        records = [rec("um"), rec("rn", doc_code="RN")]
        targets = select_fetch_targets(records, Selection(all_=True), POLICY)
        assert [t.doc_slug for t in targets] == ["um"]

    def test_policy_none_still_skips_the_gate_entirely(self) -> None:
        records = [rec("rn", doc_code="RN")]
        assert len(select_fetch_targets(records, Selection(all_=True), None)) == 1
