import os
import sys

import pytest

from profyle import main as cli


def run_cli(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["profyle", *args])
    cli.run()
    return capsys.readouterr().out


def test_help(monkeypatch, capsys):
    assert "usage: profyle" in run_cli(monkeypatch, capsys)


def test_info_and_clean(project_db, monkeypatch, capsys):
    out = run_cli(monkeypatch, capsys, "info")
    assert "DB → " in out and "MB" in out

    monkeypatch.setattr(os.path, "getsize", lambda path: 3 * 10**9)
    assert "3.0 GB" in run_cli(monkeypatch, capsys, "info")

    assert "2 traces removed" in run_cli(monkeypatch, capsys, "clean")
    assert project_db.list_traces() == []


def test_info_without_database(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PROFYLE_DB", str(tmp_path / "missing.db"))
    assert "0.0 MB" in run_cli(monkeypatch, capsys, "info")


def test_analyze(project_db, monkeypatch, capsys):
    assert "Trace digest — #2 GET /users" in run_cli(monkeypatch, capsys, "analyze")  # newest
    assert "Trace digest — #1 GET /users" in run_cli(monkeypatch, capsys, "analyze", "1")
    assert "Trace 99 not found" in run_cli(monkeypatch, capsys, "analyze", "99")


def test_analyze_without_traces(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PROFYLE_DB", str(tmp_path / "empty.db"))
    assert "No matching traces" in run_cli(monkeypatch, capsys, "analyze")


def test_replay(project_db, monkeypatch, capsys):
    from profyle.application import tools

    calls = []
    monkeypatch.setattr(tools, "replay_trace", lambda *a, **k: calls.append((a, k)) or "ok")
    out = run_cli(
        monkeypatch,
        capsys,
        "replay",
        "1",
        "--times",
        "3",
        "-H",
        "Authorization: Bearer x",
        "--base-url",
        "http://127.0.0.1:8000",
        "--allow-unsafe",
    )

    assert out.strip() == "ok"
    (_, trace_id), kwargs = calls[0]
    assert trace_id == 1
    assert kwargs == {
        "times": 3,
        "base_url": "http://127.0.0.1:8000",
        "headers": {"Authorization": "Bearer x"},
        "allow_unsafe_method": True,
    }

    monkeypatch.undo()
    monkeypatch.setenv("PROFYLE_DB", project_db.db_path)
    assert "Trace 99 not found" in run_cli(monkeypatch, capsys, "replay", "99")


def test_doctor(project_db, monkeypatch, capsys):
    assert "✓ Database" in run_cli(monkeypatch, capsys, "doctor")


def test_run_execs_the_command_with_the_bootstrap(project_db, monkeypatch, capsys):
    executed = {}
    monkeypatch.setattr(
        os, "execve", lambda path, args, env: executed.update(path=path, args=args, env=env)
    )

    monkeypatch.setattr(sys, "argv", ["profyle", "run", "--", "python", "-c", "pass"])
    cli.run()
    startup_message = capsys.readouterr().err

    assert executed["args"] == ["python", "-c", "pass"]
    env = executed["env"]
    assert env["PROFYLE_RUN"] == "1"
    assert env["PYTHONPATH"].split(os.pathsep)[0].endswith(os.path.join("profyle", "_run"))
    assert env["PROFYLE_DB"] == project_db.db_path
    assert "tracing requests of `python -c pass`" in startup_message


@pytest.mark.parametrize(
    ("args", "code", "message"),
    [((), 2, "Usage: profyle run"), (("no-such-command-xyz",), 127, "command not found")],
)
def test_run_errors(monkeypatch, capsys, args, code, message):
    with pytest.raises(SystemExit) as exit_info:
        run_cli(monkeypatch, capsys, "run", *args)
    assert exit_info.value.code == code
    assert message in capsys.readouterr().out


def test_start(monkeypatch, capsys):
    from profyle.infrastructure import server

    started = {}

    async def start_server(port, host):
        started.update(port=port, host=host)

    monkeypatch.setattr(server, "start_server", start_server)
    run_cli(monkeypatch, capsys, "start", "--port", "5555")

    assert started == {"port": 5555, "host": "127.0.0.1"}


def test_mcp(monkeypatch, capsys):
    from profyle.infrastructure import mcp_server

    ran = []
    monkeypatch.setattr(mcp_server, "run", lambda: ran.append(True))
    run_cli(monkeypatch, capsys, "mcp")
    assert ran == [True]

    monkeypatch.setitem(sys.modules, "profyle.infrastructure.mcp_server", None)
    assert "pip install 'profyle[mcp]'" in run_cli(monkeypatch, capsys, "mcp")
