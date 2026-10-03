"""Trace sync code that ASGI frameworks run in a worker thread pool.

On Python < 3.12 VizTracer hooks each thread with sys.setprofile, and only threads
created while a trace is running get hooked. Pool threads are long-lived, so from the
second request on a sync FastAPI endpoint (or sync dependency) would be invisible.
Starlette and FastAPI send all sync work through `anyio.to_thread.run_sync`, so while a
request is traced we enable tracing inside the worker thread before running the work.
Python 3.12+ traces every thread through sys.monitoring and needs none of this.
"""

import functools
import sys

from profyle.application.profyle import active_tracer

_patched = False


def trace_worker_threads() -> None:
    global _patched
    if _patched or sys.version_info >= (3, 12):
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

        def traced(*inner_args):
            tracer.enable_thread_tracing()
            try:
                return func(*inner_args)
            finally:
                # Unhook so the pool thread does not keep this request's tracer (and its
                # event buffer) alive after the request.
                sys.setprofile(None)

        return await original(traced, *args, **kwargs)

    anyio.to_thread.run_sync = run_sync
    _patched = True
