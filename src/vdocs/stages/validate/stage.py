"""The `validate` stage — the sidecar-verification HARD GATE (Steps 2-3; §8, FF C2/C5).

This is the first slice of the §8 ``validate`` gate (the broader S→T fidelity verdict, schema, and
ID/vector integrity land later and feed the *same* gate). It consumes the signals `normalize`
already records but nothing read — the per-bundle ``capture.yaml`` typed capture-attempt records
(§6.4) and the ``refs.yaml`` outbound cross-ref maps (§6.7) — and **fails loudly** on:

  1. **typed absence** (Step 1) — any per-document ``absent-unexpected`` capture outcome;
  2. **count reconciliation** (Step 2, §5.2) — an expected-nonzero sidecar class zero across a
     large corpus, or a count that dropped vs. the prior run over a same-or-larger document set
     (the emitted ``stage_runs[normalize].counts`` finally consumed; the prior validate report is
     the cross-run baseline);
  3. **ref resolution** (Step 3, §5.5) — any **severed** outbound ref (a target slug no heading
     carries — the DITA severed-conref class, hard floor zero). ``UNRESOLVED`` (unmapped) bookmarks
     are **reported as a C5 metric, not gated**: on the real corpus ~92% of Word ``_Toc``/``_Ref``
     cross-refs point at non-heading anchors (page numbers, figures, spans), so a high unmapped rate
     is expected, not a defect — the dead-anchor hard floor is for TOC entries + the heading tree.
  4. **bundle integrity** (Step 4, §5.3/§6.6) — each gold anchor bundle must carry a ``bundle.yaml``
     signed manifest whose recorded part hashes + ``bundle_digest`` match the parts on disk; a
     tamper, a missing/extra part, or a bundle with no manifest blocks (a *verifiable* unit).

It always (re)writes ``reports/validation/verification.json`` (the findings + the count baseline)
and sets its own ``ok`` via the deep gate. ``ALWAYS_RERUN`` — a gate re-checks every time. Pure
logic lives in ``reconcile_pure``/``refs_pure``; this driver is thin I/O (reads the tree + state,
writes the report). The pure cores are written to be reused by the full ``fidelity`` stage later.
"""

from __future__ import annotations

import json

import structlog

from vdocs.contracts.registry import CONSOLIDATED, TEXT_NORMALIZED, VALIDATION_REPORT
from vdocs.kernel import bundle as kbundle
from vdocs.kernel import cas
from vdocs.kernel import registry as kregistry
from vdocs.models.stage import Idempotency, PostflightResult, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.validate import reconcile_pure as rc
from vdocs.stages.validate import refs_pure as rp

log = structlog.get_logger(__name__)

# The corpus-size floor below which a zero expected-nonzero count is not treated as a whole-detector
# failure (a small selection may legitimately carry none) — §5.2 / reconcile_pure.
CORPUS_MIN = 50
# The C5 cross-ref dead-anchor rate TARGET (informational only). On the real corpus ~92% of Word
# `_Toc`/`_Ref` cross-refs are UNRESOLVED — they point at page numbers / figures / spans, not
# headings — so a high unmapped rate is *expected, not a defect* (memory: normalize anchor reality;
# fidelity-framework C5: the hard dead-anchor floor is for TOC entries + the heading tree, NOT every
# inbound body cross-ref). The unmapped rate is therefore **reported as a metric, never gated**;
# only **severed** refs (a resolved slug matching no live anchor — a true violation) block.
UNMAPPED_RATE_TARGET = 0.02


class ValidateStage(Stage):
    name = "validate"
    description = (
        "sidecar-verification gate: typed absence + count reconcile + refs + bundle integrity"
    )
    requires = [TEXT_NORMALIZED, CONSOLIDATED]
    produces = [VALIDATION_REPORT]
    idempotency = Idempotency.ALWAYS_RERUN

    def __init__(self) -> None:
        self._blocking = False
        self._reason = ""

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        normalized_root = ctx.cfg.silver_normalized

        prior_counts = _read_prior_counts(ctx.cfg.validation_report)
        current_counts = _normalize_counts(ctx)

        manifests: list[dict] = []
        ref_findings: list[rp.RefFinding] = []
        outbound_total = 0
        for body_path in sorted(normalized_root.rglob("body.md")):
            bundle = body_path.parent
            capture = _load_yaml(bundle / "capture.yaml")
            if capture:
                manifests.append(capture)
            refs = _load_yaml(bundle / "refs.yaml")
            if refs:
                outbound_total += len(refs.get("outbound") or {})
                ref_findings.extend(rp.resolve_refs(refs))

        # BUNDLE-INTEGRITY GATE (§5.3/§6.6): each gold anchor bundle must carry a bundle.yaml signed
        # manifest whose recorded part hashes + digest match the parts on disk — so the bundle is a
        # verifiable unit, not asserted. A bundle with no manifest can't be verified (unmanifested).
        bundle_findings = _verify_bundles(ctx.cfg.gold_consolidated)

        reconcile_findings = rc.reconcile(
            manifests=manifests,
            current_counts=current_counts,
            prior_counts=prior_counts,
            corpus_min=CORPUS_MIN,
        )
        severed = [f for f in ref_findings if f.kind == rp.SEVERED]
        unmapped = [f for f in ref_findings if f.kind == rp.UNMAPPED]
        expected_unmapped = [f for f in ref_findings if f.kind == rp.EXPECTED_UNMAPPED]
        # The C5 heading-resolvability rate is measured over the *heading-targeting* universe only:
        # expected-unmapped refs (_Ref… → figures/tables/spans) can never resolve to a heading
        # anchor by construction, so they are reported but excluded from the rate (triage 2026-06-03
        # — they were diluting the metric; §6.7/§8, FF C5). The residual unmapped (_Toc→heading
        # misses) is the recoverable, C5-bounded class (a `normalize` legacy-TOC follow-up).
        c5_universe = outbound_total - len(expected_unmapped)
        unmapped_rate = (len(unmapped) / c5_universe) if c5_universe else 0.0

        # The gate blocks on reconciliation findings + SEVERED refs only. Unmapped (UNRESOLVED)
        # cross-refs are reported as a C5 metric, never gated — a high _Toc unmapped rate reflects
        # the recoverable bookmark-capture gap, not a defect (see UNMAPPED_RATE_TARGET).
        blocked_by: list[str] = []
        if reconcile_findings:
            blocked_by.append(f"{len(reconcile_findings)} reconciliation finding(s)")
        if severed:
            blocked_by.append(f"{len(severed)} severed cross-ref(s)")
        if bundle_findings:
            blocked_by.append(f"{len(bundle_findings)} bundle-integrity finding(s)")
        self._blocking = bool(blocked_by)
        self._reason = "; ".join(blocked_by)

        documents = int(current_counts.get("documents", len(manifests)))
        report: dict[str, object] = {
            "blocking": self._blocking,
            "blocked_by": blocked_by,
            "documents": documents,
            "counts": current_counts,  # the cross-run baseline for the next run's drop check
            "reconcile_findings": [
                {"kind": f.kind, "sidecar": f.sidecar, "detail": f.detail}
                for f in reconcile_findings
            ],
            "ref_findings": {
                "severed": [_ref_dict(f) for f in severed],  # gated: hard floor zero
                "unmapped_count": len(unmapped),  # _Toc→heading misses (C5 class), reported
                "expected_unmapped_count": len(expected_unmapped),  # _Ref… non-heading, not C5
                "outbound_total": outbound_total,
                "unmapped_rate": round(unmapped_rate, 4),  # over the heading-targeting universe
                "unmapped_above_c5_target": unmapped_rate > UNMAPPED_RATE_TARGET,
            },
            "bundle_findings": bundle_findings,
        }
        cas.atomic_write(
            ctx.cfg.validation_report,
            (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        if self._blocking:
            log.warning("validate-gate-blocking", reason=self._reason)
        return RunResult(
            counts={
                "documents": documents,
                "reconcile_findings": len(reconcile_findings),
                "severed_refs": len(severed),
                "unmapped_refs": len(unmapped),
                "expected_unmapped_refs": len(expected_unmapped),
                "bundle_findings": len(bundle_findings),
                "blocking": int(self._blocking),
            }
        )

    def deep_gate(self, ctx: StageContext) -> PostflightResult:
        """The HARD GATE: fail (blocking publish) when any verification finding fired (§8)."""
        if self._blocking:
            return PostflightResult(ok=False, reason=f"sidecar verification failed: {self._reason}")
        return PostflightResult(ok=True)


def _ref_dict(f: rp.RefFinding) -> dict:
    return {"doc_id": f.doc_id, "bookmark": f.bookmark, "target": f.target, "kind": f.kind}


def _verify_bundles(consolidated_root) -> list[dict]:  # type: ignore[no-untyped-def]
    """Verify every gold anchor bundle against its ``bundle.yaml`` signed manifest (§6.6).

    For each bundle: read the manifest, read its on-disk parts (excluding the manifest itself), and
    recompute hashes + digest. A bundle with no ``bundle.yaml`` is ``unmanifested`` — it cannot be
    verified, so it is itself a finding. Returns flat finding dicts (empty ⇒ all verified)."""
    findings: list[dict] = []
    if not consolidated_root.is_dir():
        return findings
    for body_path in sorted(consolidated_root.rglob("body.md")):
        bdir = body_path.parent
        rel = bdir.relative_to(consolidated_root).as_posix()
        on_disk = {
            p.name: p.read_bytes()
            for p in bdir.iterdir()
            if p.is_file() and p.name != kbundle.MANIFEST_NAME
        }
        manifest_path = bdir / kbundle.MANIFEST_NAME
        if not manifest_path.is_file():
            findings.append(
                {
                    "kind": kbundle.UNMANIFESTED,
                    "bundle": rel,
                    "path": "",
                    "detail": "no bundle.yaml",
                }
            )
            continue
        manifest = kregistry.load_mapping(manifest_path)
        findings.extend(
            {"kind": f.kind, "bundle": rel, "path": f.path, "detail": f.detail}
            for f in kbundle.verify_manifest(manifest, on_disk)
        )
    return findings


def _load_yaml(path):  # type: ignore[no-untyped-def]
    """Load a sidecar YAML mapping, or ``None`` if absent/empty (defensive — a bad bundle is skipped
    by the count reconciliation rather than crashing the gate)."""
    return kregistry.load_mapping(path, missing_ok=True) or None


def _read_prior_counts(path):  # type: ignore[no-untyped-def]
    """The prior validate run's recorded counts (the §5.2 cross-run drop baseline), or ``None``."""
    if not path.is_file():
        return None
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")).get("counts") or {})
    except (ValueError, AttributeError):
        return None


def _normalize_counts(ctx: StageContext) -> dict[str, int]:
    """The emitted ``stage_runs[normalize].counts`` — the per-sidecar aggregates §5.2 reconciles
    (the artifact nothing consumed until this gate). Empty if normalize has no recorded run."""
    run = ctx.state.get("normalize", ctx.scope)
    return dict(run.counts) if run is not None else {}
