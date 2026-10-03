import os

from django.http import HttpResponse
from django.test import RequestFactory

from profyle.infrastructure.middleware.django import ProfyleMiddleware
from tests.unit.repository import InMemoryTraceRepository


def test_should_trace_a_request():
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        "tests.unit.infrastructure.middleware.django.settings"
    )
    request_factory = RequestFactory()
    req = request_factory.get('/test?demo=1')

    def get_response(request):
        resp = HttpResponse()
        resp.status_code = 200
        resp.content = b'Hello profyle!'
        return resp

    profyle = ProfyleMiddleware(get_response)
    repo = InMemoryTraceRepository()
    profyle.trace_repo = repo
    profyle(req)

    assert len(repo.traces) == 1
    assert repo.traces[0].name == "GET /test?demo=1"
    assert repo.traces[0].duration > 0
    assert "traceEvents" in repo.traces[0].data
    assert "file_info" in repo.traces[0].data
    assert "viztracer_metadata" in repo.traces[0].data


def test_should_record_the_request_for_replay():
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        "tests.unit.infrastructure.middleware.django.settings"
    )
    req = RequestFactory().post(
        '/orders?x=1', data='{"a": 1}', content_type="application/json",
        HTTP_AUTHORIZATION="Bearer secret",
    )

    def get_response(request):
        return HttpResponse(status=201)

    profyle = ProfyleMiddleware(get_response)
    repo = InMemoryTraceRepository()
    profyle.trace_repo = repo
    profyle(req)

    request = repo.traces[0].request
    assert request.method == "POST"
    assert request.path == "/orders?x=1"
    assert request.body == '{"a": 1}'
    assert request.headers["authorization"] == "[redacted]"
    assert request.status_code == 201
