"""The `profyle` command."""

import argparse
import os
import sys

from profyle.settings import settings


def _repo():
    from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository

    return SQLiteTraceRepository()


def run_command(args: argparse.Namespace) -> None:
    """Run the user's server command with zero-code tracing (see autoinstrument)."""
    import shutil
    import subprocess

    from profyle.infrastructure.console import display_path, say
    from profyle.settings import find_project_root

    command = args.command_args
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("Usage: profyle run <command>, e.g. profyle run uvicorn main:app --reload")
        sys.exit(2)
    executable = shutil.which(command[0])
    if executable is None:
        print(f"profyle run: command not found: {command[0]}")
        sys.exit(127)

    env = dict(os.environ)
    bootstrap = settings.get_path("_run")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [bootstrap, env.get("PYTHONPATH")]))
    env["PROFYLE_RUN"] = "1"
    # Pin the database and the project for every child process (reloaders, workers),
    # even if they change directory.
    env.setdefault("PROFYLE_DB", settings.get_db_path())
    env.setdefault("PROFYLE_PROJECT_DIR", find_project_root(os.getcwd()))

    say(
        f"tracing requests of `{' '.join(command)}` → {display_path(env['PROFYLE_DB'])}. "
        "Each request prints a summary line here; ask Claude Code about a slow one, "
        "or run `profyle start` to browse traces."
    )
    if os.name == "nt":  # pragma: no cover - Windows has no exec; run as a child
        sys.exit(subprocess.call([executable, *command[1:]], env=env))
    os.execve(executable, [command[0], *command[1:]], env)


def start(args: argparse.Namespace) -> None:
    import asyncio

    from profyle.infrastructure.server import start_server

    asyncio.run(start_server(port=args.port, host=args.host))


def analyze(args: argparse.Namespace) -> None:
    from profyle.application import tools

    repo = _repo()
    trace_id = args.trace_id or repo.latest_trace_id()
    if not trace_id:
        print(tools.list_traces(repo))  # explains that there are no traces yet
        return
    try:
        print(tools.analyze_trace(repo, trace_id))
    except tools.TraceNotFound as error:
        print(error)


def replay(args: argparse.Namespace) -> None:
    from profyle.application import tools

    headers = {}
    for header in args.header or []:
        name, _, value = header.partition(":")
        headers[name.strip()] = value.strip()
    try:
        print(
            tools.replay_trace(
                _repo(),
                args.trace_id,
                times=args.times,
                base_url=args.base_url,
                headers=headers or None,
                allow_unsafe_method=args.allow_unsafe,
            )
        )
    except tools.TraceNotFound as error:
        print(error)


def doctor(args: argparse.Namespace) -> None:
    from profyle.application import tools

    print(tools.doctor(_repo()))


def info(args: argparse.Namespace) -> None:
    db_path = settings.get_db_path()
    size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    print(f"DB → {db_path}")
    if size > 1e9:
        print(f"DB size → {round(size / 1e9, 2)} GB")
    else:
        print(f"DB size → {round(size / 1e6, 2)} MB")


def clean(args: argparse.Namespace) -> None:
    print(f"{_repo().delete_all_traces()} traces removed")


def mcp(args: argparse.Namespace) -> None:
    from profyle.infrastructure.mcp_server import run as run_mcp_server

    run_mcp_server()


def init(args: argparse.Namespace) -> None:
    from profyle.infrastructure.claude_code import init_project
    from profyle.settings import find_project_root

    project_dir = find_project_root(os.getcwd())
    print(f"Setting up Claude Code for {project_dir}")
    for path, status in init_project(project_dir):
        print(f"  {path:<45} {status}")
    print(
        "\nCommit these files so your team gets the same setup.\n"
        "Next: start your app with `profyle run <command>` (for example\n"
        "`profyle run uvicorn main:app --reload`), open Claude Code in this project, approve\n"
        "the profyle MCP server when asked, and ask about a slow endpoint."
    )


def uninstall(args: argparse.Namespace) -> None:
    from profyle.infrastructure.claude_code import uninstall_project
    from profyle.settings import DATA_DIR, find_project_root

    project_dir = find_project_root(os.getcwd())
    remove_traces = not args.keep_traces
    if remove_traces and os.path.isdir(os.path.join(project_dir, DATA_DIR)) and not args.yes:
        remove_traces = _confirm(f"Delete all traces in {os.path.join(project_dir, DATA_DIR)}?")
    print(f"Removing Profyle from {project_dir}")
    for path, status in uninstall_project(project_dir, remove_traces):
        print(f"  {path:<45} {status}")
    if os.getenv("PROFYLE_DB"):
        print(f"\nPROFYLE_DB points to {os.environ['PROFYLE_DB']}: delete it yourself if needed.")
    print(
        "\nLast step: `pip uninstall profyle` (or `uv remove profyle`, which also removes the\n"
        "dependencies it installed). If you installed the Claude Code plugin instead:\n"
        "`claude plugin uninstall profyle`."
    )


def _confirm(question: str) -> bool:
    if not sys.stdin.isatty():
        print(f"{question} Not asked (no terminal): traces kept, pass --yes to delete them.")
        return False
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="profyle", description="Profyle CLI")
    commands = parser.add_subparsers(title="commands")

    def command(name: str, handler, help: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help)
        sub.set_defaults(handler=handler)
        return sub

    command("init", init, "Set up Claude Code for this project (MCP server and skill)")
    remove = command(
        "uninstall", uninstall, "Remove Profyle from this project: Claude Code setup and traces"
    )
    remove.add_argument("-y", "--yes", action="store_true", help="Delete traces without asking")
    remove.add_argument("--keep-traces", action="store_true", help="Keep the traces in .profyle")

    run = command(
        "run",
        run_command,
        "Run your app with tracing, no code changes (e.g. profyle run uvicorn main:app)",
    )
    run.add_argument("command_args", nargs=argparse.REMAINDER, help="Command that starts the app")

    viewer = command("start", start, "Open the trace viewer in the browser")
    viewer.add_argument("--port", type=int, default=0, help="Port to bind")
    viewer.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind")

    analyze_ = command("analyze", analyze, "Print the bottleneck digest of a trace")
    analyze_.add_argument("trace_id", type=int, nargs="?", help="Trace id (default: the newest)")

    replay_ = command("replay", replay, "Send the request of a trace again")
    replay_.add_argument("trace_id", type=int, help="Trace id")
    replay_.add_argument("--times", type=int, default=1, help="Number of replays")
    replay_.add_argument("--base-url", help="e.g. http://127.0.0.1:8000")
    replay_.add_argument(
        "-H", "--header", action="append", help="Extra header, e.g. 'Authorization: Bearer x'"
    )
    replay_.add_argument("--allow-unsafe", action="store_true", help="Allow POST/PUT/PATCH/DELETE")

    command("doctor", doctor, "Check that traces are recorded and replayable")
    command("mcp", mcp, "Run the MCP server (stdio) for Claude Code / Desktop")
    command("info", info, "Show where traces are stored and how much space they use")
    command("clean", clean, "Delete all traces")
    return parser


def run() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "handler"):
        parser.print_help()
        return
    args.handler(args)


if __name__ == "__main__":
    run()
