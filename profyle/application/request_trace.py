"""Trace one request (or any block of code) with VizTracer and store the result.

    with RequestTrace(name="GET /users", repo=repo):
        ...

Middlewares create one per request through `Integration.tracer`, with
`store_in_background=True`: turning the tracer's buffer into a trace and writing it to
the database can take a moment on big traces, and the request should not wait for it.

VizTracer records one trace per process at a time, so a request that arrives while
another one is traced is served untraced (`on_busy` is called); so is one that arrives
while MAX_PENDING traces are still being stored, which bounds the memory they hold.
Storing runs in threads named "profyle-store", whose events are left out of traces
(Python 3.12+ traces every thread).
"""

import fnmatch
import functools
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass

from viztracer import VizTracer
from viztracer.report_builder import ReportBuilder

from profyle.application.requests.capture import redact
from profyle.domain.trace import NewTrace, RecordedRequest
from profyle.domain.trace_repository import TraceRepository

MAX_PENDING = 2
STORE_THREAD = "profyle-store"

_state = threading.Condition()
# A request is being traced (its tracer may still be starting or stopping).
_tracing = False
# Traces started and not stored yet (including the one being traced).
_pending = 0
# The running tracer, for code that hooks it into other threads (see threadpool).
_active_tracer: VizTracer | None = None


def active_tracer() -> VizTracer | None:
    return _active_tracer


@dataclass
class RequestTrace:
    name: str
    repo: TraceRepository
    # What `pattern` is matched against; defaults to the name.
    path: str | None = None
    # Glob such as "/api/*"; None traces everything.
    pattern: str | None = None
    max_stack_depth: int = -1
    min_duration: float = 0
    # Set by the middleware once the response is known (see request_capture). A callable
    # is resolved after the tracer stops, so recording the exchange (copying headers,
    # fingerprinting the response) does not show up in the trace it describes.
    request: RecordedRequest | Callable[[], RecordedRequest] | None = None
    # Called with the id of the stored trace (e.g. to print a summary line).
    on_stored: Callable[[int], None] | None = None
    # Called when the request is not traced because another one is being traced.
    on_busy: Callable[[], None] | None = None
    # Keep credentials in the recorded request instead of redacting them.
    capture_secrets: bool = False
    # Store the trace in a background thread instead of before __exit__ returns.
    store_in_background: bool = False
    tracer: VizTracer | None = None

    def should_trace(self) -> bool:
        if not self.pattern:
            return True
        return _glob(self.pattern).match(self.path or self.name) is not None

    def __enter__(self) -> "RequestTrace":
        global _active_tracer, _tracing, _pending
        if not self.should_trace():
            return self
        with _state:
            # A second tracer started while a concurrent request is traced would
            # corrupt both traces.
            busy = _tracing or _pending >= MAX_PENDING
            if not busy:
                _tracing = True
                _pending += 1
        if busy:
            if self.on_busy:
                self.on_busy()
            return self
        self.tracer = VizTracer(
            log_func_args=True,
            log_print=True,
            log_func_retval=True,
            log_async=True,
            file_info=True,
            min_duration=self.min_duration,
            max_stack_depth=self.max_stack_depth,
            verbose=0,
        )
        self.tracer.start()
        _active_tracer = self.tracer
        return self

    def __exit__(self, *exc_info) -> None:
        global _active_tracer, _tracing
        if self.tracer is None:  # not traced: filtered out, or another request was
            return
        _active_tracer = None
        self.tracer.stop()
        with _state:
            _tracing = False
        try:
            request = self.request() if callable(self.request) else self.request
            if request is not None and not self.capture_secrets:
                request = redact(request)
        except Exception:
            _stored()
            raise
        if self.store_in_background:
            # Not a daemon thread: a server shutting down waits for its last traces.
            threading.Thread(target=self._store, args=(request,), name=STORE_THREAD).start()
        else:
            self._store(request)

    def _store(self, request: RecordedRequest | None) -> None:
        try:
            raw_trace = _trace_json(self.tracer)
            self.tracer = None  # the buffer can be freed
            trace_id = self.repo.add_trace(
                NewTrace(name=self.name, raw_trace=raw_trace, request=request)
            )
            if trace_id is not None and self.on_stored:
                self.on_stored(trace_id)
        finally:
            _stored()


def _stored() -> None:
    global _pending
    with _state:
        _pending -= 1
        _state.notify_all()


def wait_until_stored(timeout: float = 30) -> bool:
    """Wait until every started trace is stored (for tests and scripts)."""
    with _state:
        return _state.wait_for(lambda: _pending == 0, timeout)


def _trace_json(tracer: VizTracer) -> dict:
    tracer.parse()
    report = ReportBuilder(tracer.data, verbose=0)
    report.prepare_json(file_info=True)
    trace = report.combined_json
    # Leave out Profyle storing earlier traces in the background.
    storing = {
        (event.get("pid"), event.get("tid"))
        for event in trace.get("traceEvents", [])
        if event.get("ph") == "M" and (event.get("args") or {}).get("name") == STORE_THREAD
    }
    if storing:
        trace["traceEvents"] = [
            e for e in trace["traceEvents"] if (e.get("pid"), e.get("tid")) not in storing
        ]
    return trace


@functools.cache
def _glob(pattern: str) -> re.Pattern:
    return re.compile(fnmatch.translate(pattern))
