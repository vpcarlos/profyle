import io
import os
import subprocess
import sys

from profyle.infrastructure import console


def test_reporter_stops_after_a_failure(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("no python")

    monkeypatch.setattr(subprocess, "Popen", broken)
    reporter = console.ConsoleReporter("/tmp/x.db")

    reporter.report(1)
    assert reporter._failed
    reporter.report(2)  # ignored once failed


def test_display_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert console.display_path(str(tmp_path / ".profyle" / "p.db")) == os.path.join(
        ".profyle", "p.db"
    )
    assert console.display_path("/elsewhere/p.db") == "/elsewhere/p.db"

    def other_drive(path):
        raise ValueError("path is on mount 'D:'")

    monkeypatch.setattr(os.path, "relpath", other_drive)
    assert console.display_path("D:/p.db") == "D:/p.db"


def test_say_falls_back_to_ascii(monkeypatch):
    stream = io.TextIOWrapper(io.BytesIO(), encoding="ascii", newline="\n")
    monkeypatch.setattr(sys, "stderr", stream)

    console.say("GET /a → b")

    stream.flush()
    assert stream.buffer.getvalue().decode() == "profyle > GET /a ? b\n"


def test_worker_prints_one_line_per_trace(project_db, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("1 first\n2\n999\n"))

    console._worker()

    lines = capsys.readouterr().err.splitlines()
    assert lines[0].startswith("profyle ▸ GET /users") and lines[0].endswith(
        "· first request, includes warm-up"
    )
    assert "· #2 ·" in lines[1]
    assert lines[2] == "profyle ▸ trace 999: could not summarize (Trace 999 not found)"


def test_messages_are_shown_while_a_request_is_traced(capsys):
    from profyle.application.request_trace import RequestTrace
    from tests.unit.repository import InMemoryTraceRepository

    # VizTracer replaces print() while it traces; Profyle's messages must still show.
    with RequestTrace(name="GET /", repo=InMemoryTraceRepository()):
        console.say("GET /other not traced")

    assert "GET /other not traced" in capsys.readouterr().err
