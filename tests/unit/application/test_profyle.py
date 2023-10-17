import pytest
import asyncio

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
    assert trace_repo.traces[0].duration/1000 > 0.1


@pytest.mark.asyncio
async def test_should_trace_a_process_with_min_duration():
    trace_repo = InMemoryTraceRepository()

    with profyle(
        name="test",
        repo=trace_repo,
        min_duration=1
    ):
        await asyncio.sleep(2)

    assert len(trace_repo.traces) == 1
    assert len(trace_repo.traces[0].data)
    assert trace_repo.traces[0].duration/1000 > 2


@pytest.mark.asyncio
async def test_should_not_trace_a_process_if_min_duration_not_reached():
    trace_repo = InMemoryTraceRepository()
    with profyle(
        name="test",
        repo=trace_repo,
        min_duration=3000
    ):
        await asyncio.sleep(2)

    assert len(trace_repo.traces) == 1
    assert len(trace_repo.traces[0].data)
    assert int(trace_repo.traces[0].duration/1000) == 0
