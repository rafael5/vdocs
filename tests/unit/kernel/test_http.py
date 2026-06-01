"""Unit tests for kernel/http PoliteClient — the hardened crawl/fetch HTTP layer (A1, §3.1).

No network: every test drives the client through an ``httpx.MockTransport`` whose handler
returns canned responses, so we assert the User-Agent, retry/backoff, redirect handling,
final-URL exposure, and inter-request delay deterministically.
"""

from __future__ import annotations

import httpx
import pytest

from vdocs.kernel import http


def _client(handler, **kw):
    """A PoliteClient wired to a MockTransport handler, with sleeps recorded not slept."""
    slept: list[float] = []
    kw.setdefault("sleep", slept.append)
    client = http.PoliteClient(transport=httpx.MockTransport(handler), **kw)
    return client, slept


def test_sends_descriptive_user_agent():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("user-agent", ""))
        return httpx.Response(200, text="ok")

    client, _ = _client(handler)
    client.get_page("https://vdl.test/")
    assert seen[0].startswith("vdocs/")
    assert "github.com/rafael5/vdocs" in seen[0]


def test_custom_user_agent_override():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("user-agent", ""))
        return httpx.Response(200, text="ok")

    client, _ = _client(handler, user_agent="vdocs/9.9 (+example)")
    client.get_page("https://vdl.test/")
    assert seen == ["vdocs/9.9 (+example)"]


def test_get_page_returns_final_url_after_redirect():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://vdl.test/vdl/final"})
        return httpx.Response(200, text="<html>done</html>")

    client, _ = _client(handler)
    page = client.get_page("https://vdl.test/start")
    assert page.text == "<html>done</html>"
    assert page.url == "https://vdl.test/vdl/final"
    assert page.status_code == 200


def test_retries_on_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, text="ok")

    client, slept = _client(handler)
    page = client.get_page("https://vdl.test/")
    assert page.status_code == 200
    assert calls["n"] == 3  # two retries
    # two backoff sleeps (2.0, 4.0) preceding the final per-request delay
    assert slept[:2] == [2.0, 4.0]


def test_gives_up_after_max_retries_returns_last_5xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="still busy")

    client, _ = _client(handler, max_retries=2)
    # get_page does NOT raise on a persistent 5xx — it returns the response so the crawl
    # driver can skip the page with a WARN (spec §3.6).
    page = client.get_page("https://vdl.test/")
    assert page.status_code == 503


def test_backs_off_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429 if calls["n"] == 1 else 200, text="x")

    client, slept = _client(handler)
    page = client.get_page("https://vdl.test/")
    assert page.status_code == 200
    assert slept[0] == 2.0  # first 429 backoff is 2s


def test_get_page_sleeps_configured_delay_between_requests():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    client, slept = _client(handler, delay=1.5)
    client.get_page("https://vdl.test/")
    assert slept[-1] == 1.5  # the politeness delay after the GET


def test_get_bytes_returns_none_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client, _ = _client(handler)
    assert client.get_bytes("https://vdl.test/missing.docx") is None


def test_get_bytes_returns_content_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"PK\x03\x04")

    client, _ = _client(handler)
    assert client.get_bytes("https://vdl.test/doc.docx") == b"PK\x03\x04"


def test_get_bytes_raises_on_persistent_5xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client, _ = _client(handler, max_retries=1)
    with pytest.raises(httpx.HTTPStatusError):
        client.get_bytes("https://vdl.test/doc.docx")
