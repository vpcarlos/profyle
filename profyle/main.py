import typer
import asyncio
from rich import print

from profyle.database.sql_lite import remove_all_traces
from profyle.deps.get_connection import get_connection
from profyle.server import start_server

app = typer.Typer()


@app.command()
def start():
    asyncio.run(start_server())


@app.command()
def clean():
    db = get_connection()
    removed_traces = remove_all_traces(db)
    print(f'[green]{removed_traces} traces removed [/green]')
