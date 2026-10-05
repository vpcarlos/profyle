"""Trace one request (or any block of code) with VizTracer and store the result.

    with RequestTrace(name="GET /users", repo=repo):
        ...

Middlewares create one per request through `Integration.tracer`, with
`store_in_background=True`: turning the tracer's buffer into a trace and writing it to
the database can take a moment on big traces, and the request should not wait for it.

One trace at a time: VizTracer records one trace per process, and a trace being stored
must not overlap with the next one (Python 3.12+ traces every thread, so the storing
would be traced and slowed down). A request that arrives while another one is traced is
served untraced (`on_busy` is called). One that arrives while the previous trace is
being stored waits for it, up to `wait_for_storing` seconds; async middlewares wait in a
worker thread (`storing_in_progress`, `wait_until_stored`) so the event loop is not
blocked.

A trace can be suspended and resumed: the WSGI middleware traces the app call and then
each chunk of a streamed body, with the tracer stopped in between. A suspended trace
that nobody resumes (a client that never reads the body) is finished by the next request
that wants to be traced, or when the process exits, so it never blocks tracing.
"""

import atexit
import fnmatch
import functools
import re
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from viztracer import VizTracer
from viztracer.report_builder import ReportBuilder

from profyle.application.requests.capture import redact
from profyle.domain.trace import NewTrace, RecordedRequest
from profyle.domain.trace_repository import TraceRepository

STORE_THREAD = "profyle-store"

# What a RequestTrace is doing.
NOT_TRACED, RUNNING, STOPPING, SUSPENDED, FINISHED = (
    "not traced",
    "running",
    "stopping",  # being suspended: the tracer stops in a moment
    "suspended",
    "finished",
)

_state = threading.Condition()
# The trace that owns the tracer (running or suspended).
_owner: "RequestTrace | None" = None
# Traces being stored.
_storing = 0
# The running tracer, for code that hooks it into other threads (see threadpool).
_active_tracer: VizTracer | None = None


# Seconds a thread gets to finish the event it is recording before the tracer stops.
STOP_GRACE = 0.005


def _stop_safely(tracer: VizTracer) -> None:
    """Stop the tracer, first letting other threads finish the event they are recording.

    VizTracer 1.1.1 races when it stops: it clears the call stacks of every thread it
    traced, while another thread may be in the middle of recording an argument (a
    __repr__ written in Python lets threads switch), and that thread then crashes the
    process. Python 3.12+ traces every thread, so stop delivering events first and give
    threads a moment to finish; earlier versions only trace the threads Profyle hooks.
    """
    if sys.version_info >= (3, 12):  # pragma: no cover - coverage is measured on 3.11
        for tool in range(6):
            if sys.monitoring.get_tool(tool) == "viztracer":
                sys.monitoring.set_events(tool, 0)
        time.sleep(STOP_GRACE)
    tracer.stop()


def active_tracer() -> VizTracer | None:
    return _active_tracer


def storing_in_progress() -> bool:
    return _storing > 0


def wait_until_stored(timeout: float = 30) -> bool:
    """Wait until no trace is being stored; False on timeout."""
    with _state:
        return _state.wait_for(lambda: _storing == 0, timeout)


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
    # Store the trace in a background thread instead of before finish() returns.
    store_in_background: bool = False
    # How long start() waits for the previous trace to be stored.
    wait_for_storing: float = 0
    tracer: VizTracer | None = None
    phase: str = NOT_TRACED

    def should_trace(self) -> bool:
        if not self.pattern:
            return True
        return _glob(self.pattern).match(self.path or self.name) is not None

    def __enter__(self) -> "RequestTrace":
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.finish()

    def start(self) -> None:
        global _owner, _active_tracer
        if not self.should_trace():
            return
        with _state:
            # Wait for the previous trace to be stored, or to finish suspending.
            _state.wait_for(_ready_for_next_trace, self.wait_for_storing)
            # The owner is suspended: nobody is reading its body anymore.
            abandoned = _owner if _owner is not None and _owner.phase == SUSPENDED else None
            if abandoned:
                abandoned._release()
        if abandoned:
            abandoned._store_after_stop(background=False)
        with _state:
            busy = _owner is not None or _storing > 0
            if not busy:
                self.phase, _owner = RUNNING, self
        if busy:
            if self.on_busy:
                self.on_busy()
            return
        self.tracer = _tracer(self.min_duration, self.max_stack_depth)
        self.tracer.clear()
        self.tracer.start()
        _active_tracer = self.tracer

    def suspend(self) -> None:
        """Stop the tracer but keep the trace open (and the tracer)."""
        global _active_tracer
        with _state:
            if self.phase != RUNNING:
                return
            self.phase = STOPPING
        _active_tracer = None
        _stop_safely(self.tracer)
        with _state:
            self.phase = SUSPENDED
            _state.notify_all()

    def resume(self) -> bool:
        """Restart a suspended trace; False if it is not suspended (or was finished)."""
        global _active_tracer
        with _state:
            if self.phase != SUSPENDED:
                return False
            self.phase = RUNNING
        self.tracer.start()
        _active_tracer = self.tracer
        return True

    def finish(self, background: bool | None = None) -> None:
        """Stop tracing and store the trace."""
        global _active_tracer
        with _state:
            was = self.phase
            if was not in (RUNNING, SUSPENDED):  # not traced, or already finished
                return
            self._release()
        if was == RUNNING:
            _active_tracer = None
            _stop_safely(self.tracer)
        self._store_after_stop(background)

    def _release(self) -> None:
        """Give up the tracer; the trace now counts as being stored. Holds _state."""
        global _owner, _storing
        self.phase, _owner = FINISHED, None
        _storing += 1

    def _store_after_stop(self, background: bool | None = None) -> None:
        try:
            request = self.request() if callable(self.request) else self.request
            if request is not None and not self.capture_secrets:
                request = redact(request)
        except Exception:
            _stored()
            raise
        if self.store_in_background if background is None else background:
            # Not a daemon thread: a server shutting down waits for its last traces.
            threading.Thread(target=self._store, args=(request,), name=STORE_THREAD).start()
        else:
            self._store(request)

    def _store(self, request: RecordedRequest | None) -> None:
        try:
            raw_trace = _trace_json(self.tracer)
            trace_id = self.repo.add_trace(
                NewTrace(name=self.name, raw_trace=raw_trace, request=request)
            )
            if trace_id is not None and self.on_stored:
                self.on_stored(trace_id)
        finally:
            _stored()


def _ready_for_next_trace() -> bool:
    return _storing == 0 and (_owner is None or _owner.phase != STOPPING)


def _stored() -> None:
    global _storing
    with _state:
        _storing -= 1
        _state.notify_all()


@atexit.register
def _finish_abandoned_trace() -> None:
    """Store a suspended trace nobody finished (threads cannot start at exit)."""
    owner = _owner
    if owner is not None and owner.phase == SUSPENDED:
        owner.finish(background=False)


@functools.cache
def _tracer(min_duration: float, max_stack_depth: int) -> VizTracer:
    """One VizTracer per configuration, reused by every trace and never freed.

    VizTracer must outlive every thread it traced: freeing a tracer leaves a dangling
    pointer in the thread-local state of those threads, which VizTracer writes to when
    such a thread exits (worker pools exit long after the request), corrupting memory
    and crashing the process later. Reusing the tracer also avoids allocating its event
    buffer for every request.
    """
    return VizTracer(
        log_func_args=True,
        log_print=True,
        log_func_retval=True,
        log_async=True,
        file_info=True,
        min_duration=min_duration,
        max_stack_depth=max_stack_depth,
        verbose=0,
    )


def _trace_json(tracer: VizTracer) -> dict:
    tracer.parse()
    report = ReportBuilder(tracer.data, verbose=0)
    tracer.data = None  # the reused tracer would otherwise keep the last trace alive
    report.prepare_json(file_info=True)
    return report.combined_json


@functools.cache
def _glob(pattern: str) -> re.Pattern:
    return re.compile(fnmatch.translate(pattern))
