"""``vdocs doctor`` — the shipped corpus-soundness gate (the B1–B5 checks, baked in).

Replaces the throwaway ``/tmp/validate_gold*.py`` harness with a first-class command that reads
``index.db`` and answers, for a no-AI operator, **"is my gold corpus sound?"** — emitting a check
table with three buckets and a final ``GOLD LIBRARY: GREEN|RED``:

- **PASS** — the check holds.
- **BY-DESIGN** — an expected gap, not a defect (e.g. ``function_category`` is empty for the
  fallback-profile apps that have no Monograph SPM line). Encoded in ``doctor-policy.yaml`` as a
  per-field ``min_pct`` floor + ``by_design`` note, so it is **separated from real defects** (F6).
- **WARN** — worth the operator's eye but not corrupting (e.g. an accepted anchor edge case, or a
  gold document admitted untyped and awaiting triage, F5).
- **FAIL** — a real defect. **Any FAIL ⇒ RED.**

The pure check builders (this module's top half) take already-queried numbers so they are
unit-tested without a database; :func:`diagnose` is the thin ``index.db`` driver that runs the SQL
and assembles the report. This GREEN/RED is the authoritative gate (replacing the manual sign-off).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

# --- the check model ----------------------------------------------------------------------------


class Health(StrEnum):
    PASS = "PASS"
    BY_DESIGN = "BY-DESIGN"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Check:
    name: str
    health: Health
    detail: str


@dataclass
class DoctorReport:
    gold_count: int
    checks: list[Check] = field(default_factory=list)

    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.health is Health.FAIL]

    def verdict(self) -> str:
        """GREEN unless any check FAILed — BY-DESIGN/WARN never flip the verdict (F6)."""
        return "RED" if self.failures() else "GREEN"


def _sample(offenders: Sequence[str], n: int = 5) -> str:
    if not offenders:
        return ""
    shown = ", ".join(offenders[:n])
    more = f" (+{len(offenders) - n} more)" if len(offenders) > n else ""
    return f": {shown}{more}"


# --- pure check builders ------------------------------------------------------------------------


def coverage_check(
    field: str,
    populated: int,
    total: int,
    *,
    min_pct: float,
    by_design: str = "",
    offenders: Sequence[str] = (),
) -> Check:
    """A per-field coverage check (PASS / BY-DESIGN / FAIL). ``populated``/``total`` over gold docs;
    ``min_pct`` is the FAIL floor; ``by_design`` (if set) labels a below-100 gap as expected."""
    pct = 100.0 if total == 0 else populated / total * 100.0
    base = f"{populated}/{total} ({pct:.1f}%)"
    if pct + 1e-9 < min_pct:
        return Check(
            f"coverage:{field}", Health.FAIL, f"{base} < min {min_pct:g}%{_sample(offenders)}"
        )
    if pct < 100.0 and by_design:
        return Check(f"coverage:{field}", Health.BY_DESIGN, f"{base} — {by_design}")
    return Check(f"coverage:{field}", Health.PASS, base)


def integrity_check(
    name: str,
    violations: int,
    *,
    detail_ok: str = "",
    detail_bad: str = "{n} violations",
    health_bad: Health = Health.FAIL,
    offenders: Sequence[str] = (),
) -> Check:
    """A clean-or-not structural check: PASS when ``violations == 0``, else ``health_bad`` with a
    rendered ``detail_bad`` (``{n}`` → the count) + an offender sample."""
    if violations == 0:
        return Check(name, Health.PASS, detail_ok)
    return Check(name, health_bad, detail_bad.format(n=violations) + _sample(offenders))


# --- the policy (expected-coverage floors + known-empty / accepted edge cases) -------------------


@dataclass(frozen=True)
class CoverageSpec:
    min_pct: float
    by_design: str = ""


@dataclass(frozen=True)
class DoctorPolicy:
    coverage: dict[str, CoverageSpec]
    accepted_anchor_edge_cases: frozenset[str]


_DEFAULT_COVERAGE = {
    "app_user": CoverageSpec(100),
    "doc_user": CoverageSpec(100),
    "software_class": CoverageSpec(100),
    "function_category": CoverageSpec(90, "fallback-profile apps have no Monograph SPM line"),
    "doc_type": CoverageSpec(100),
}


def load_doctor_policy(registries_dir: Path) -> DoctorPolicy:
    """Load ``registries/doctor-policy.yaml`` (expected-coverage floors + accepted edge cases);
    fall back to sensible defaults if the file is absent."""
    path = registries_dir / "doctor-policy.yaml"
    raw: dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cov_raw = raw.get("coverage") or {}
    coverage = {
        fld: CoverageSpec(
            float((spec or {}).get("min_pct", 100)), str((spec or {}).get("by_design", ""))
        )
        for fld, spec in cov_raw.items()
    } or dict(_DEFAULT_COVERAGE)
    accepted = frozenset(raw.get("accepted_anchor_edge_cases") or [])
    return DoctorPolicy(coverage=coverage, accepted_anchor_edge_cases=accepted)


# --- the index.db driver ------------------------------------------------------------------------


def diagnose(
    conn: sqlite3.Connection, *, kept_doctypes: frozenset[str], policy: DoctorPolicy
) -> DoctorReport:
    """Run every soundness check against ``index.db`` and assemble the report. ``kept_doctypes`` is
    the gate's Tier-A keep set (gold must contain only those)."""

    def one(sql: str, *params: object) -> int:
        return int(conn.execute(sql, params).fetchone()[0])

    def ids(sql: str, *params: object) -> list[str]:
        return [r[0] for r in conn.execute(sql, params).fetchall()]

    gold = one("SELECT count(*) FROM documents WHERE is_latest=1")
    checks: list[Check] = [
        integrity_check(
            "gold documents present",
            0 if gold > 0 else 1,
            detail_ok=f"{gold} is_latest documents",
            detail_bad="index.db has no is_latest gold documents",
        )
    ]

    # coverage per configured field
    for fld, spec in policy.coverage.items():
        populated = one(f"SELECT count(*) FROM documents WHERE is_latest=1 AND {fld}<>''")
        offenders = (
            ids(f"SELECT doc_id FROM documents WHERE is_latest=1 AND {fld}='' LIMIT 50")
            if populated < gold
            else []
        )
        checks.append(
            coverage_check(
                fld,
                populated,
                gold,
                min_pct=spec.min_pct,
                by_design=spec.by_design,
                offenders=offenders,
            )  # fmt: skip
        )

    # anchor integrity: exactly one is_latest per anchor_key (no version-collapse over-marking)
    over = ids(
        "SELECT anchor_key FROM documents WHERE is_latest=1 AND anchor_key<>'' "
        "GROUP BY anchor_key HAVING count(*)>1"
    )
    checks.append(
        integrity_check(
            "anchor integrity",
            len(over),
            detail_ok="one is_latest per anchor_key",
            detail_bad="{n} anchor_keys carry >1 is_latest",
            offenders=over,
        )  # fmt: skip
    )

    # gate fidelity: every gold doc_type is in the Tier-A keep set (no forbidden Tier-B/C/D leaked)
    forbidden = ids(
        "SELECT DISTINCT doc_type FROM documents WHERE is_latest=1 AND doc_type<>'' "
        f"AND doc_type NOT IN ({','.join('?' * len(kept_doctypes))})",
        *sorted(kept_doctypes),
    )
    checks.append(
        integrity_check(
            "gate fidelity",
            len(forbidden),
            detail_ok="all gold doc_types are Tier-A",
            detail_bad="{n} forbidden doc_type(s) in gold",
            offenders=forbidden,
        )  # fmt: skip
    )

    # anchor form: a well-formed anchor_key is 4 parts (app:pkg:type:stem); flag others (minus the
    # documented accepted edge cases) as WARN, so new corruption is caught but the known one is not.
    malformed = [
        d
        for d in ids(
            "SELECT doc_id FROM documents WHERE is_latest=1 AND anchor_key<>'' "
            "AND (length(anchor_key)-length(replace(anchor_key,':','')))<>3"
        )
        if d not in policy.accepted_anchor_edge_cases
    ]
    checks.append(
        integrity_check(
            "anchor form",
            len(malformed),
            detail_ok="anchor_keys are 4-part",
            detail_bad="{n} non-4-part anchor_key(s)",
            health_bad=Health.WARN,
            offenders=malformed,
        )  # fmt: skip
    )

    # search surface: FTS non-empty and indexes only is_latest chunks
    fts = one("SELECT count(*) FROM chunks_fts")
    fts_non_latest = one(
        "SELECT count(*) FROM chunks_fts f WHERE f.doc_key NOT IN "
        "(SELECT doc_key FROM documents WHERE is_latest=1)"
    )
    if fts == 0:
        checks.append(Check("search surface", Health.FAIL, "chunks_fts is empty"))
    else:
        checks.append(
            integrity_check(
                "search surface",
                fts_non_latest,
                detail_ok=f"{fts} FTS chunks, latest-only",
                detail_bad="{n} FTS chunks from non-latest docs",
            )  # fmt: skip
        )

    # entity graph: entities present + entity_mentions join intact (no dangling ids)
    ent = one("SELECT count(*) FROM entities")
    dangling = one(
        "SELECT count(*) FROM entity_mentions m "
        "WHERE m.entity_id NOT IN (SELECT entity_id FROM entities) "
        "OR m.doc_key NOT IN (SELECT doc_key FROM documents)"
    )
    if ent == 0:
        checks.append(Check("entity graph", Health.WARN, "no entities extracted"))
    else:
        checks.append(
            integrity_check(
                "entity graph",
                dangling,
                detail_ok=f"{ent} entities, joins intact",
                detail_bad="{n} dangling entity_mention(s)",
            )  # fmt: skip
        )

    return DoctorReport(gold_count=gold, checks=checks)


# --- rendering ------------------------------------------------------------------------------------

_GLYPH = {Health.PASS: "✅", Health.BY_DESIGN: "◎", Health.WARN: "⚠️", Health.FAIL: "❌"}


def render_report(report: DoctorReport, echo: Any) -> None:
    """Emit the check table + the bucketed counts + the GOLD LIBRARY verdict (plain stdout)."""
    echo("=== vdocs doctor — gold corpus soundness ===")
    for c in report.checks:
        glyph = _GLYPH[c.health]
        echo(f"  {glyph} {c.health.value:<9} {c.name:<24} {c.detail}".rstrip())
    n = {h: sum(1 for c in report.checks if c.health is h) for h in Health}
    echo(
        f"\n{report.gold_count} gold documents · "
        f"{n[Health.PASS]} pass · {n[Health.BY_DESIGN]} by-design · "
        f"{n[Health.WARN]} warn · {n[Health.FAIL]} fail"
    )
    echo(f"\nGOLD LIBRARY: {report.verdict()}")


__all__ = [
    "Check",
    "CoverageSpec",
    "DoctorPolicy",
    "DoctorReport",
    "Health",
    "coverage_check",
    "diagnose",
    "integrity_check",
    "load_doctor_policy",
    "render_report",
]
