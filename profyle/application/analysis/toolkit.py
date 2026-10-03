"""Read-only trace analysis tools shared by the MCP server and the in-app Claude chat.

Every function returns plain text (Markdown or JSON) so it can be handed to a model as
a tool result as is.
"""

import json
import statistics
from collections import OrderedDict, defaultdict
from typing import Any

from profyle.application.analysis.digest import (
    build_digest,
    compare_digests,
    get_call_details,
    get_function_source,
    render_digest,
)
from profyle.domain.trace import Trace
from profyle.domain.trace_repository import TraceRepository


class TraceNotFound(LookupError):
    pass


def _load(repo: TraceRepository, trace_id: int) -> Trace:
    trace = repo.get_trace_by_id(trace_id)
    if not trace or not trace.data:
        raise TraceNotFound(f"Trace {trace_id} not found")
    return trace


_DIGEST_CACHE: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
_DIGEST_CACHE_SIZE = 32


def _digest(trace: Trace) -> dict[str, Any]:
    # Keyed by id + timestamp so a deleted/recreated id never returns a stale digest.
    key = (str(trace.id), trace.timestamp)
    if key not in _DIGEST_CACHE:
        _DIGEST_CACHE[key] = build_digest(trace.data)
        if len(_DIGEST_CACHE) > _DIGEST_CACHE_SIZE:
            _DIGEST_CACHE.popitem(last=False)
    _DIGEST_CACHE.move_to_end(key)
    return _DIGEST_CACHE[key]


def list_traces(
    repo: TraceRepository,
    limit: int = 20,
    name_contains: str | None = None,
    min_duration_ms: float = 0,
) -> str:
    traces = repo.get_all_traces()
    if name_contains:
        traces = [t for t in traces if name_contains.lower() in t.name.lower()]
    traces = [t for t in traces if t.duration / 1000 >= min_duration_ms][:limit]
    if not traces:
        return "No traces recorded yet."
    rows = ["| id | request | duration (ms) | recorded at |", "|---|---|---|---|"]
    rows += [
        f"| {t.id} | {t.name} | {round(t.duration / 1000, 2)} | {t.timestamp} |" for t in traces
    ]
    return "\n".join(rows)


def slowest_endpoints(repo: TraceRepository, limit: int = 15) -> str:
    """Aggregate recorded traces per request name: count, median, p95 and max duration."""
    groups: dict[str, list[float]] = defaultdict(list)
    for trace in repo.get_all_traces():
        groups[trace.name.split("?")[0]].append(trace.duration / 1000)
    if not groups:
        return "No traces recorded yet."

    def p95(values: list[float]) -> float:
        ordered = sorted(values)
        return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]

    rows = sorted(groups.items(), key=lambda item: p95(item[1]), reverse=True)[:limit]
    out = ["| request | traces | median ms | p95 ms | max ms |", "|---|---|---|---|---|"]
    out += [
        f"| {name} | {len(d)} | {round(statistics.median(d), 2)} | {round(p95(d), 2)} | "
        f"{round(max(d), 2)} |"
        for name, d in rows
    ]
    return "\n".join(out)


def analyze_trace(repo: TraceRepository, trace_id: int) -> str:
    trace = _load(repo, trace_id)
    return render_digest(_digest(trace), name=f"#{trace.id} {trace.name}")


def function_source(repo: TraceRepository, trace_id: int, function: str) -> str:
    trace = _load(repo, trace_id)
    source = get_function_source(trace.data, function)
    return source or f"No source captured for '{function}' in trace {trace_id}."


def call_details(repo: TraceRepository, trace_id: int, function: str) -> str:
    trace = _load(repo, trace_id)
    details = get_call_details(trace.data, function)
    if not details:
        return f"'{function}' was not called in trace {trace_id}."
    return json.dumps(details, indent=1, default=str)


def compare_traces(repo: TraceRepository, before_id: int, after_id: int) -> str:
    before, after = _load(repo, before_id), _load(repo, after_id)
    diff = compare_digests(_digest(before), _digest(after))
    return json.dumps(diff, indent=1)
