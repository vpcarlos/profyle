from profyle.application import tools
from profyle.application.analysis.digest import DIGEST_VERSION, build_digest, headline
from tests.unit.application.analysis.test_digest import make_trace
from tests.unit.repository import InMemoryTraceRepository, store_trace


class CountingRepository(InMemoryTraceRepository):
    """Counts how often the (large) trace data is loaded."""

    def __init__(self):
        super().__init__()
        self.data_loads = 0

    def get_trace(self, trace_id, include_data=True):
        if include_data:
            self.data_loads += 1
        return super().get_trace(trace_id, include_data)


def repo_with_trace():
    repo = CountingRepository()
    store_trace(raw_trace=make_trace(), name="GET /users", repo=repo)
    return repo, repo.traces[0].id


def test_headline_names_the_main_suspect():
    # make_trace: handler sleeps 0.5 of 1 ms, then calls get_user 12 times (1.2%).
    assert headline(build_digest(make_trace())) == "wait: time.sleep 0.5 ms (50.0%)"
    handler = "handler (/app/views.py:8)"
    get_user = "get_user (/app/views.py:4)"
    events = [{"ph": "X", "pid": 1, "tid": 1, "ts": 0, "dur": 1000, "name": handler}]
    events += [
        {"ph": "X", "pid": 1, "tid": 1, "ts": 50 + i * 70, "dur": 60, "name": get_user}
        for i in range(12)
    ]
    assert headline(build_digest({"traceEvents": events})) == (
        "repeated: handler → get_user ×12 (72.0%)"
    )


def test_digest_is_built_once_and_reused():
    repo, trace_id = repo_with_trace()

    first = tools.analyze_trace(repo, trace_id)
    second = tools.analyze_trace(repo, trace_id)

    assert first == second
    assert repo.data_loads == 1
    assert repo.digests[trace_id]["version"] == DIGEST_VERSION
    assert repo.traces[0].headline


def test_outdated_digest_is_rebuilt():
    repo, trace_id = repo_with_trace()
    repo.digests[trace_id] = {"version": DIGEST_VERSION - 1}

    tools.analyze_trace(repo, trace_id)

    assert repo.digests[trace_id]["version"] == DIGEST_VERSION


def test_precompute_fills_listings():
    repo, trace_id = repo_with_trace()
    assert "not analyzed yet" in tools.list_traces(repo)

    assert tools.precompute_digests(repo) == 1
    assert tools.precompute_digests(repo) == 0

    listing = tools.list_traces(repo)
    assert "not analyzed yet" not in listing
    assert repo.traces[0].headline in listing
    assert f"#{trace_id}: {repo.traces[0].headline}" in tools.slowest_endpoints(repo)


def test_headline_ignores_recursion():
    walker = "encode (/lib/site-packages/fastapi/encoders.py:1)"
    events = [{"ph": "X", "pid": 1, "tid": 1, "ts": 0, "dur": 1000, "name": walker}]
    events += [
        {"ph": "X", "pid": 1, "tid": 1, "ts": 50 + i * 70, "dur": 60, "name": walker}
        for i in range(12)
    ]
    assert not headline(build_digest({"traceEvents": events})).startswith("repeated:")
