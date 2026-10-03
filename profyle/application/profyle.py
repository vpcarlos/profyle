import fnmatch
import re
from dataclasses import dataclass

from viztracer import VizTracer
from viztracer.report_builder import ReportBuilder

from profyle.application.trace.store import store_trace
from profyle.domain.trace_repository import TraceRepository


@dataclass
class profyle:
    name: str
    repo: TraceRepository
    max_stack_depth: int = -1
    min_duration: float = 0
    pattern: str|None = None
    tracer: VizTracer|None = None

    def __enter__(self) -> None:

        if self.should_trace():
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

    def __exit__(
        self,
        *args,
    ) -> None:
        if self.tracer and self.tracer.enable:
            self.tracer.stop()
            self.tracer.parse()
            report_builder = ReportBuilder(self.tracer.data, verbose=0)
            report_builder.prepare_json(file_info=True)
            store_trace(raw_trace=report_builder.combined_json, name=self.name, repo=self.repo)

    def should_trace(self) -> bool:
        if not self.pattern:
            return True

        regex = fnmatch.translate(self.pattern)
        reobj = re.compile(regex)
        method_and_name = self.name.split(" ")
        if len(method_and_name) > 1:
            return bool(reobj.match(method_and_name[1]))
        return bool(reobj.match(self.name))
