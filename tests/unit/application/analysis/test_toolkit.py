import pytest

from profyle.application.analysis import toolkit
from tests.unit.application.analysis.test_digest import make_trace
from tests.unit.repository import InMemoryTraceRepository, store_trace


@pytest.fixture
def repo():
    repo = InMemoryTraceRepository()
    store_trace(raw_trace=make_trace(), name="GET /users?page=1", repo=repo)
    store_trace(raw_trace=make_trace(get_user_dur=5.0), name="GET /users?page=2", repo=repo)
    return repo


def test_list_and_rank_endpoints(repo):
    assert "GET /users?page=1" in toolkit.list_traces(repo)
    ranking = toolkit.slowest_endpoints(repo)
    assert "| GET /users | 2 |" in ranking


def test_analyze_and_drill_down(repo):
    trace_id = repo.traces[0].id

    assert "handler → get_user ×12" in toolkit.analyze_trace(repo, trace_id)
    assert '"calls": 12' in toolkit.call_details(repo, trace_id, "get_user")
    assert "def handler" in toolkit.function_source(repo, trace_id, "handler")
    assert "delta_total_ms" in toolkit.compare_traces(repo, trace_id, repo.traces[1].id)


def test_unknown_trace(repo):
    with pytest.raises(toolkit.TraceNotFound):
        toolkit.analyze_trace(repo, 123)
