from profyle.infrastructure.middleware.flask import ProfyleMiddleware
from tests.unit.repository import InMemoryTraceRepository

# WSGI traces end once the response body has been sent, so the tests read it (get_data)
# as a real client does; see test_wsgi_streaming for bodies that are never read.


def test_should_trace_all_requests(flask_client, flask_app):
    trace_repo = InMemoryTraceRepository()
    flask_app.wsgi_app = ProfyleMiddleware(flask_app.wsgi_app, trace_repo=trace_repo)

    flask_client.post("/test").get_data()
    flask_client.get("/test?demo=true").get_data()

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

    flask_client.post("/test").get_data()
    flask_client.get("/test?demo=true").get_data()
    flask_client.get("/other").get_data()

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

    flask_client.post("/test").get_data()
    flask_client.get("/test?demo=true").get_data()

    assert len(trace_repo.traces) == 0


def test_should_record_the_request_and_keep_the_body_readable(flask_app):
    from flask import request

    bodies = []

    @flask_app.route("/echo", methods=["POST"])
    def echo():
        bodies.append(request.get_data())
        return "created", 201

    trace_repo = InMemoryTraceRepository()
    flask_app.wsgi_app = ProfyleMiddleware(flask_app.wsgi_app, trace_repo=trace_repo)

    flask_app.test_client().post("/echo?x=1", data=b"payload", content_type="text/plain").get_data()

    assert bodies == [b"payload"]
    request_info = trace_repo.traces[0].request
    assert request_info.method == "POST"
    assert request_info.path == "/echo?x=1"
    assert request_info.body == "payload"
    assert request_info.headers["content-type"] == "text/plain"
    assert request_info.status_code == 201
