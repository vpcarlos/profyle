import fnmatch
import re
from collections.abc import Callable
from dataclasses import dataclass

from viztracer import VizTracer
from viztracer.report_builder import ReportBuilder

from profyle.application.trace.store import store_trace
from profyle.domain.trace import RecordedRequest
from profyle.domain.trace_repository import TraceRepository

# The tracer of the request being traced right now (VizTracer is process-global).
_active_tracer: VizTracer | None = None


def active_tracer() -> VizTracer | None:
    return _active_tracer


@dataclass
class profyle:
    name: str
    repo: TraceRepository
    max_stack_depth: int = -1
    min_duration: float = 0
    pattern: str|None = None
    tracer: VizTracer|None = None
    # Set by the middleware once the response is known (see request_capture). A callable
    # is resolved after the tracer stops, so recording the exchange (copying headers,
    # fingerprinting the response) does not show up in the trace it describes.
    request: RecordedRequest | Callable[[], RecordedRequest] | None = None
    # Called with the id of the stored trace (e.g. to print a summary line).
    on_stored: Callable[[int], None] | None = None
    # Called when the request is not traced because another one is being traced.
    on_busy: Callable[[], None] | None = None

    def __enter__(self) -> "profyle":
        global _active_tracer
        if not self.should_trace():
            return self
        if _active_tracer is not None:
            # VizTracer can record one trace per process: starting a second one while a
            # concurrent request is traced would corrupt both traces.
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

    def __exit__(
        self,
        *args,
    ) -> None:
        global _active_tracer
        if _active_tracer is self.tracer:
            _active_tracer = None
        if self.tracer and self.tracer.enable:
            self.tracer.stop()
            request = self.request() if callable(self.request) else self.request
            self.tracer.parse()
            report_builder = ReportBuilder(self.tracer.data, verbose=0)
            report_builder.prepare_json(file_info=True)
            trace_id = store_trace(
                raw_trace=report_builder.combined_json,
                name=self.name,
                repo=self.repo,
                request=request,
            )
            if trace_id is not None and self.on_stored:
                self.on_stored(trace_id)

    def should_trace(self) -> bool:
        if not self.pattern:
            return True

        regex = fnmatch.translate(self.pattern)
        reobj = re.compile(regex)
        method_and_name = self.name.split(" ")
        if len(method_and_name) > 1:
            return bool(reobj.match(method_and_name[1]))
        return bool(reobj.match(self.name))
