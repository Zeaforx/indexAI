"""Opt-in, HEAD-only link observations for an explicit list of safe publisher hosts.

No scraping, no asset GETs, no redirects, no deletion and no automatic rejection.
HTTP errors are signals for human review, not final judgments of availability.
"""

from dataclasses import dataclass
from datetime import timedelta
import ipaddress
import socket
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Resource, utcnow

SAFE_PUBLISHER_HOSTS = frozenset({"kenney.nl", "polyhaven.com", "ambientcg.com"})
USER_AGENT = "indexAI/0.5 (+https://github.com/Zeaforx/indexAI; link-check HEAD only)"
MIN_CHECK_INTERVAL = timedelta(hours=24)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


@dataclass(frozen=True)
class Probe:
    status: str
    http_status: int | None
    note: str


def _safe_host(url: str) -> tuple[bool, str]:
    try:
        parsed = urlsplit(url)
        secure_default_port = parsed.port in (None, 443)
    except ValueError:
        return False, "Malformed publisher URL or port"
    if parsed.scheme != "https" or not secure_default_port:
        return False, "Only HTTPS publisher URLs on default ports are checked"
    if parsed.hostname not in SAFE_PUBLISHER_HOSTS or parsed.username or parsed.password:
        return False, "Host is not in the explicitly reviewed publisher allowlist"
    return True, "approved publisher host"


def _public_addresses(host: str) -> bool:
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        return False
    return bool(addresses) and all(
        ipaddress.ip_address(info[4][0]).is_global for info in addresses
    )


def _classify(code: int) -> Probe:
    if 200 <= code < 300:
        return Probe("healthy", code, "HEAD returned a successful status")
    if code in (301, 302, 303, 307, 308):
        return Probe("redirect", code, "Redirect intentionally not followed")
    if code in (404, 410):
        return Probe("suspect_missing", code, "HEAD suggests a missing page; manual confirmation required")
    if code in (401, 403, 429):
        return Probe("restricted", code, "Access restricted or rate limited; not evidence of a broken URL")
    if code in (405, 501):
        return Probe("unsupported", code, "Provider may not support HEAD; no GET fallback")
    return Probe("transient_error", code, "Uncertain HTTP response; retry after cooldown")


def probe_url(url: str, *, timeout: float = 6.0) -> Probe:
    """Safely observe a curated URL once without fetching a body or redirecting."""
    allowed, reason = _safe_host(url)
    if not allowed:
        return Probe("skipped", None, reason)
    host = urlsplit(url).hostname
    if not _public_addresses(host):
        return Probe("skipped", None, "DNS resolution failed or includes a non-public address")
    if not 1 <= timeout <= 10:
        raise ValueError("Timeout must be between 1 and 10 seconds")
    request = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with build_opener(NoRedirect).open(request, timeout=timeout) as response:
            return _classify(response.status)
    except HTTPError as exc:
        return _classify(exc.code)
    except (URLError, TimeoutError, OSError):
        return Probe("transient_error", None, "Connection failed; retry later")


def check_links(
    session: Session, *, limit: int = 10, source_name: str | None = None,
    execute: bool = False, force: bool = False,
    checker=probe_url,
    pause_seconds: float = 0.25,
) -> dict:
    """Preview by default; an explicit --execute records cautious observations.

    Limits/check intervals prevent accidental hammering. Never deletes entries,
    and URL health does not silently change curator approvals or licenses.
    """
    if not 1 <= limit <= 20:
        raise ValueError("Link-check limit must be 1–20")
    if not 0 <= pause_seconds <= 5:
        raise ValueError("Pause must be between 0 and 5 seconds")
    stmt = select(Resource).where(Resource.review_status == "approved")
    if source_name:
        from .models import Source
        stmt = stmt.join(Source).where(func.lower(Source.name) == source_name.casefold())
    # Unchecked first, then oldest check; calls progress through the catalog.
    stmt = stmt.order_by(Resource.last_checked_at.is_not(None), Resource.last_checked_at, Resource.id).limit(limit)
    items = list(session.scalars(stmt))
    report = {"mode": "execute" if execute else "preview", "selected": len(items), "checked": 0, "skipped": 0, "results": []}
    for item in items:
        row = {"id": item.id, "url": item.canonical_url}
        safe, reason = _safe_host(item.canonical_url)
        if not safe:
            row.update({"status": "skipped", "note": reason})
            report["skipped"] += 1
        elif not execute:
            row.update({"status": "preview", "note": "No network request or DB update made"})
        elif not force and item.last_checked_at and utcnow().replace(tzinfo=None) - item.last_checked_at.replace(tzinfo=None) < MIN_CHECK_INTERVAL:
            row.update({"status": "skipped", "note": "Checked in the last 24 hours"})
            report["skipped"] += 1
        else:
            result = checker(item.canonical_url)
            row.update({"status": result.status, "http_status": result.http_status, "note": result.note})
            if result.status == "skipped":
                report["skipped"] += 1
            else:
                item.url_status = result.status
                item.last_http_status = result.http_status
                item.last_checked_at = utcnow()
                report["checked"] += 1
                session.flush()
                if pause_seconds:
                    sleep(pause_seconds)
        report["results"].append(row)
    return report
