"""Hardened HTTP layer — shared by `crawl` and `fetch` (§9.2 anti-duplication, §3.1).

Both network stages (crawl pulls HTML, fetch pulls binaries) read through one configured
client so politeness/robustness lives here once. ``PoliteClient`` adds, over raw httpx:

  * a descriptive **User-Agent** (VA infra 403s the default client UA),
  * **retry with exponential backoff on 5xx** (500/502/503/504) and **429**,
  * followed redirects capped at ``max_redirects=5``, exposing the **final URL**,
  * a configurable **inter-request delay** for politeness on a ``.gov`` host.

The transport and the sleep function are injectable, so tests drive it through an
``httpx.MockTransport`` with sleeps recorded rather than slept — no network, no waiting.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from vdocs import __version__

USER_AGENT = f"vdocs/{__version__} (+github.com/rafael5/vdocs)"

_TEXT_TIMEOUT = 30.0
_BYTES_TIMEOUT = 120.0
_MAX_REDIRECTS = 5
_RETRY_TOTAL = 3
_BACKOFF_FACTOR = 2.0
_RETRY_STATUS = frozenset({500, 502, 503, 504})
_TOO_MANY_REQUESTS = 429
_DEFAULT_DELAY = 1.5

SleepFn = Callable[[float], None]


@dataclass(frozen=True)
class Page:
    """A fetched page: its text, the **final** URL after redirects, and the status code."""

    text: str
    url: str
    status_code: int


PageFetcher = Callable[[str], Page]


class PoliteClient:
    """A configured httpx client: descriptive UA, 5xx/429 retry+backoff, capped redirects,
    an inter-request delay, and the post-redirect final URL exposed on every page."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        delay: float = _DEFAULT_DELAY,
        sleep: SleepFn = time.sleep,
        user_agent: str = USER_AGENT,
        max_retries: int = _RETRY_TOTAL,
        backoff_factor: float = _BACKOFF_FACTOR,
    ) -> None:
        self._client = httpx.Client(
            transport=transport,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
            max_redirects=_MAX_REDIRECTS,
            timeout=_TEXT_TIMEOUT,
        )
        self._delay = delay
        self._sleep = sleep
        self._max_retries = max_retries
        self._backoff = backoff_factor

    def get_page(self, url: str) -> Page:
        """GET ``url`` as text. Returns the final URL + status even on a persistent 5xx, so
        the crawl driver can skip a bad page with a WARN rather than aborting (§3.6). A persistent
        transport error (after retries) yields a ``status_code=0`` empty page — the same skip
        signal, never an exception."""
        resp = self._request(url)
        if resp is None:
            page = Page(text="", url=url, status_code=0)
        else:
            page = Page(text=resp.text, url=str(resp.url), status_code=resp.status_code)
        self._sleep(self._delay)
        return page

    def get_bytes(self, url: str) -> bytes | None:
        """GET ``url`` as bytes, or ``None`` on **any** failure — a missing format (404), a
        persistent transport error, or a non-2xx status that survives the retry loop (a VA 500,
        a 403, …). ``None`` is the skippable-WARN sentinel the fetch driver records as a failed
        acquisition and moves past; per the module's "skip a bad page, never abort" rule one bad
        document can never raise out and kill the whole batch (§3.6)."""
        resp = self._request(url, timeout=_BYTES_TIMEOUT)
        self._sleep(self._delay)
        if resp is None or not resp.is_success:
            return None
        return resp.content

    def _request(self, url: str, *, timeout: float | None = None) -> httpx.Response | None:
        """GET with retry: exponential backoff on 5xx and on transport errors (connect/read
        timeouts, protocol errors), escalating backoff on 429. Returns the response, or ``None``
        when transport errors persist past ``max_retries`` — the drivers treat ``None`` as a
        skippable WARN, never an abort (the module's "skip a bad page, never abort" rule + §3.6)."""
        attempt = 0
        backoff_429 = 2.0
        while True:
            try:
                if timeout is None:
                    resp = self._client.get(url)
                else:
                    resp = self._client.get(url, timeout=timeout)
            except httpx.TransportError:
                if attempt >= self._max_retries:
                    return None
                self._sleep(self._backoff * (2.0**attempt))
                attempt += 1
                continue
            if attempt >= self._max_retries:
                return resp
            if resp.status_code == _TOO_MANY_REQUESTS:
                self._sleep(backoff_429)
                backoff_429 *= 2
                attempt += 1
                continue
            if resp.status_code in _RETRY_STATUS:
                self._sleep(self._backoff * (2.0**attempt))
                attempt += 1
                continue
            return resp


# --- module-level defaults (real network) used by stages that don't inject a client ---
# A lazily-built default client so importing this module never opens a connection.
_default: PoliteClient | None = None


def _client() -> PoliteClient:  # pragma: no cover - real network, faked in tests
    global _default
    if _default is None:
        _default = PoliteClient()
    return _default


def get_text(url: str) -> str:  # pragma: no cover - real network, faked in tests
    """Fetch a URL as text (default polite client)."""
    return _client().get_page(url).text


def get_bytes(url: str) -> bytes | None:  # pragma: no cover - real network, faked in tests
    """Fetch a URL as bytes; ``None`` on 404 (default polite client)."""
    return _client().get_bytes(url)
