from typing import Any

from profyle.domain.trace import Trace, TraceCreate, TraceData
from profyle.domain.trace_repository import TraceRepository


def store_trace_selected(trace_id: int, repo: TraceRepository) -> None:
    repo.store_trace_selected(trace_id=trace_id)


def store_trace(raw_trace: dict[Any, Any], name: str, repo: TraceRepository) -> None:
    new_trace = TraceCreate(raw_trace=raw_trace, name=name)
    trace = Trace(
        id=new_trace.id,
        timestamp=new_trace.timestamp,
        duration=new_trace.duration,
        name=new_trace.name,
    )

    trace_data = TraceData(
        trace_id=trace.id,
        events=raw_trace.get("traceEvents", []),
        file_info=raw_trace.get("file_info", {}),
        metadata=raw_trace.get("viztracer_metadata", {}),
    )
