import os

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from profyle.application.profyle import profyle
from profyle.application.request_capture import MAX_BODY_BYTES, build_recorded_request
from profyle.application.response_fingerprint import MAX_FINGERPRINT_BYTES, fingerprint
from profyle.domain.trace import RecordedRequest
from profyle.infrastructure.middleware.threadpool import trace_worker_threads
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository


class ProfyleMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        enabled: bool = True,
        pattern: str|None = None,
        max_stack_depth: int = -1,
        min_duration: int = 0,
        trace_repo: SQLiteTraceRepository = SQLiteTraceRepository(),
    ):
        self.app = app
        self.trace_repo = trace_repo

        PROFYLE_ENABLED = os.getenv("PROFYLE_ENABLED", "")
        PROFYLE_PATTERN = os.getenv("PROFYLE_PATTERN")
        PROFYLE_MAX_STACK_DEPTH = os.getenv("PROFYLE_MAX_STACK_DEPTH")
        PROFYLE_MIN_DURATION = os.getenv("PROFYLE_MIN_DURATION")

        self.enabled = PROFYLE_ENABLED.lower() == "true" or enabled
        self.pattern = PROFYLE_PATTERN or pattern
        self.max_stack_depth = int(PROFYLE_MAX_STACK_DEPTH or max_stack_depth)
        self.min_duration = int(PROFYLE_MIN_DURATION or min_duration)
        if self.enabled:
            trace_worker_threads()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.enabled and scope["type"] == "http":
            method = scope.get("method", "").upper()
            # Per the ASGI spec raw_path has no query string, but some servers and older
            # Starlette test clients include it.
            path = scope.get("raw_path", b"").split(b"?", 1)[0].decode("utf-8")
            query_string = scope.get("query_string", b"").decode("utf-8")
            if query_string:
                path = f"{path}?{query_string}"

            exchange = _ExchangeRecorder(scope, receive, send)
            with profyle(
                name=f"{method} {path}",
                pattern=self.pattern,
                repo=self.trace_repo,
                max_stack_depth=self.max_stack_depth,
                min_duration=self.min_duration,
            ) as trace:
                try:
                    await self.app(scope, exchange.receive, exchange.send)
                finally:
                    trace.request = lambda: exchange.recorded_request(method, path)
            return
        await self.app(scope, receive, send)


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
