"""One line per traced request in the app's console:

    profyle ▸ GET /orders 245.1 ms · #12 · repeated: list_orders → get_customer ×100 (83%)

Building the line needs the trace digest, which can take a while on big traces. It runs
in a separate worker process that reads the trace from the database, so the app's
requests never wait for it nor compete with it for the GIL. The worker exits when the
app does (its stdin closes).
"""

import os
import subprocess
import sys
import threading

PREFIX = "profyle ▸"


class ConsoleReporter:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._process: subprocess.Popen | None = None
        self._failed = False
        self._lock = threading.Lock()
        self._reported = 0

    def report(self, trace_id: int) -> None:
        if self._failed:
            return
        with self._lock:
            # The first request of a process pays for imports, caches and connections.
            first = " first" if self._reported == 0 else ""
            self._reported += 1
            try:
                if self._process is None or self._process.poll() is not None:
                    self._process = self._start()
                self._process.stdin.write(f"{trace_id}{first}\n")
                self._process.stdin.flush()
            except (OSError, ValueError):
                # Never let the console line break the app.
                self._failed = True

    def _start(self) -> subprocess.Popen:
        env = dict(os.environ, PROFYLE_DB=self.db_path, PROFYLE_RUN="0")
        return subprocess.Popen(
            [sys.executable, "-m", "profyle.infrastructure.console"],
            stdin=subprocess.PIPE,
            env=env,
            text=True,
        )


_reporters: dict[str, ConsoleReporter] = {}


def reporter_for(db_path: str) -> ConsoleReporter:
    if db_path not in _reporters:
        _reporters[db_path] = ConsoleReporter(db_path)
    return _reporters[db_path]


def display_path(path: str) -> str:
    """A path relative to the working directory when it is inside it."""
    try:
        relative = os.path.relpath(path)
    except ValueError:  # another drive on Windows
        return path
    return path if relative.startswith("..") else relative


def say(message: str) -> None:
    """Print a Profyle message to the app's console (stderr, like server logs).

    Written to the stream directly: while a request is traced, VizTracer replaces print()
    to record what the app prints, which would swallow the message."""
    try:
        sys.stderr.write(f"{PREFIX} {message}\n")
    except UnicodeEncodeError:
        sys.stderr.write(f"profyle > {message}\n".encode("ascii", "replace").decode())
    sys.stderr.flush()


def _worker() -> None:
    from profyle.application import tools
    from profyle.infrastructure.sqlite3.get_connection import get_connection
    from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository

    repo = SQLiteTraceRepository(get_connection())
    for line in sys.stdin:
        trace_id, _, flag = line.strip().partition(" ")
        try:
            summary = tools.summary_line(repo, int(trace_id))
            if flag == "first":
                summary += " · first request, includes warm-up"
            say(summary)
        except Exception as error:  # a bad trace must not stop the next lines
            say(f"trace {trace_id}: could not summarize ({error})")


if __name__ == "__main__":
    _worker()
