import time
from typing import Any

from profyle.domain.trace import NewTrace, RecordedRequest, Trace
from profyle.domain.trace_repository import TraceRepository


class InMemoryTraceRepository(TraceRepository):
    def __init__(self):
        self.traces: list[Trace] = []
        self.digests: dict[int, dict] = {}
        self.runtime: dict | None = None

    def add_trace(self, trace: NewTrace) -> int:
        stored = Trace(
            id=self.latest_trace_id() + 1,
            timestamp=str(time.time()),
            data=trace.raw_trace,
            duration=trace.duration,
            name=trace.name,
            request=trace.request,
        )
        self.traces.append(stored)
        return stored.id

    def get_trace(self, trace_id: int, include_data: bool = True) -> Trace | None:
        trace = next((t for t in self.traces if t.id == trace_id), None)
        if trace is None or include_data:
            return trace
        return trace.model_copy(update={"data": None})

    def list_traces(self, limit=None, name_contains=None, min_duration_ms=0) -> list[Trace]:
        traces = [
            t
            for t in reversed(self.traces)
            if (name_contains or "").lower() in t.name.lower() and t.duration_ms >= min_duration_ms
        ]
        return traces[:limit]

    def latest_trace_id(self) -> int:
        return max((t.id for t in self.traces), default=0)

    def delete_trace(self, trace_id: int) -> None:
        self.traces = [t for t in self.traces if t.id != trace_id]

    def delete_all_traces(self) -> int:
        removed = len(self.traces)
        self.traces = []
        return removed

    def get_digest(self, trace_id: int) -> dict | None:
        return self.digests.get(trace_id)

    def store_digest(self, trace_id: int, digest: dict, headline: str) -> None:
        self.digests[trace_id] = digest
        self._stored(trace_id).headline = headline

    def trace_ids_without_digest(self, limit: int) -> list[int]:
        missing = [t.id for t in reversed(self.traces) if t.id not in self.digests]
        return missing[:limit]

    def _stored(self, trace_id: int) -> Trace:
        return next(t for t in self.traces if t.id == trace_id)

    def store_runtime(self, info: dict) -> None:
        self.runtime = info

    def get_runtime(self) -> dict | None:
        return self.runtime


def store_trace(
    raw_trace: dict[str, Any],
    name: str,
    repo: TraceRepository,
    request: RecordedRequest | None = None,
) -> int | None:
    return repo.add_trace(NewTrace(raw_trace=raw_trace, name=name, request=request))
