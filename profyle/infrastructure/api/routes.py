"""The trace viewer started by `profyle start`: a list of traces, each opened in
VizTracer's build of Perfetto."""

import os
from collections.abc import Iterator

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse

from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository
from profyle.settings import settings

app = FastAPI(title="Profyle", version="1.0.0")
app.mount(
    "/static",
    StaticFiles(directory=settings.get_path("infrastructure", "web", "static")),
    name="static",
)
app.mount(
    "/perfetto_static",
    StaticFiles(directory=settings.get_viztracer_static_files(), html=False),
    name="perfetto_static",
)
templates = Jinja2Templates(directory=settings.get_path("infrastructure", "web", "templates"))

# Perfetto loads the trace to show from fixed URLs (/localtrace, /file_info), so the
# viewer remembers which trace was opened last.
app.state.opened_trace = None


def get_repo() -> Iterator[SQLiteTraceRepository]:
    repo = SQLiteTraceRepository()
    try:
        yield repo
    finally:
        repo.close()


@app.get("/")
async def index():
    return RedirectResponse("/traces")


@app.get("/traces")
def traces(request: Request, repo: SQLiteTraceRepository = Depends(get_repo)):
    return templates.TemplateResponse(
        request,
        "traces.html",
        context={"traces": [trace.model_dump() for trace in repo.list_traces()]},
    )


@app.get("/traces/{trace_id}")
async def open_trace(trace_id: int):
    app.state.opened_trace = trace_id
    return RedirectResponse(url="/show")


@app.delete("/traces/{trace_id}", status_code=204)
def delete_trace(trace_id: int, repo: SQLiteTraceRepository = Depends(get_repo)) -> None:
    repo.delete_trace(trace_id)


@app.get("/show", response_class=HTMLResponse)
async def show_perfetto_ui():
    """Perfetto's page, with Profyle's overlay and its assets served from here."""
    page = _read(settings.get_viztracer_static_files(), "index.html")
    overlay = _read(
        settings.get_path("infrastructure", "web", "templates"), "perfetto_injection.html"
    )
    page = page.replace("</head>", f"{overlay}</head>")
    return page.replace(
        "script.src = version + '/frontend_bundle.js';",
        "script.src = '/perfetto_static/' + version + '/frontend_bundle.js';",
    )


@app.get("/localtrace")
def localtrace(repo: SQLiteTraceRepository = Depends(get_repo)):
    trace = _opened_trace(repo)
    return trace.data if trace else {}


@app.get("/file_info")
def file_info(repo: SQLiteTraceRepository = Depends(get_repo)):
    trace = _opened_trace(repo)
    return trace.data.get("file_info") if trace else {}


@app.get("/vizviewer_info")
async def vizviewer_info():
    return {"is_flamegraph": False}


def _opened_trace(repo: SQLiteTraceRepository):
    trace_id = app.state.opened_trace
    return repo.get_trace(trace_id) if trace_id is not None else None


def _read(directory: str, name: str) -> str:
    with open(os.path.join(directory, name), encoding="utf-8") as f:
        return f.read()
