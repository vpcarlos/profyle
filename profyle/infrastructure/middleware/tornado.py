"""Tornado integration.

Tornado is neither ASGI nor WSGI, so instead of a middleware Profyle wraps the
execution of each request handler (`RequestHandler._execute`, which covers prepare(),
the HTTP method and finish(), including async handlers):

    from profyle.tornado import instrument

    app = instrument(tornado.web.Application([...]))

`profyle run` does the same for every Tornado application without code changes, also
under gunicorn's tornado worker.
"""

from typing import Any

from tornado.web import Application, RequestHandler

from profyle.application.requests.capture import MAX_BODY_BYTES, build_recorded_request
from profyle.application.requests.fingerprint import MAX_FINGERPRINT_BYTES, fingerprint
from profyle.domain.trace import RecordedRequest
from profyle.domain.trace_repository import TraceRepository
from profyle.infrastructure.middleware.base import MIDDLEWARE, PROFYLE_RUN, Integration

INTEGRATION = "_profyle_integration"

_original_execute = None
_original_flush = None
# Set by `profyle run`: trace every Tornado application that was not instrumented.
_auto = False


def instrument(
    app: Application,
    enabled: bool | None = None,
    pattern: str | None = None,
    max_stack_depth: int | None = None,
    min_duration: float | None = None,
    console: bool | None = None,
    trace_repo: TraceRepository | None = None,
) -> Application:
    """Trace every request of a Tornado application. Settings left as None come from
    PROFYLE_* environment variables, `[tool.profyle]` in pyproject.toml or defaults."""
    _patch_request_handler()
    setattr(
        app,
        INTEGRATION,
        Integration(
            "Tornado",
            trace_repo=trace_repo,
            mode=MIDDLEWARE,
            enabled=enabled,
            pattern=pattern,
            max_stack_depth=max_stack_depth,
            min_duration=min_duration,
            console=console,
        ),
    )
    return app


def enable_auto() -> None:
    """Used by `profyle run`."""
    global _auto
    _auto = True
    _patch_request_handler()


def _integration_for(app: Application) -> Integration | None:
    integration = getattr(app, INTEGRATION, None)
    if integration is None and _auto:
        integration = Integration("Tornado", mode=PROFYLE_RUN)
        setattr(app, INTEGRATION, integration)
    return integration


def _patch_request_handler() -> None:
    global _original_execute, _original_flush
    if _original_execute is not None:
        return
    _original_execute = RequestHandler._execute
    _original_flush = RequestHandler.flush

    async def _execute(self: RequestHandler, transforms, *args, **kwargs):
        integration = _integration_for(self.application)
        if integration is None or not integration.config.enabled:
            return await _original_execute(self, transforms, *args, **kwargs)
        request = self.request
        self._profyle_response = []
        with integration.tracer(request.method, request.uri) as trace:
            try:
                return await _original_execute(self, transforms, *args, **kwargs)
            finally:
                trace.request = lambda: _recorded_request(self)

    def flush(self: RequestHandler, include_footers: bool = False):
        captured = getattr(self, "_profyle_response", None)
        if captured is not None and sum(map(len, captured)) <= MAX_FINGERPRINT_BYTES:
            # Taken before transforms such as gzip: the body a replay receives.
            captured.append(b"".join(self._write_buffer))
        return _original_flush(self, include_footers)

    RequestHandler._execute = _execute
    RequestHandler.flush = flush


def _recorded_request(handler: RequestHandler) -> RecordedRequest:
    request = handler.request
    body: Any = request.body or None
    truncated = bool(body) and len(body) > MAX_BODY_BYTES
    recorded = build_recorded_request(
        method=request.method or "",
        path=request.uri or "/",
        scheme=request.protocol,
        host=request.host,
        headers=list(request.headers.get_all()),
        body=None if truncated else body,
        body_truncated=truncated,
        status_code=handler.get_status(),
    )
    response = b"".join(getattr(handler, "_profyle_response", None) or [])
    if len(response) <= MAX_FINGERPRINT_BYTES:
        recorded.response = fingerprint(response, handler._headers.get("Content-Type"))
    return recorded
