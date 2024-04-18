import asyncio
import os

import typer
from rich import print

from profyle.application.trace.delete import delete_all_selected_traces, delete_all_traces
from profyle.application.trace.vacuum import vacuum
from profyle.infrastructure.http_server import start_server
from profyle.infrastructure.sqlite3.get_connection import get_connection
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository
from profyle.settings import settings

app = typer.Typer()


@app.command(help="Start the Profyle server")
def start(port: int = 0, host: str = "127.0.0.1"):
    asyncio.run(start_server(port=port, host=host))


@app.command(help="Remove all traces")
def clean():
    db = get_connection()
    sqlite_repo = SQLiteTraceRepository(db)
    removed_traces = delete_all_traces(sqlite_repo)
    removed_selected_traces = delete_all_selected_traces(sqlite_repo)
    vacuum(sqlite_repo)
    removed_traces = removed_traces + removed_selected_traces
    print(f"[green]{removed_traces} records removed [/green]")


@app.command(help="Proyfle info")
def info():
    db_size_in_bytes = os.path.getsize(settings.get_path("profile.db"))

    print(f"[bold]Project[/bold] → {settings.project_dir}")
    print(db_size_in_bytes)
    if db_size_in_bytes > 1e9:
        db_size = f"{round(db_size_in_bytes/1e9, 2)} GB"
    else:
        db_size = f"{round(db_size_in_bytes/1e6, 2)} MB"

    print(f"[bold]DB size[/bold] → {db_size}")
