import argparse
import os
import asyncio

from profyle.application.trace.delete import delete_all_selected_traces, delete_all_traces
from profyle.application.trace.vacuum import vacuum
from profyle.infrastructure.server import start_server
from profyle.infrastructure.sqlite3.get_connection import get_connection
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository
from profyle.settings import settings


def clean():
    db = get_connection()
    sqlite_repo = SQLiteTraceRepository(db)
    removed_traces = delete_all_traces(sqlite_repo)
    removed_selected_traces = delete_all_selected_traces(sqlite_repo)
    vacuum(sqlite_repo)
    removed_traces = removed_traces + removed_selected_traces
    print(f"{removed_traces} records removed")


def info():
    db_path = settings.get_path("profile.db")
    if os.path.exists(db_path):
        db_size_in_bytes = os.path.getsize(db_path)
    else:
        db_size_in_bytes = 0

    print(f"Project → {settings.project_dir}")
    print(db_size_in_bytes)
    if db_size_in_bytes > 1e9:
        db_size = f"{round(db_size_in_bytes/1e9, 2)} GB"
    else:
        db_size = f"{round(db_size_in_bytes/1e6, 2)} MB"

    print(f"DB size → {db_size}")


async def main():
    parser = argparse.ArgumentParser(description="Profyle CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # start
    parser_start = subparsers.add_parser("start", help="Start the Profyle server")
    parser_start.add_argument("--port", type=int, default=0, help="Port to bind")
    parser_start.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind")

    # clean
    parser_clean = subparsers.add_parser("clean", help="Remove all traces")

    # info
    parser_info = subparsers.add_parser("info", help="Profyle info")

    args = parser.parse_args()

    if args.command == "start":
        await start_server(port=args.port, host=args.host)
    elif args.command == "clean":
        clean()
    elif args.command == "info":
        info()
    else:
        parser.print_help()


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
