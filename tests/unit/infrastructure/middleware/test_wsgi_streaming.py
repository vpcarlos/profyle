"""WSGI traces cover the response body: work done while a generator streams it is traced,
and a body nobody reads never leaves the tracer running."""

import builtins
import io

import pytest

from profyle.application import request_trace
from profyle.wsgi import ProfyleMiddleware
from tests.unit.repository import InMemoryTraceRepository


def render_row(number):
    return f"row {number}\n".encode()


def streaming_app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])
    for number in range(3):
        yield render_row(number)


def failing_app(environ, start_response):
    raise RuntimeError("boom")


def request(middleware, path="/rows"):
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "wsgi.url_scheme": "http",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
        "wsgi.input": io.BytesIO(b""),
    }
    return middleware(environ, lambda status, headers: None)


def traced(app):
    repo = InMemoryTraceRepository()
    return ProfyleMiddleware(app, trace_repo=repo, console=False), repo


def function_calls(trace):
    return [
        event["name"].split(" (")[0]
        for event in trace.data["traceEvents"]
        if event.get("ph") == "X"
    ]


def test_streamed_body_is_traced_and_fingerprinted():
    middleware, repo = traced(streaming_app)

    body = request(middleware)
    assert repo.traces == []  # the body has not been sent yet
    sent = b"".join(body)
    body.close()

    assert sent == b"row 0\nrow 1\nrow 2\n"
    [trace] = repo.traces
    assert function_calls(trace).count("render_row") == 3
    assert trace.request.response.size == len(sent)


def test_the_tracer_is_stopped_between_chunks():
    middleware, repo = traced(streaming_app)
    original_print = builtins.print

    chunks = iter(request(middleware))
    next(chunks)

    # Between chunks the app's process runs untraced.
    assert request_trace.active_tracer() is None
    assert builtins.print is original_print
    list(chunks)
    assert len(repo.traces) == 1


def test_a_body_that_is_never_read_is_finished_by_the_next_request():
    middleware, repo = traced(streaming_app)

    request(middleware, "/abandoned")  # a test client that ignores the body
    b"".join(request(middleware, "/read"))

    assert [t.name for t in repo.traces] == ["GET /abandoned", "GET /read"]
    abandoned = repo.traces[0]
    assert "render_row" not in function_calls(abandoned)
    assert abandoned.request.response is None  # the body was never sent


def test_a_body_that_is_never_read_is_stored_at_exit():
    middleware, repo = traced(streaming_app)

    request(middleware)
    request_trace._finish_abandoned_trace()

    assert [t.name for t in repo.traces] == ["GET /rows"]
    request_trace._finish_abandoned_trace()  # nothing left to finish


def test_closing_a_partly_sent_body_finishes_the_trace_without_fingerprint():
    middleware, repo = traced(streaming_app)

    body = request(middleware)
    next(iter(body))
    body.close()

    [trace] = repo.traces
    assert trace.request.response is None


def test_closing_an_unread_list_body():
    def list_app(environ, start_response):
        start_response("204 No Content", [])
        return []

    middleware, repo = traced(list_app)
    request(middleware).close()

    assert repo.traces[0].request.status_code == 204


def test_an_app_that_raises_still_stores_its_trace():
    middleware, repo = traced(failing_app)

    with pytest.raises(RuntimeError, match="boom"):
        request(middleware)

    assert [t.name for t in repo.traces] == ["GET /rows"]


def test_large_bodies_get_no_fingerprint():
    from profyle.application.requests.fingerprint import MAX_FINGERPRINT_BYTES

    def large_app(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/plain")])
        yield b"x" * MAX_FINGERPRINT_BYTES
        yield b"x"
        yield b"x"

    middleware, repo = traced(large_app)
    b"".join(request(middleware))

    assert repo.traces[0].request.response is None
