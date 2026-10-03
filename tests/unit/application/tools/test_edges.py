import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from profyle.application import tools
from profyle.domain.trace import RecordedRequest
from profyle.settings import settings
from tests.unit.application.analysis.test_digest import make_trace
from tests.unit.repository import InMemoryTraceRepository, store_trace


def request(base_url="http://127.0.0.1:9", **kwargs):
    return RecordedRequest(method="GET", path="/users", base_url=base_url, **kwargs)


def test_traces_without_data():
    repo = InMemoryTraceRepository()
    store_trace(raw_trace={}, name="GET /empty", repo=repo)

    assert tools.precompute_digests(repo) == 0
    with pytest.raises(tools.TraceNotFound, match="has no data"):
        tools.analyze_trace(repo, 1)


def test_empty_listings_explain_where_they_look():
    repo = InMemoryTraceRepository()
    assert "Reading traces from" in tools.slowest_endpoints(repo)

    store_trace(raw_trace=make_trace(), name="GET /users", repo=repo)
    assert "No matching traces" in tools.list_traces(repo, name_contains="orders")
    assert "'missing' was not called" in tools.call_details(repo, 1, "missing")


def test_request_summary_in_the_digest():
    repo = InMemoryTraceRepository()
    store_trace(raw_trace=make_trace(), name="GET /old", repo=repo)
    store_trace(
        raw_trace=make_trace(),
        name="POST /a",
        repo=repo,
        request=request(body="{}", body_encoding="utf-8"),
    )
    store_trace(
        raw_trace=make_trace(), name="POST /b", repo=repo, request=request(body_truncated=True)
    )

    assert "Request: not recorded (cannot be replayed)." in tools.analyze_trace(repo, 1)
    assert "body 2 chars · replayable" in tools.analyze_trace(repo, 2)
    assert "body too large to record · not replayable" in tools.analyze_trace(repo, 3)
    assert "no recorded request" in tools.replay_trace(repo, 1)


class _VaryingHandler(BaseHTTPRequestHandler):
    """A local app without Profyle whose body changes on every request."""

    def do_GET(self):  # noqa: N802
        body = f'{{"now": {time.time_ns()}}}'.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def plain_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _VaryingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_replay_against_an_app_that_records_nothing(plain_server):
    repo = InMemoryTraceRepository()
    store_trace(
        raw_trace=make_trace(),
        name="GET /users",
        repo=repo,
        request=request(base_url=plain_server, status_code=200),
    )

    result = tools.replay_trace(repo, 1, times=2, wait_seconds=0.3)

    assert "| 1 | 200 |" in result and "not recorded" in result
    assert "the body differs between runs" in result
    assert "no new trace was stored" in result


def test_doctor_reports_the_running_app(monkeypatch):
    repo = InMemoryTraceRepository()
    store_trace(
        raw_trace=make_trace(),
        name="GET /users",
        repo=repo,
        request=request(base_url="https://api.example.com"),
    )
    repo.store_runtime(
        {
            "framework": "FastAPI",
            "mode": "middleware",
            "pid": os.getpid(),
            "profyle": "0.4.0",
            "python": "3.11",
            "config": ["enabled = True"],
        }
    )

    report = tools.doctor(repo)

    assert "✓ App: FastAPI traced via ProfyleMiddleware" in report and "running" in report
    assert "Tip: `profyle run <command>`" in report
    assert "not local; replay is disabled" in report


@pytest.mark.parametrize(
    ("pid", "kill_error", "state"),
    [
        (None, None, "unknown state"),
        (2**22 + 7, None, "not running"),
        (1, PermissionError, "running"),
    ],
)
def test_doctor_process_states(monkeypatch, pid, kill_error, state):
    if kill_error:

        def kill(pid, signal):
            raise kill_error

        monkeypatch.setattr(os, "kill", kill)
    repo = InMemoryTraceRepository()
    repo.store_runtime({"framework": "Flask", "mode": "profyle run", "pid": pid, "config": []})

    report = tools.doctor(repo)

    assert f"traced via `profyle run` (pid {pid}, {state}" in report
    assert "Tip:" not in report


def test_doctor_warns_about_traces_in_the_old_location(tmp_path, monkeypatch):
    legacy = tmp_path / "old.db"
    with sqlite3.connect(legacy) as db:
        db.execute("CREATE TABLE traces (id INTEGER)")
        db.execute("INSERT INTO traces VALUES (1)")
    monkeypatch.setattr(settings, "get_legacy_db_path", lambda: str(legacy))

    assert "Found 1 traces in the old location" in tools.doctor(InMemoryTraceRepository())

    legacy.write_text("not a database")
    assert "old location" not in tools.doctor(InMemoryTraceRepository())


def test_doctor_without_an_old_database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "get_legacy_db_path", lambda: str(tmp_path / "none"))

    assert "old location" not in tools.doctor(InMemoryTraceRepository())
