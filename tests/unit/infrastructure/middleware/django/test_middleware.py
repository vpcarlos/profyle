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
        return HttpResponse(b'{"ok": true}', status=201, content_type="application/json")

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
    assert request.response.size == len(b'{"ok": true}')


async def test_should_trace_async_views_under_asgi_on_every_request():
    """Under ASGI Django runs this (sync) middleware in a worker thread and async views
    back on the event loop thread; both, and sync_to_async code, must be traced."""
    import asyncio

    from asgiref.sync import async_to_sync, sync_to_async

    from profyle.application.analysis.digest import build_digest

    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        "tests.unit.infrastructure.middleware.django.settings"
    )

    def lookup_in_pool(i):
        return i

    async def lookup(i):
        await asyncio.sleep(0)
        return await sync_to_async(lookup_in_pool, thread_sensitive=False)(i)

    async def async_view(request):
        return HttpResponse(str([await lookup(i) for i in range(3)]))

    middleware = ProfyleMiddleware(async_to_sync(async_view))
    repo = InMemoryTraceRepository()
    middleware.trace_repo = repo

    for _ in range(3):
        await sync_to_async(middleware)(RequestFactory().get("/async"))

    assert len(repo.traces) == 3
    for trace in repo.traces:
        calls = {
            row["function"].rsplit(".", 1)[-1]: row["calls"]
            for row in build_digest(trace.data, top=1000)["top_inclusive"]
        }
        assert calls.get("lookup_in_pool") == 3, calls
        assert calls.get("lookup", 0) >= 3, calls


def test_disabled_middleware_still_returns_the_response():
    from django.test import override_settings

    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE", "tests.unit.infrastructure.middleware.django.settings"
    )
    repo = InMemoryTraceRepository()
    with override_settings(PROFYLE_ENABLED=False):
        middleware = ProfyleMiddleware(lambda request: HttpResponse("ok"))
        middleware.trace_repo = repo
        response = middleware(RequestFactory().get("/x"))

    assert response.content == b"ok"
    assert repo.traces == []


def test_reads_profyle_min_duration_and_warns_on_old_setting():
    import pytest
    from django.test import override_settings

    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE", "tests.unit.infrastructure.middleware.django.settings"
    )
    with override_settings(PROFYLE_MIN_DURATION=5):
        assert ProfyleMiddleware(lambda r: None).integration.config.min_duration == 5

    with override_settings(MIN_DURATION=7):
        with pytest.warns(DeprecationWarning, match="PROFYLE_MIN_DURATION"):
            middleware = ProfyleMiddleware(lambda r: None)
    assert middleware.integration.config.min_duration == 7
