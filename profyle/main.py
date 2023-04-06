import os
import asyncio

import typer
from rich import print


from profyle.database.sql_lite import remove_all_traces, vacuum
from profyle.deps.get_connection import get_connection
from profyle.server import start_server
from profyle.settings import settings
app = typer.Typer()


@app.command()
def start():
    asyncio.run(start_server())


@app.command()
def clean():
    db = get_connection()
    removed_traces = remove_all_traces(db)
    vacuum(db)
    print(f'[green]{removed_traces} traces removed [/green]')


@app.command()
def check():

    db_size_in_bytes = os.path.getsize(settings.get_path('profile.db'))
    db_size_in_megabytes = round(db_size_in_bytes/10**6, 2)
    db_size_in_gigabytes = round(db_size_in_megabytes/10**3, 2)

    if db_size_in_megabytes > 1000:
        print(f'[orange1]DB size: {db_size_in_gigabytes} GB [/orange1]')
        return
    print(f'[orange1]DB size: {db_size_in_megabytes} MB [/orange1]')
