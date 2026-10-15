"""Request guards for the unauthenticated, tailnet-only web service.

The service has no login by design, so the browser is the trust boundary:
reject Host names that are not this service (DNS rebinding), refuse state
changes that a foreign page triggered (CSRF via simple requests), and cap how
much a single request may upload.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Iterable
from threading import Lock
from urllib.parse import urlsplit

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
DEFAULT_PORTS = {"http": 80, "https": 443}
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
UNSPECIFIED_HOSTS = frozenset({"", "0.0.0.0", "::", "*"})
# JSON command bodies are a few hundred bytes; anything near this is abuse.
MAX_BODY_BYTES = 1024 * 1024
# Multipart framing and the three text fields of a device request.
UPLOAD_OVERHEAD_BYTES = 64 * 1024
DEVICE_REQUEST_RATE_LIMIT = 20
DEVICE_REQUEST_RATE_WINDOW_SECONDS = 3600


def split_host(value: str) -> tuple[str, int | None]:
    """Lower-cased host and explicit port of a Host header or URL netloc.

    The port is ``None`` when absent and ``-1`` when it is not a number, so a
    malformed port never compares equal to a real one.
    """

    value = value.strip().lower()
    port_text = ""
    if value.startswith("["):
        end = value.find("]")
        if end <= 0:
            return value, None
        host, rest = value[1:end], value[end + 1:]
        if rest.startswith(":"):
            port_text = rest[1:]
        elif rest:
            return host, -1
    elif value.count(":") == 1:
        host, port_text = value.rsplit(":", 1)
    else:
        host = value
    if not port_text:
        return host, None
    return host, int(port_text) if port_text.isdigit() else -1


def host_name(value: str) -> str:
    """Lower-cased host part of a Host header or URL netloc without the port."""

    return split_host(value)[0]


def trusted_hosts(bind_host: str, extra_hosts: Iterable[str] = ()) -> frozenset[str]:
    """Host names this service answers to: bind address, loopback and configured extras."""

    hosts = {host_name(host) for host in extra_hosts}
    hosts.update(LOOPBACK_HOSTS)
    bind = host_name(bind_host)
    if bind not in UNSPECIFIED_HOSTS:
        hosts.add(bind)
    hosts.discard("")
    return frozenset(hosts)


class SlidingWindowLimiter:
    """Allow at most ``limit`` events per ``window_seconds`` across the process."""

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._events: deque[float] = deque()
        self._lock = Lock()

    def _expire(self, now: float) -> None:
        while self._events and now - self._events[0] >= self._window:
            self._events.popleft()

    def allow(self) -> bool:
        now = self._clock()
        with self._lock:
            self._expire(now)
            if len(self._events) >= self._limit:
                return False
            self._events.append(now)
            return True

    def retry_after_seconds(self) -> int:
        now = self._clock()
        with self._lock:
            self._expire(now)
            if len(self._events) < self._limit:
                return 0
            return max(1, int(self._window - (now - self._events[0])) + 1)


def _limited_receive(receive: Receive, limit: int) -> Receive:
    received = 0

    async def wrapped() -> Message:
        nonlocal received
        message = await receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > limit:
                # FastAPI re-raises HTTPException from body reads, so this
                # becomes a JSON 413 instead of a 400 parse error.
                raise HTTPException(
                    status_code=413, detail=f"request body exceeds {limit} bytes"
                )
        return message

    return wrapped


class RequestGuardMiddleware:
    """Validate Host and Origin before any handler runs, and bound request bodies."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_hosts: Iterable[str],
        service_port: int,
        upload_path: str,
        upload_max_bytes: int,
        upload_limiter: SlidingWindowLimiter | None = None,
        max_body_bytes: int = MAX_BODY_BYTES,
    ) -> None:
        self.app = app
        self.allowed_hosts = frozenset(host_name(host) for host in allowed_hosts) - {""}
        self.service_port = service_port
        self.upload_path = upload_path
        self.upload_max_bytes = upload_max_bytes
        self.upload_limiter = upload_limiter
        self.max_body_bytes = max_body_bytes

    def is_trusted_host(self, host: str, scope: Scope) -> bool:
        if not host:
            return False
        if host in self.allowed_hosts:
            return True
        # The address the connection arrived on is this service by definition;
        # a rebinding page always presents the attacker's DNS name instead.
        server = scope.get("server")
        return isinstance(server, tuple | list) and bool(server) and (
            host == host_name(str(server[0]))
        )

    def _origin_allowed(self, origin: str, scope: Scope, request_host: str) -> bool:
        """True only for the request's own origin or this service on another allowed name.

        Scheme, host and effective port must all match, so another HTTP UI on the
        same loopback/tailnet address but a different port (e.g. the Zigbee2MQTT
        frontend on :8080) is still a foreign origin.
        """

        scheme = str(scope.get("scheme", "http")).lower()
        parts = urlsplit(origin.strip())
        if (
            parts.scheme.lower() != scheme or parts.path or parts.query or parts.fragment
            or "@" in parts.netloc
        ):
            return False
        try:
            port = parts.port
        except ValueError:
            return False
        host = parts.hostname or ""
        effective_port = port if port is not None else DEFAULT_PORTS.get(scheme)
        own_host, own_port = split_host(request_host)
        if own_port is None:
            own_port = DEFAULT_PORTS.get(scheme)
        if host == own_host and effective_port == own_port:
            return True
        return self.is_trusted_host(host, scope) and effective_port == self.service_port

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        request_host = headers.get("host", "")
        if not self.is_trusted_host(host_name(request_host), scope):
            await self._reject(scope, receive, send, 400, "Host header is not this service")
            return
        if scope.get("method", "GET").upper() in SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        origin = headers.get("origin")
        if headers.get("sec-fetch-site", "").strip().lower() == "cross-site" or (
            origin is not None and not self._origin_allowed(origin, scope, request_host)
        ):
            await self._reject(
                scope, receive, send, 403, "cross-site requests cannot change this service"
            )
            return

        limit = self.max_body_bytes
        is_upload = scope.get("path") == self.upload_path
        if is_upload:
            if "content-length" not in headers:
                await self._reject(
                    scope, receive, send, 411, "device requests must declare Content-Length"
                )
                return
            limit = self.upload_max_bytes
        declared = headers.get("content-length")
        if declared is not None:
            try:
                length = int(declared)
            except ValueError:
                await self._reject(scope, receive, send, 400, "invalid Content-Length")
                return
            if length > limit:
                await self._reject(
                    scope, receive, send, 413, f"request body exceeds {limit} bytes"
                )
                return
        # Only a request that may actually upload spends a rate-limit token, so
        # bodyless or oversized probes cannot lock the route for everyone.
        if is_upload and self.upload_limiter is not None and not self.upload_limiter.allow():
            await self._reject(
                scope, receive, send, 429,
                "too many device requests; try again later",
                {"Retry-After": str(self.upload_limiter.retry_after_seconds())},
            )
            return
        await self.app(scope, _limited_receive(receive, limit), send)

    @staticmethod
    async def _reject(
        scope: Scope,
        receive: Receive,
        send: Send,
        status_code: int,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        response = JSONResponse({"detail": detail}, status_code=status_code, headers=headers)
        await response(scope, receive, send)
