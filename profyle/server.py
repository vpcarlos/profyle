import tempfile
from sqlite3 import Connection
from ast import literal_eval
from pstats import Stats
import marshal


from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from snakeviz.stats import table_rows, json_stats
from starlette.responses import RedirectResponse
import uvicorn

from profyle.database.sql_lite import create_trace_table, get_trace_by_id, get_traces
from profyle.deps.get_connection import get_connection
from profyle.settings import settings


app = FastAPI(
    title='Profyle',
    version='0.1.0'
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


app.mount(
    '/static',
    StaticFiles(directory=settings.get_path('web', 'static')),
    name='static'
)


templates = Jinja2Templates(directory=settings.get_path('web', 'templates'))


@app.on_event('startup')
async def startup_event():
    db = get_connection()
    create_trace_table(db)


@app.get('/')
async def home():
    return RedirectResponse(url='/trace')


@app.get('/trace')
def traces(
    request: Request,
    db: Connection = Depends(get_connection),

):
    traces = get_traces(db)
    return templates.TemplateResponse(
        name='home.html',
        context={
            'request': request,
            'traces': [trace.dict() for trace in traces]
        }
    )


@app.get('/trace/{id}')
def get_trace(
    id: str,
    request: Request,
    db: Connection = Depends(get_connection),
):

    trace = get_trace_by_id(id, db)

    with tempfile.NamedTemporaryFile(suffix='.prof') as tf:
        marshal.dump(literal_eval(trace.file), tf)
        stats = Stats(tf.name)

    rows = table_rows(stats)
    stats_data = json_stats(stats)

    return templates.TemplateResponse(
        name='trace.html',
        context={
            'request': request,
            'table_rows': rows,
            'callees': stats_data
        }
    )


async def start_server():
    config = uvicorn.Config(app, port=0, log_level='info')
    server = uvicorn.Server(config)
    await server.serve()