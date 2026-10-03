"""The trace viewer: `profyle start`."""

import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def no_trace_opened_yet():
    from profyle.infrastructure.api.routes import app

    app.state.opened_trace = None


def client():
    from profyle.infrastructure.api.routes import app

    return TestClient(app)


def test_list_shows_traces_and_their_main_finding(project_db):
    from profyle.application.analysis import toolkit

    toolkit.precompute_digests(project_db)
    with client() as c:
        page = c.get("/traces")
        assert c.get("/", follow_redirects=False).headers["location"] == "/traces"

    assert page.status_code == 200
    assert "/traces/1" in page.text and "/traces/2" in page.text
    assert "wait: time.sleep" in page.text


def test_open_a_trace_in_perfetto(project_db):
    with client() as c:
        assert c.get("/localtrace").json() == {}  # nothing selected yet
        assert c.get("/file_info").json() == {}

        redirect = c.get("/traces/2", follow_redirects=False)
        assert redirect.headers["location"] == "/show"
        assert "traceEvents" in c.get("/localtrace").json()
        assert "functions" in c.get("/file_info").json()

        page = c.get("/show")
        assert page.status_code == 200
        assert "profyle_overlay.js" in page.text
        assert c.get("/vizviewer_info").json() == {"is_flamegraph": False}


def test_selected_trace_that_was_deleted(project_db):
    with client() as c:
        c.get("/traces/2", follow_redirects=False)
        assert c.delete("/traces/2").status_code == 204
        assert c.get("/localtrace").json() == {}
        assert c.get("/file_info").json() == {}
    assert [t.id for t in project_db.list_traces()] == [1]


def test_start_server(monkeypatch):
    import uvicorn

    from profyle.infrastructure import server

    started = {}

    async def serve(self):
        started.update(host=self.config.host, port=self.config.port)

    monkeypatch.setattr(uvicorn.Server, "serve", serve)
    asyncio.run(server.start_server(port=1234, host="127.0.0.1"))

    assert started == {"host": "127.0.0.1", "port": 1234}
