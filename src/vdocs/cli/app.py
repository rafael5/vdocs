"""The vdocs CLI — one subcommand per stage + ``run`` (ADR-009, §7.5).

Every command drives stages through the identical orchestrator preflight→run→postflight
path — there is no second execution route (§7.1). A preflight FAIL surfaces as a non-zero
exit with the remediation hint (tenet #7).
"""

from __future__ import annotations

import functools
from collections.abc import Callable

import typer

from vdocs.config import Settings
from vdocs.orchestrator.engine import Orchestrator, StageFailed
from vdocs.orchestrator.report import RunReporter
from vdocs.orchestrator.stage import PostflightError, Stage, StageContext
from vdocs.orchestrator.state import StateStore
from vdocs.stages.catalog.stage import CatalogStage
from vdocs.stages.consolidate.stage import ConsolidateStage
from vdocs.stages.convert.stage import ConvertStage
from vdocs.stages.crawl.stage import CrawlStage
from vdocs.stages.discover.stage import DiscoverStage
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


def _guarded(fn: Callable[..., None]) -> Callable[..., None]:
    """Wrap a CLI command so an *unhandled* exception surfaces as one clean ERROR line + exit 1 —
    the same no-traceback contract the orchestrated run/build path gives, for the aux commands
    (gate/fetch/doctor/ask/inventory) that don't go through `_drive`. An intentional `typer.Exit`
    (a handled error condition, already clean) passes through untouched. So a malformed registry
    YAML or a missing file reads as "ERROR: doctor failed — …" instead of a Python traceback the
    no-AI operator would have to decode."""

    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> None:
        try:
            fn(*args, **kwargs)
        except typer.Exit:
            raise
        except Exception as exc:  # noqa: BLE001 — the CLI's outermost clean-error boundary
            typer.secho(f"ERROR: {fn.__name__} failed — {exc}", fg="red", bold=True)
            raise typer.Exit(code=1) from exc

    return wrapper


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
    strict: bool = False,
    stages: list[Stage] | None = None,
) -> None:
    cfg = Settings()
    cfg.lake.mkdir(parents=True, exist_ok=True)
    store = StateStore.open(cfg.state_db)
    ctx = StageContext(cfg=cfg, state=store, verify=verify)
    reporter = RunReporter()
    failed = False
    try:
        Orchestrator(stages or build_stages()).run(
            ctx, from_=from_stage, to=to_stage, only=only, force=force, reporter=reporter
        )
    except (StageFailed, PostflightError):
        # the reporter already recorded the ERROR outcome; render a clean summary (no traceback)
        # and exit per the contract — exit_code() resolves the recorded ERROR to 1.
        failed = True
    finally:
        store.close()
    reporter.render_summary()
    code = reporter.exit_code(strict=strict)
    if failed or code != 0:
        raise typer.Exit(code=code or 1)


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
@_guarded
def fetch(
    apps: list[str] = typer.Option([], "--app", help="app code (exact) or app-name substring"),
    sections: list[str] = typer.Option([], "--section", help="section code (exact)"),
    statuses: list[str] = typer.Option([], "--status", help="app status: active|decommissioned"),
    doc_types: list[str] = typer.Option([], "--doc-type", help="doc code, e.g. UM, DIBR (exact)"),
    groups: list[str] = typer.Option([], "--group", help="group_key or anchor_key (exact)"),
    select_file: str = typer.Option(None, "--select", help="file of doc_ids, one per line"),
    all_: bool = typer.Option(False, "--all", help="select the whole genuine inventory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="report the match count, fetch nothing"),
    refetch: bool = typer.Option(
        False, "--refetch", help="re-download even docs already in the CAS (default: skip them)"
    ),
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
            stage.refetch = refetch  # type: ignore[attr-defined]
    typer.echo(f"fetching {len(targets)} of {available} genuine in-scope documents…")
    # --refetch means "actually re-download now", so it implies --force (else an unchanged
    # selection would SKIP_IF_UNCHANGED before the stage runs).
    _drive(only="fetch", stages=stages, force=force or refetch)


@app.command()
@_guarded
def gate(
    counts: bool = typer.Option(
        True, "--counts/--no-counts", help="also show admitted counts against the gold inventory"
    ),
) -> None:
    """Explain the corpus **admission gate** — what gets fetched into (and promoted to) gold.

    Prints the effective, assembled policy in plain terms (app-scope prefixes + denied statuses,
    the kept vs omitted doc-types, and the fail-safe for untyped docs) so an operator can see and
    change the gate without reading code. With a gold inventory present it also reports how the gate
    partitions it (admitted vs excluded, with a per-doc-type breakdown). See docs/gate-reference.md.
    """
    from vdocs.models.catalog import EnrichedInventory
    from vdocs.stages.fetch import fetch_pure as fp
    from vdocs.stages.fetch.policy import load_gate_config, load_gate_policy

    cfg = Settings()
    cfgd = load_gate_config(cfg.registries)

    typer.echo("=== vdocs corpus admission gate ===")
    typer.echo("App scope (registries/inventory/scope-policy.yaml):")
    typer.echo(f"  allowed system-type prefixes: {', '.join(cfgd.allowed_system_prefixes) or '—'}")
    typer.echo(f"  denied app statuses:          {', '.join(cfgd.denied_app_status) or '—'}")
    typer.echo("Doc-type policy (registries/inventory/doctype-policy.yaml):")
    safe = "  (fail-safe → admitted, surfaces for triage)" if cfgd.default_doctype == "keep" else ""
    typer.echo(f"  untyped/unmapped default:     {cfgd.default_doctype.upper()}{safe}")
    typer.echo(f"  KEPT doc-types ({len(cfgd.kept)}):")
    for d in cfgd.kept:
        typer.echo(f"    {d.code:<5} {d.label}")
    typer.echo(f"  OMITTED doc-types ({len(cfgd.omitted)}):")
    for d in cfgd.omitted:
        typer.echo(f"    {d.code:<5} {d.label}  — {d.reason}")

    if not counts:
        return
    if not cfg.gold_inventory_json.exists():
        typer.echo("\n(no gold inventory yet — run `vdocs serve-inventory` to see admitted counts)")
        return
    records = EnrichedInventory.model_validate_json(
        cfg.gold_inventory_json.read_text(encoding="utf-8")
    ).records
    s = fp.summarize_gate(records, load_gate_policy(cfg.registries))
    typer.echo("\nAgainst the current gold inventory:")
    typer.echo(f"  genuine in-scope documents:   {s.genuine}")
    typer.echo(f"  ADMITTED (fetch targets):     {s.admitted}")
    typer.echo(f"  excluded — app out of scope:  {s.excluded_app_scope}")
    typer.echo(f"  excluded — doc-type omitted:  {s.excluded_doctype}")
    typer.echo("  admitted by doc-type:")
    for code, n in sorted(s.admitted_by_doctype.items(), key=lambda kv: (-kv[1], kv[0])):
        typer.echo(f"    {code or '(untyped)':<10} {n}")


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
    """Assemble corpus-manifest.json + discovery.json + the AI corpus card (agent front door)."""
    _drive(only="manifest", force=force)


@app.command()
@_guarded
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


def _emit_doctor(cfg: Settings) -> str:
    """Run the doctor checks against index.db, render the report, and return the verdict (shared by
    the ``doctor`` command and ``build``). Returns ``"RED"`` if there is no index.db to check."""
    from vdocs.kernel import db
    from vdocs.server import doctor as doc
    from vdocs.stages.fetch.policy import load_gate_config

    if not cfg.index_db.exists():
        typer.echo("no index.db to check — run `vdocs build` (or vdocs index, relate, manifest).")
        return "RED"
    kept = frozenset(r.code for r in load_gate_config(cfg.registries).kept)
    policy = doc.load_doctor_policy(cfg.registries)
    from vdocs.kernel import read_contract as rc

    spec = rc.load(rc.contract_path(base=cfg.read_contract_dir))
    conn = db.connect(cfg.index_db, read_only=True)
    try:
        report = doc.diagnose(conn, kept_doctypes=kept, policy=policy, read_spec=spec)
    finally:
        conn.close()
    doc.render_report(report, typer.echo)
    return report.verdict()


@app.command()
@_guarded
def doctor() -> None:
    """Check the gold corpus and emit GOLD LIBRARY: GREEN|RED — the shipped soundness gate (B1–B5).

    Reads index.db and reports each check as PASS / BY-DESIGN / WARN / FAIL: persona + identity
    coverage (against doctor-policy.yaml floors), anchor integrity, gate fidelity (only Tier-A
    doc-types in gold), the FTS search surface, and the entity graph. By-design gaps (e.g. the
    fallback-profile function_category) are separated from real defects. Exits 1 on RED.
    """
    cfg = Settings()
    if _emit_doctor(cfg) == "RED":
        raise typer.Exit(code=1)


@app.command()
def validate(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Sidecar-verification HARD GATE: typed absence (capture.yaml) + count reconciliation +
    refs.yaml ref-resolution. Fails loudly on a silent detector miss, an implausible corpus
    aggregate, or a severed cross-ref; writes reports/validation/verification.json (§8)."""
    _drive(only="validate", force=force)


@app.command()
@_guarded
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
    strict: bool = typer.Option(False, "--strict", help="exit non-zero (10) if any stage WARNs"),
) -> None:
    """Run the pipeline DAG (optionally a slice) through the generic orchestrator."""
    _drive(
        from_stage=from_stage,
        to_stage=to_stage,
        only=only,
        force=force,
        verify=verify,
        strict=strict,
    )


def _other_vdocs_running() -> bool:
    """Honor the shared-lake rule: is another vdocs pipeline process active? (Two orchestrators race
    state.db/index.db/CAS.) Heuristic over ``pgrep``; treats a missing/erroring pgrep as 'no'."""
    import os
    import subprocess

    try:
        out = subprocess.run(
            ["pgrep", "-af", "vdocs"], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    mypid = str(os.getpid())
    verbs = (" build", " run", " fetch", " crawl", " catalog", " serve-inventory")
    for line in out.splitlines():
        pid, _, rest = line.partition(" ")
        if pid != mypid and any(v in f" {rest}" for v in verbs):
            return True
    return False


def _wipe_lake(cfg: Settings) -> None:
    """The from-scratch wipe (F9/F11): delete every DERIVED artifact so the build is truly de-novo.

    Removes documents/ (incl. the bronze CAS), index.db, **state.db** (so fetch re-downloads — the
    idempotent resume must not skip-present bytes that were wiped), reports/, the inventory
    silver+gold, and stray lake clutter (select-*.txt, leftover vectors.db tmp). KEEPS
    inventory/bronze/catalog.raw.json (so --skip-crawl reuses it) and the repo registries."""
    import shutil

    for tree in (cfg.documents, cfg.reports, cfg.inventory_silver, cfg.inventory_gold):
        if tree.exists():
            shutil.rmtree(tree)
    for pattern in ("index.db*", "state.db*", "vectors.db*", ".vectors.db.tmp*", "select-*.txt"):
        for f in cfg.lake.glob(pattern):
            f.unlink()


@app.command()
def build(
    fresh: bool = typer.Option(
        False, "--fresh", help="wipe derived lake data and rebuild de-novo (destructive)"
    ),
    yes: bool = typer.Option(False, "--yes", help="confirm the destructive --fresh wipe"),
    skip_crawl: bool = typer.Option(
        False, "--skip-crawl", help="reuse the saved catalog.raw.json instead of re-crawling"
    ),
) -> None:
    """Guided from-scratch build: crawl → … → manifest → doctor, in one command with run messaging.

    The operator-facing "build the corpus" path — it sequences the whole pipeline (the descoped
    `embed` stage is gone, so it can't be pulled in), fetches every gate-admitted document, and ends
    with the GOLD LIBRARY: GREEN|RED verdict. `--fresh` wipes the derived lake first (requires
    `--yes`). Refuses to run while another vdocs process is active on the shared lake. Needs network
    (crawl + fetch); everything after fetch is offline.
    """
    from vdocs.stages.fetch.fetch_pure import Selection

    cfg = Settings()
    if _other_vdocs_running():
        typer.echo(
            "another vdocs pipeline process appears to be active on the shared lake — aborting "
            "(check reports/*.log; two orchestrators race state.db/index.db/CAS)."
        )
        raise typer.Exit(code=1)
    if fresh:
        if not yes:
            typer.echo(
                "--fresh will DELETE all derived data under "
                f"{cfg.lake} (documents/, index.db, state.db, reports/, inventory silver+gold). "
                "Re-run with `--fresh --yes` to confirm."
            )
            raise typer.Exit(code=1)
        _wipe_lake(cfg)
        typer.echo(
            f"wiped derived lake data under {cfg.lake} (registries + catalog.raw.json kept)."
        )

    cfg.lake.mkdir(parents=True, exist_ok=True)
    stages = build_stages()
    for stage in stages:
        if stage.name == "fetch":
            stage.selection = Selection(all_=True)  # type: ignore[attr-defined]
    # one orchestrator run, crawl→manifest (includes validate); force so a de-novo build re-runs.
    _drive(
        from_stage="catalog" if skip_crawl else "crawl",
        to_stage="manifest",
        force=True,
        stages=stages,
    )

    typer.echo("")
    if _emit_doctor(cfg) == "RED":
        raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
