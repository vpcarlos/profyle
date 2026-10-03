import socket

from profyle.application.analysis import toolkit
from profyle.domain.trace import RecordedRequest
from tests.unit.repository import InMemoryTraceRepository, store_trace


def test_empty_database_explains_the_setup():
    report = toolkit.doctor(InMemoryTraceRepository())

    assert "✗ Database" in report and "has no traces" in report
    assert report.endswith("Fix the ✗ items above, then run doctor again.")


def test_reports_old_traces_without_requests():
    repo = InMemoryTraceRepository()
    store_trace(raw_trace={"traceEvents": []}, name="GET /", repo=repo)

    report = toolkit.doctor(repo)

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
        report = toolkit.doctor(repo)
    finally:
        listener.close()

    assert f"✓ The app is running at http://127.0.0.1:{port}" in report
    assert report.endswith("Ready.")
    assert "Nothing is listening" in toolkit.doctor(repo)
