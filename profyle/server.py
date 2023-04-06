from sqlite3 import Connection

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
import uvicorn

from profyle.database.sql_lite import create_select_trace, create_trace_table, get_all_traces, get_select_trace, get_trace_by_id, store_select_trace
from profyle.deps.get_connection import get_connection
from profyle.settings import settings


app = FastAPI(
    title='Profyle',
    version='1.0.0'
)

origins = [
    '*'
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.on_event('startup')
async def startup_event():
    db = get_connection()
    create_trace_table(db)
    create_select_trace(db)

app.mount(
    '/static',
    StaticFiles(directory=settings.get_path('web', 'static')),
    name='static'
)
app.mount(
    '/show',
    StaticFiles(directory=settings.get_viztracer_static_files(), html=True),
    name='perfetto'
)

templates = Jinja2Templates(directory=settings.get_path('web', 'templates'))


@app.get('/vizviewer_info')
async def vizviewer_info():
    return {'is_flamegraph': False}


@app.get('/file_info')
async def file_info(
    db: Connection = Depends(get_connection),
):
    trace_id = get_select_trace(db)
    if not trace_id:
        return {}
    trace = get_trace_by_id(trace_id, db)
    if not trace:
        return {}
    return trace.data.get('file_info')


@app.get('/localtrace')
async def localtrace(
    db: Connection = Depends(get_connection),
):
    trace_id = get_select_trace(db)
    if not trace_id:
        return {}
    trace = get_trace_by_id(trace_id, db)
    if not trace:
        return {}
    return trace.data


@app.get('/')
async def index():
    return RedirectResponse('/traces')


@app.get('/traces')
async def traces(
    request: Request,
    db: Connection = Depends(get_connection),

):
    traces = get_all_traces(db)
    return templates.TemplateResponse(
        name='traces.html',
        context={
            'request': request,
            'traces': [trace.dict() for trace in traces]
        }
    )


@app.get('/traces/{id}')
async def get_trace(
    id: int,
    db: Connection = Depends(get_connection),
):
    store_select_trace(
        trace_id=id,
        db=db
    )
    return RedirectResponse(url='/show')


async def start_server():
    config = uvicorn.Config(app, port=0, log_level='info')
    server = uvicorn.Server(config)
    await server.serve()
