"""Conservative URL canonicalization for catalog identities."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_KEYS = frozenset({"fbclid", "gclid", "gbraid", "wbraid", "mc_cid", "mc_eid"})


def canonicalize_url(raw: str) -> str:
    """Canonicalize an HTTP(S) URL while preserving content-bearing query params."""
    try:
        parsed = urlsplit(raw.strip())
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError("Only http:// and https:// resource URLs are allowed")
        if not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("URL must have a host and no embedded credentials")
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port
        default_port = (parsed.scheme.lower() == "https" and port == 443) or (
            parsed.scheme.lower() == "http" and port == 80
        )
        if ":" in host:
            host = f"[{host}]"
        netloc = host if port is None or default_port else f"{host}:{port}"
        params = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS
        ]
        # Keep the original order: parameter order may be meaningful on some sites.
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", urlencode(params), ""))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"Invalid URL {raw!r}: {exc}") from exc

