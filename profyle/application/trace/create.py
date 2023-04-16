from profyle.domain.trace_repository import TraceRepository


def create_trace_selected_table(repo: TraceRepository) -> None:
    return repo.create_trace_selected_table()


def create_trace_table(repo: TraceRepository) -> None:
    return repo.create_trace_table()
