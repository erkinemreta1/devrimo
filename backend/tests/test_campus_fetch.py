"""The fetcher's boundary: where it may connect, and where it must refuse.

These are the tests that matter most in this package. Source rows are
admin-editable and this process holds every resident student's METU password,
so "which hosts can this reach" is a security property, not a configuration
convenience. Nothing here opens a socket: DNS is stubbed, and the HTTP client
is a transport that answers from a dictionary.
"""

import httpx
import pytest

from app.campus.sources import fetch
from app.campus.sources.fetch import CampusFetcher, host_allowed
from app.campus.sources.models import SourceError

ALLOWLIST = ["*.metu.edu.tr"]


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    """Every hostname resolves to a public address unless a test says otherwise."""

    async def _ok(host: str) -> None:
        return None

    monkeypatch.setattr(fetch, "_assert_public_host", _ok)


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch):
    """Skip robots.txt and the crawl delay; both are covered separately."""

    async def _instant(self, host: str, scheme: str) -> None:
        return None

    monkeypatch.setattr(CampusFetcher, "_wait_turn", _instant)


def make_fetcher(handler, **kwargs) -> CampusFetcher:
    fetcher = CampusFetcher(allowed_hosts=ALLOWLIST, default_delay=0, **kwargs)

    async def _enter(self):
        self._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
        return self

    fetcher.__class__ = type("_TestFetcher", (CampusFetcher,), {"__aenter__": _enter})
    return fetcher


# --- The allowlist itself ---------------------------------------------------


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("oidb.metu.edu.tr", True),
        ("metu.edu.tr", True),
        ("faq.cc.metu.edu.tr", True),
        ("OIDB.METU.EDU.TR", True),
        ("oidb.metu.edu.tr.", True),
        # The one that matters: a suffix match on a substring rather than on a
        # dot boundary would let any domain ending in these characters through.
        ("metu.edu.tr.evil.example", False),
        ("notmetu.edu.tr", False),
        ("evil.example", False),
        ("", False),
    ],
)
def test_host_allowlist_matches_on_dot_boundaries(host, expected):
    assert host_allowed(host, ALLOWLIST) is expected


# --- Refusals ---------------------------------------------------------------


async def test_off_allowlist_host_is_refused():
    def handler(request):  # pragma: no cover - must never be reached
        raise AssertionError("the fetcher connected to a host outside the allowlist")

    async with make_fetcher(handler) as fetcher:
        with pytest.raises(SourceError) as exc:
            await fetcher.get("https://evil.example/page")
    assert exc.value.code == "blocked_host"


async def test_non_http_scheme_is_refused():
    def handler(request):  # pragma: no cover
        raise AssertionError("the fetcher opened a non-HTTP URL")

    async with make_fetcher(handler) as fetcher:
        for url in ("file:///etc/passwd", "gopher://metu.edu.tr/"):
            with pytest.raises(SourceError) as exc:
                await fetcher.get(url)
            assert exc.value.code == "blocked_scheme"


async def test_redirect_off_the_allowlist_is_refused(monkeypatch):
    """``follow_redirects`` is off precisely so this hop can be re-checked.

    The redirect target is the one part of a fetch an attacker controls if they
    control any page we read.
    """

    def handler(request):
        if request.url.host == "oidb.metu.edu.tr":
            return httpx.Response(302, headers={"location": "https://evil.example/steal"})
        raise AssertionError("the fetcher followed a redirect off the allowlist")

    async with make_fetcher(handler) as fetcher:
        with pytest.raises(SourceError) as exc:
            await fetcher.get("https://oidb.metu.edu.tr/tr/x")
    assert exc.value.code == "blocked_host"


async def test_redirect_within_the_allowlist_is_followed():
    def handler(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://spormd.metu.edu.tr/new"})
        return httpx.Response(200, content=b"<main>arrived</main>")

    async with make_fetcher(handler) as fetcher:
        page = await fetcher.get("https://spormd.metu.edu.tr/old")
    assert page.status == 200
    assert page.url == "https://spormd.metu.edu.tr/new"
    assert b"arrived" in page.body


async def test_redirect_loop_stops():
    def handler(request):
        return httpx.Response(302, headers={"location": "https://oidb.metu.edu.tr/loop"})

    async with make_fetcher(handler) as fetcher:
        with pytest.raises(SourceError) as exc:
            await fetcher.get("https://oidb.metu.edu.tr/loop")
    assert exc.value.code == "too_many_redirects"


async def test_private_addresses_are_refused(monkeypatch):
    """An allowlisted *name* is not enough — DNS is not ours.

    A record pointing at loopback or a metadata endpoint would otherwise be
    fetched with the broker's own network position.
    """
    monkeypatch.undo()  # restore the real _assert_public_host

    def resolve(host, *args, **kwargs):
        return [(2, 1, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(fetch.socket, "getaddrinfo", resolve)
    with pytest.raises(SourceError) as exc:
        await fetch._assert_public_host("oidb.metu.edu.tr")
    assert exc.value.code == "blocked_address"


async def test_public_addresses_are_allowed(monkeypatch):
    monkeypatch.undo()

    def resolve(host, *args, **kwargs):
        return [(2, 1, 6, "", ("144.122.1.1", 0))]

    monkeypatch.setattr(fetch.socket, "getaddrinfo", resolve)
    await fetch._assert_public_host("oidb.metu.edu.tr")


# --- Behaviour --------------------------------------------------------------


async def test_conditional_get_sends_validators_and_reports_304():
    seen: dict[str, str] = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(304)

    async with make_fetcher(handler) as fetcher:
        page = await fetcher.get(
            "https://oidb.metu.edu.tr/x", etag='W/"abc"', last_modified="Mon, 01 Jan 2026 00:00:00 GMT"
        )
    assert seen["if-none-match"] == 'W/"abc"'
    assert seen["if-modified-since"] == "Mon, 01 Jan 2026 00:00:00 GMT"
    assert page.not_modified


async def test_oversized_body_is_truncated_not_rejected():
    def handler(request):
        return httpx.Response(200, content=b"x" * 5_000)

    async with make_fetcher(handler, max_bytes=1_000) as fetcher:
        page = await fetcher.get("https://oidb.metu.edu.tr/big")
    assert len(page.body) == 1_000
    assert fetcher.bytes_fetched == 1_000


async def test_http_errors_carry_a_code():
    def handler(request):
        return httpx.Response(503)

    async with make_fetcher(handler) as fetcher:
        with pytest.raises(SourceError) as exc:
            await fetcher.get("https://oidb.metu.edu.tr/down")
    assert exc.value.code == "http_error"


async def test_crawl_delay_is_read_from_robots(monkeypatch):
    """``faq.cc.metu.edu.tr`` asks for ``Crawl-delay: 10``, and gets it."""
    monkeypatch.undo()  # restore the real _wait_turn

    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(fetch.asyncio, "sleep", fake_sleep)

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 10\nDisallow: /misc/\n")
        return httpx.Response(200, content=b"<main>ok</main>")

    async with make_fetcher(handler) as fetcher:
        await fetcher.get("https://faq.cc.metu.edu.tr/tr/sss/a")
        assert fetcher._budgets["faq.cc.metu.edu.tr"].delay_seconds == 10
        await fetcher.get("https://faq.cc.metu.edu.tr/tr/sss/b")

    assert slept, "the second request to the same host must wait out the crawl delay"
