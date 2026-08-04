"""The admitted-set composition baseline (CI.4, audit R‑19) — pure verdict logic, no I/O.

Nothing tracked the admitted set's composition over time, so a scope change — a VA relabel, a
policy edit, an enrichment regression — was silent. This compares the admitted set against the
last recorded one **by document identifier, grouped by application**: a count can hide a swap
(the P1 lesson), and "XOBW is no longer admitted (23 documents)" is the sentence an operator can
act on where 23 bare identifiers are not.

A deliberate change is acknowledged in ``registries/inventory/scope-changes.yaml`` (application,
date, reason) — acknowledged departures pass (and stay reported); unacknowledged ones are a
blocking finding. Additions never block: growth is the VDL publishing, not scope drift. With the
CI.2 master-set rule in place a departure loses nothing — this gate exists purely so the change
is *seen*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class CompositionVerdict:
    """The gate's decision. ``departures`` (app → sorted doc_ids) is always populated — an
    acknowledged departure is reported, not silenced; ``reason`` names only the fatal ones."""

    ok: bool
    departures: dict[str, list[str]] = field(default_factory=dict)
    reason: str = ""


def diff_admitted(
    prior: Mapping[str, str] | None, current: Mapping[str, str]
) -> dict[str, list[str]]:
    """Departures — prior admitted doc_ids absent now — grouped by application, both sorted."""
    if prior is None:
        return {}
    by_app: dict[str, list[str]] = {}
    for did in sorted(set(prior) - set(current)):
        by_app.setdefault(prior[did], []).append(did)
    return dict(sorted(by_app.items()))


def _describe(app: str, doc_ids: list[str], sample: int = 5) -> str:
    shown = ", ".join(doc_ids[:sample]) + (
        f", +{len(doc_ids) - sample} more" if len(doc_ids) > sample else ""
    )
    return f"{app} ({len(doc_ids)} document(s): {shown})"


def check_composition(
    prior: Mapping[str, str] | None,
    current: Mapping[str, str],
    *,
    acknowledged_apps: frozenset[str],
) -> CompositionVerdict:
    """Compare the admitted set against the recorded baseline (``None`` on the first run —
    there is no history to defend yet; the caller records the fresh baseline)."""
    departures = diff_admitted(prior, current)
    fatal = {app: dids for app, dids in departures.items() if app not in acknowledged_apps}
    if not fatal:
        return CompositionVerdict(ok=True, departures=departures)
    reason = (
        "admitted-set departure(s) not acknowledged: "
        + "; ".join(_describe(app, dids) for app, dids in fatal.items())
        + " — a deliberate scope change is acknowledged with an {app_code, date, reason} entry "
        "in registries/inventory/scope-changes.yaml; otherwise investigate the crawl/policy"
    )
    return CompositionVerdict(ok=False, departures=departures, reason=reason)
