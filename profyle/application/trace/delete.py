from profyle.domain.trace_repository import TraceRepository


def delete_all_traces(repo: TraceRepository) -> int:
    return repo.delete_all_traces()


def delete_trace_by_id(repo: TraceRepository, trace_id: int):
    repo.delete_trace_by_id(trace_id=trace_id)


def delete_all_selected_traces(repo: TraceRepository) -> int:
    return repo.deleted_all_selected_traces()
