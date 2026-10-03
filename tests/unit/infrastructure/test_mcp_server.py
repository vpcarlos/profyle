import asyncio

import pytest

from profyle.infrastructure import mcp_server


def test_tools_are_registered():
    names = {tool.name for tool in asyncio.run(mcp_server.server.list_tools())}

    assert names == {
        "doctor", "list_traces", "slowest_endpoints", "analyze_trace", "get_call_details",
        "get_function_source", "compare_traces", "replay_request",
    }


def test_tools_answer_from_the_project_database(project_db):
    assert "✓ Database" in mcp_server.doctor()
    assert "| 2 | GET /users" in mcp_server.list_traces(name_contains="users")
    assert "| GET /users | 2 |" in mcp_server.slowest_endpoints()
    assert "Trace digest — #1 GET /users" in mcp_server.analyze_trace(1)
    assert '"calls": 12' in mcp_server.get_call_details(1, "get_user")
    assert "def handler" in mcp_server.get_function_source(1, "handler")
    assert "function_deltas" in mcp_server.compare_traces(1, 2)
    assert "Could not reach the app" in mcp_server.replay_request(1)


def test_unknown_trace_is_a_message_not_an_error(project_db):
    assert mcp_server.analyze_trace(99) == "Trace 99 not found"


def test_run_starts_the_digest_worker_and_the_stdio_server(monkeypatch):
    started = []
    monkeypatch.setattr(mcp_server.threading, "Thread", lambda target, daemon: started.append(
        (target, daemon)) or type("T", (), {"start": lambda self: None})())
    monkeypatch.setattr(mcp_server.server, "run", lambda transport: started.append(transport))

    mcp_server.run()

    assert started == [(mcp_server._precompute_digests_forever, True), "stdio"]


def test_digest_worker_survives_errors(project_db, monkeypatch):
    calls = []

    def precompute(repo, limit):
        calls.append(limit)
        if len(calls) == 1:
            raise RuntimeError("broken trace")

    class Stop(Exception):
        pass

    def sleep(seconds):
        if len(calls) >= 2:
            raise Stop

    monkeypatch.setattr(mcp_server.toolkit, "precompute_digests", precompute)
    monkeypatch.setattr(mcp_server.time, "sleep", sleep)

    with pytest.raises(Stop):
        mcp_server._precompute_digests_forever()

    assert calls == [20, 20]
