import threading
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest
from flask import Flask, request

from profyle.application import replay
from profyle.application.analysis import toolkit
from profyle.domain.trace import RecordedRequest
from profyle.flask import ProfyleMiddleware
from tests.unit.repository import InMemoryTraceRepository


def recorded(method="GET", base_url="http://127.0.0.1:8000", **kwargs):
    return RecordedRequest(method=method, path="/orders", base_url=base_url, **kwargs)


def test_refuses_unsafe_methods_without_permission():
    with pytest.raises(replay.ReplayRefused, match="side effects"):
        replay.check_replayable(recorded("POST"), "http://127.0.0.1:8000", False)

    replay.check_replayable(recorded("POST"), "http://127.0.0.1:8000", True)


def test_refuses_remote_hosts(monkeypatch):
    with pytest.raises(replay.ReplayRefused, match="only local hosts"):
        replay.check_replayable(recorded(), "https://api.example.com", False)

    monkeypatch.setenv("PROFYLE_REPLAY_ALLOW_REMOTE", "true")
    replay.check_replayable(recorded(), "https://api.example.com", False)


def test_refuses_requests_whose_body_was_not_recorded():
    with pytest.raises(replay.ReplayRefused, match="64 KB"):
        replay.check_replayable(
            recorded(body_truncated=True), "http://127.0.0.1:8000", False
        )


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def traced_server():
    """A real HTTP server running a Flask app behind ProfyleMiddleware."""
    app = Flask("replay_test")
    received = []

    @app.post("/orders")
    def create_order():
        received.append(request.get_json())
        if request.headers.get("Authorization") != "Bearer token":
            return {"error": "unauthorized"}, 401
        return {"ok": True}, 201

    repo = InMemoryTraceRepository()
    app.wsgi_app = ProfyleMiddleware(app.wsgi_app, trace_repo=repo)
    server = make_server("127.0.0.1", 0, app, handler_class=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", repo, received
    server.shutdown()


def test_replay_sends_the_same_request_and_reports_the_new_trace(traced_server):
    import urllib.request

    base_url, repo, received = traced_server
    urllib.request.urlopen(
        urllib.request.Request(
            f"{base_url}/orders",
            data=b'{"customer_id": 7}',
            headers={"Content-Type": "application/json", "Authorization": "Bearer token"},
            method="POST",
        )
    )
    [original] = repo.traces
    assert original.request.status_code == 201
    assert original.request.headers["authorization"] == "[redacted]"

    refused = toolkit.replay_trace(repo, original.id)
    assert "side effects" in refused

    without_auth = toolkit.replay_trace(repo, original.id, allow_unsafe_method=True)
    assert "Status changed: original 201, now 401" in without_auth
    assert "authorization" in without_auth

    result = toolkit.replay_trace(
        repo,
        original.id,
        times=2,
        headers={"Authorization": "Bearer token"},
        allow_unsafe_method=True,
    )
    assert "| 1 | 201 |" in result and "| 2 | 201 |" in result
    assert f"compare_traces({original.id}, {repo.traces[-1].id})" in result
    assert received == [{"customer_id": 7}] * 4


def test_replay_reports_unreachable_app():
    repo = InMemoryTraceRepository()
    from profyle.application.trace.store import store_trace

    store_trace(
        raw_trace={"traceEvents": []},
        name="GET /orders",
        repo=repo,
        request=recorded(base_url="http://127.0.0.1:9"),
    )

    result = toolkit.replay_trace(repo, repo.traces[0].id)

    assert "Could not reach the app" in result
