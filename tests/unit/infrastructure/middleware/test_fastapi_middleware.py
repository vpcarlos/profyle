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


def test_should_record_the_request_for_replay(fastapi_client, fastapi_app):
    @fastapi_app.post("/items")
    async def create_item(item: dict):
        return item

    trace_repo = InMemoryTraceRepository()
    fastapi_app.add_middleware(ProfyleMiddleware, trace_repo=trace_repo)

    fastapi_client.post("items?x=1", json={"a": 1}, headers={"Authorization": "Bearer secret"})

    request = trace_repo.traces[0].request
    assert request.method == "POST"
    assert request.path == "/items?x=1"
    assert request.base_url == "http://testserver"
    assert request.body == '{"a":1}'
    assert request.headers["authorization"] == "[redacted]"
    assert request.status_code == 200


def test_should_trace_sync_endpoints_on_every_request(fastapi_app):
    from fastapi.testclient import TestClient

    from profyle.application.analysis.digest import build_digest

    def slow_lookup():
        return 42

    @fastapi_app.get("/sync")
    def sync_endpoint():
        return {"value": slow_lookup()}

    trace_repo = InMemoryTraceRepository()
    fastapi_app.add_middleware(ProfyleMiddleware, trace_repo=trace_repo)

    with TestClient(fastapi_app) as client:
        for _ in range(3):
            client.get("/sync")

    # The worker thread is reused after the first request; it must still be traced.
    for trace in trace_repo.traces:
        digest = build_digest(trace.data, top=1000)
        functions = {row["function"] for row in digest["top_inclusive"]}
        assert any(name.endswith("slow_lookup") for name in functions), trace.name
