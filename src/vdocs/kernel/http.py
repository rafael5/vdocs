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
        the crawl driver can skip a bad page with a WARN rather than aborting (§3.6)."""
        resp = self._request(url)
        page = Page(text=resp.text, url=str(resp.url), status_code=resp.status_code)
        self._sleep(self._delay)
        return page

    def get_bytes(self, url: str) -> bytes | None:
        """GET ``url`` as bytes; ``None`` on 404 (a missing format), raise on other errors."""
        resp = self._request(url, timeout=_BYTES_TIMEOUT)
        self._sleep(self._delay)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content

    def _request(self, url: str, *, timeout: float | None = None) -> httpx.Response:
        """GET with retry: exponential backoff on 5xx, escalating backoff on 429."""
        attempt = 0
        backoff_429 = 2.0
        while True:
            if timeout is None:
                resp = self._client.get(url)
            else:
                resp = self._client.get(url, timeout=timeout)
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
