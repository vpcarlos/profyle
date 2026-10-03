"""Trace code that frameworks run in a thread other than the one that started tracing.

On Python < 3.12 VizTracer hooks each thread with sys.setprofile, and only the thread that
starts the tracer plus threads created while it runs get hooked. Long-lived threads are
therefore invisible:

- FastAPI/Starlette run sync endpoints and dependencies in a reused worker pool through
  `anyio.to_thread.run_sync`.
- Django under ASGI runs the (sync) Profyle middleware in a worker thread and async views
  back on the event loop thread through asgiref's `async_to_sync`; `sync_to_async` sends
  sync code to executor threads.
- Tornado and plain asyncio code send blocking calls to a thread pool with
  `loop.run_in_executor`.

While a request is traced, these bridges enable tracing inside the thread that actually
runs the code and unhook it afterwards, so the pool thread does not keep the request's
tracer (and its event buffer) alive. Python 3.12+ traces every thread through
sys.monitoring and needs none of this.
"""

import copy
import functools
import sys
import threading

from viztracer import VizTracer

from profyle.application.profyle import active_tracer

_patched: set[str] = set()


def trace_worker_threads() -> None:
    if sys.version_info >= (3, 12):  # pragma: no cover - coverage is measured on 3.11
        return
    _patch_anyio()
    _patch_asgiref()
    _patch_asyncio()


# VizTracer is attached to a thread with enable_thread_tracing() the first time and
# paused/resumed afterwards. Both calls must happen in the same frame (like start/stop):
# hooking or unhooking inside a helper, or with sys.setprofile(None), leaves VizTracer's
# per-thread call stack unbalanced and it stops tracing that thread for good
# ("Unexpected function return"). pause() also drops the thread's reference to the
# tracer, so pool threads do not keep a finished request's event buffer alive.
#
# Known VizTracer limitation: a thread that has ever had another Python-level profiler
# (cProfile, some debuggers) cannot be traced with enable_thread_tracing() afterwards;
# VizTracer warns "Unexpected function return" and skips that thread. Profyle still
# gives the other profiler back when the call ends.


def _first_time_in_thread(tracer) -> bool:
    threads = tracer.__dict__.setdefault("_profyle_threads", set())
    thread_id = threading.get_ident()
    if thread_id in threads:
        return False
    threads.add(thread_id)
    return True


def _restore(previous) -> None:
    # Give back a profiler the user had installed; drop hooks of earlier tracers.
    if previous is not None and not isinstance(previous, VizTracer):
        sys.setprofile(previous)


def _traced_sync(func, tracer):
    @functools.wraps(func)
    def traced(*args, **kwargs):
        previous = sys.getprofile()
        if previous is tracer:
            # Already traced, e.g. thread-sensitive code returning to the thread that
            # started the tracer: pausing it would stop the rest of the trace.
            return func(*args, **kwargs)
        if _first_time_in_thread(tracer):
            tracer.enable_thread_tracing()
        else:
            tracer.resume()
        try:
            return func(*args, **kwargs)
        finally:
            tracer.pause()
            _restore(previous)

    return traced


def _traced_async(func, tracer):
    @functools.wraps(func)
    async def traced(*args, **kwargs):
        previous = sys.getprofile()
        if previous is tracer:
            return await func(*args, **kwargs)
        if _first_time_in_thread(tracer):
            tracer.enable_thread_tracing()
        else:
            tracer.resume()
        try:
            return await func(*args, **kwargs)
        finally:
            tracer.pause()
            _restore(previous)

    return traced


def _patch_anyio() -> None:
    if "anyio" in _patched:
        return
    try:
        import anyio.to_thread
    except ImportError:
        return

    original = anyio.to_thread.run_sync

    @functools.wraps(original)
    async def run_sync(func, *args, **kwargs):
        tracer = active_tracer()
        if tracer is None:
            return await original(func, *args, **kwargs)
        return await original(_traced_sync(func, tracer), *args, **kwargs)

    anyio.to_thread.run_sync = run_sync
    _patched.add("anyio")


def _patch_asyncio() -> None:
    """`loop.run_in_executor`: how Tornado (IOLoop.run_in_executor) and plain asyncio
    code run blocking functions in a thread pool."""
    if "asyncio" in _patched:
        return
    import asyncio.base_events

    loop_class = asyncio.base_events.BaseEventLoop
    original = loop_class.run_in_executor

    @functools.wraps(original)
    def run_in_executor(self, executor, func, *args):
        tracer = active_tracer()
        if tracer is None:
            return original(self, executor, func, *args)
        return original(self, executor, _traced_sync(func, tracer), *args)

    loop_class.run_in_executor = run_in_executor
    _patched.add("asyncio")


def _patch_asgiref() -> None:
    if "asgiref" in _patched:
        return
    try:
        from asgiref.sync import AsyncToSync, SyncToAsync
    except ImportError:
        return

    original_async_to_sync = AsyncToSync.__call__
    original_sync_to_async = SyncToAsync.__call__

    @functools.wraps(original_async_to_sync)
    def async_to_sync_call(self, *args, **kwargs):
        tracer = active_tracer()
        if tracer is None:
            return original_async_to_sync(self, *args, **kwargs)
        # Work on a copy: the same wrapper may be shared by concurrent requests.
        bridge = copy.copy(self)
        bridge.awaitable = _traced_async(self.awaitable, tracer)
        return original_async_to_sync(bridge, *args, **kwargs)

    @functools.wraps(original_sync_to_async)
    async def sync_to_async_call(self, *args, **kwargs):
        tracer = active_tracer()
        if tracer is None:
            return await original_sync_to_async(self, *args, **kwargs)
        bridge = copy.copy(self)
        bridge.func = _traced_sync(self.func, tracer)
        return await original_sync_to_async(bridge, *args, **kwargs)

    AsyncToSync.__call__ = async_to_sync_call
    SyncToAsync.__call__ = sync_to_async_call
    _patched.add("asgiref")
