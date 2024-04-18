from typing import Optional

from profyle.domain.trace import Trace
from profyle.domain.trace_repository import TraceRepository


def get_all_traces(repo: TraceRepository) -> list[Trace]:
    return repo.get_all_traces()


def get_trace_selected(repo: TraceRepository) -> Optional[int]:
    return repo.get_trace_selected()


def get_trace_by_id(trace_id: int, repo: TraceRepository) -> Optional[Trace]:
    return repo.get_trace_by_id(trace_id)
