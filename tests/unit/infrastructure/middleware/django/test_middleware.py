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
