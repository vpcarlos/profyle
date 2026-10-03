"""Check that traces flow from the app to the tools, and say how to fix what doesn't."""

import os
import socket
import sqlite3
from typing import Any
from urllib.parse import urlsplit

from profyle.application.requests import sender
from profyle.domain.trace import Trace
from profyle.domain.trace_repository import TraceRepository
from profyle.settings import settings

# A check passed (True), failed (False) or is only informative (None).
Check = tuple[bool | None, str]


def doctor(repo: TraceRepository) -> str:
    traces = repo.list_traces()  # newest first
    checks = [
        _database_check(traces),
        *_old_database_checks(),
        *_runtime_checks(repo.get_runtime()),
        *_replay_checks(traces),
    ]
    lines = [f"{'✓' if ok else '✗' if ok is False else '•'} {text}" for ok, text in checks]
    ready = all(ok is not False for ok, _ in checks)
    lines.append("\nReady." if ready else "\nFix the ✗ items above, then run doctor again.")
    return "\n".join(lines)


def _database_check(traces: list[Trace]) -> Check:
    """Which database is read (and why), and whether the app has written to it."""
    db_path = settings.get_db_path()
    if os.getenv("PROFYLE_DB"):
        source = "PROFYLE_DB"
    elif os.getenv("PROFYLE_PROJECT_DIR"):
        source = "plugin project dir"
    else:
        source = "project root found from the working directory"
    if not traces:
        return False, (
            f"Database {db_path} ({source}) has no traces. Start the app from this project "
            "with `profyle run <command>` (for example `profyle run uvicorn main:app "
            "--reload`), or add ProfyleMiddleware, then make one request."
        )
    newest = traces[0]
    return True, (
        f"Database {db_path} ({source}): {len(traces)} traces, newest #{newest.id} "
        f"{newest.name} at {newest.timestamp} UTC."
    )


def _old_database_checks() -> list[Check]:
    """Before 0.4 traces were stored inside the installed package."""
    legacy_path = settings.get_legacy_db_path()
    legacy = _count_traces(legacy_path)
    if not legacy or legacy_path == settings.get_db_path():
        return []
    return [
        (
            False,
            f"Found {legacy} traces in the old location {legacy_path}: the app is probably "
            "running an older Profyle. Upgrade it in the app's environment and restart.",
        )
    ]


def _replay_checks(traces: list[Trace]) -> list[Check]:
    if not traces:
        return []
    replayable = next((t for t in traces if t.request), None)
    if replayable is None:
        return [
            (
                False,
                "Traces have no recorded request, so they cannot be replayed. "
                "The app runs an older Profyle: upgrade and restart it.",
            )
        ]
    return [
        (True, "Requests are recorded, so they can be replayed."),
        _app_reachable(replayable.request.base_url),
    ]


def _runtime_checks(runtime: dict[str, Any] | None) -> list[Check]:
    """What the app reported about itself when it started writing traces."""
    if not runtime:
        return []
    alive = _process_alive(runtime.get("pid"))
    state = {True: "running", False: "not running", None: "unknown state"}[alive]
    how = "`profyle run`" if runtime.get("mode") == "profyle run" else "ProfyleMiddleware"
    checks: list[Check] = [
        (
            True if alive is not False else None,
            f"App: {runtime.get('framework')} traced via {how} (pid {runtime.get('pid')}, "
            f"{state}; Profyle {runtime.get('profyle')}, Python {runtime.get('python')}).",
        ),
        (None, "Configuration: " + "; ".join(runtime.get("config", []))),
    ]
    if runtime.get("mode") != "profyle run":
        checks.append((None, "Tip: `profyle run <command>` traces the app without code changes."))
    checks.append(
        (
            None,
            "Make sure the app auto-reloads code changes (uvicorn --reload, flask --debug, "
            "manage.py runserver); otherwise it must be restarted before verifying a fix.",
        )
    )
    return checks


def _process_alive(pid: Any) -> bool | None:
    if not isinstance(pid, int) or os.name == "nt":
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _count_traces(path: str) -> int:
    if not os.path.exists(path):
        return 0
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            return db.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
    except sqlite3.Error:
        return 0


def _app_reachable(base_url: str) -> Check:
    parts = urlsplit(base_url)
    host = parts.hostname or "localhost"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if not sender.is_local(base_url):
        return None, f"The app was reached at {base_url}, which is not local; replay is disabled."
    try:
        with socket.create_connection((host, port), timeout=1):
            return True, f"The app is running at {base_url}."
    except OSError:
        return False, (
            f"Nothing is listening at {base_url}. Start the app, with auto-reload, "
            "e.g. `profyle run uvicorn main:app --reload`, so requests can be "
            "replayed."
        )
