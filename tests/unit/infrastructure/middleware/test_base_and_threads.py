import asyncio
import importlib.metadata
import sys
import threading

import pytest
from viztracer import VizTracer

from profyle.infrastructure.middleware import base, threadpool
from profyle.infrastructure.middleware.base import Integration
from tests.unit.repository import InMemoryTraceRepository


def test_console_off_means_no_reporter_and_no_busy_message(capsys):
    integration = Integration("ASGI", trace_repo=InMemoryTraceRepository(), console=False)

    assert integration._console_callback() is None
    integration._say_busy("GET /a")
    assert capsys.readouterr().err == ""


def test_register_once_and_never_break_the_app(monkeypatch):
    repo = InMemoryTraceRepository()
    disabled = Integration("ASGI", trace_repo=repo, enabled=False)
    disabled.register()
    assert repo.get_runtime() is None

    def broken(info):
        raise RuntimeError("database locked")

    monkeypatch.setattr(repo, "store_runtime", broken)
    integration = Integration("ASGI", trace_repo=repo)
    integration.register()  # swallowed
    integration.register()  # already registered: no-op
    assert integration._registered


def test_unknown_version_when_not_installed(monkeypatch):
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(base, "version", missing)
    assert base._profyle_version() == "unknown"


def in_thread(func):
    result = {}
    thread = threading.Thread(target=lambda: result.update(value=func()))
    thread.start()
    thread.join()
    return result["value"]


@pytest.mark.skipif(sys.version_info >= (3, 12), reason="threadpool hooks run before 3.12")
def test_worker_threads_give_back_a_foreign_profiler():
    tracer = VizTracer(verbose=0)
    tracer.start()
    try:

        def foreign(*args):
            return None

        def with_foreign_profiler():
            sys.setprofile(foreign)
            threadpool._traced_sync(lambda: None, tracer)()
            return sys.getprofile()

        # Known VizTracer limitation (see threadpool): it cannot trace a thread that had
        # another Python profiler. Profyle must still give that profiler back.
        with pytest.warns(RuntimeWarning, match="Unexpected function return"):
            assert in_thread(with_foreign_profiler) is foreign
    finally:
        tracer.stop()


def test_async_tracing_is_resumed_in_a_reused_worker_thread():
    from concurrent.futures import ThreadPoolExecutor

    # Like a server's thread pool: the thread exists before the request is traced.
    pool = ThreadPoolExecutor(max_workers=1)
    pool.submit(lambda: None).result()
    tracer = VizTracer(verbose=0)
    tracer.start()
    try:

        async def work():
            return 42

        def async_twice():
            traced = threadpool._traced_async(work, tracer)
            return asyncio.run(traced()) + asyncio.run(traced())

        assert pool.submit(async_twice).result() == 84
        # Hooked once, then resumed.
        assert pool.submit(lambda: id(tracer) in threadpool._attached.tracers).result()
        # In the thread that started the tracer the coroutine runs as is.
        assert asyncio.run(threadpool._traced_async(work, tracer)()) == 42
    finally:
        tracer.stop()
        pool.shutdown()


def test_missing_optional_libraries(monkeypatch):
    monkeypatch.setattr(threadpool, "_patched", set())
    monkeypatch.setitem(sys.modules, "anyio.to_thread", None)
    monkeypatch.setitem(sys.modules, "asgiref.sync", None)

    threadpool._patch_anyio()
    threadpool._patch_asgiref()

    assert threadpool._patched == set()


def test_async_to_sync_without_an_active_trace():
    from asgiref.sync import async_to_sync

    threadpool.trace_worker_threads()

    async def answer():
        return "ok"

    assert async_to_sync(answer)() == "ok"
