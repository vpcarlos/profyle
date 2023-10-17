
import pytest
import os

from flask import Flask
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

@pytest.fixture
def fastapi_app():
    app = FastAPI()

    router = APIRouter()

    @router.post('/test-post')
    async def test_post():
        return {'message': 'OK'}

    @router.get('/test-get')
    async def test_get(demo: bool = False):
        return {'message': demo}

    @router.patch('/test-patch')
    async def test_patch():
        return {'message': 'OK'}

    @router.put('/test-put')
    async def test_put():
        return {'message': 'OK'}

    app.include_router(router)

    yield app


@pytest.fixture
def flask_app():
    app = Flask('flask_test', root_path=os.path.dirname(__file__))
    app.config.update(
        TESTING=True,
        SECRET_KEY='test key',
    )

    @app.route('/test-post', methods=['POST'])
    def test_post():
        return 'Test'

    @app.route('/test-get', methods=['GET'])
    def test_get():
        return 'Test'

    @app.route('/test-patch', methods=['PATCH'])
    def test_patch():
        return 'Test'
    
    yield app

@pytest.fixture
def flask_client(flask_app):
    yield flask_app.test_client()


@pytest.fixture()
def fastapi_client(fastapi_app):
    yield TestClient(fastapi_app)
