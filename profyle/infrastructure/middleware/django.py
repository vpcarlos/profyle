import warnings
from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.http import HttpRequest
from django.http.request import RawPostDataException

from profyle.application.request_capture import MAX_BODY_BYTES, build_recorded_request
from profyle.application.response_fingerprint import MAX_FINGERPRINT_BYTES, fingerprint
from profyle.domain.trace import RecordedRequest
from profyle.infrastructure.middleware.base import MIDDLEWARE, TRACED, Integration, Middleware


def get_setting(name: str, default: Any | None = None) -> Any:
    return getattr(settings, name, default)


def _min_duration_setting() -> Any:
    value = get_setting("PROFYLE_MIN_DURATION")
    if value is None and get_setting("MIN_DURATION") is not None:
        warnings.warn(
            "The MIN_DURATION setting is deprecated; use PROFYLE_MIN_DURATION.",
            DeprecationWarning,
            stacklevel=3,
        )
        value = get_setting("MIN_DURATION")
    return value


class ProfyleMiddleware(Middleware):
    """Add "profyle.django.ProfyleMiddleware" to MIDDLEWARE (first, to trace the rest).

    PROFYLE_* Django settings act as code configuration; environment variables and
    `[tool.profyle]` in pyproject.toml work as for the other integrations.
    """

    mode = MIDDLEWARE

    def __init__(self, get_response: Callable):
        self.get_response = get_response
        self.integration = Integration(
            "Django",
            mode=self.mode,
            enabled=get_setting("PROFYLE_ENABLED"),
            pattern=get_setting("PROFYLE_PATTERN"),
            max_stack_depth=get_setting("PROFYLE_MAX_STACK_DEPTH"),
            min_duration=_min_duration_setting(),
            console=get_setting("PROFYLE_CONSOLE"),
        )

    def __call__(self, request: HttpRequest):
        method = request.method and request.method.upper()
        if not self.integration.config.enabled or not method or _already_traced(request):
            return self.get_response(request)
        request.META[TRACED] = True

        response = None
        with self.integration.tracer(method, request.get_full_path()) as trace:
            try:
                response = self.get_response(request)
                return response
            finally:
                trace.request = lambda: _recorded_request(request, response)


class AutoProfyleMiddleware(ProfyleMiddleware):
    """Inserted by `profyle run`; same as ProfyleMiddleware but reported as such."""

    mode = "profyle run"

    def __init__(self, get_response: Callable):
        super().__init__(get_response)
        self.integration.register()


def _already_traced(request: HttpRequest) -> bool:
    # WSGI: META is the environ. ASGI: Django keeps the scope on the request.
    return bool(request.META.get(TRACED) or getattr(request, "scope", {}).get(TRACED))


def _recorded_request(request: HttpRequest, response: Any) -> RecordedRequest:
    # Read the body only after the view ran: reading it first could break views
    # that consume request.stream themselves.
    body, truncated = None, False
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length > MAX_BODY_BYTES:
        truncated = True
    elif length > 0:
        try:
            body = request.body
        except RawPostDataException:
            truncated = True
    try:
        host = request.get_host()
    except DisallowedHost:
        host = request.META.get("SERVER_NAME", "localhost")
    recorded = build_recorded_request(
        method=request.method or "",
        path=request.get_full_path(),
        scheme=request.scheme or "http",
        host=host,
        headers=request.headers.items(),
        body=body,
        body_truncated=truncated,
        status_code=getattr(response, "status_code", None),
    )
    content = None if getattr(response, "streaming", True) else response.content
    if content is not None and len(content) <= MAX_FINGERPRINT_BYTES:
        recorded.response = fingerprint(content, response.get("Content-Type"))
    return recorded
