import tempfile
import json
import fnmatch
import re
from typing import Any, Optional

from viztracer import VizTracer

from profyle.application.trace.store import store_trace
from profyle.domain.trace_repository import TraceRepository
from profyle.domain.trace import Trace


class profyle:

    def __init__(
        self,
        name: str,
        pattern: Optional[str] = None,
        tracer: VizTracer = VizTracer(
            verbose=0,
            log_async=True
        )
    ) -> None:
        self.name = name
        self.tracer = tracer
        self.temp_file = None
        self.pattern = pattern
        self.trace: Optional[Trace] = None

    def __enter__(self):

        if self.should_trace():
            self.temp_file = tempfile.NamedTemporaryFile(suffix='.json')
            self.tracer.start()

    def __exit__(
        self,
        *args,
    ):
        if self.temp_file:
            self.tracer.stop()
            self.tracer.save(self.temp_file.name)
            self.temp_file.close()
            self.data = self.tracer.data

            self.trace = Trace(
                data=json.dumps(self.data),
                name=self.name,
            )

    def should_trace(self) -> bool:
        if not self.pattern:
            return True

        regex = fnmatch.translate(self.pattern)
        reobj = re.compile(regex)
        return bool(reobj.match(self.name))


class profyle_stored(profyle):

    def __init__(
        self,
        repo: TraceRepository,
        **data: Any,
    ) -> None:
        self.repo = repo
        super().__init__(**data)

    def __exit__(self, *args):
        super().__exit__(*args)

        if self.temp_file and self.trace:
            store_trace(
                trace=self.trace,
                repo=self.repo
            )
