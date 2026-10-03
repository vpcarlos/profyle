"""Generic ASGI middleware: FastAPI, Starlette, Litestar, Quart, Django (ASGI)..."""

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from profyle.application.requests.capture import MAX_BODY_BYTES, build_recorded_request
from profyle.application.requests.fingerprint import MAX_FINGERPRINT_BYTES, fingerprint
from profyle.domain.trace import RecordedRequest
from profyle.domain.trace_repository import TraceRepository
from profyle.infrastructure.middleware.base import MIDDLEWARE, TRACED, Integration, Middleware

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class ProfyleMiddleware(Middleware):
    """Trace every HTTP request of an ASGI app.

    Settings left as None come from PROFYLE_* environment variables, `[tool.profyle]` in
    pyproject.toml or defaults (see profyle.config).
    """

    def __init__(
        self,
        app: ASGIApp,
        enabled: bool | None = None,
        pattern: str | None = None,
        max_stack_depth: int | None = None,
        min_duration: float | None = None,
        console: bool | None = None,
        trace_repo: TraceRepository | None = None,
        *,
        framework: str = "ASGI",
        mode: str = MIDDLEWARE,
    ):
        self.app = app
        self.integration = Integration(
            framework,
            trace_repo=trace_repo,
            mode=mode,
            enabled=enabled,
            pattern=pattern,
            max_stack_depth=max_stack_depth,
            min_duration=min_duration,
            console=console,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.integration.config.enabled or scope["type"] != "http" or scope.get(TRACED):
            await self.app(scope, receive, send)
            return
        scope[TRACED] = True
        method = scope.get("method", "").upper()
        # raw_path is optional in ASGI and, against the spec, some servers and older
        # Starlette test clients include the query string in it.
        raw_path = scope.get("raw_path")
        path = raw_path.split(b"?", 1)[0].decode("latin-1") if raw_path else scope["path"]
        query_string = scope.get("query_string", b"").decode("latin-1")
        if query_string:
            path = f"{path}?{query_string}"

        exchange = _ExchangeRecorder(scope, receive, send)
        with self.integration.tracer(method, path) as trace:
            try:
                await self.app(scope, exchange.receive, exchange.send)
            finally:
                trace.request = lambda: exchange.recorded_request(method, path)


class _ExchangeRecorder:
    """Wraps receive/send to keep what is needed to replay the request and to check
    later that a change did not alter the response."""

    def __init__(self, scope: Scope, receive: Receive, send: Send):
        self.scope = scope
        self._receive = receive
        self._send = send
        self.body = bytearray()
        self.body_truncated = False
        self.status_code: int | None = None
        self.content_type: str | None = None
        self.response_body = bytearray()
        self.response_too_large = False

    # Only the body the app actually reads is captured; a body the app ignores cannot
    # influence the response, so replaying without it is equivalent.
    async def receive(self) -> Message:
        message = await self._receive()
        if message["type"] == "http.request" and not self.body_truncated:
            self.body.extend(message.get("body", b""))
            if len(self.body) > MAX_BODY_BYTES:
                self.body_truncated = True
                self.body.clear()
        return message

    async def send(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.status_code = message["status"]
            for name, value in message.get("headers", []):
                if name.lower() == b"content-type":
                    self.content_type = value.decode("latin-1")
        elif message["type"] == "http.response.body" and not self.response_too_large:
            self.response_body.extend(message.get("body", b""))
            if len(self.response_body) > MAX_FINGERPRINT_BYTES:
                self.response_too_large = True
                self.response_body.clear()
        await self._send(message)

    def recorded_request(self, method: str, path: str) -> RecordedRequest:
        headers = [
            (k.decode("latin-1"), v.decode("latin-1")) for k, v in self.scope.get("headers", [])
        ]
        request = build_recorded_request(
            method=method,
            path=path,
            scheme=self.scope.get("scheme", "http"),
            host=dict(headers).get("host") or _server_host(self.scope),
            headers=headers,
            body=bytes(self.body),
            body_truncated=self.body_truncated,
            status_code=self.status_code,
        )
        if self.status_code is not None and not self.response_too_large:
            request.response = fingerprint(bytes(self.response_body), self.content_type)
        return request


def _server_host(scope: Scope) -> str:
    server = scope.get("server")
    return f"{server[0]}:{server[1]}" if server else "localhost"
