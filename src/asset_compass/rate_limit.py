"""Local, in-process HTTP rate guard covering REST and Streamable HTTP MCP.

Not a distributed quota, reverse-proxy security boundary or authorization layer.
Only ASGI's actual peer address is used: X-Forwarded-For is never trusted.
"""

from collections import deque
import math
import os
from threading import Lock
from time import monotonic

from starlette.responses import JSONResponse


class RateLimitGuard:
    """Sliding-window per-peer request limit for catalog and MCP endpoints."""

    def __init__(
        self, app, *, max_requests: int | None = None, window_seconds: int = 60,
        max_clients: int = 2048, clock=monotonic,
    ):
        if max_requests is None:
            max_requests = int(os.environ.get("ASSET_COMPASS_RATE_LIMIT", "120"))
        if not 1 <= max_requests <= 1000 or not 1 <= window_seconds <= 3600:
            raise ValueError("Rate limit must be 1–1000 requests per 1–3600 second window")
        if not 1 <= max_clients <= 100000:
            raise ValueError("Maximum clients must be between 1 and 100000")
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self.clock = clock
        self.visits: dict[str, deque[float]] = {}
        self.lock = Lock()

    def _throttle(self, key: str) -> int:
        now = self.clock()
        cutoff = now - self.window_seconds
        with self.lock:
            if key not in self.visits and len(self.visits) >= self.max_clients:
                expired = [ip for ip, visits in self.visits.items() if not visits or visits[-1] <= cutoff]
                for ip in expired:
                    del self.visits[ip]
                if len(self.visits) >= self.max_clients:
                    return self.window_seconds

            visits = self.visits.setdefault(key, deque())
            while visits and visits[0] <= cutoff:
                visits.popleft()
            if len(visits) >= self.max_requests:
                return max(1, math.ceil(visits[0] + self.window_seconds - now))
            visits.append(now)
        return 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path.startswith("/v1/") or path in {"/mcp", "/mcp/"}:
            peer = scope.get("client")
            client_ip = str(peer[0]) if peer else "unknown"
            retry_after = self._throttle(client_ip)
            if retry_after:
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded; retry later"},
                    headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
