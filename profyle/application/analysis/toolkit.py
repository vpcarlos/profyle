"""Read-only trace analysis tools behind the MCP server and `profyle analyze`.

Every function returns plain text (Markdown or JSON) so it can be handed to a model as
a tool result as is.
"""

import json
import statistics
import time
from collections import OrderedDict, defaultdict
from typing import Any

from profyle.application import replay
from profyle.application.analysis.digest import (
    build_digest,
    compare_digests,
    get_call_details,
    get_function_source,
    render_digest,
)
from profyle.domain.trace import Trace
from profyle.domain.trace_repository import TraceRepository
from profyle.settings import settings


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
        return "No matching traces. " + _empty_db_hint()
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
        return "No traces recorded yet. " + _empty_db_hint()

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
    digest = render_digest(_digest(trace), name=f"#{trace.id} {trace.name}")
    return digest.replace("\n", "\n" + _request_summary(trace) + "\n", 1)


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


def replay_trace(
    repo: TraceRepository,
    trace_id: int,
    times: int = 1,
    base_url: str | None = None,
    headers: dict[str, str] | None = None,
    allow_unsafe_method: bool = False,
    wait_seconds: float = 30,
) -> str:
    """Send the request behind a trace again and report the traces it produced."""
    original = _load(repo, trace_id)
    request = original.request
    if request is None:
        return (
            f"Trace {trace_id} has no recorded request (it was captured by an older "
            "Profyle version). Ask the user to trigger the request once more."
        )
    target = base_url or request.base_url
    try:
        replay.check_replayable(request, target, allow_unsafe_method)
    except replay.ReplayRefused as error:
        return str(error)

    runs = []
    for _ in range(max(1, min(times, 10))):
        last_id = _latest_trace_id(repo)
        response = replay.send(request, base_url=target, extra_headers=headers)
        if response.error:
            runs.append((response, None))
            break
        runs.append((response, _wait_for_trace(repo, original.name, last_id, wait_seconds)))

    return _render_replay(original, runs, missing_auth=replay.redacted_headers(request),
                          headers=headers)


def _render_replay(original: Trace, runs, missing_auth: list[str], headers) -> str:
    request = original.request
    lines = [
        f"Replayed {request.method} {request.path} (original trace #{original.id}: "
        f"{round(original.duration / 1000, 2)} ms, status {request.status_code}).",
        "",
        "| run | status | response ms | new trace | trace ms |",
        "|---|---|---|---|---|",
    ]
    new_ids, durations = [], []
    for number, (response, trace) in enumerate(runs, start=1):
        if response.error:
            lines.append(f"| {number} | error | {response.elapsed_ms} | – | – |")
            lines.append(
                f"\nCould not reach the app ({response.error}). Is it running? "
                "Pass base_url if it listens on a different host or port."
            )
            break
        trace_cell = ms_cell = "not recorded"
        if trace:
            new_ids.append(trace.id)
            durations.append(trace.duration / 1000)
            trace_cell, ms_cell = f"#{trace.id}", str(round(trace.duration / 1000, 2))
        lines.append(
            f"| {number} | {response.status_code} | {response.elapsed_ms} | {trace_cell} "
            f"| {ms_cell} |"
        )

    statuses = {response.status_code for response, _ in runs if not response.error}
    status_changed = bool(request.status_code and statuses and statuses != {request.status_code})
    if status_changed:
        lines.append(
            f"\n⚠ Status changed: original {request.status_code}, now "
            f"{', '.join(str(s) for s in sorted(statuses))}. The endpoint behaves "
            "differently; check this before comparing timings."
        )
    if missing_auth and not headers:
        lines.append(
            f"\nNote: these headers were redacted when recording: {', '.join(missing_auth)}. "
            "If the endpoint needs them, ask the user for credentials and pass them as headers."
        )
    if durations:
        next_step = (
            "" if status_changed else f" Next: compare_traces({original.id}, {new_ids[-1]})."
        )
        lines.append(
            f"\nMedian trace duration: {round(statistics.median(durations), 2)} ms.{next_step}"
        )
    elif runs and not runs[-1][0].error:
        lines.append(
            "\nThe app answered but no new trace was stored. Make sure it runs with "
            f"ProfyleMiddleware and the same database ({settings.get_db_path()}), and that "
            "PROFYLE_PATTERN matches this path."
        )
    return "\n".join(lines)


def _request_summary(trace: Trace) -> str:
    request = trace.request
    if request is None:
        return "Request: not recorded (cannot be replayed)."
    body = (
        "body too large to record" if request.body_truncated
        else f"body {len(request.body)} chars" if request.body else "no body"
    )
    replayable = "replayable" if not request.body_truncated else "not replayable"
    return (
        f"Request: {request.method} {request.base_url}{request.path} · status "
        f"{request.status_code} · {body} · {replayable}"
    )


def _latest_trace_id(repo: TraceRepository) -> int:
    return max((int(t.id) for t in repo.get_all_traces()), default=0)


def _wait_for_trace(
    repo: TraceRepository, name: str, after_id: int, wait_seconds: float
) -> Trace | None:
    # The middleware stores the trace after the response is sent, so poll briefly.
    deadline = time.monotonic() + wait_seconds
    while True:
        new = [t for t in repo.get_all_traces() if int(t.id) > after_id and t.name == name]
        if new:
            return min(new, key=lambda t: int(t.id))
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.25)


def _empty_db_hint() -> str:
    return (
        f"Reading traces from {settings.get_db_path()}. If the app records traces "
        "elsewhere, run it and this server with the same PROFYLE_DB."
    )
