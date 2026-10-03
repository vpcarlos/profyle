import io
import os

from profyle.application.profyle import profyle
from profyle.application.request_capture import MAX_BODY_BYTES, build_recorded_request
from profyle.domain.trace_repository import TraceRepository
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository


class ProfyleMiddleware:
    def __init__(
        self,
        app,
        enabled: bool = True,
        pattern: str|None = None,
        max_stack_depth: int = -1,
        min_duration: int = 0,
        trace_repo: TraceRepository = SQLiteTraceRepository()
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


    def __call__(self, environ, start_response):
        if environ.get("wsgi.url_scheme") == "http" and self.enabled:
            method = environ.get("REQUEST_METHOD", "").upper()
            path = environ.get("REQUEST_URI") or _path(environ)
            body, body_truncated = _read_body(environ)
            status_code: int | None = None

            def start_response_and_capture(status, headers, *args):
                nonlocal status_code
                status_code = int(status.split(" ", 1)[0])
                return start_response(status, headers, *args)

            with profyle(
                name=f"{method} {path}",
                pattern=self.pattern,
                max_stack_depth=self.max_stack_depth,
                min_duration=self.min_duration,
                repo=self.trace_repo
            ) as trace:
                try:
                    return self.app(environ, start_response_and_capture)
                finally:
                    trace.request = lambda: build_recorded_request(
                        method=method,
                        path=path,
                        scheme=environ.get("wsgi.url_scheme", "http"),
                        host=environ.get("HTTP_HOST") or _server_host(environ),
                        headers=_headers(environ),
                        body=body,
                        body_truncated=body_truncated,
                        status_code=status_code,
                    )
        return self.app(environ, start_response)


def _path(environ) -> str:
    path = environ.get("SCRIPT_NAME", "") + environ.get("PATH_INFO", "/")
    query = environ.get("QUERY_STRING")
    return f"{path}?{query}" if query else path


def _read_body(environ) -> tuple[bytes | None, bool]:
    """Read the body for replay and hand the app an identical stream."""
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return None, False
    if length <= 0:
        return None, False
    if length > MAX_BODY_BYTES:
        return None, True
    body = environ["wsgi.input"].read(length)
    environ["wsgi.input"] = io.BytesIO(body)
    return body, False


def _headers(environ) -> list[tuple[str, str]]:
    headers = [
        (key[5:].replace("_", "-").lower(), value)
        for key, value in environ.items()
        if key.startswith("HTTP_")
    ]
    if environ.get("CONTENT_TYPE"):
        headers.append(("content-type", environ["CONTENT_TYPE"]))
    return headers


def _server_host(environ) -> str:
    return f"{environ.get('SERVER_NAME', 'localhost')}:{environ.get('SERVER_PORT', '80')}"
