"""Trace one request (or any block of code) with VizTracer and store the result.

    with RequestTrace(name="GET /users", repo=repo):
        ...

Middlewares create one per request through `Integration.tracer`.
"""

import fnmatch
import functools
import re
from collections.abc import Callable
from dataclasses import dataclass

from viztracer import VizTracer
from viztracer.report_builder import ReportBuilder

from profyle.domain.trace import NewTrace, RecordedRequest
from profyle.domain.trace_repository import TraceRepository

# The tracer of the request being traced right now. VizTracer can record one trace per
# process at a time, so this is process-wide.
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
    tracer: VizTracer | None = None

    def should_trace(self) -> bool:
        if not self.pattern:
            return True
        return _glob(self.pattern).match(self.path or self.name) is not None

    def __enter__(self) -> "RequestTrace":
        global _active_tracer
        if not self.should_trace():
            return self
        if _active_tracer is not None:
            # Starting a second tracer while a concurrent request is traced would
            # corrupt both traces.
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
        global _active_tracer
        if self.tracer is None:  # not traced: filtered out, or another request was
            return
        _active_tracer = None
        self.tracer.stop()
        request = self.request() if callable(self.request) else self.request
        trace_id = self.repo.add_trace(
            NewTrace(name=self.name, raw_trace=_trace_json(self.tracer), request=request)
        )
        if trace_id is not None and self.on_stored:
            self.on_stored(trace_id)


def _trace_json(tracer: VizTracer) -> dict:
    tracer.parse()
    report = ReportBuilder(tracer.data, verbose=0)
    report.prepare_json(file_info=True)
    return report.combined_json


@functools.cache
def _glob(pattern: str) -> re.Pattern:
    return re.compile(fnmatch.translate(pattern))
