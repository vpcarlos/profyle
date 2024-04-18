import os
from typing import Optional

from starlette.types import ASGIApp, Receive, Scope, Send

from profyle.application.profyle import profyle
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository


class ProfyleMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        enabled: bool = True,
        pattern: Optional[str] = None,
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

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.enabled and scope["type"] == "http":
            method = scope.get("method", "").upper()
            path = scope.get("raw_path", b"").decode("utf-8")
            with profyle(
                name=f"{method} {path}",
                pattern=self.pattern,
                repo=self.trace_repo,
                max_stack_depth=self.max_stack_depth,
                min_duration=self.min_duration,
            ):
                await self.app(scope, receive, send)
            return
        await self.app(scope, receive, send)
