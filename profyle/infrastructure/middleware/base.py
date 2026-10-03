"""What every integration (ASGI, WSGI, Django, `profyle run`) shares."""

import os
import sys
import time
from importlib.metadata import PackageNotFoundError, version

from profyle.application.profyle import profyle
from profyle.config import load_config
from profyle.domain.trace_repository import TraceRepository
from profyle.infrastructure.middleware.threadpool import trace_worker_threads

MIDDLEWARE = "middleware"
PROFYLE_RUN = "profyle run"


class Integration:
    """Resolves the configuration, owns the trace repository (opened lazily, so a
    disabled or idle Profyle never touches the database) and builds the tracer for each
    request."""

    def __init__(
        self,
        framework: str,
        trace_repo: TraceRepository | None = None,
        mode: str = MIDDLEWARE,
        **code_config,
    ):
        self.framework = framework
        self.mode = mode
        self.config = load_config(**code_config)
        self._repo = trace_repo
        self._registered = False
        if self.config.enabled:
            trace_worker_threads()

    @property
    def repo(self) -> TraceRepository:
        if self._repo is None:
            from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository

            self._repo = SQLiteTraceRepository()
        return self._repo

    @repo.setter
    def repo(self, repo: TraceRepository) -> None:
        self._repo = repo

    def tracer(self, name: str) -> profyle:
        if not self._registered:
            self.register()
        return profyle(
            name=name,
            repo=self.repo,
            pattern=self.config.pattern,
            max_stack_depth=self.config.max_stack_depth,
            min_duration=self.config.min_duration,
            on_stored=self._console_callback(),
        )

    def _console_callback(self):
        if not self.config.console:
            return None
        db_path = getattr(self.repo, "db_path", None)
        if not db_path:
            # The console worker reads traces back from the SQLite database.
            return None
        from profyle.infrastructure.console import reporter_for

        return reporter_for(db_path).report

    def register(self) -> None:
        """Tell `profyle doctor` which app writes traces and how it is configured."""
        if self._registered or not self.config.enabled:
            return
        self._registered = True
        try:
            self.repo.store_runtime(
                {
                    "framework": self.framework,
                    "mode": self.mode,
                    "pid": os.getpid(),
                    "python": sys.version.split()[0],
                    "profyle": _profyle_version(),
                    "started_at": time.time(),
                    "config": self.config.describe(),
                }
            )
        except Exception:
            pass  # diagnostics must never break the app


def _profyle_version() -> str:
    try:
        return version("profyle")
    except PackageNotFoundError:
        return "unknown"
