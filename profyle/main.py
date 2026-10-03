import argparse
import asyncio
import os

from profyle.application.trace.delete import delete_all_selected_traces, delete_all_traces
from profyle.application.trace.vacuum import vacuum
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
    db_path = settings.get_db_path()
    if os.path.exists(db_path):
        db_size_in_bytes = os.path.getsize(db_path)
    else:
        db_size_in_bytes = 0

    print(f"Project → {settings.project_dir}")
    if db_size_in_bytes > 1e9:
        db_size = f"{round(db_size_in_bytes/1e9, 2)} GB"
    else:
        db_size = f"{round(db_size_in_bytes/1e6, 2)} MB"

    print(f"DB size → {db_size}")


def analyze(trace_id: int | None) -> None:
    from profyle.application.analysis import toolkit

    repo = SQLiteTraceRepository(get_connection())
    if trace_id is None:
        trace_id = repo.get_trace_selected()
    if trace_id is None:
        print(toolkit.list_traces(repo))
        return
    try:
        print(toolkit.analyze_trace(repo, trace_id))
    except toolkit.TraceNotFound as error:
        print(error)


def mcp() -> None:
    try:
        from profyle.infrastructure.mcp_server import run as run_mcp_server
    except ImportError:
        print("The MCP server needs the 'mcp' extra: pip install 'profyle[mcp]'")
        return
    run_mcp_server()


def main():
    parser = argparse.ArgumentParser(description="Profyle CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # start
    parser_start = subparsers.add_parser("start", help="Start the Profyle server")
    parser_start.add_argument("--port", type=int, default=0, help="Port to bind")
    parser_start.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind")

    # clean
    subparsers.add_parser("clean", help="Remove all traces")

    # info
    subparsers.add_parser("info", help="Profyle info")

    # analyze
    parser_analyze = subparsers.add_parser(
        "analyze", help="Print an LLM-ready bottleneck digest of a trace"
    )
    parser_analyze.add_argument(
        "trace_id", type=int, nargs="?", help="Trace id (defaults to the selected trace)"
    )

    # mcp
    subparsers.add_parser("mcp", help="Run the MCP server (stdio) for Claude Code / Desktop")

    args = parser.parse_args()

    if args.command == "start":
        from profyle.infrastructure.server import start_server

        asyncio.run(start_server(port=args.port, host=args.host))
    elif args.command == "clean":
        clean()
    elif args.command == "info":
        info()
    elif args.command == "analyze":
        analyze(args.trace_id)
    elif args.command == "mcp":
        mcp()
    else:
        parser.print_help()


def run():
    main()


if __name__ == "__main__":
    run()
