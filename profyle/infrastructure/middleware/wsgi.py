"""Generic WSGI middleware: Flask, Django (WSGI), Falcon, Bottle, Pyramid..."""

import io

from profyle.application.requests.capture import MAX_BODY_BYTES, build_recorded_request
from profyle.application.requests.fingerprint import MAX_FINGERPRINT_BYTES, fingerprint
from profyle.domain.trace import RecordedRequest
from profyle.domain.trace_repository import TraceRepository
from profyle.infrastructure.middleware.base import MIDDLEWARE, TRACED, Integration, Middleware


class ProfyleMiddleware(Middleware):
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

    def __call__(self, environ, start_response):
        if not self.integration.config.enabled or environ.get(TRACED):
            return self.app(environ, start_response)
        environ[TRACED] = True
        exchange = _Exchange(environ)
        trace = self.integration.tracer(exchange.method, exchange.path)
        trace.request = exchange.recorded_request
        trace.start()
        try:
            body = self.app(environ, exchange.capture(start_response))
        except BaseException:
            trace.finish()
            raise
        # The body may still do work while it is sent (a generator streaming a
        # response): trace each chunk, with the tracer stopped in between.
        trace.suspend()
        return _TracedBody(body, exchange, trace)


class _Exchange:
    """What is kept of a request and its response: enough to replay the request and to
    check later that a change did not alter the response."""

    def __init__(self, environ):
        self.environ = environ
        self.method = environ.get("REQUEST_METHOD", "").upper()
        self.path = environ.get("REQUEST_URI") or _path(environ)
        self.body, self.body_truncated = _read_body(environ)
        self.status_code: int | None = None
        self.content_type: str | None = None
        self.response_body = bytearray()
        self.response_complete = False
        self.response_too_large = False

    def capture(self, start_response):
        def start_response_and_capture(status, headers, *args):
            self.status_code = int(status.split(" ", 1)[0])
            self.content_type = next(
                (value for name, value in headers if name.lower() == "content-type"), None
            )
            return start_response(status, headers, *args)

        return start_response_and_capture

    def add_response_chunk(self, chunk: bytes) -> None:
        if self.response_too_large:
            return
        self.response_body.extend(chunk)
        if len(self.response_body) > MAX_FINGERPRINT_BYTES:
            self.response_too_large = True
            self.response_body.clear()

    def recorded_request(self) -> RecordedRequest:
        environ = self.environ
        request = build_recorded_request(
            method=self.method,
            path=self.path,
            scheme=environ.get("wsgi.url_scheme", "http"),
            host=environ.get("HTTP_HOST") or _server_host(environ),
            headers=_headers(environ),
            body=self.body,
            body_truncated=self.body_truncated,
            status_code=self.status_code,
        )
        # A body that was not sent entirely (client gone, never read) has no fingerprint.
        if self.response_complete and not self.response_too_large:
            request.response = fingerprint(bytes(self.response_body), self.content_type)
        return request


class _TracedBody:
    """The app's response body, passed through to the server. Producing each chunk is
    traced; the trace is finished once the body is sent or closed."""

    def __init__(self, body, exchange: _Exchange, trace):
        self._body = body
        self._exchange = exchange
        self._trace = trace

    def __iter__(self):
        chunks = iter(self._body)
        while True:
            resumed = self._trace.resume()
            try:
                chunk = next(chunks)
            except StopIteration:
                self._exchange.response_complete = True
                break
            finally:
                if resumed:
                    self._trace.suspend()
            self._exchange.add_response_chunk(chunk)
            yield chunk
        self._trace.finish()

    def close(self) -> None:
        resumed = self._trace.resume()
        try:
            if hasattr(self._body, "close"):
                self._body.close()
        finally:
            if resumed:
                self._trace.finish()


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
