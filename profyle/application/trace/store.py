from profyle.domain.trace import TraceCreate
from profyle.domain.trace_repository import TraceRepository


def store_trace_selected(trace_id: int, repo: TraceRepository) -> None:
    repo.store_trace_selected(trace_id=trace_id)


def store_trace(new_trace: TraceCreate, repo: TraceRepository) -> None:
    repo.store_trace(new_trace)
