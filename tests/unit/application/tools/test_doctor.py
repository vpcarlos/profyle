import socket

from profyle.application import tools
from profyle.domain.trace import RecordedRequest
from tests.unit.repository import InMemoryTraceRepository, store_trace


def test_empty_database_explains_the_setup():
    report = tools.doctor(InMemoryTraceRepository())

    assert "✗ Database" in report and "has no traces" in report
    assert report.endswith("Fix the ✗ items above, then run doctor again.")


def test_reports_old_traces_without_requests():
    repo = InMemoryTraceRepository()
    store_trace(raw_trace={"traceEvents": []}, name="GET /", repo=repo)

    report = tools.doctor(repo)

    assert "cannot be replayed" in report


def test_ready_when_app_is_listening():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    repo = InMemoryTraceRepository()
    store_trace(
        raw_trace={"traceEvents": []},
        name="GET /orders",
        repo=repo,
        request=RecordedRequest(method="GET", path="/orders", base_url=f"http://127.0.0.1:{port}"),
    )

    try:
        report = tools.doctor(repo)
    finally:
        listener.close()

    assert f"✓ The app is running at http://127.0.0.1:{port}" in report
    assert report.endswith("Ready.")
    assert "Nothing is listening" in tools.doctor(repo)


def test_says_why_this_database_is_read(tmp_path, monkeypatch):
    monkeypatch.delenv("PROFYLE_DB", raising=False)
    monkeypatch.setenv("PROFYLE_PROJECT_DIR", str(tmp_path))
    assert "(plugin project dir)" in tools.doctor(InMemoryTraceRepository())

    monkeypatch.delenv("PROFYLE_PROJECT_DIR")
    assert "(project root found from the working directory)" in tools.doctor(
        InMemoryTraceRepository()
    )

    monkeypatch.setenv("PROFYLE_DB", str(tmp_path / "p.db"))
    assert "(PROFYLE_DB)" in tools.doctor(InMemoryTraceRepository())
