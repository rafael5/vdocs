"""HTTP GET primitives — shared by `crawl` and `fetch` (§9.2 anti-duplication).

Two stages need network reads (crawl pulls HTML, fetch pulls binaries), so the client
lives here once rather than being re-implemented per stage. Stages take these as injected
callables, so the network is faked in tests and only these thin wrappers touch the wire.
"""

from __future__ import annotations

import httpx

_TEXT_TIMEOUT = 30.0
_BYTES_TIMEOUT = 120.0


def get_text(url: str) -> str:  # pragma: no cover - network I/O, faked in tests
    """Fetch a URL as text, following redirects; raise on non-2xx."""
    resp = httpx.get(url, follow_redirects=True, timeout=_TEXT_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def get_bytes(url: str) -> bytes | None:  # pragma: no cover - network I/O, faked in tests
    """Fetch a URL as bytes; return None on 404 (a missing format), raise on other errors."""
    resp = httpx.get(url, follow_redirects=True, timeout=_BYTES_TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content
