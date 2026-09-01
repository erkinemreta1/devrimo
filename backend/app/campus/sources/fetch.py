"""The one place this service reaches out to a campus website.

Three properties are enforced here rather than left to each adapter, because
each of them is the kind of thing that is either true everywhere or worthless:

* **Where we may connect.** Source rows are admin-editable, and the broker is
  the process holding every resident student's METU password in memory. An
  admin account that gets taken over must not be able to turn the fetcher into
  a probe of the broker's own network, so a URL is checked against a host
  allowlist *and* its resolved addresses are rejected if they are private,
  loopback, or link-local — before the connection, and again on every redirect
  rather than trusting ``follow_redirects``.

* **How politely.** ``faq.cc.metu.edu.tr`` asks for ``Crawl-delay: 10`` and it
  gets it. Delays are per host and shared across sources, so two sources on one
  host cannot each spend the site's budget.

* **How cheaply.** Conditional GET with stored ``ETag``/``Last-Modified``, so a
  refresh of an unchanged announcement costs one 304 and no re-embedding.

Nothing here parses HTML. A fetch returns bytes plus enough headers for
:mod:`app.campus.sources.htmlkit` to decode them.
"""

import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from app.campus.sources.models import SourceError
from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

# Redirect chains on Drupal sites are short (language negotiation, trailing
# slash). Anything longer is a loop or a redirector, and either way is not a
# campus page.
MAX_REDIRECTS = 5


@dataclass(frozen=True)
class FetchedPage:
    url: str
    status: int
    body: bytes
    declared_charset: str | None = None
    etag: str | None = None
    last_modified: str | None = None

    @property
    def not_modified(self) -> bool:
        return self.status == 304


@dataclass
class HostBudget:
    """Per-host crawl delay, shared by every source pointed at that host."""

    delay_seconds: float
    last_request_at: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def host_allowed(host: str, patterns: list[str]) -> bool:
    """Whether a hostname matches any configured allowlist pattern.

    ``*.metu.edu.tr`` matches ``oidb.metu.edu.tr`` and ``metu.edu.tr`` itself,
    but deliberately not ``metu.edu.tr.example.com`` — the suffix check is on
    a dot boundary, not a substring.
    """
    host = (host or "").strip().lower().rstrip(".")
    if not host:
        return False
    for pattern in patterns:
        if pattern.startswith("*."):
            root = pattern[2:]
            if host == root or host.endswith(f".{root}"):
                return True
        elif host == pattern:
            return True
    return False


def _is_public_address(raw: str) -> bool:
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


async def _assert_public_host(host: str) -> None:
    """Reject a host that resolves anywhere inside our own network.

    An allowlisted name is not enough on its own: DNS is not ours, and a record
    that points at ``127.0.0.1`` or a metadata endpoint would otherwise be
    fetched with the broker's own network position.
    """
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None, 0, socket.SOCK_STREAM)
    except OSError as exc:
        raise SourceError("dns_failed", f"Could not resolve {host}: {exc}") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise SourceError("dns_failed", f"Could not resolve {host}")
    bad = [address for address in addresses if not _is_public_address(address)]
    if bad:
        raise SourceError("blocked_address", f"{host} resolves to a non-public address ({', '.join(sorted(bad))})")


class CampusFetcher:
    """An allowlisted, rate-limited, conditional HTTP reader for campus sites.

    One instance per ingest run (or per live-read request). It counts its own
    requests and bytes so a run record can say what a source actually cost.
    """

    def __init__(
        self,
        *,
        allowed_hosts: list[str] | None = None,
        timeout_seconds: float | None = None,
        max_bytes: int | None = None,
        user_agent: str | None = None,
        default_delay: float | None = None,
    ) -> None:
        settings = get_settings()
        self.allowed_hosts = allowed_hosts if allowed_hosts is not None else settings.campus_fetch_allowed_host_patterns
        self.timeout_seconds = timeout_seconds or settings.campus_fetch_timeout_seconds
        self.max_bytes = max_bytes or settings.campus_fetch_max_bytes
        self.user_agent = user_agent or settings.campus_fetch_user_agent
        self.default_delay = (
            default_delay if default_delay is not None else settings.campus_fetch_default_crawl_delay_seconds
        )
        self.requests_made = 0
        self.bytes_fetched = 0
        self._budgets: dict[str, HostBudget] = {}
        self._robots: dict[str, float] = {}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "CampusFetcher":
        self._client = httpx.AsyncClient(
            timeout=self.timeout_seconds,
            # Redirects are followed by hand so each hop is re-checked against
            # the allowlist. httpx would happily follow one off-campus.
            follow_redirects=False,
            headers={"User-Agent": self.user_agent, "Accept-Language": "tr,en;q=0.8"},
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise SourceError("not_started", "CampusFetcher must be used as an async context manager")
        return self._client

    async def _check_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise SourceError("blocked_scheme", f"Refusing non-HTTP URL: {url}")
        if not host_allowed(parsed.hostname or "", self.allowed_hosts):
            raise SourceError("blocked_host", f"{parsed.hostname} is not in the campus fetch allowlist")
        await _assert_public_host(parsed.hostname or "")
        return url

    async def _crawl_delay(self, host: str, scheme: str) -> float:
        """The delay this host asks for, read once from robots.txt per run.

        A site that declines to say gets ``default_delay``. A site we cannot
        reach for robots.txt also gets the default rather than being skipped:
        robots is advisory about *rate* here, and the allowlist is what decides
        whether we may read the host at all.
        """
        if host in self._robots:
            return self._robots[host]
        delay = self.default_delay
        try:
            response = await self._require_client().get(f"{scheme}://{host}/robots.txt")
            if response.status_code == 200:
                for line in response.text.splitlines():
                    name, _, value = line.partition(":")
                    if name.strip().lower() == "crawl-delay":
                        try:
                            delay = max(delay, float(value.strip()))
                        except ValueError:
                            continue
        except httpx.HTTPError:
            pass
        delay = min(delay, get_settings().campus_fetch_max_crawl_delay_seconds)
        self._robots[host] = delay
        return delay

    async def _wait_turn(self, host: str, scheme: str) -> None:
        delay = await self._crawl_delay(host, scheme)
        budget = self._budgets.setdefault(host, HostBudget(delay_seconds=delay))
        budget.delay_seconds = delay
        async with budget.lock:
            elapsed = time.monotonic() - budget.last_request_at
            if budget.last_request_at and elapsed < budget.delay_seconds:
                await asyncio.sleep(budget.delay_seconds - elapsed)
            budget.last_request_at = time.monotonic()

    async def get(self, url: str, *, etag: str | None = None, last_modified: str | None = None) -> FetchedPage:
        """Fetch one page, honouring the allowlist, the delay, and validators."""
        client = self._require_client()
        current = await self._check_url(url)
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        for _ in range(MAX_REDIRECTS + 1):
            parsed = urlparse(current)
            await self._wait_turn(parsed.hostname or "", parsed.scheme)
            self.requests_made += 1
            try:
                response = await client.get(current, headers=headers)
            except httpx.HTTPError as exc:
                raise SourceError("unreachable", f"{current}: {exc.__class__.__name__}: {exc}") from exc

            # Checked before the redirect branch: 304 is in the 3xx class, so
            # httpx's ``is_redirect`` is true for it, and a Not Modified carries
            # no Location — which would fail every conditional GET we make.
            if response.status_code == 304:
                return FetchedPage(url=current, status=304, body=b"", etag=etag, last_modified=last_modified)

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise SourceError("bad_redirect", f"{current} redirected without a Location header")
                # Re-checked rather than trusted: this is the hop an attacker
                # controls if they control any page we read.
                current = await self._check_url(str(response.url.join(location)))
                continue
            if response.status_code >= 400:
                raise SourceError("http_error", f"{current} returned HTTP {response.status_code}")

            body = response.content
            if len(body) > self.max_bytes:
                # Truncated rather than rejected: an oversized listing page is
                # still worth the items at the top of it.
                logger.warning("campus_fetch_truncated", url=current, bytes=len(body))
                body = body[: self.max_bytes]
            self.bytes_fetched += len(body)
            return FetchedPage(
                url=current,
                status=response.status_code,
                body=body,
                declared_charset=response.charset_encoding,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )

        raise SourceError("too_many_redirects", f"{url} exceeded {MAX_REDIRECTS} redirects")
