"""Find slow requests and explain where their time goes."""

import json
import statistics
from collections import defaultdict

from profyle.application.analysis.digest import compare_digests, headline
from profyle.application.analysis.drilldown import get_call_details, get_function_source
from profyle.application.analysis.render import render_digest
from profyle.application.requests.fingerprint import VERDICT_TEXT
from profyle.application.requests.fingerprint import compare as compare_responses
from profyle.application.tools.common import digest_of, load_trace, where_traces_are_read
from profyle.domain.trace import Trace
from profyle.domain.trace_repository import TraceRepository

NOT_ANALYZED = "not analyzed yet"


def list_traces(
    repo: TraceRepository,
    limit: int = 20,
    name_contains: str | None = None,
    min_duration_ms: float = 0,
) -> str:
    traces = repo.list_traces(limit, name_contains, min_duration_ms)
    if not traces:
        return "No matching traces. " + where_traces_are_read()
    rows = [
        "| id | request | duration (ms) | recorded at | main finding |",
        "|---|---|---|---|---|",
    ]
    rows += [
        f"| {t.id} | {t.name} | {round(t.duration_ms, 2)} | {t.timestamp} "
        f"| {t.headline or NOT_ANALYZED} |"
        for t in traces
    ]
    return "\n".join(rows)


def slowest_endpoints(repo: TraceRepository, limit: int = 15) -> str:
    """Endpoints ranked by p95 duration, with the main finding of a typical trace."""
    traces_by_endpoint: dict[str, list[Trace]] = defaultdict(list)
    for trace in repo.list_traces():
        traces_by_endpoint[trace.name.split("?")[0]].append(trace)
    if not traces_by_endpoint:
        return "No traces recorded yet. " + where_traces_are_read()

    def durations(traces: list[Trace]) -> list[float]:
        return [t.duration_ms for t in traces]

    ranking = sorted(
        traces_by_endpoint.items(), key=lambda item: _p95(durations(item[1])), reverse=True
    )
    out = [
        "| request | traces | median ms | p95 ms | max ms | typical trace: main finding |",
        "|---|---|---|---|---|---|",
    ]
    for endpoint, traces in ranking[:limit]:
        ms = durations(traces)
        out.append(
            f"| {endpoint} | {len(ms)} | {round(statistics.median(ms), 2)} | "
            f"{round(_p95(ms), 2)} | {round(max(ms), 2)} | {_typical_finding(traces)} |"
        )
    return "\n".join(out)


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def _typical_finding(traces: list[Trace]) -> str:
    # The trace closest to the median: the slowest one is often a cold first request.
    median = statistics.median(t.duration_ms for t in traces)
    typical = min(traces, key=lambda t: abs(t.duration_ms - median))
    return f"#{typical.id}: {typical.headline or NOT_ANALYZED}"


def analyze_trace(repo: TraceRepository, trace_id: int) -> str:
    trace = load_trace(repo, trace_id, include_data=False)
    title, rest = render_digest(digest_of(repo, trace), name=f"#{trace.id} {trace.name}").split(
        "\n", 1
    )
    return f"{title}\n{_request_summary(trace)}\n{rest}"


def _request_summary(trace: Trace) -> str:
    request = trace.request
    if request is None:
        return "Request: not recorded (cannot be replayed)."
    if request.body_truncated:
        body = "body too large to record"
    else:
        body = f"body {len(request.body)} chars" if request.body else "no body"
    replayable = "not replayable" if request.body_truncated else "replayable"
    return (
        f"Request: {request.method} {request.base_url}{request.path} · status "
        f"{request.status_code} · {body} · {replayable}"
    )


def call_details(repo: TraceRepository, trace_id: int, function: str) -> str:
    details = get_call_details(load_trace(repo, trace_id).data, function)
    if not details:
        return f"'{function}' was not called in trace {trace_id}."
    return json.dumps(details, indent=1, default=str)


def function_source(repo: TraceRepository, trace_id: int, function: str) -> str:
    source = get_function_source(load_trace(repo, trace_id).data, function)
    return source or f"No source captured for '{function}' in trace {trace_id}."


def compare_traces(repo: TraceRepository, before_id: int, after_id: int) -> str:
    """Timing deltas, plus whether the response stayed the same."""
    before = load_trace(repo, before_id, include_data=False)
    after = load_trace(repo, after_id, include_data=False)
    verdict = compare_responses(_fingerprint(before), _fingerprint(after))
    comparison = {
        "response_body": VERDICT_TEXT[verdict],
        "status": [_status(before), _status(after)],
        **compare_digests(digest_of(repo, before), digest_of(repo, after)),
    }
    if verdict == "different":
        comparison["warning"] = (
            "The response body changed structure (keys, types or list lengths): the change "
            "altered what the endpoint returns, not only how fast."
        )
    return json.dumps(comparison, indent=1)


def _fingerprint(trace: Trace):
    return trace.request.response if trace.request else None


def _status(trace: Trace) -> int | None:
    return trace.request.status_code if trace.request else None


def summary_line(repo: TraceRepository, trace_id: int) -> str:
    """One line describing a stored trace, for the console of the traced app."""
    trace = load_trace(repo, trace_id, include_data=False)
    finding = headline(digest_of(repo, trace))
    return f"{trace.name} {round(trace.duration_ms, 1)} ms · #{trace.id} · {finding}"
