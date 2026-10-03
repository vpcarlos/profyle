from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.http import HttpRequest
from django.http.request import RawPostDataException

from profyle.application.profyle import profyle
from profyle.application.request_capture import MAX_BODY_BYTES, build_recorded_request
from profyle.application.response_fingerprint import MAX_FINGERPRINT_BYTES, fingerprint
from profyle.domain.trace import RecordedRequest
from profyle.domain.trace_repository import TraceRepository
from profyle.infrastructure.middleware.threadpool import trace_worker_threads
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository


def get_setting(name: str, default: Any|None = None) -> Any:
    return getattr(settings, name, default)


class ProfyleMiddleware:
    def __init__(self, get_response: Callable):
        self.get_response = get_response
        self.enabled: bool = get_setting("PROFYLE_ENABLED", True)
        self.pattern: str|None = get_setting("PROFYLE_PATTERN", None)
        self.max_stack_depth: int = get_setting("PROFYLE_MAX_STACK_DEPTH", -1)
        self.min_duration: int = get_setting("MIN_DURATION", 0)
        self.trace_repo: TraceRepository = SQLiteTraceRepository()
        if self.enabled:
            trace_worker_threads()

    def __call__(self, request: HttpRequest):
        profyle_enabled = self.enabled
        is_http = request.scheme and request.scheme.startswith("http")
        method = request.method and request.method.upper()

        if profyle_enabled and is_http and method:
            response = None
            with profyle(
                name=f"{method} {request.get_full_path()}",
                pattern=self.pattern,
                repo=self.trace_repo,
                max_stack_depth=self.max_stack_depth,
                min_duration=self.min_duration,
            ) as trace:
                try:
                    response = self.get_response(request)
                    return response
                finally:
                    trace.request = lambda: _recorded_request(request, response)


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
