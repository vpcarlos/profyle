"""Limits and fallbacks of the middlewares: big bodies, missing headers, odd servers."""

import asyncio
import io

from profyle.application.requests.capture import MAX_BODY_BYTES
from profyle.application.requests.fingerprint import MAX_FINGERPRINT_BYTES
from profyle.asgi import ProfyleMiddleware as ASGIMiddleware
from profyle.wsgi import ProfyleMiddleware as WSGIMiddleware
from tests.unit.repository import InMemoryTraceRepository

BIG_RESPONSE = MAX_FINGERPRINT_BYTES + 1


async def chunked_app(scope, receive, send):
    """Reads the whole request body, answers with a body bigger than the fingerprint limit,
    sent in several chunks."""
    while (await receive()).get("more_body"):
        pass
    await send({"type": "http.response.start", "status": 200, "headers": []})
    for _ in range(3):
        await send(
            {"type": "http.response.body", "body": b"x" * (BIG_RESPONSE // 2), "more_body": True}
        )
    await send({"type": "http.response.body", "body": b""})


def call_asgi(app, scope_extra=None, chunks=(b"",)):
    messages = [
        {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
        for i, chunk in enumerate(chunks)
    ]

    async def receive():
        return messages.pop(0)

    async def send(message):
        pass

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/upload",
        "headers": [],
        "query_string": b"",
    }
    scope.update(scope_extra or {})
    asyncio.run(app(scope, receive, send))


def test_asgi_large_bodies_are_not_recorded():
    repo = InMemoryTraceRepository()
    middleware = ASGIMiddleware(chunked_app, trace_repo=repo, console=False)
    assert middleware.trace_repo is repo

    big_chunk = b"y" * (MAX_BODY_BYTES // 2 + 1)
    call_asgi(middleware, {"server": ("10.0.0.1", 8000)}, chunks=(big_chunk,) * 3)

    request = repo.traces[0].request
    assert request.body is None and request.body_truncated
    assert request.response is None
    assert request.base_url == "http://10.0.0.1:8000"


def test_asgi_host_fallback_and_repo_setter():
    repo = InMemoryTraceRepository()
    middleware = ASGIMiddleware(chunked_app, console=False)
    middleware.trace_repo = repo

    call_asgi(middleware)

    assert repo.traces[0].request.base_url == "http://localhost"


def wsgi_app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"ok"]


def call_wsgi(middleware, **environ):
    base = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/upload",
        "wsgi.url_scheme": "http",
        "SERVER_NAME": "example.local",
        "SERVER_PORT": "8080",
        "wsgi.input": io.BytesIO(b""),
    }
    base.update(environ)
    # Like a WSGI server: send the whole body, then close it.
    body = middleware(base, lambda status, headers: None)
    sent = b"".join(body)
    body.close()
    return sent


def test_wsgi_body_limits_and_host_fallback():
    repo = InMemoryTraceRepository()
    middleware = WSGIMiddleware(wsgi_app, console=False)
    middleware.trace_repo = repo
    assert middleware.trace_repo is repo

    call_wsgi(middleware, CONTENT_LENGTH="not-a-number")
    call_wsgi(middleware, CONTENT_LENGTH=str(MAX_BODY_BYTES + 1))

    invalid, too_large = (t.request for t in repo.traces)
    assert invalid.body is None and not invalid.body_truncated
    assert too_large.body_truncated
    assert invalid.base_url == "http://example.local:8080"


def test_tornado_large_responses_get_no_fingerprint():
    import tornado.httpserver
    import tornado.testing
    import tornado.web
    from tornado.httpclient import AsyncHTTPClient

    from profyle.tornado import instrument

    class Big(tornado.web.RequestHandler):
        def get(self):
            self.write(b"x" * BIG_RESPONSE)

    repo = InMemoryTraceRepository()

    async def scenario():
        app = instrument(tornado.web.Application([(r"/big", Big)]), trace_repo=repo, console=False)
        sock, port = tornado.testing.bind_unused_port()
        server = tornado.httpserver.HTTPServer(app)
        server.add_sockets([sock])
        try:
            await AsyncHTTPClient().fetch(f"http://127.0.0.1:{port}/big")
        finally:
            server.stop()

    asyncio.run(scenario())

    assert repo.traces[0].request.response is None
