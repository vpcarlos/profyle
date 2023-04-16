from profyle.domain.trace_repository import TraceRepository


def vacuum(repo: TraceRepository) -> None:
    repo.vacuum()
