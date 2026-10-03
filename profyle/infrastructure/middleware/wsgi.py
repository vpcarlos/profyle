"""Generic WSGI middleware: Flask, Django (WSGI), Falcon, Bottle, Pyramid..."""

import io

from profyle.application.request_capture import MAX_BODY_BYTES, build_recorded_request
from profyle.domain.trace_repository import TraceRepository
from profyle.infrastructure.middleware.base import MIDDLEWARE, Integration

# Set in the environ by the outermost Profyle middleware so nested ones skip the request.
TRACED = "profyle.traced"


class ProfyleMiddleware:
    """Trace every HTTP request of a WSGI app.

    Settings left as None come from PROFYLE_* environment variables, `[tool.profyle]` in
    pyproject.toml or defaults (see profyle.config).
    """

    def __init__(
        self,
        app,
        enabled: bool | None = None,
        pattern: str | None = None,
        max_stack_depth: int | None = None,
        min_duration: float | None = None,
        console: bool | None = None,
        trace_repo: TraceRepository | None = None,
        *,
        framework: str = "WSGI",
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

    @property
    def trace_repo(self) -> TraceRepository:
        return self.integration.repo

    @trace_repo.setter
    def trace_repo(self, repo: TraceRepository) -> None:
        self.integration.repo = repo

    def __call__(self, environ, start_response):
        if not self.integration.config.enabled or environ.get(TRACED):
            return self.app(environ, start_response)
        environ[TRACED] = True
        method = environ.get("REQUEST_METHOD", "").upper()
        path = environ.get("REQUEST_URI") or _path(environ)
        body, body_truncated = _read_body(environ)
        status_code: int | None = None

        def start_response_and_capture(status, headers, *args):
            nonlocal status_code
            status_code = int(status.split(" ", 1)[0])
            return start_response(status, headers, *args)

        with self.integration.tracer(f"{method} {path}") as trace:
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
