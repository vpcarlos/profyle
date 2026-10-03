import os

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from flask import Flask


@pytest.fixture
def fastapi_app():
    app = FastAPI()

    router = APIRouter()

    @router.post("/test-post")
    async def test_post():
        return {"message": "OK"}

    @router.get("/test-get")
    async def test_get(demo: bool = False):
        return {"message": demo}

    @router.patch("/test-patch")
    async def test_patch():
        return {"message": "OK"}

    @router.put("/test-put")
    async def test_put():
        return {"message": "OK"}

    app.include_router(router)

    yield app


@pytest.fixture
def flask_app():
    app = Flask("flask_test", root_path=os.path.dirname(__file__))
    app.config.update(
        TESTING=True,
        SECRET_KEY="test key",
    )

    @app.route("/test-post", methods=["POST"])
    def test_post():
        return "Test"

    @app.route("/test-get", methods=["GET"])
    def test_get():
        return "Test"

    @app.route("/test-patch", methods=["PATCH"])
    def test_patch():
        return "Test"

    yield app


@pytest.fixture
def flask_client(flask_app):
    yield flask_app.test_client()


@pytest.fixture()
def fastapi_client(fastapi_app):
    yield TestClient(fastapi_app)


@pytest.fixture
def project_db(tmp_path, monkeypatch):
    """An isolated project whose trace database holds two traces of GET /users."""
    from profyle.domain.trace import RecordedRequest, TraceCreate
    from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository
    from tests.unit.application.analysis.test_digest import make_trace

    (tmp_path / "pyproject.toml").write_text("")
    monkeypatch.chdir(tmp_path)
    for name in ("DB", "PROJECT_DIR", "ENABLED", "PATTERN", "CONSOLE"):
        monkeypatch.delenv(f"PROFYLE_{name}", raising=False)
    db_path = tmp_path / ".profyle" / "profile.db"
    monkeypatch.setenv("PROFYLE_DB", str(db_path))
    db_path.parent.mkdir()
    repo = SQLiteTraceRepository()
    request = RecordedRequest(method="GET", path="/users", base_url="http://127.0.0.1:9")
    for duration in (1.0, 5.0):
        repo.store_trace(
            TraceCreate(raw_trace=make_trace(duration), name="GET /users", request=request)
        )
    yield repo
