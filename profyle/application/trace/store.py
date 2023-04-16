from profyle.domain.trace import Trace
from profyle.domain.trace_repository import TraceRepository


def store_trace_selected(trace_id: int, repo: TraceRepository) -> None:
    repo.store_trace_selected(trace_id=trace_id)


def store_trace(trace: Trace, repo: TraceRepository) -> None:
    repo.store_trace(trace)
