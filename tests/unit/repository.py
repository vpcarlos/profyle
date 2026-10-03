import time

from profyle.domain.trace import RecordedRequest, Trace, TraceCreate
from profyle.domain.trace_repository import TraceRepository


class InMemoryTraceRepository(TraceRepository):
    def __init__(self):
        self.traces: list[Trace] = []
        self.digests: dict[int, dict] = {}
        self.selected_trace: int = 0

    def create_trace_selected_table(self) -> None:
        ...

    def create_trace_table(self) -> None:
        ...

    def deleted_all_selected_traces(self) -> int:
        ...

    def delete_all_traces(self) -> int:
        removed = len(self.traces)
        self.traces = []
        return removed

    def vacuum(self) -> None:
        ...

    def store_trace_selected(self, trace_id: int) -> None:
        self.selected_trace = trace_id

    def store_trace(self, new_trace: TraceCreate) -> int:
        trace = Trace(
            id=len(self.traces) + 1,
            timestamp=str(time.time()),
            data=new_trace.raw_trace,
            duration=new_trace.duration,
            name=new_trace.name,
            request=new_trace.request,
        )
        self.traces.append(trace)
        return trace.id

    def update_trace_request(self, trace_id: int, request: RecordedRequest) -> None:
        for trace in self.traces:
            if trace.id == trace_id:
                trace.request = request

    def get_all_traces(self) -> list[Trace]:
        return self.traces

    def store_runtime(self, info: dict) -> None:
        self.runtime = info

    def get_runtime(self) -> dict | None:
        return getattr(self, "runtime", None)

    def get_digest(self, trace_id: int) -> dict | None:
        return self.digests.get(trace_id)

    def store_digest(self, trace_id: int, digest: dict, headline: str) -> None:
        self.digests[trace_id] = digest
        for trace in self.traces:
            if trace.id == trace_id:
                trace.headline = headline

    def trace_ids_without_digest(self, limit: int) -> list[int]:
        missing = [t.id for t in reversed(self.traces) if t.id not in self.digests]
        return missing[:limit]

    def get_trace_by_id(self, id: int, include_data: bool = True) -> Trace|None:
        for trace in self.traces:
            if trace.id == id:
                return trace
        return

    def get_trace_selected(self) -> int|None:
        return self.selected_trace

    def delete_trace_by_id(self, trace_id: int):
        for trace in self.traces:
            if trace.id == trace_id:
                self.traces.remove(trace)
                return
