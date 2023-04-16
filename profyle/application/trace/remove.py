from profyle.domain.trace_repository import TraceRepository


def remove_all_traces(repo: TraceRepository) -> int:
    return repo.remove_all_traces()