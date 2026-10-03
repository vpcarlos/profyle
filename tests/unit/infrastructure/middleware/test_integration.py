import subprocess
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from flask import Flask

from profyle.asgi import ProfyleMiddleware as ASGIMiddleware
from profyle.wsgi import ProfyleMiddleware as WSGIMiddleware
from tests.unit.repository import InMemoryTraceRepository


def fastapi_app(**middleware_kwargs):
    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    repo = InMemoryTraceRepository()
    app.add_middleware(ASGIMiddleware, trace_repo=repo, **middleware_kwargs)
    return app, repo


def test_environment_variable_disables_tracing(monkeypatch):
    monkeypatch.setenv("PROFYLE_ENABLED", "false")
    app, repo = fastapi_app()

    assert TestClient(app).get("/ping").status_code == 200
    assert repo.traces == []


def test_nested_middlewares_trace_once():
    app, outer_repo = fastapi_app()
    inner_repo = InMemoryTraceRepository()
    app.add_middleware(ASGIMiddleware, trace_repo=inner_repo)

    TestClient(app).get("/ping")

    # The outermost middleware (added last) traces; the inner one sees the marker.
    assert len(inner_repo.traces) == 1
    assert outer_repo.traces == []


def test_registers_the_running_app_for_doctor():
    app, repo = fastapi_app(pattern="/ping")

    TestClient(app).get("/ping")

    runtime = repo.get_runtime()
    assert runtime["framework"] == "ASGI" and runtime["mode"] == "middleware"
    assert "pattern = '/ping' (code)" in runtime["config"]


def test_wsgi_traces_https_requests():
    app = Flask("https_app")

    @app.get("/secure")
    def secure():
        return "ok"

    repo = InMemoryTraceRepository()
    app.wsgi_app = WSGIMiddleware(app.wsgi_app, trace_repo=repo)

    app.test_client().get("/secure", base_url="https://localhost")

    assert [t.name for t in repo.traces] == ["GET /secure"]
    assert repo.traces[0].request.base_url == "https://localhost"


def test_importing_middlewares_does_not_touch_the_database(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    code = (
        "import profyle.fastapi, profyle.flask, profyle.asgi, profyle.wsgi\n"
        "from profyle.asgi import ProfyleMiddleware\n"
        "ProfyleMiddleware(app=None)\n"
    )
    subprocess.run([sys.executable, "-c", code], cwd=tmp_path, check=True)

    assert not (tmp_path / ".profyle").exists()


async def test_concurrent_requests_do_not_corrupt_each_other():
    """VizTracer records one trace per process: a request arriving while another one is
    traced passes through untraced instead of overwriting the running tracer."""
    import asyncio

    import httpx

    from profyle.application.analysis.digest import build_digest

    def work_a():
        return sum(range(1000))

    app = FastAPI()

    @app.get("/a")
    async def a():
        await asyncio.sleep(0.05)
        work_a()
        await asyncio.sleep(0.05)
        work_a()
        return {}

    @app.get("/b")
    async def b():
        await asyncio.sleep(0.02)
        return {}

    repo = InMemoryTraceRepository()
    asgi = ASGIMiddleware(app, trace_repo=repo)
    transport = httpx.ASGITransport(app=asgi)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        responses = await asyncio.gather(client.get("/a"), client.get("/b"))

    assert [r.status_code for r in responses] == [200, 200]
    assert [t.name for t in repo.traces] == ["GET /a"]
    calls = {
        row["function"].rsplit(".", 1)[-1]: row["calls"]
        for row in build_digest(repo.traces[0].data, top=1000)["top_inclusive"]
    }
    assert calls.get("work_a") == 2, calls
