from typing import Optional
from uuid import uuid4
import time
import json

from profyle.domain.trace import TraceCreate
from profyle.domain.trace_repository import TraceRepository
from profyle.domain.trace import Trace


class InMemoryTraceRepository(TraceRepository):
    def __init__(self):
        self.traces: list[Trace] = []
        self.selected_trace: int = 0

    def create_trace_selected_table(self) -> None:
        ...

    def create_trace_table(self) -> None:
        ...

    def delete_all_traces(self) -> int:
        removed = len(self.traces)
        self.traces = []
        return removed

    def vacuum(self) -> None:
        ...

    def store_trace_selected(self, trace_id: int) -> None:
        self.selected_trace = trace_id

    def store_trace(self, new_trace: TraceCreate) -> None:

        trace = Trace(
            id=uuid4().int,
            timestamp=str(time.time()),
            data=  json.dumps(new_trace.data),
            duration=new_trace.duration,
            name=new_trace.name,
        )
        self.traces.append(trace)

    def get_all_traces(self) -> list[Trace]:
        return self.traces

    def get_trace_by_id(self, id: int) -> Optional[Trace]:
        for trace in self.traces:
            if trace.id == id:
                return trace
        return

    def get_trace_selected(self) -> Optional[int]:
        return self.selected_trace

    def delete_trace_by_id(self, trace_id: int):
        for trace in self.traces:
            if trace.id == trace_id:
                self.traces.remove(trace)
                return
