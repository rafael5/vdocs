"""The vdocs CLI — one subcommand per stage + ``run`` (ADR-009, §7.5).

Every command drives stages through the identical orchestrator preflight→run→postflight
path — there is no second execution route (§7.1). A preflight FAIL surfaces as a non-zero
exit with the remediation hint (tenet #7).
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from pathlib import Path

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
from vdocs.stages.doctor.stage import DoctorStage
from vdocs.stages.enrich.stage import EnrichStage
from vdocs.stages.fetch.stage import FetchStage
from vdocs.stages.index.stage import IndexStage
from vdocs.stages.manifest.stage import ManifestStage
from vdocs.stages.merge.stage import MergeStage
from vdocs.stages.normalize.stage import NormalizeStage
from vdocs.stages.relate.stage import RelateStage
from vdocs.stages.resolve.stage import ResolveStage
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
        ResolveStage(),
        MergeStage(),
        ManifestStage(),
        ValidateStage(),
        DoctorStage(),
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
def crawl(
    accept_shrink: bool = typer.Option(
        False,
        "--accept-shrink",
        help="accept a crawl below the completeness floor (a genuinely smaller VDL) — "
        "it becomes the new baseline",
    ),
) -> None:
    """Crawl the VDL site into catalog.raw (network; FORCE_ONLY → always runs when invoked).

    A yield materially below the last good crawl fails and leaves the prior catalog in place
    (completeness floor, CRAWL_FLOOR_RATIO); --accept-shrink acknowledges a real shrink."""
    stages = build_stages()
    for stage in stages:
        if stage.name == "crawl":
            stage.accept_shrink = accept_shrink  # type: ignore[attr-defined]
    _drive(only="crawl", stages=stages, force=True)


@app.command(name="vdl-delta")
def vdl_delta_cmd(
    before: str = typer.Argument("", help="earlier snapshot name (default: second-newest)"),
    after: str = typer.Argument("", help="later snapshot name (default: newest)"),
) -> None:
    """What changed on the VDL between two preserved crawl snapshots (VO.3/VO.4a).

    Reads only inventory-bronze snapshots, so two consecutive crawls are comparable long after the
    fact without re-crawling. Applications are keyed on the VDL's own `appid`, so a rename reads as
    a rename rather than a departure plus an arrival. A corpus-wide lifecycle change is reported as
    SUSPECT-PARSER instead of as history — `app_status` is parsed from the application name's
    suffix, so that shape is a broken regex until proven otherwise.
    """
    from vdocs.models.catalog import Catalog
    from vdocs.stages.crawl.delta_pure import render_delta, vdl_delta
    from vdocs.stages.crawl.snapshot_pure import snapshot_order

    cfg = Settings()
    root = cfg.inventory_snapshots
    # a snapshot is a directory holding a catalog — not merely a directory. The hand-banked first
    # snapshot carries `bronze/`/`gold/` subdirectories, and treating those as snapshots would
    # pick one as "newest" and fail on the missing catalog.
    names = (
        sorted(
            (p.name for p in root.iterdir() if (p / "catalog.raw.json").is_file()),
            key=snapshot_order,
        )
        if root.exists()
        else []
    )
    if len(names) < 2:
        typer.echo(
            f"need two snapshots to compare, found {len(names)} in {root}. "
            "The timeline starts when snapshots start — each crawl keeps one."
        )
        raise typer.Exit(code=1)

    before, after = (before or names[-2]), (after or names[-1])
    for name in (before, after):
        if name not in names:
            typer.echo(f"no snapshot named {name!r}. Available: {', '.join(names)}")
            raise typer.Exit(code=1)

    def _read(name: str) -> Catalog:
        return Catalog.model_validate_json(
            (root / name / "catalog.raw.json").read_text(encoding="utf-8")
        )

    typer.echo(
        render_delta(vdl_delta(_read(before), _read(after)), before_name=before, after_name=after)
    )


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
def completeness(
    as_json: bool = typer.Option(False, "--json", help="machine-readable report on stdout"),
) -> None:
    """Rule on whether the library is **complete**, and show why not (VO.9).

    Complete does **not** mean "we hold everything". It means *nothing is missing for a reason we
    did not choose*: every genuine VistA document is either held, or carries an explicit reason
    from a closed vocabulary, and none is lost to an **implementation limitation**.

    That distinction is the point. Omitting release notes is a decision, recorded in a registry and
    reversible — it is compatible with completeness. A document absent because it is a PDF and the
    converter reads DOCX is a limitation wearing a decision's clothes, and it makes the corpus
    incomplete however the registries are set. Exits non-zero when anything is unreachable, so the
    claim can be checked rather than asserted.
    """
    import json

    from vdocs.models.catalog import EnrichedInventory
    from vdocs.stages.fetch.fetch_pure import sole_survivors
    from vdocs.stages.fetch.policy import load_gate_policy
    from vdocs.stages.serve_inventory.completeness_pure import completeness_report

    cfg = Settings()
    if not cfg.gold_inventory_json.exists():
        typer.echo("no gold inventory yet — run `vdocs serve-inventory` first.")
        raise typer.Exit(code=1)
    records = EnrichedInventory.model_validate_json(
        cfg.gold_inventory_json.read_text(encoding="utf-8")
    ).records
    policy = load_gate_policy(cfg.registries)
    report = completeness_report(records, policy, sole_survivors=sole_survivors(records, policy))

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "verdict": report.verdict,
                    "complete": report.complete,
                    "total": report.total,
                    "held": report.held,
                    "not_vista": report.not_vista,
                    "excluded_by_policy": report.excluded_by_policy,
                    "covered_by_other_format": report.covered_by_other_format,
                    "unreachable": report.unreachable,
                    "by_reason": report.by_reason,
                    "unreachable_by_reason": report.unreachable_by_reason,
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise typer.Exit(code=0 if report.complete else 1)

    typer.echo("=== vdocs library completeness ===")
    typer.echo(f"  inventory records:            {report.total}")
    typer.echo(f"  HELD (in or admitted to gold):{report.held:>7}")
    typer.echo(f"  outside the library (not VistA):{report.not_vista:>5}")
    typer.echo(f"  excluded by policy (a choice):{report.excluded_by_policy:>7}")
    typer.echo(f"  covered in another format:    {report.covered_by_other_format}")
    typer.echo(f"  UNREACHABLE (a real hole):    {report.unreachable}")
    typer.echo("\n  every exclusion, by recorded reason:")
    for reason, n in sorted(report.by_reason.items(), key=lambda kv: (-kv[1], kv[0])):
        typer.echo(f"    {reason:<40} {n}")
    if not report.complete:
        typer.echo("\n  unreachable — these are not decisions, they are limitations:")
        for reason, n in sorted(report.unreachable_by_reason.items()):
            typer.echo(f"    {reason:<40} {n}")
    typer.echo(f"\nVERDICT: {report.verdict}")
    raise typer.Exit(code=0 if report.complete else 1)


@app.command()
def gate(
    counts: bool = typer.Option(
        True, "--counts/--no-counts", help="also show admitted counts against the gold inventory"
    ),
) -> None:
    """Explain the corpus **admission gate** — what gets fetched into (and promoted to) gold.

    Prints the effective, assembled policy in plain terms (app-scope prefixes + denied statuses,
    the kept vs omitted doc-types, and the fail-safe for untyped docs) so an operator can see and
    change the gate without reading code. With a gold inventory present it also reports how the gate
    partitions it (admitted vs excluded, with a per-doc-type breakdown).
    See docs/reference/gate-reference.md.
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


@app.command(name="build-termbase")
@_guarded
def build_termbase(
    out_dir: str = typer.Option(
        "termbase", "--out-dir", "-o", help="directory to write the gate artifacts into"
    ),
) -> None:
    """Compile the curated registries into docs-as-code **quality-gate config** (Vale + typos).

    Single-sources the controlled vocabulary — ``product-names.yaml`` (abbr/full/match +
    Term-classification facets), ``typo-corrections.yaml`` (forbidden→preferred), and the glossary
    acronyms — into an ``accept.txt``, a typo ``substitution`` style (``VistA.yml``), a selective
    *casing* ``substitution`` style (``Casing.yml`` — enforces canonical capitalization only for
    terms that don't collide with English, SKL S1.3), and a ``typos`` extend-words snippet for a
    ``*-docs`` repo's gate (the VDL-modernization program; see
    docs/proposals/vdl-content-quality-and-ia-strategy.md §6/§9).
    A registry edit re-flows here on re-run
    (tenet #13) — the docs gate never hand-maintains its own copy of the vocabulary.
    """
    from pathlib import Path

    from vdocs.kernel import termbase

    cfg = Settings()
    # S3.1: project from the SKL Term catalog (knowledge.db) when present — else the registries
    # (equivalent by construction). One source, no hand-maintained parallel vocab (tenet #13).
    arts = termbase.termbase_artifacts(cfg.registries, knowledge_db=cfg.knowledge_db)
    src = "SKL (knowledge.db)" if cfg.knowledge_db.exists() else "registries"
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(arts.items()):
        (out / name).write_text(content, encoding="utf-8")
    n_terms = sum(1 for ln in arts["accept.txt"].splitlines() if ln and not ln.startswith("#"))
    typer.echo(f"wrote {len(arts)} termbase artifacts to {out}/ — {n_terms} terms (from {src}):")
    for name in sorted(arts):
        typer.echo(f"  {name}")


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
def resolve(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Build the Semantic Knowledge Layer (gold/knowledge.db): resolve the FileMan (DI) gold's
    entity/term/relationship nodes from the registries + the live-DD seed (SKL S2)."""
    _drive(only="resolve", force=force)


@app.command()
def merge(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Fold the SKL (knowledge.db) into index.db: reconcile entity ids, project the synonym catalog,
    and tag chunks with resolved entities (entity-keyed retrieval, SKL S3.3)."""
    _drive(only="merge", force=force)


@app.command()
def manifest(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Assemble corpus-manifest.json + discovery.json + the AI corpus card (agent front door)."""
    _drive(only="manifest", force=force)


@app.command()
@_guarded
def ask(
    query: str = typer.Argument(..., help="a natural-language question about VistA / the corpus"),
    k: int | None = typer.Option(
        None,
        "--k",
        "-k",
        help="how many ranked hits to return (default: 8 for the terminal, 15 for --json)",
    ),
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
    # RR.1: two callers, two defaults. `--json` is the agent front door and gets the measured wide
    # default (77.1% of correct answers visible vs 61.5% at the old 8); the terminal keeps the
    # short list, because for a person more results are reading work rather than free recall. An
    # explicit --k wins on either surface.
    if k is None:
        k = search.ASSISTANT_DEFAULT_K if json_out else search.HUMAN_DISPLAY_K
    hits = search.lexical_search(
        cfg.index_db, query, k=k, app=list(apps) or None, doc_type=list(doc_types) or None
    )
    if json_out:
        # the SAME envelope the MCP `search` tool returns (P6.3) — one shape, one rule, whichever
        # front door the agent came through
        typer.echo(json.dumps(search.search_envelope(hits), indent=2, ensure_ascii=False))
        return
    if not hits:
        # never "no matches in the gold corpus" — that is the sentence that licenses a false
        # "not documented", and it is exactly what the MCP surface is forbidden to say (R-11)
        typer.echo(search.NO_MATCH_WARNING)
        return
    for i, h in enumerate(hits, 1):
        typer.echo(f"{i}. [{h['score']}] {h['doc_title']} — §{h['section_title']}")
        typer.echo(f"   {h['uri']}")
        typer.echo(f"   {h['body_path']}")
        typer.echo(f"   {h['snippet']}")


@app.command("serve-mcp")
@_guarded
def serve_mcp() -> None:
    """Serve the gold corpus over MCP stdio — the machine front door (§14, lexical slice).

    Tools: search (the `ask` engine, pre-cited hits) / lookup (doc | section | entity) /
    query (read-only SQL over index.db) / orientation (pins + surface + citation contract).
    Aligned with vista-meta's MCP server, the peer front door for measured facts.
    """
    import sys

    from vdocs.server import mcp

    cfg = Settings()
    if not cfg.index_db.exists():
        typer.echo("no index.db yet — run: vdocs index (then relate, manifest)")
        raise typer.Exit(code=1)
    handler = mcp.Handler(cfg.index_db)
    for out in mcp.serve_lines(handler, sys.stdin):
        print(out, flush=True)  # noqa: T201 — the MCP transport itself, not operator chatter


def _emit_doctor(cfg: Settings) -> str:
    """Render the written ``reports/doctor/doctor.json`` and return its verdict.

    The diagnosis itself belongs to the ``doctor`` stage (P2.1) — this only *renders* the gate's
    record, so there is exactly one diagnosis path (§7.1). ``"RED"`` when no report exists."""
    import json

    from vdocs.server import doctor as doc
    from vdocs.stages.doctor import doctor_pure as dp

    if not cfg.doctor_report.is_file():
        typer.echo("no doctor report — run: vdocs doctor")
        return "RED"
    payload = json.loads(cfg.doctor_report.read_text(encoding="utf-8"))
    doc.render_report(dp.report_from_payload(payload), typer.echo)
    return str(payload.get("verdict", "RED"))


def _run_doctor(cfg: Settings) -> str:
    """Run the ``doctor`` STAGE (a fresh diagnosis), then render its report; returns the verdict.

    Used by the ``doctor`` command and the ``release`` gate — both need a verdict about the
    database *now*, never a possibly-stale report on disk. Anything that prevents the stage from
    completing (a missing index.db, a preflight FAIL, a RED verdict) yields ``"RED"``: a gate that
    could not certify the corpus must not report GREEN (degrade loud, never fail open)."""
    if not cfg.index_db.exists():
        typer.echo("no index.db to check — run `vdocs build` (or vdocs index, relate, manifest).")
        return "RED"
    completed = True
    try:
        _drive(only="doctor", force=True)
    except typer.Exit:
        completed = False  # RED (or an unusable input) — rendered below for triage
    verdict = _emit_doctor(cfg) if cfg.doctor_report.is_file() else "RED"
    return verdict if completed else "RED"


@app.command("entity-quality")
@_guarded
def entity_quality_cmd(
    vista_meta: Path = typer.Option(
        ...,
        "--vista-meta",
        help="Path to an unpacked vista-meta data-v1 tree (the vocabulary peer)",
    ),
) -> None:
    """Measure entity join rates against the vista-meta data-v1 vocabularies (D2.5).

    Floors are numbers: every floor-verified type in registries/entity-quality.yaml must
    measure rate >= its declared floor against the peer vocabulary named there; an entity
    type shipping without a declaration is UNDECLARED. Exits 1 on FAIL — the release gate.
    """
    from vdocs.kernel import db
    from vdocs.kernel.entity_quality import load_entity_quality
    from vdocs.server import entity_quality_gate as eq

    cfg = Settings()
    quality = load_entity_quality(cfg.registries)
    conn = db.connect(cfg.index_db, read_only=True)
    try:
        by_type: dict[str, list[str]] = {}
        for etype, name in conn.execute("SELECT type, canonical_name FROM entities"):
            by_type.setdefault(etype, []).append(name)
    finally:
        conn.close()
    vocabs = {
        name: eq.load_vocab(vista_meta, pol.vocabulary)
        for name, pol in quality.types.items()
        if pol.status == "floor-verified"
    }
    rows = eq.measure(by_type, vocabs, quality)
    eq.render(rows, typer.echo)
    out = eq.verdict(rows)
    peer = quality.peer_vocabulary.get("content_hash", "?")[:12]
    typer.echo(f"ENTITY QUALITY: {out}  (peer {peer}…)")
    if out == "FAIL":
        raise typer.Exit(code=1)


@app.command()
@_guarded
def release(
    vista_meta: Path = typer.Option(
        ...,
        "--vista-meta",
        help="Path to an unpacked vista-meta data-v1 tree (the entity-quality peer)",
    ),
    publish: bool = typer.Option(False, "--publish", help="create the GitHub Release"),
) -> None:
    """Assemble (and optionally publish) the vdocs data-v1 release bundle (Track D3).

    Preflight: lake quiescent (no live `vdocs run`, corpus_content_hash stable across
    the assembly window), repo tree clean with HEAD == upstream (source_commit must
    not lie), doctor GREEN, entity-quality floors PASS. Assets land in DATA_DIR/dist/.
    """
    import hashlib
    import json
    import subprocess

    from vdocs.kernel import db
    from vdocs.kernel.entity_quality import load_entity_quality
    from vdocs.server import entity_quality_gate as eq
    from vdocs.server import release as rel

    cfg = Settings()
    repo_root = Path(__file__).resolve().parents[3]

    def _git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo_root, capture_output=True, text=True, check=True
        ).stdout.strip()

    def _meta_hash() -> str:
        conn = db.connect(cfg.index_db, read_only=True)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='corpus_content_hash'").fetchone()
            return str(row[0])
        finally:
            conn.close()

    # F15: lake quiescence — a live orchestrator would race the database being released
    live = subprocess.run(
        ["pgrep", "-f", "vdocs run"], capture_output=True, text=True
    ).stdout.strip()
    if live:
        typer.echo(f"ERROR: live `vdocs run` (pid {live.splitlines()[0]}) — lake not quiescent")
        raise typer.Exit(code=1)
    hash_before = _meta_hash()

    # F16: source_commit must not lie. Tracked files only: untracked files are not
    # part of the committed code, but surface them so a forgotten new module is seen.
    if _git("status", "--porcelain", "--untracked-files=no"):
        typer.echo("ERROR: repo tree not clean (tracked changes) — commit or stash first")
        raise typer.Exit(code=1)
    untracked = _git("status", "--porcelain", "--untracked-files=normal")
    if untracked:
        typer.echo(f"WARN: untracked files present (not in source_commit):\n{untracked}")
    head = _git("rev-parse", "HEAD")
    if head != _git("rev-parse", "@{upstream}"):
        typer.echo("ERROR: HEAD != upstream — push first")
        raise typer.Exit(code=1)

    # release gates: doctor GREEN + entity-quality floors PASS
    if _run_doctor(cfg) == "RED":
        typer.echo("ERROR: doctor RED — not releasable")
        raise typer.Exit(code=1)
    quality = load_entity_quality(cfg.registries)
    conn = db.connect(cfg.index_db, read_only=True)
    try:
        by_type: dict[str, list[str]] = {}
        for etype, name in conn.execute("SELECT type, canonical_name FROM entities"):
            by_type.setdefault(etype, []).append(name)
    finally:
        conn.close()
    vocabs = {
        n: eq.load_vocab(vista_meta, pol.vocabulary)
        for n, pol in quality.types.items()
        if pol.status == "floor-verified"
    }
    rows = eq.measure(by_type, vocabs, quality)
    eq.render(rows, typer.echo)
    if eq.verdict(rows) == "FAIL":
        typer.echo("ERROR: entity quality below declared floors — not releasable")
        raise typer.Exit(code=1)

    # assemble
    dist = cfg.lake / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    shipped_db = dist / "index.db"
    rel.strip_staged(cfg.index_db, shipped_db)
    contract = json.loads(cfg.contract_manifest.read_text(encoding="utf-8"))
    flat = {
        "index.db": shipped_db,
        **{f: cfg.gold / f for f in rel._GOLD_FILES if (cfg.gold / f).is_file()},
    }
    files = {
        name: {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size,
        }
        for name, p in sorted(flat.items())
    }
    tree = {
        str(p.relative_to(cfg.gold)): p.read_bytes()
        for d in rel._GOLD_DIRS
        for p in sorted((cfg.gold / d).rglob("*"))
        if p.is_file()
    }
    manifest = rel.release_manifest(
        contract,
        source_commit=head,
        files=files,
        consolidated={"files": len(tree), "tree_sha256": rel.tree_hash(tree)},
    )
    bundle_sha = rel.write_bundle(
        dist / rel.BUNDLE_NAME, index_db=shipped_db, gold_dir=cfg.gold, manifest=manifest
    )
    standalone = rel.standalone_manifest(manifest, bundle_sha)
    (dist / rel.STANDALONE_NAME).write_text(
        json.dumps(standalone, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (dist / rel.SUMS_NAME).write_text(
        rel.sha256sums([dist / rel.BUNDLE_NAME, dist / rel.STANDALONE_NAME]),
        encoding="utf-8",
    )

    # F15: the assembly window must not have raced a mutation
    if _meta_hash() != hash_before:
        typer.echo("ERROR: corpus_content_hash moved during assembly — rerun")
        raise typer.Exit(code=1)

    for n in (rel.BUNDLE_NAME, rel.STANDALONE_NAME, rel.SUMS_NAME):
        typer.echo(f"dist/{n}: {(dist / n).stat().st_size} bytes")
    typer.echo(f"bundle_sha256: {bundle_sha}")
    typer.echo(f"corpus_content_hash: {contract['corpus_content_hash']}")

    if publish:
        # `gh release create` fails on an existing tag (it stranded the
        # 2026-07-04 re-cut) — probe first, then upload --clobber + edit.
        tag_exists = (
            subprocess.run(
                ["gh", "release", "view", rel.TAG],
                cwd=repo_root,
                capture_output=True,
            ).returncode
            == 0
        )
        notes = rel.release_notes(contract, bundle_sha)
        for cmd in rel.publish_commands(tag_exists, dist, notes):
            subprocess.run(cmd, cwd=repo_root, check=True)
        record = repo_root / "docs" / "releases" / rel.STANDALONE_NAME
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(standalone, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        typer.echo(
            f"published {rel.TAG} ({'assets replaced' if tag_exists else 'release created'}); "
            f"in-repo record at {record.relative_to(repo_root)}"
        )


@app.command()
@_guarded
def doctor() -> None:
    """Check the gold corpus and emit GOLD LIBRARY: GREEN|RED — the shipped soundness gate (B1–B5).

    Reads index.db and reports each check as PASS / BY-DESIGN / WARN / FAIL: persona + identity
    coverage (against doctor-policy.yaml floors), anchor integrity, gate fidelity (only Tier-A
    doc-types in gold), the FTS search surface, and the entity graph. By-design gaps (e.g. the
    fallback-profile function_category) are separated from real defects. Exits 1 on RED.

    A thin alias for the terminal ``doctor`` DAG stage (P2.1) — same diagnosis, same
    ``reports/doctor/doctor.json``, whether it runs here or at the end of ``vdocs run``.
    """
    cfg = Settings()
    if _run_doctor(cfg) == "RED":
        raise typer.Exit(code=1)


_VDL_URL = "https://www.va.gov/vdl/"


def _dir_writable(path) -> bool:  # type: ignore[no-untyped-def]
    """Whether the lake dir can be created + written (ensure it, write a temp file, clean up)."""
    import tempfile

    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path):
            return True
    except OSError:
        return False


def _vdl_reachable(url: str = _VDL_URL, timeout: float = 5.0) -> bool:  # pragma: no cover - net I/O
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:
        return False


@app.command()
@_guarded
def preflight() -> None:
    """Check the environment is ready to run the pipeline → PREFLIGHT: GO|NO-GO (exit 1 on NO-GO).

    Verifies what strands a run *before* stage 1: the converter binaries (pandoc, + docling if a doc
    is routed to it), a writable $DATA_DIR, free disk, and VDL reachability (crawl/fetch only —
    post-fetch runs offline, so that's a WARN). Each is OK / WARN / FAIL with a fix. Run it before
    `vdocs build`."""
    import shutil

    from vdocs.server import preflight as pf
    from vdocs.stages.convert.stage import _converter_available, _load_converter_routing

    cfg = Settings()
    routing = _load_converter_routing(
        cfg.registries / "converter-routing" / "converter-routing.yaml"
    )
    checks = pf.converter_checks(
        need_pandoc=True, need_docling=bool(routing), available=_converter_available
    )
    checks.append(pf.data_dir_check(_dir_writable(cfg.lake), str(cfg.lake)))
    probe = cfg.lake if cfg.lake.exists() else cfg.lake.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError:
        free = pf.MIN_FREE_BYTES  # can't probe → don't WARN spuriously
    checks.append(pf.disk_check(free))
    checks.append(pf.network_check(_vdl_reachable(), _VDL_URL))
    if pf.render(checks, typer.echo) == "NO-GO":
        raise typer.Exit(code=1)


@app.command(name="publish-rich-assets")
@_guarded
def publish_rich_assets() -> None:
    """Build the rich-publication subset image bundle (rich-publication proposal §3/§7).

    Collects the *union* of the curated docs' (``registries/rich-publication.yaml``) referenced
    figures into ``$DATA_DIR/rich-assets/`` — a flat, content-addressed bundle that rides alongside
    ``index.db`` (which stays text-only). vdocs-web serves these via ``GET /api/asset/{sha}``.
    Reports any listed doc with no gold body and any referenced figure that didn't resolve."""
    from vdocs.server import rich_assets

    cfg = Settings()
    subset = rich_assets.load_subset(cfg.registries)
    if not subset:
        typer.echo("no curated subset — populate registries/rich-publication.yaml (key: rich)")
        raise typer.Exit(code=1)
    plan = rich_assets.build_bundle(cfg, subset=subset)
    for d in plan.docs:
        if not d.present:
            typer.echo(f"  ! {d.doc_key}: no gold body (skipped) — check the registry entry")
        elif d.missing:
            typer.echo(f"  ~ {d.doc_key}: {d.image_count} figures, {d.missing} unresolved ref(s)")
    mb = plan.total_bytes / 1_048_576
    typer.echo(
        f"rich-assets bundle: {len(plan.assets)} figures, {mb:.1f} MB "
        f"from {sum(d.present for d in plan.docs)}/{len(plan.docs)} docs → {cfg.rich_assets}"
    )


@app.command(name="publish-rich-tables")
@_guarded
def publish_rich_tables() -> None:
    """Build the rich-reading table distribution (tables proposal P3).

    Copies every gold bundle's extracted ``tables/*.csv`` sidecars into ``$DATA_DIR/rich-tables/``,
    structure-preserving (``<app>/<slug>/tables/…``) so it rides alongside ``index.db``. The
    whole-corpus set is small (~10 MB), so it is NOT curated — every doc's tables ship. vdocs-web
    serves these via ``GET /api/table`` on a downloaded-only install (no co-located gold tree)."""
    from vdocs.server import rich_tables

    cfg = Settings()
    plan = rich_tables.build_tables_bundle(cfg)
    mb = plan.total_bytes / 1_048_576
    typer.echo(
        f"rich-tables distribution: {len(plan.tables)} CSVs, {mb:.1f} MB "
        f"from {plan.doc_count} docs → {cfg.rich_tables}"
    )


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
    idempotent resume must not skip-present bytes that were wiped), the derived report trees, the
    inventory silver+gold, and stray lake clutter (select-*.txt, leftover vectors.db tmp). KEEPS
    inventory/bronze/catalog.raw.json (so --skip-crawl reuses it) and the repo registries.

    R‑14: it also keeps **``reports/validation/``**. That report is validate's cross-run count
    baseline — *evidence*, not derived state — and wiping it disarms the §5.2 drop detection on
    exactly the run most likely to lose documents. Same argument that already spares
    catalog.raw.json."""
    import shutil

    for tree in (cfg.documents, cfg.inventory_silver, cfg.inventory_gold):
        if tree.exists():
            shutil.rmtree(tree)
    if cfg.reports.is_dir():
        for child in cfg.reports.iterdir():
            if child == cfg.validation_report.parent:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
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
    # One orchestrator run, crawl→doctor (includes validate and, since P2.1, the terminal
    # soundness gate — the bound must reach `doctor` or the guided build stops short of it);
    # force so a de-novo build re-runs.
    code = 0
    try:
        _drive(
            from_stage="catalog" if skip_crawl else "crawl",
            to_stage="doctor",
            force=True,
            stages=stages,
        )
    except typer.Exit as exc:
        code = exc.exit_code or 1

    # Render the gate's report even when the run stopped on it — the check table IS the operator's
    # triage surface, and it must not be swallowed by the non-zero exit.
    typer.echo("")
    if cfg.doctor_report.is_file():
        _emit_doctor(cfg)
    if code:
        raise typer.Exit(code=code)


if __name__ == "__main__":  # pragma: no cover
    app()
