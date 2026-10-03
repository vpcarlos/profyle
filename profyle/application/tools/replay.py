"""Send the request behind a trace again, to measure a fix on fresh traces and check
that the endpoint still answers the same."""

import statistics
import time
from dataclasses import dataclass

from profyle.application.requests import sender
from profyle.application.requests.fingerprint import VERDICT_TEXT
from profyle.application.requests.fingerprint import compare as compare_responses
from profyle.application.tools.common import load_trace
from profyle.config import load_config
from profyle.domain.trace import Trace
from profyle.domain.trace_repository import TraceRepository
from profyle.settings import settings

MAX_TIMES = 10


@dataclass
class Run:
    response: sender.ReplayResponse
    trace: Trace | None  # the trace the app recorded for this replay, if any


def replay_trace(
    repo: TraceRepository,
    trace_id: int,
    times: int = 1,
    base_url: str | None = None,
    headers: dict[str, str] | None = None,
    allow_unsafe_method: bool = False,
    wait_seconds: float = 30,
) -> str:
    original = load_trace(repo, trace_id)
    request = original.request
    if request is None:
        return (
            f"Trace {trace_id} has no recorded request (it was captured by an older "
            "Profyle version). Ask the user to trigger the request once more."
        )
    target = base_url or request.base_url
    try:
        sender.check_replayable(
            request, target, allow_unsafe_method, allow_remote=load_config().replay_allow_remote
        )
    except sender.ReplayRefused as error:
        return str(error)

    runs: list[Run] = []
    for _ in range(max(1, min(times, MAX_TIMES))):
        last_id = repo.latest_trace_id()
        response = sender.send(request, base_url=target, extra_headers=headers)
        if response.error:
            runs.append(Run(response, None))
            break
        runs.append(Run(response, _wait_for_trace(repo, original.name, last_id, wait_seconds)))
    return _report(original, runs, extra_headers=headers)


def _wait_for_trace(
    repo: TraceRepository, name: str, after_id: int, wait_seconds: float
) -> Trace | None:
    # The middleware stores the trace after the response is sent, so poll briefly.
    deadline = time.monotonic() + wait_seconds
    while True:
        new = [
            t for t in repo.list_traces(name_contains=name) if t.id > after_id and t.name == name
        ]
        if new:
            return min(new, key=lambda t: t.id)
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.25)


def _report(original: Trace, runs: list[Run], extra_headers) -> str:
    request = original.request
    lines = [
        f"Replayed {request.method} {request.path} (original trace #{original.id}: "
        f"{round(original.duration_ms, 2)} ms, status {request.status_code}).",
        "",
        f"| run | status | response ms | new trace | trace ms | body vs #{original.id} |",
        "|---|---|---|---|---|---|",
    ]
    for number, run in enumerate(runs, start=1):
        response, trace = run.response, run.trace
        if response.error:
            lines.append(f"| {number} | error | {response.elapsed_ms} | – | – | – |")
            lines.append(
                f"\nCould not reach the app ({response.error}). Is it running? "
                "Pass base_url if it listens on a different host or port."
            )
            break
        trace_cell, ms_cell = (
            (f"#{trace.id}", str(round(trace.duration_ms, 2))) if trace else ("not recorded",) * 2
        )
        body = VERDICT_TEXT[compare_responses(request.response, response.fingerprint)]
        lines.append(
            f"| {number} | {response.status_code} | {response.elapsed_ms} | {trace_cell} "
            f"| {ms_cell} | {body} |"
        )

    answered = [run.response for run in runs if not run.response.error]
    new_traces = [run.trace for run in runs if run.trace]
    status_changed = _status_changed(request.status_code, answered)
    lines += _warnings(original, answered, status_changed)
    lines += _notes(original, answered, extra_headers)
    if new_traces:
        median = statistics.median(t.duration_ms for t in new_traces)
        next_step = (
            "" if status_changed else f" Next: compare_traces({original.id}, {new_traces[-1].id})."
        )
        lines.append(f"\nMedian trace duration: {round(median, 2)} ms.{next_step}")
    elif answered:
        lines.append(
            "\nThe app answered but no new trace was stored. Make sure it runs with "
            f"ProfyleMiddleware and the same database ({settings.get_db_path()}), and that "
            "PROFYLE_PATTERN matches this path. Run doctor to check the setup."
        )
    return "\n".join(lines)


def _status_changed(original_status: int | None, answered: list[sender.ReplayResponse]) -> bool:
    statuses = {response.status_code for response in answered}
    return bool(original_status and statuses and statuses != {original_status})


def _warnings(original: Trace, answered, status_changed: bool) -> list[str]:
    """The endpoint behaves differently than when it was recorded."""
    request = original.request
    if status_changed:
        statuses = sorted({response.status_code for response in answered})
        return [
            f"\n⚠ Status changed: original {request.status_code}, now "
            f"{', '.join(str(s) for s in statuses)}. The endpoint behaves "
            "differently; check this before comparing timings."
        ]
    verdicts = {compare_responses(request.response, r.fingerprint) for r in answered}
    if "different" in verdicts:
        return [
            "\n⚠ The response body changed structure (keys, types or list lengths) "
            f"compared with #{original.id}. A performance fix must return the same data."
        ]
    return []


def _notes(original: Trace, answered, extra_headers) -> list[str]:
    """What limits the comparison, and how to get around it."""
    request = original.request
    notes = []
    if len({r.fingerprint.sha256 for r in answered if r.fingerprint}) > 1:
        notes.append(
            "\nNote: the body differs between runs of the same code (timestamps, random "
            "ids...), so exact comparison is not meaningful; rely on the structure check."
        )
    if request.response is None and answered:
        notes.append(
            f"\nNote: #{original.id} has no recorded response body to compare with. Use "
            "the first replayed trace as the baseline and compare_traces against it."
        )
    redacted = sender.redacted_headers(request)
    if redacted and not extra_headers:
        notes.append(
            f"\nNote: these headers were redacted when recording: {', '.join(redacted)}. "
            "If the endpoint needs them, ask the user for credentials and pass them as headers."
        )
    return notes
