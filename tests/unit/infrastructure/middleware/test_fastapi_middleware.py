from profyle.fastapi import ProfyleMiddleware
from tests.unit.repository import InMemoryTraceRepository


def test_should_trace_all_requests(fastapi_client, fastapi_app):
    trace_repo = InMemoryTraceRepository()
    fastapi_app.add_middleware(
        ProfyleMiddleware,
        trace_repo=trace_repo
    )

    fastapi_client.post("test")
    fastapi_client.get("test?demo=true")

    assert len(trace_repo.traces) == 2
    assert trace_repo.traces[0].name == "POST /test"
    assert trace_repo.traces[1].name == "GET /test?demo=true"


def test_should_trace_filtered_requests(monkeypatch, fastapi_client, fastapi_app):
    monkeypatch.setenv("PROFYLE_PATTERN", "/test*")
    trace_repo = InMemoryTraceRepository()
    fastapi_app.add_middleware(
        ProfyleMiddleware,
        pattern="/test*",
        trace_repo=trace_repo
    )

    fastapi_client.post("test")
    fastapi_client.get("test?demo=true")
    fastapi_client.get("other")

    assert len(trace_repo.traces) == 2
    assert trace_repo.traces[0].name == "POST /test"
    assert trace_repo.traces[1].name == "GET /test?demo=true"


def test_should_no_trace_if_disabled(fastapi_client, fastapi_app):
    trace_repo = InMemoryTraceRepository()
    fastapi_app.add_middleware(
        ProfyleMiddleware,
        enabled=False,
        trace_repo=InMemoryTraceRepository()
    )

    fastapi_client.post("test")
    fastapi_client.get("test?demo=true")

    assert len(trace_repo.traces) == 0
