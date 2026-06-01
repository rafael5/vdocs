"""The `fetch` stage driver — download documents into the content-addressed raw store (§8).

For each logical document (DOCX preferred) it tries the candidate URLs via an injected byte
fetcher, stores the bytes write-once in the CAS, and records ``raw/index.json`` (sha256 →
provenance). Idempotent: re-downloading identical bytes is a CAS no-op.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from vdocs.contracts.registry import CATALOG_ENRICHED, RAW_INDEX, RAW_TREE
from vdocs.kernel import http
from vdocs.kernel.cas import Cas, atomic_write
from vdocs.models.catalog import DriftStatus, EnrichedCatalog
from vdocs.models.stage import Idempotency, RunResult
from vdocs.orchestrator.stage import Stage, StageContext

ByteFetcher = Callable[[str], bytes | None]


class FetchStage(Stage):
    name = "fetch"
    description = "download catalog documents into the content-addressed bronze raw store"
    requires = [CATALOG_ENRICHED]
    produces = [RAW_TREE, RAW_INDEX]
    idempotency = Idempotency.SKIP_IF_UNCHANGED

    def __init__(self, fetch_bytes: ByteFetcher | None = None) -> None:
        self._get = fetch_bytes or http.get_bytes

    def run(self, ctx: StageContext, force: bool) -> RunResult:
        from vdocs.stages.fetch import fetch_pure as fp

        catalog = EnrichedCatalog.model_validate_json(
            ctx.cfg.catalog_enriched.read_text(encoding="utf-8")
        )
        live = [d for d in catalog.documents if d.drift_status is not DriftStatus.WITHDRAWN]
        targets = fp.select_fetch_targets(live)

        store = Cas(ctx.cfg.bronze_raw)
        index: dict[str, dict[str, str]] = {}
        fetched = failed = 0
        for doc in targets:
            data: bytes | None = None
            used_url = ""
            for url in fp.candidate_urls(doc.url):
                data = self._get(url)
                if data is not None:
                    used_url = url
                    break
            if data is None:
                failed += 1
                continue
            ext = fp.url_ext(used_url) or doc.file_ext.lstrip(".")
            sha = store.put(data, ext=ext)
            index[sha] = fp.index_entry(
                app_code=doc.app_code, title=doc.title, source_url=used_url, ext=ext
            )
            fetched += 1

        atomic_write(ctx.cfg.raw_index, json.dumps(index, indent=2).encode("utf-8"))
        return RunResult(counts={"targets": len(targets), "fetched": fetched, "failed": failed})
