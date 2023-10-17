from profyle.infrastructure.middleware.flask import ProfyleMiddleware
from tests.unit.repository import InMemoryTraceRepository


def test_should_trace_all_requests(flask_client, flask_app):
    trace_repo = InMemoryTraceRepository()
    flask_app.wsgi_app = ProfyleMiddleware(
        flask_app.wsgi_app,
        trace_repo=trace_repo
    )

    flask_client.post("/test")
    flask_client.get("/test?demo=true")

    assert len(trace_repo.traces) == 2
    assert trace_repo.traces[0].name == "POST /test"
    assert trace_repo.traces[1].name == "GET /test?demo=true"


def test_should_trace_filtered_requests(flask_client, flask_app):
    trace_repo = InMemoryTraceRepository()
    flask_app.wsgi_app = ProfyleMiddleware(
        flask_app.wsgi_app,
        trace_repo=trace_repo,
        pattern="/test*",
    )

    flask_client.post("/test")
    flask_client.get("/test?demo=true")
    flask_client.get("/other")

    assert len(trace_repo.traces) == 2
    assert trace_repo.traces[0].name == "POST /test"
    assert trace_repo.traces[1].name == "GET /test?demo=true"


def test_should_no_trace_if_disabled(flask_client, flask_app):
    trace_repo = InMemoryTraceRepository()
    flask_app.wsgi_app = ProfyleMiddleware(
        flask_app.wsgi_app,
        trace_repo=trace_repo,
        enabled=False,
    )

    flask_client.post("/test")
    flask_client.get("/test?demo=true")

    assert len(trace_repo.traces) == 0
