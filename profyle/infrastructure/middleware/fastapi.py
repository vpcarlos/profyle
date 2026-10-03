import os

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from profyle.application.profyle import profyle
from profyle.application.request_capture import MAX_BODY_BYTES, build_recorded_request
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
            path = scope.get("raw_path", b"").decode("utf-8")
            query_string = scope.get("query_string", b"").decode("utf-8")
            if query_string:
                path = f"{path}?{query_string}"

            body = bytearray()
            body_truncated = False
            status_code: int | None = None

            # Only the body the app actually reads is captured; a body the app ignores
            # cannot influence the response, so replaying without it is equivalent.
            async def receive_and_capture() -> Message:
                nonlocal body_truncated
                message = await receive()
                if message["type"] == "http.request" and not body_truncated:
                    body.extend(message.get("body", b""))
                    if len(body) > MAX_BODY_BYTES:
                        body_truncated = True
                        body.clear()
                return message

            async def send_and_capture(message: Message) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                await send(message)

            with profyle(
                name=f"{method} {path}",
                pattern=self.pattern,
                repo=self.trace_repo,
                max_stack_depth=self.max_stack_depth,
                min_duration=self.min_duration,
            ) as trace:
                try:
                    await self.app(scope, receive_and_capture, send_and_capture)
                finally:
                    headers = [
                        (k.decode("latin-1"), v.decode("latin-1"))
                        for k, v in scope.get("headers", [])
                    ]
                    host = dict(headers).get("host") or _server_host(scope)
                    trace.request = build_recorded_request(
                        method=method,
                        path=path,
                        scheme=scope.get("scheme", "http"),
                        host=host,
                        headers=headers,
                        body=bytes(body),
                        body_truncated=body_truncated,
                        status_code=status_code,
                    )
            return
        await self.app(scope, receive, send)


def _server_host(scope: Scope) -> str:
    server = scope.get("server")
    return f"{server[0]}:{server[1]}" if server else "localhost"
