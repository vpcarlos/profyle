import asyncio
import json

import pytest
import tornado.httpserver
import tornado.testing
import tornado.web
from tornado.httpclient import AsyncHTTPClient

from profyle.application.analysis.digest import build_digest
from profyle.tornado import instrument
from tests.unit.repository import InMemoryTraceRepository


def blocking_lookup(i):
    return {"id": i}


class ItemsHandler(tornado.web.RequestHandler):
    async def get(self):
        loop = asyncio.get_running_loop()
        # Blocking work in a thread pool, the usual Tornado pattern.
        items = [await loop.run_in_executor(None, blocking_lookup, i) for i in range(3)]
        self.write({"items": items})

    def post(self):
        self.set_status(201)
        self.write({"received": json.loads(self.request.body)})


async def serve(app):
    sock, port = tornado.testing.bind_unused_port()
    server = tornado.httpserver.HTTPServer(app)
    server.add_sockets([sock])
    return server, f"http://127.0.0.1:{port}"


async def test_traces_tornado_requests_with_request_and_response():
    repo = InMemoryTraceRepository()
    app = instrument(tornado.web.Application([(r"/items", ItemsHandler)]), trace_repo=repo)
    server, base_url = await serve(app)
    client = AsyncHTTPClient()
    try:
        for _ in range(2):
            await client.fetch(f"{base_url}/items?x=1")
        await client.fetch(
            f"{base_url}/items",
            method="POST",
            body='{"a": 1}',
            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
        )
    finally:
        server.stop()

    assert [t.name for t in repo.traces] == ["GET /items?x=1", "GET /items?x=1", "POST /items"]
    for trace in repo.traces[:2]:
        calls = {
            row.function: row.calls for row in build_digest(trace.data, top=1000).top_inclusive
        }
        # run_in_executor threads are traced on every request.
        assert calls.get("blocking_lookup") == 3, calls
    post = repo.traces[2].request
    assert (post.method, post.status_code, post.body) == ("POST", 201, '{"a": 1}')
    assert post.headers["authorization"] == "[redacted]"
    assert post.response.content_type.startswith("application/json")
    assert post.response.shape is not None


async def test_disabled_by_environment(monkeypatch):
    monkeypatch.setenv("PROFYLE_ENABLED", "false")
    repo = InMemoryTraceRepository()
    app = instrument(tornado.web.Application([(r"/items", ItemsHandler)]), trace_repo=repo)
    server, base_url = await serve(app)
    try:
        response = await AsyncHTTPClient().fetch(f"{base_url}/items")
    finally:
        server.stop()

    assert response.code == 200
    assert repo.traces == []


async def test_applications_without_instrument_are_not_traced():
    repo = InMemoryTraceRepository()
    instrument(tornado.web.Application([(r"/items", ItemsHandler)]), trace_repo=repo)
    plain = tornado.web.Application([(r"/items", ItemsHandler)])
    server, base_url = await serve(plain)
    try:
        await AsyncHTTPClient().fetch(f"{base_url}/items")
    finally:
        server.stop()

    assert repo.traces == []


@pytest.fixture(autouse=True)
def fresh_http_client():
    yield
    AsyncHTTPClient().close()
