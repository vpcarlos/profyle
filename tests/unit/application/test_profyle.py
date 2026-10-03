import asyncio

import pytest

from profyle.application.profyle import profyle
from tests.unit.repository import InMemoryTraceRepository


def test_should_trace_a_process():
    trace_repo = InMemoryTraceRepository()

    with profyle(
        name="test",
        repo=trace_repo,
    ):
        print("demo")

    assert len(trace_repo.traces) == 1
    assert len(trace_repo.traces[0].data)


@pytest.mark.asyncio
async def test_should_trace_an_async_process():
    trace_repo = InMemoryTraceRepository()

    with profyle(
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

    with profyle(name="test", repo=trace_repo, min_duration=1):
        await asyncio.sleep(2)

    assert len(trace_repo.traces) == 1
    assert len(trace_repo.traces[0].data)
    assert trace_repo.traces[0].duration / 1000 > 2


@pytest.mark.asyncio
async def test_should_not_trace_a_process_if_min_duration_not_reached():
    trace_repo = InMemoryTraceRepository()
    with profyle(name="test", repo=trace_repo, min_duration=3000000):
        await asyncio.sleep(2)

    assert len(trace_repo.traces) == 1
    assert len(trace_repo.traces[0].data)
    assert int(trace_repo.traces[0].duration / 1000) == 0


def test_concurrent_trace_without_busy_callback_is_skipped():
    trace_repo = InMemoryTraceRepository()

    with profyle(name="outer", repo=trace_repo):
        with profyle(name="inner", repo=trace_repo) as inner:
            assert inner.tracer is None

    assert [t.name for t in trace_repo.traces] == ["outer"]


def test_pattern_matches_names_without_a_method():
    assert profyle(name="nightly-job", repo=None, pattern="nightly*").should_trace()
    assert not profyle(name="other", repo=None, pattern="nightly*").should_trace()
