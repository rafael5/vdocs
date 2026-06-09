"""The vdocs CLI — one subcommand per stage + ``run`` (ADR-009, §7.5).

Every command drives stages through the identical orchestrator preflight→run→postflight
path — there is no second execution route (§7.1). A preflight FAIL surfaces as a non-zero
exit with the remediation hint (tenet #7).
"""

from __future__ import annotations

import typer

from vdocs.config import Settings
from vdocs.orchestrator.engine import Orchestrator, StageFailed
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.orchestrator.state import StateStore
from vdocs.stages.catalog.stage import CatalogStage
from vdocs.stages.consolidate.stage import ConsolidateStage
from vdocs.stages.convert.stage import ConvertStage
from vdocs.stages.crawl.stage import CrawlStage
from vdocs.stages.discover.stage import DiscoverStage
from vdocs.stages.embed.stage import EmbedStage
from vdocs.stages.enrich.stage import EnrichStage
from vdocs.stages.fetch.stage import FetchStage
from vdocs.stages.index.stage import IndexStage
from vdocs.stages.manifest.stage import ManifestStage
from vdocs.stages.normalize.stage import NormalizeStage
from vdocs.stages.relate.stage import RelateStage
from vdocs.stages.serve_inventory.stage import ServeInventoryStage
from vdocs.stages.validate.stage import ValidateStage

app = typer.Typer(
    help="vdocs — VistA Document Library modernization pipeline", no_args_is_help=True
)


def build_stages() -> list[Stage]:
    """All implemented stages, wired with their real (network) I/O defaults."""
    return [
        CrawlStage(),
        CatalogStage(),
        ServeInventoryStage(),
        FetchStage(),
        ConvertStage(),
        DiscoverStage(),
        EnrichStage(),
        NormalizeStage(),
        ConsolidateStage(),
        IndexStage(),
        RelateStage(),
        EmbedStage(),
        ManifestStage(),
        ValidateStage(),
    ]


def _drive(
    *,
    from_stage: str | None = None,
    to_stage: str | None = None,
    only: str | None = None,
    force: bool = False,
    verify: bool = False,
    stages: list[Stage] | None = None,
) -> None:
    cfg = Settings()
    cfg.lake.mkdir(parents=True, exist_ok=True)
    store = StateStore.open(cfg.state_db)
    ctx = StageContext(cfg=cfg, state=store, verify=verify)
    try:
        results = Orchestrator(stages or build_stages()).run(
            ctx, from_=from_stage, to=to_stage, only=only, force=force
        )
    except StageFailed as exc:
        typer.echo(f"FAILED: {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        store.close()
    for result in results:
        if result is not None:
            typer.echo(f"{result.stage}: ok {result.counts}")


@app.command()
def crawl() -> None:
    """Crawl the VDL site into catalog.raw (network; FORCE_ONLY → always runs when invoked)."""
    _drive(only="crawl", force=True)


@app.command()
def catalog(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Enrich catalog.raw into the conformed inventory (identity, doc-type, noise, groups)."""
    _drive(only="catalog", force=force)


@app.command(name="serve-inventory")
def serve_inventory(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Promote the enriched inventory to the gold selection surface; the postflight HARD GATE
    blesses it (the fetch gate)."""
    _drive(only="serve-inventory", force=force)


def _flatten(values: list[str]) -> frozenset[str]:
    """Repeatable + comma-separated option values → a flat set (``--app A,B --app C``)."""
    return frozenset(v.strip() for raw in values for v in raw.split(",") if v.strip())


def _read_select_file(path: str) -> frozenset[str]:
    """One ``doc_id`` per line — the §5.6 curated list. Blank lines and ``#`` comments are ignored,
    both full-line and *inline* (a trailing ``# rationale``); ``doc_id``s never contain ``#`` so the
    first ``#`` always starts a comment. This is what lets ``registries/dev-corpus.txt`` annotate
    each pick."""
    from pathlib import Path

    lines = Path(path).read_text(encoding="utf-8").splitlines()
    ids = (line.split("#", 1)[0].strip() for line in lines)
    return frozenset(i for i in ids if i)


@app.command()
def fetch(
    apps: list[str] = typer.Option([], "--app", help="app code (exact) or app-name substring"),
    sections: list[str] = typer.Option([], "--section", help="section code (exact)"),
    statuses: list[str] = typer.Option([], "--status", help="app status: active|decommissioned"),
    doc_types: list[str] = typer.Option([], "--doc-type", help="doc code, e.g. UM, DIBR (exact)"),
    groups: list[str] = typer.Option([], "--group", help="group_key or anchor_key (exact)"),
    select_file: str = typer.Option(None, "--select", help="file of doc_ids, one per line"),
    all_: bool = typer.Option(False, "--all", help="select the whole genuine inventory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="report the match count, fetch nothing"),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Download a **selection** of documents into the content-addressed bronze raw store (§5.6).

    There is no blind/full download: with no selection this fetches nothing and prints how many
    genuine in-scope documents are available. Narrow with the dimension filters (AND across them,
    OR within each), or take the whole genuine inventory with ``--all``. The selection always
    acquires every version in a selected logical document's lineage (§5.6 invariant 2).
    """
    from vdocs.models.catalog import EnrichedInventory
    from vdocs.stages.fetch.fetch_pure import Selection, select_fetch_targets
    from vdocs.stages.fetch.policy import load_gate_policy

    cfg = Settings()
    if not cfg.gold_inventory_json.exists():
        typer.echo("no gold inventory yet — run: vdocs serve-inventory")
        raise typer.Exit(code=1)
    records = EnrichedInventory.model_validate_json(
        cfg.gold_inventory_json.read_text(encoding="utf-8")
    ).records
    # the always-on admission gate (app scope + doc-type policy) — the preview must match what
    # the fetch stage will actually pull, so apply it here too.
    policy = load_gate_policy(cfg.registries)
    selection = Selection(
        apps=_flatten(apps),
        sections=_flatten(sections),
        statuses=_flatten(statuses),
        doc_types=_flatten(doc_types),
        groups=_flatten(groups),
        ids=_read_select_file(select_file) if select_file else frozenset(),
        all_=all_,
    )

    available = len(select_fetch_targets(records, Selection(all_=True), policy))
    if selection.is_empty:
        typer.echo(
            f"no selection — fetched nothing. {available} genuine in-scope documents available; "
            "narrow with --app/--section/--status/--doc-type/--group/--select, or all with --all."
        )
        return
    targets = select_fetch_targets(records, selection, policy)
    if dry_run:
        typer.echo(
            f"selection matches {len(targets)} of {available} genuine in-scope documents "
            "(dry-run; nothing fetched)."
        )
        return
    if not targets:
        typer.echo(
            f"selection matched 0 of {available} genuine in-scope documents — nothing to fetch."
        )
        return

    stages = build_stages()
    for stage in stages:
        if stage.name == "fetch":
            stage.selection = selection  # type: ignore[attr-defined]
    typer.echo(f"fetching {len(targets)} of {available} genuine in-scope documents…")
    _drive(only="fetch", stages=stages, force=force)


@app.command()
def convert(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Convert fetched documents to markdown bundles (text@converted) + extract images."""
    _drive(only="convert", force=force)


@app.command()
def discover(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Mine candidate patterns (boilerplate / dead phrases / glossary) into reports/patterns."""
    _drive(only="discover", force=force)


@app.command()
def enrich(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Bake identity frontmatter onto converted bundles (text@enriched) + stage doc metadata."""
    _drive(only="enrich", force=force)


@app.command()
def normalize(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Normalize enriched bodies (strip artifacts, subtract phrases, regen TOC)."""
    _drive(only="normalize", force=force)


@app.command()
def consolidate(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Collapse each version group to one anchor document + capture its append-only lineage
    (history.yaml + retained prior bodies); the deferred git replay is push --replay-history."""
    _drive(only="consolidate", force=force)


@app.command()
def index(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Build index.db: documents + doc_sections (+ FTS5 over is_latest only) + entities."""
    _drive(only="index", force=force)


@app.command()
def relate(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Materialize the knowledge graph (doc↔entity, entity↔entity, doc↔doc) into relations."""
    _drive(only="relate", force=force)


@app.command()
def manifest(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Assemble corpus-manifest.json + discovery.json — the MCP front door (semantic off now)."""
    _drive(only="manifest", force=force)


@app.command()
def ask(
    query: str = typer.Argument(..., help="a natural-language question about VistA / the corpus"),
    k: int = typer.Option(8, "--k", "-k", help="how many ranked hits to return"),
    apps: list[str] = typer.Option([], "--app", help="restrict to these app codes (exact)"),
    doc_types: list[str] = typer.Option([], "--doc-type", help="restrict to these doc codes"),
    json_out: bool = typer.Option(False, "--json", help="emit hits as JSON (for tools/agents)"),
) -> None:
    """Search the gold corpus and return ranked, **pre-cited** hits — the answer to "based on the
    vdocs gold corpus, …" without guessing (§14.7). Lexical FTS5 over the is_latest search chunks;
    each hit carries its section_id, the document/section titles, a snippet, and the gold body path.
    """
    import json

    from vdocs.server import search

    cfg = Settings()
    if not cfg.index_db.exists():
        typer.echo("no index.db yet — run: vdocs index (then relate, manifest)")
        raise typer.Exit(code=1)
    hits = search.lexical_search(
        cfg.index_db, query, k=k, app=list(apps) or None, doc_type=list(doc_types) or None
    )
    if json_out:
        typer.echo(json.dumps(hits, indent=2, ensure_ascii=False))
        return
    if not hits:
        typer.echo("no matches in the gold corpus.")
        return
    for i, h in enumerate(hits, 1):
        typer.echo(f"{i}. [{h['score']}] {h['doc_title']} — §{h['section_title']}")
        typer.echo(f"   {h['uri']}")
        typer.echo(f"   {h['body_path']}")
        typer.echo(f"   {h['snippet']}")


@app.command()
def validate(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Sidecar-verification HARD GATE: typed absence (capture.yaml) + count reconciliation +
    refs.yaml ref-resolution. Fails loudly on a silent detector miss, an implausible corpus
    aggregate, or a severed cross-ref; writes reports/validation/verification.json (§8)."""
    _drive(only="validate", force=force)


@app.command()
def inventory(
    status: bool = typer.Option(False, "--status", help="show per-document fetch status"),
) -> None:
    """Inspect the gold inventory. ``--status`` prints the inventory ⋈ acquisitions join
    (genuine docs annotated with fetch status — fetched / pending / failed / not_acquired /
    out_of_scope [PDF-only, §1])."""
    from vdocs.models.catalog import EnrichedInventory
    from vdocs.stages.serve_inventory import serve_pure as sp

    cfg = Settings()
    if not cfg.gold_inventory_json.exists():
        typer.echo("no gold inventory yet — run: vdocs serve-inventory")
        raise typer.Exit(code=1)
    records = EnrichedInventory.model_validate_json(
        cfg.gold_inventory_json.read_text(encoding="utf-8")
    ).records
    store = StateStore.open(cfg.state_db)
    try:
        rows = sp.inventory_status(records, store.all_acquisitions())
    finally:
        store.close()
    if status:
        summary = sp.status_summary(rows)
        parts = [f"{k}={v}" for k, v in summary.items()]
        typer.echo("inventory status: " + "  ".join(parts))
    else:
        typer.echo(f"gold inventory: {len(records)} records, {len(rows)} genuine documents")


@app.command()
def run(
    from_stage: str = typer.Option(None, "--from", help="start at this stage"),
    to_stage: str = typer.Option(None, "--to", help="stop after this stage"),
    only: str = typer.Option(None, "--only", help="run only this stage"),
    force: bool = typer.Option(False, "--force", "-f", help="re-run even if unchanged"),
    verify: bool = typer.Option(False, "--verify", help="use strong content-hash fingerprints"),
) -> None:
    """Run the pipeline DAG (optionally a slice) through the generic orchestrator."""
    _drive(from_stage=from_stage, to_stage=to_stage, only=only, force=force, verify=verify)


if __name__ == "__main__":  # pragma: no cover
    app()
