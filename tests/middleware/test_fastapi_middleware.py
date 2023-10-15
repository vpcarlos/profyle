from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from profyle.fastapi import ProfyleMiddleware

app = FastAPI()
app.add_middleware(ProfyleMiddleware, pattern='*test[?]*')

router = APIRouter()


@router.post('/test')
def run_middleware():
    return {'message': 'OK'}


@router.post('/test1')
def run_middleware_1():
    return {'message': 'OK'}


app.include_router(router)

client = TestClient(app)


def test_fastapi_middleware():
    client.post('test?demo=true')
    client.post('test1')
