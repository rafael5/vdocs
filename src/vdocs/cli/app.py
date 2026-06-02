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
from vdocs.stages.convert.stage import ConvertStage
from vdocs.stages.crawl.stage import CrawlStage
from vdocs.stages.discover.stage import DiscoverStage
from vdocs.stages.enrich.stage import EnrichStage
from vdocs.stages.fetch.stage import FetchStage
from vdocs.stages.serve_inventory.stage import ServeInventoryStage

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
    ]


def _drive(
    *,
    from_stage: str | None = None,
    to_stage: str | None = None,
    only: str | None = None,
    force: bool = False,
    verify: bool = False,
) -> None:
    cfg = Settings()
    cfg.lake.mkdir(parents=True, exist_ok=True)
    store = StateStore.open(cfg.state_db)
    ctx = StageContext(cfg=cfg, state=store, verify=verify)
    try:
        results = Orchestrator(build_stages()).run(
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


@app.command()
def fetch(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Download catalog documents into the content-addressed bronze raw store."""
    _drive(only="fetch", force=force)


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
def inventory(
    status: bool = typer.Option(False, "--status", help="show per-document fetch status"),
) -> None:
    """Inspect the gold inventory. ``--status`` prints the inventory ⋈ acquisitions join
    (genuine docs annotated with fetch status — fetched / pending / failed / not_acquired)."""
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
