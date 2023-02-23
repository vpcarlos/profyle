from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from profyle.middleware.fastapi import ProfileMiddleware

app = FastAPI()
app.add_middleware(ProfileMiddleware)

router = APIRouter()


@router.post('/test')
def run_middleware():
    return {'message': 'OK'}


app.include_router(router)

client = TestClient(app)


def test_fastapi_middleware():
    client.post('test')
