"""The `fetch` stage driver — download documents into the content-addressed raw store (§8).

For each selected logical document (its DOCX representation, §1 — the pipeline is DOCX-only) it
downloads the bytes via an injected byte fetcher, stores them write-once in the CAS, and records
``raw/index.json`` (sha256 → provenance). Idempotent: re-downloading identical bytes is a CAS no-op.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from vdocs.contracts.registry import GOLD_INVENTORY, RAW_INDEX, RAW_TREE
from vdocs.kernel import http
from vdocs.kernel.cas import Cas, atomic_write
from vdocs.kernel.ids import doc_id
from vdocs.models.catalog import EnrichedInventory
from vdocs.models.stage import Acquisition, Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.fetch.fetch_pure import MAX_FETCH_ATTEMPTS, Selection

ByteFetcher = Callable[[str], bytes | None]


def _url_list(urls: list[str], sample: int = 8) -> str:
    shown = ", ".join(urls[:sample])
    return shown + (f" (+{len(urls) - sample} more)" if len(urls) > sample else "")


def _fetch_warnings(
    failed: int, failed_urls: list[str], permanent: int, permanent_urls: list[str]
) -> list[str]:
    """Human-readable WARN lines for the run summary (F3): permanently-unavailable docs (give up,
    here is the list) and transient failures (re-run to retry). Empty when every fetch succeeded."""
    warnings: list[str] = []
    if permanent:
        warnings.append(
            f"{permanent} document(s) permanently unavailable after {MAX_FETCH_ATTEMPTS} attempts "
            f"(no DOCX upstream): {_url_list(permanent_urls)}"
        )
    if failed:
        warnings.append(
            f"{failed} document(s) failed this run (transient — re-run "
            f"`vdocs fetch --force` to retry): {_url_list(failed_urls)}"
        )
    return warnings


class FetchStage(Stage):
    name = "fetch"
    description = "download selected documents into the content-addressed bronze raw store"
    # Requires the GOLD INVENTORY — serve-inventory's blessed `ok` is the fetch gate (§8):
    # the generic preflight refuses to run until that gate is green.
    requires = [GOLD_INVENTORY]
    produces = [RAW_TREE, RAW_INDEX]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def __init__(
        self,
        fetch_bytes: ByteFetcher | None = None,
        selection: Selection | None = None,
        refetch: bool = False,
    ) -> None:
        self._get = fetch_bytes or http.get_bytes
        # The §5.6 selection surface. Default = empty ⇒ select nothing (no blind download); the
        # CLI sets it from the operator's flags. Public + mutable so the driver can inject it.
        self.selection = selection or Selection()
        # Idempotent resume (F2/F9): by default already-fetched docs are CAS hits we skip and only
        # transient failures are re-attempted; `--refetch` forces a re-GET of everything. Public +
        # mutable so the CLI driver can set it alongside the selection.
        self.refetch = refetch

    def extra_input_fps(self, ctx: StageContext) -> dict[str, str]:
        # the resolved selection AND the admission gate participate in SKIP_IF_UNCHANGED
        # (§5.6/§7.3): editing scope-policy/doctype-policy re-runs fetch.
        from vdocs.stages.fetch.policy import load_gate_policy

        return {
            "selection": self.selection.fingerprint(),
            "gate_policy": load_gate_policy(ctx.cfg.registries).fingerprint(),
        }

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.fetch import fetch_pure as fp
        from vdocs.stages.fetch.policy import load_gate_policy

        inventory = EnrichedInventory.model_validate_json(
            ctx.cfg.gold_inventory_json.read_text(encoding="utf-8")
        )
        # The always-on admission gate (app scope + doc-type policy): out-of-scope apps and
        # omitted doc-types never enter the corpus, regardless of the operator's selection.
        policy = load_gate_policy(ctx.cfg.registries)
        targets = fp.select_fetch_targets(inventory.records, self.selection, policy)

        store = Cas(ctx.cfg.bronze_raw)
        # Merge into the existing index so a selective re-fetch never drops previously-fetched docs
        # (R1): this run's entries are unioned over the prior index (new keys added, re-fetched
        # keys refreshed), never an overwrite that would strand docs `convert` then skips.
        index: dict[str, dict[str, str]] = {}
        if ctx.cfg.raw_index.exists():
            index = json.loads(ctx.cfg.raw_index.read_text(encoding="utf-8"))
        fetched = skipped = failed = permanent = 0
        failed_urls: list[str] = []
        permanent_urls: list[str] = []
        now = ctx.clock()
        for i, doc in enumerate(targets, 1):
            did = doc_id(doc)
            url = doc.doc_url  # the DOCX URL — selection guarantees a DOCX target (§1)
            prior = ctx.state.get_acquisition(did)
            # Idempotent resume (F2/F9): don't re-GET a doc already in the CAS or one we've given
            # up on; only (re)fetch never-attempted + transiently-failed targets, unless --refetch.
            action = fp.decide_fetch_action(prior, refetch=self.refetch)
            if action is fp.FetchAction.SKIP_PRESENT:
                skipped += 1
                continue
            if action is fp.FetchAction.SKIP_PERMANENT:
                permanent += 1
                permanent_urls.append(url)
                continue
            # Accrue attempts across re-runs and preserve the original first_attempt_at (§5.5):
            # a retry re-fetch increments the count, it doesn't reset it.
            attempts = (prior.attempts if prior else 0) + 1
            first_at = prior.first_attempt_at if (prior and prior.first_attempt_at) else now
            data = self._get(url)
            if i % 25 == 0 or i == len(targets):
                ctx.progress(f"{i}/{len(targets)} processed")
            if data is None:
                # Classify by cross-run attempt count (F3): give up after MAX_FETCH_ATTEMPTS so a
                # re-run loop terminates instead of re-GETting a permanently-broken URL forever.
                if attempts >= fp.MAX_FETCH_ATTEMPTS:
                    status, permanent, bucket = "permanent_missing", permanent + 1, permanent_urls
                else:
                    status, failed, bucket = "failed", failed + 1, failed_urls
                bucket.append(url)
                ctx.state.record_acquisition(
                    Acquisition(
                        doc_id=did,
                        source_url=url,
                        status=status,  # type: ignore[arg-type]
                        attempts=attempts,
                        first_attempt_at=first_at,
                        last_attempt_at=now,
                        error="docx unavailable",
                        tool_ver=ctx.cfg.tool_ver,
                    )
                )
                continue
            ext = fp.url_ext(url) or doc.doc_format
            sha = store.put(data, ext=ext)
            index[sha] = fp.index_entry(
                app_code=doc.app_name_abbrev,
                doc_slug=doc.doc_slug,
                title=doc.doc_title,
                source_url=url,
                ext=ext,
            )
            ctx.state.record_acquisition(
                Acquisition(
                    doc_id=did,
                    source_url=url,
                    status="fetched",
                    sha256=sha,
                    bytes=len(data),
                    attempts=attempts,
                    first_attempt_at=first_at,
                    last_attempt_at=now,
                    fetched_at=now,
                    tool_ver=ctx.cfg.tool_ver,
                )
            )
            fetched += 1

        atomic_write(ctx.cfg.raw_index, json.dumps(index, indent=2).encode("utf-8"))
        return RunResult(
            counts={
                "targets": len(targets),
                "fetched": fetched,
                "skipped": skipped,
                "failed": failed,
                "permanent_missing": permanent,
            },
            warnings=_fetch_warnings(failed, failed_urls, permanent, permanent_urls),
        )
