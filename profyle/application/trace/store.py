from typing import Any

from profyle.domain.trace import TraceCreate
from profyle.domain.trace_repository import TraceRepository


def store_trace_selected(trace_id: int, repo: TraceRepository) -> None:
    repo.store_trace_selected(trace_id=trace_id)


def store_trace(raw_trace: dict[Any, Any], name: str, repo: TraceRepository) -> None:
    repo.store_trace(TraceCreate(raw_trace=raw_trace, name=name))
