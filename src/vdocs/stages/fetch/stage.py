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
from vdocs.models.catalog import EnrichedInventory
from vdocs.models.stage import Acquisition, Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext
from vdocs.stages.fetch.fetch_pure import Selection

ByteFetcher = Callable[[str], bytes | None]


class FetchStage(Stage):
    name = "fetch"
    description = "download selected documents into the content-addressed bronze raw store"
    # Requires the GOLD INVENTORY — serve-inventory's blessed `ok` is the fetch gate (§8):
    # the generic preflight refuses to run until that gate is green.
    requires = [GOLD_INVENTORY]
    produces = [RAW_TREE, RAW_INDEX]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def __init__(
        self, fetch_bytes: ByteFetcher | None = None, selection: Selection | None = None
    ) -> None:
        self._get = fetch_bytes or http.get_bytes
        # The §5.6 selection surface. Default = empty ⇒ select nothing (no blind download); the
        # CLI sets it from the operator's flags. Public + mutable so the driver can inject it.
        self.selection = selection or Selection()

    def extra_input_fps(self, ctx: StageContext) -> dict[str, str]:
        # the resolved selection participates in SKIP_IF_UNCHANGED (§5.6/§7.3)
        return {"selection": self.selection.fingerprint()}

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.fetch import fetch_pure as fp

        inventory = EnrichedInventory.model_validate_json(
            ctx.cfg.gold_inventory_json.read_text(encoding="utf-8")
        )
        targets = fp.select_fetch_targets(inventory.records, self.selection)

        store = Cas(ctx.cfg.bronze_raw)
        index: dict[str, dict[str, str]] = {}
        fetched = failed = 0
        now = ctx.clock()
        for doc in targets:
            doc_id = f"{doc.app_name_abbrev}:{doc.doc_slug}"
            url = doc.doc_url  # the DOCX URL — selection guarantees a DOCX target (§1)
            data = self._get(url)
            if data is None:
                failed += 1
                ctx.state.record_acquisition(
                    Acquisition(
                        doc_id=doc_id,
                        source_url=url,
                        status="failed",
                        attempts=1,
                        first_attempt_at=now,
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
                    doc_id=doc_id,
                    source_url=url,
                    status="fetched",
                    sha256=sha,
                    bytes=len(data),
                    attempts=1,
                    first_attempt_at=now,
                    last_attempt_at=now,
                    fetched_at=now,
                    tool_ver=ctx.cfg.tool_ver,
                )
            )
            fetched += 1

        atomic_write(ctx.cfg.raw_index, json.dumps(index, indent=2).encode("utf-8"))
        return RunResult(counts={"targets": len(targets), "fetched": fetched, "failed": failed})
