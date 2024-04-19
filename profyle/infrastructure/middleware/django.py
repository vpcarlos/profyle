from typing import Any, Callable, Optional

from django.conf import settings
from django.http import HttpRequest

from profyle.application.profyle import profyle
from profyle.domain.trace_repository import TraceRepository
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository


def get_setting(name, default=None) -> Any:
    return getattr(settings, name, default)


class ProfyleMiddleware:
    def __init__(self, get_response: Callable):
        self.get_response = get_response
        self.enabled: bool = get_setting("PROFYLE_ENABLED", True)
        self.pattern: Optional[str] = get_setting("PROFYLE_PATTERN", None)
        self.max_stack_depth: int = get_setting("PROFYLE_MAX_STACK_DEPTH", -1)
        self.min_duration: int = get_setting("MIN_DURATION", 0)
        self.trace_repo: TraceRepository = SQLiteTraceRepository()

    def __call__(self, request: HttpRequest):
        profyle_enabled = self.enabled
        is_http = request.scheme and request.scheme.startswith("http")
        method = request.method and request.method.upper()

        if profyle_enabled and is_http and method:
            with profyle(
                name=f"{method} {request.get_full_path()}",
                pattern=self.pattern,
                repo=self.trace_repo,
                max_stack_depth=self.max_stack_depth,
                min_duration=self.min_duration,
            ):
                return self.get_response(request)
