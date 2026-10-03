import asyncio
import threading

import pytest

from profyle.application.request_trace import (
    RequestTrace,
    storing_in_progress,
    wait_until_stored,
)
from tests.unit.repository import InMemoryTraceRepository


def test_should_trace_a_process():
    trace_repo = InMemoryTraceRepository()

    with RequestTrace(
        name="test",
        repo=trace_repo,
    ):
        print("demo")

    assert len(trace_repo.traces) == 1
    assert len(trace_repo.traces[0].data)


@pytest.mark.asyncio
async def test_should_trace_an_async_process():
    trace_repo = InMemoryTraceRepository()

    with RequestTrace(
        name="test",
        repo=trace_repo,
    ):
        await asyncio.sleep(0.1)

    assert len(trace_repo.traces) == 1
    assert len(trace_repo.traces[0].data)
    assert trace_repo.traces[0].duration / 1000 > 0.1


@pytest.mark.asyncio
async def test_should_trace_a_process_with_min_duration():
    trace_repo = InMemoryTraceRepository()

    with RequestTrace(name="test", repo=trace_repo, min_duration=1):
        await asyncio.sleep(2)

    assert len(trace_repo.traces) == 1
    assert len(trace_repo.traces[0].data)
    assert trace_repo.traces[0].duration / 1000 > 2


@pytest.mark.asyncio
async def test_should_not_trace_a_process_if_min_duration_not_reached():
    trace_repo = InMemoryTraceRepository()
    with RequestTrace(name="test", repo=trace_repo, min_duration=3000000):
        await asyncio.sleep(2)

    assert len(trace_repo.traces) == 1
    assert len(trace_repo.traces[0].data)
    assert int(trace_repo.traces[0].duration / 1000) == 0


def test_concurrent_trace_without_busy_callback_is_skipped():
    trace_repo = InMemoryTraceRepository()

    with RequestTrace(name="outer", repo=trace_repo):
        with RequestTrace(name="inner", repo=trace_repo) as inner:
            assert inner.tracer is None

    assert [t.name for t in trace_repo.traces] == ["outer"]


def test_pattern_matches_names_without_a_method():
    assert RequestTrace(name="nightly-job", repo=None, pattern="nightly*").should_trace()
    assert not RequestTrace(name="other", repo=None, pattern="nightly*").should_trace()


class SlowRepository(InMemoryTraceRepository):
    """Stores a trace only once `release` is set, doing some work meanwhile."""

    def __init__(self):
        super().__init__()
        self.release = threading.Event()

    def add_trace(self, trace):
        self.release.wait(10)
        storing_work()
        return super().add_trace(trace)


def storing_work():
    return sorted(range(1000))


def test_traces_are_stored_in_the_background_and_the_next_one_waits_for_it():
    repo = SlowRepository()
    busy = []

    def traced(name, wait=0):
        with RequestTrace(
            name=name,
            repo=repo,
            store_in_background=True,
            wait_for_storing=wait,
            on_busy=lambda: busy.append(name),
        ):
            sum(range(10))

    traced("first")  # returns while its trace waits to be stored
    assert storing_in_progress() and repo.traces == []
    traced("impatient")  # does not wait: served untraced
    assert busy == ["impatient"]

    threading.Timer(0.1, repo.release.set).start()
    traced("second", wait=5)  # waits until "first" is stored, then is traced
    assert wait_until_stored()
    assert [t.name for t in repo.traces] == ["first", "second"]
    # Storing "first" happened before "second" started: it is not in its trace.
    names = {event.get("name", "") for event in repo.traces[1].data["traceEvents"]}
    assert not any("storing_work" in name for name in names)


def test_a_failing_request_description_frees_the_tracer():
    repo = InMemoryTraceRepository()

    def broken_request():
        raise RuntimeError("cannot describe the request")

    with pytest.raises(RuntimeError):
        with RequestTrace(name="broken", repo=repo) as trace:
            trace.request = broken_request

    assert wait_until_stored(timeout=1)
    with RequestTrace(name="next", repo=repo):
        pass
    assert [t.name for t in repo.traces] == ["next"]
