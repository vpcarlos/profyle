import os

from django.http import HttpResponse, StreamingHttpResponse
from django.test import RequestFactory

from profyle.application.request_capture import MAX_BODY_BYTES
from profyle.infrastructure.middleware.django import ProfyleMiddleware
from tests.unit.repository import InMemoryTraceRepository

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "tests.unit.infrastructure.middleware.django.settings"
)


def traced(view, request):
    middleware = ProfyleMiddleware(view)
    repo = InMemoryTraceRepository()
    middleware.trace_repo = repo
    assert middleware.trace_repo is repo
    middleware(request)
    return repo.traces[0].request


def test_body_limits():
    factory = RequestFactory()

    bad_length = factory.post("/a", data="x", content_type="text/plain")
    bad_length.META["CONTENT_LENGTH"] = "oops"
    assert traced(lambda r: HttpResponse("ok"), bad_length).body is None

    too_large = factory.post("/a", data="x" * (MAX_BODY_BYTES + 1), content_type="text/plain")
    assert traced(lambda r: HttpResponse("ok"), too_large).body_truncated


def test_body_consumed_as_a_stream_by_the_view():
    def view(request):
        request.read()
        return HttpResponse("ok")

    request = RequestFactory().post("/a", data="payload", content_type="text/plain")
    assert traced(view, request).body_truncated


def test_streaming_responses_get_no_fingerprint():
    request = RequestFactory().get("/a")
    recorded = traced(lambda r: StreamingHttpResponse(iter([b"a", b"b"])), request)
    assert recorded.response is None
