"""`profyle run` against real servers: the examples in examples/ have no Profyle code."""

import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.name == "nt", reason="uses POSIX process groups"),
]

EXAMPLES = Path(__file__).parents[2] / "examples"
BIN = Path(sys.executable).parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


CASES = {
    "fastapi-uvicorn-reload": ("fastapi", "FastAPI", ["uvicorn", "main:app", "--reload"]),
    "flask-run-debug": ("flask", "Flask", ["flask", "--app", "app", "run", "--debug"]),
    "django-runserver": ("django", "Django", ["python", "manage.py", "runserver"]),
    "django-asgi-uvicorn": ("django", "Django", ["uvicorn", "manage:application"]),
    "plain-asgi-uvicorn": ("asgi", "ASGI", ["uvicorn", "app:app"]),
}


def command_with_port(command: list[str], port: int) -> list[str]:
    command = [str(BIN / command[0]), *command[1:]]
    if "runserver" in command:
        return [*command, str(port)]
    return [*command, "--port", str(port)]


@pytest.mark.parametrize("case", CASES)
def test_profyle_run_traces_without_code_changes(case, tmp_path):
    example, framework, command = CASES[case]
    project = tmp_path / "project"
    shutil.copytree(EXAMPLES / example, project)
    (project / "pyproject.toml").write_text("")
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("PROFYLE_")}
    log_path = project / "console.log"

    with open(log_path, "w") as log:
        process = subprocess.Popen(
            [str(BIN / "profyle"), "run", *command_with_port(command, port)],
            cwd=project,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            url = f"http://127.0.0.1:{port}/orders"
            for _ in range(80):
                try:
                    urllib.request.urlopen(url, timeout=5).read()
                    break
                except OSError:
                    time.sleep(0.25)
            else:
                pytest.fail("server did not start:\n" + log_path.read_text())
            urllib.request.urlopen(url, timeout=10).read()
            deadline = time.time() + 20
            while time.time() < deadline and log_path.read_text().count("· #") < 2:
                time.sleep(0.25)
        finally:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(15)

    console = log_path.read_text()
    db = sqlite3.connect(project / ".profyle" / "profile.db")
    names = [row[0] for row in db.execute("SELECT name FROM traces ORDER BY id")]
    runtime = json.loads(db.execute("SELECT info FROM runtime").fetchone()[0])

    assert names[:2] == ["GET /orders", "GET /orders"], console
    assert (runtime["framework"], runtime["mode"]) == (framework, "profyle run")
    assert console.count("profyle ▸ tracing requests") == 1, console
    assert "· first request, includes warm-up" in console
    # The caller is "list_orders" (or "app"); Python 3.10 has no function name for the
    # comprehension frame, so it is reported as "list comprehension at <file>:<line>".
    assert any(
        f"repeated: {caller}" in console and "→ get_customer ×50" in console
        for caller in ("list_orders →", "app →", "list comprehension at ")
    ), console
