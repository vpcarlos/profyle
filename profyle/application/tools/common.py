"""What the tools share: loading a trace and its (cached) digest."""

from profyle.application.analysis.digest import DIGEST_VERSION, Digest, build_digest, headline
from profyle.domain.trace import Trace
from profyle.domain.trace_repository import TraceRepository
from profyle.settings import settings


class TraceNotFound(LookupError):
    pass


def load_trace(repo: TraceRepository, trace_id: int, include_data: bool = True) -> Trace:
    trace = repo.get_trace(trace_id, include_data=include_data)
    if not trace or (include_data and not trace.data):
        raise TraceNotFound(f"Trace {trace_id} not found")
    return trace


def digest_of(repo: TraceRepository, trace: Trace) -> Digest:
    """The stored digest of a trace, built and stored on first use.

    Digests are computed on the reading side (here, or ahead of time by
    precompute_digests), never in the app's request path."""
    stored = repo.get_digest(trace.id)
    if stored and stored.get("version") == DIGEST_VERSION:
        return Digest.model_validate(stored)
    data = trace.data
    if data is None:
        full = repo.get_trace(trace.id)
        data = full.data if full else None
    if not data:
        raise TraceNotFound(f"Trace {trace.id} has no data")
    digest = build_digest(data)
    repo.store_digest(trace.id, digest.model_dump(), headline(digest))
    return digest


def precompute_digests(repo: TraceRepository, limit: int = 50) -> int:
    """Build missing digests for the newest traces; returns how many were built."""
    built = 0
    for trace_id in repo.trace_ids_without_digest(limit):
        trace = repo.get_trace(trace_id)
        if trace and trace.data:
            digest_of(repo, trace)
            built += 1
    return built


def where_traces_are_read() -> str:
    return (
        f"Reading traces from {settings.get_db_path()}. If the app records traces "
        "elsewhere, run it and this server with the same PROFYLE_DB."
    )
