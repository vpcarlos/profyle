import fnmatch
import json
import re
from typing import Optional
from dataclasses import dataclass

from viztracer import VizTracer

from profyle.application.trace.store import store_trace
from profyle.domain.trace_repository import TraceRepository
from profyle.domain.trace import TraceCreate


@dataclass
class profyle:
    name: str
    repo: TraceRepository
    pattern: Optional[str] = None
    tracer: VizTracer = VizTracer(
        verbose=0,
        log_async=True
    )

    def __enter__(self):

        if self.should_trace():
            self.tracer.start()

    def __exit__(
        self,
        *args,
    ):
        if not  self.tracer.enable:
            return
        self.tracer.stop()
        self.tracer.parse()
        new_trace = TraceCreate(
            data=json.dumps(self.tracer.data),
            name=self.name
        )
        store_trace(
            new_trace=new_trace,
            repo=self.repo
        )

    def should_trace(self) -> bool:
        if not self.pattern:
            return True

        regex = fnmatch.translate(self.pattern)
        reobj = re.compile(regex)
        return bool(reobj.match(self.name))
