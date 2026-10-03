import os
from sqlite3 import Connection

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse

from profyle.application.trace.delete import delete_trace_by_id
from profyle.application.trace.get import get_all_traces, get_trace_by_id, get_trace_selected
from profyle.application.trace.store import store_trace_selected
from profyle.infrastructure.sqlite3.get_connection import get_connection
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository
from profyle.settings import settings

app = FastAPI(title="Profyle", version="1.0.0")


STATIC_PATH = ("infrastructure", "web", "static")
app.mount("/static", StaticFiles(directory=settings.get_path(*STATIC_PATH)), name="static")

app.mount(
    "/perfetto_static",
    StaticFiles(directory=settings.get_viztracer_static_files(), html=False),
    name="perfetto_static",
)


@app.get("/show", response_class=HTMLResponse)
async def show_perfetto_ui():
    viztracer_path = settings.get_viztracer_static_files()
    index_path = os.path.join(viztracer_path, "index.html")
    with open(index_path, encoding="utf-8") as f:
        content = f.read()

    # Read injection content
    injection_path = settings.get_path(
        "infrastructure", "web", "templates", "perfetto_injection.html"
    )
    with open(injection_path, encoding="utf-8") as f:
        injection_content = f.read()

    modified_content = content.replace("</head>", f"{injection_content}</head>")

    # Fix asset loading path to use the new static mount
    modified_content = modified_content.replace(
        "script.src = version + '/frontend_bundle.js';",
        "script.src = '/perfetto_static/' + version + '/frontend_bundle.js';",
    )

    return modified_content


TEMPLATES_PATH = ("infrastructure", "web", "templates")
templates = Jinja2Templates(directory=settings.get_path(*TEMPLATES_PATH))


@app.get("/vizviewer_info")
async def vizviewer_info():
    return {"is_flamegraph": False}


@app.get("/file_info")
async def file_info(
    db: Connection = Depends(get_connection),
):
    sqlite_trace_repo = SQLiteTraceRepository(db)
    trace_id = get_trace_selected(repo=sqlite_trace_repo)
    if not trace_id:
        return {}
    trace = get_trace_by_id(trace_id=trace_id, repo=sqlite_trace_repo)
    if not trace:
        return {}
    return trace.data.get("file_info")


@app.get("/localtrace")
async def localtrace(
    db: Connection = Depends(get_connection),
):
    sqlite_trace_repo = SQLiteTraceRepository(db)
    trace_id = get_trace_selected(repo=sqlite_trace_repo)
    if not trace_id:
        return {}
    trace = get_trace_by_id(trace_id=trace_id, repo=sqlite_trace_repo)
    if not trace:
        return {}
    return trace.data


@app.get("/")
async def index():
    return RedirectResponse("/traces")


@app.get("/traces")
async def traces(
    request: Request,
    db: Connection = Depends(get_connection),
):
    sqlite_trace_repo = SQLiteTraceRepository(db)
    traces = get_all_traces(repo=sqlite_trace_repo)
    return templates.TemplateResponse(
        request,
        "traces.html",
        context={"traces": [trace.model_dump(exclude={"data"}) for trace in traces]},
    )


@app.get("/traces/{id}")
async def get_trace(
    id: int,
    db: Connection = Depends(get_connection),
):
    sqlite_trace_repo = SQLiteTraceRepository(db)
    store_trace_selected(trace_id=id, repo=sqlite_trace_repo)
    return RedirectResponse(url="/show")


@app.delete("/traces/{id}", status_code=204)
async def delete_trace(
    id: int,
    db: Connection = Depends(get_connection),
) -> None:
    sqlite_trace_repo = SQLiteTraceRepository(db)
    delete_trace_by_id(repo=sqlite_trace_repo, trace_id=id)
