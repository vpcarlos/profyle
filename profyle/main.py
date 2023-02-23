import typer
import asyncio
from profyle.server import start_server

app = typer.Typer()


@app.command()
def start():
    asyncio.run(start_server())


@app.command()
def check():
    ...
