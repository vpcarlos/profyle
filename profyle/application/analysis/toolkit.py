"""Read-only trace analysis tools behind the MCP server and `profyle analyze`.

Every function returns plain text (Markdown or JSON) so it can be handed to a model as
a tool result as is.
"""

import json
import os
import socket
import sqlite3
import statistics
import time
from collections import defaultdict
from typing import Any
from urllib.parse import urlsplit

from profyle.application import replay
from profyle.application.analysis.digest import (
    DIGEST_VERSION,
    build_digest,
    compare_digests,
    get_call_details,
    get_function_source,
    headline,
    render_digest,
)
from profyle.application.response_fingerprint import VERDICT_TEXT
from profyle.application.response_fingerprint import compare as compare_responses
from profyle.domain.trace import Trace
from profyle.domain.trace_repository import TraceRepository
from profyle.settings import settings


class TraceNotFound(LookupError):
    pass


def _load(repo: TraceRepository, trace_id: int, include_data: bool = True) -> Trace:
    trace = repo.get_trace_by_id(trace_id, include_data=include_data)
    if not trace or (include_data and not trace.data):
        raise TraceNotFound(f"Trace {trace_id} not found")
    return trace


def _digest(repo: TraceRepository, trace: Trace) -> dict[str, Any]:
    """The stored digest of a trace, built and stored on first use.

    Digests are computed on the reading side (here, or ahead of time by
    precompute_digests), never in the app's request path."""
    trace_id = int(trace.id)
    stored = repo.get_digest(trace_id)
    if stored and stored.get("version") == DIGEST_VERSION:
        return stored
    data = trace.data
    if data is None:
        full = repo.get_trace_by_id(trace_id)
        data = full.data if full else None
    if not data:
        raise TraceNotFound(f"Trace {trace_id} has no data")
    digest = build_digest(data)
    repo.store_digest(trace_id, digest, headline(digest))
    return digest


def precompute_digests(repo: TraceRepository, limit: int = 50) -> int:
    """Build missing digests for the newest traces; returns how many were built."""
    built = 0
    for trace_id in repo.trace_ids_without_digest(limit):
        trace = repo.get_trace_by_id(trace_id)
        if trace and trace.data:
            _digest(repo, trace)
            built += 1
    return built


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
    rows = [
        "| id | request | duration (ms) | recorded at | main finding |",
        "|---|---|---|---|---|",
    ]
    rows += [
        f"| {t.id} | {t.name} | {round(t.duration / 1000, 2)} | {t.timestamp} "
        f"| {t.headline or 'not analyzed yet'} |"
        for t in traces
    ]
    return "\n".join(rows)


def slowest_endpoints(repo: TraceRepository, limit: int = 15) -> str:
    """Aggregate recorded traces per request name: count, median, p95 and max duration."""
    groups: dict[str, list[float]] = defaultdict(list)
    traces_by_name: dict[str, list[Trace]] = defaultdict(list)
    for trace in repo.get_all_traces():
        name = trace.name.split("?")[0]
        groups[name].append(trace.duration / 1000)
        traces_by_name[name].append(trace)
    if not groups:
        return "No traces recorded yet. " + _empty_db_hint()

    def p95(values: list[float]) -> float:
        ordered = sorted(values)
        return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]

    rows = sorted(groups.items(), key=lambda item: p95(item[1]), reverse=True)[:limit]
    out = [
        "| request | traces | median ms | p95 ms | max ms | typical trace: main finding |",
        "|---|---|---|---|---|---|",
    ]
    out += [
        f"| {name} | {len(d)} | {round(statistics.median(d), 2)} | {round(p95(d), 2)} | "
        f"{round(max(d), 2)} | {_typical_finding(traces_by_name[name], d)} |"
        for name, d in rows
    ]
    return "\n".join(out)


def _typical_finding(traces: list[Trace], durations_ms: list[float]) -> str:
    # The trace closest to the median: the slowest one is often a cold first request.
    median = statistics.median(durations_ms)
    typical = min(traces, key=lambda t: abs(t.duration / 1000 - median))
    return f"#{typical.id}: {typical.headline or 'not analyzed yet'}"


def analyze_trace(repo: TraceRepository, trace_id: int) -> str:
    trace = _load(repo, trace_id, include_data=False)
    digest = render_digest(_digest(repo, trace), name=f"#{trace.id} {trace.name}")
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
    before = _load(repo, before_id, include_data=False)
    after = _load(repo, after_id, include_data=False)
    diff = compare_digests(_digest(repo, before), _digest(repo, after))
    verdict = compare_responses(_fingerprint_of(before), _fingerprint_of(after))
    diff = {
        "response_body": VERDICT_TEXT[verdict],
        "status": [_status_of(before), _status_of(after)],
        **diff,
    }
    if verdict == "different":
        diff["warning"] = (
            "The response body changed structure (keys, types or list lengths): the change "
            "altered what the endpoint returns, not only how fast."
        )
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
        trace = _wait_for_trace(repo, original.name, last_id, wait_seconds)
        if trace and trace.request and not trace.request.response and response.fingerprint:
            # Frameworks whose middleware cannot see the body (Flask) get it from here.
            trace.request.response = response.fingerprint
            repo.update_trace_request(int(trace.id), trace.request)
        runs.append((response, trace))

    return _render_replay(original, runs, missing_auth=replay.redacted_headers(request),
                          headers=headers)


def _render_replay(original: Trace, runs, missing_auth: list[str], headers) -> str:
    request = original.request
    lines = [
        f"Replayed {request.method} {request.path} (original trace #{original.id}: "
        f"{round(original.duration / 1000, 2)} ms, status {request.status_code}).",
        "",
        f"| run | status | response ms | new trace | trace ms | body vs #{original.id} |",
        "|---|---|---|---|---|---|",
    ]
    new_ids, durations = [], []
    for number, (response, trace) in enumerate(runs, start=1):
        if response.error:
            lines.append(f"| {number} | error | {response.elapsed_ms} | – | – | – |")
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
        body = VERDICT_TEXT[compare_responses(request.response, response.fingerprint)]
        lines.append(
            f"| {number} | {response.status_code} | {response.elapsed_ms} | {trace_cell} "
            f"| {ms_cell} | {body} |"
        )

    answered = [response for response, _ in runs if not response.error]
    status_changed = _status_changed(request.status_code, answered)
    lines += _replay_notes(original, answered, status_changed, missing_auth, headers)
    if durations:
        next_step = (
            "" if status_changed else f" Next: compare_traces({original.id}, {new_ids[-1]})."
        )
        lines.append(
            f"\nMedian trace duration: {round(statistics.median(durations), 2)} ms.{next_step}"
        )
    elif answered:
        lines.append(
            "\nThe app answered but no new trace was stored. Make sure it runs with "
            f"ProfyleMiddleware and the same database ({settings.get_db_path()}), and that "
            "PROFYLE_PATTERN matches this path. Run doctor to check the setup."
        )
    return "\n".join(lines)


def _status_changed(original_status: int | None, answered) -> bool:
    statuses = {response.status_code for response in answered}
    return bool(original_status and statuses and statuses != {original_status})


def _replay_notes(original: Trace, answered, status_changed, missing_auth, headers) -> list:
    request = original.request
    notes = []
    if status_changed:
        statuses = sorted({response.status_code for response in answered})
        notes.append(
            f"\n⚠ Status changed: original {request.status_code}, now "
            f"{', '.join(str(s) for s in statuses)}. The endpoint behaves "
            "differently; check this before comparing timings."
        )
    verdicts = {compare_responses(request.response, r.fingerprint) for r in answered}
    if "different" in verdicts and not status_changed:
        notes.append(
            "\n⚠ The response body changed structure (keys, types or list lengths) "
            f"compared with #{original.id}. A performance fix must return the same data."
        )
    hashes = {r.fingerprint.sha256 for r in answered if r.fingerprint}
    if len(hashes) > 1:
        notes.append(
            "\nNote: the body differs between runs of the same code (timestamps, random "
            "ids...), so exact comparison is not meaningful; rely on the structure check."
        )
    if request.response is None and answered:
        notes.append(
            f"\nNote: #{original.id} has no recorded response body to compare with. Use "
            "the first replayed trace as the baseline and compare_traces against it."
        )
    if missing_auth and not headers:
        notes.append(
            f"\nNote: these headers were redacted when recording: {', '.join(missing_auth)}. "
            "If the endpoint needs them, ask the user for credentials and pass them as headers."
        )
    return notes


def _fingerprint_of(trace: Trace):
    return trace.request.response if trace.request else None


def _status_of(trace: Trace) -> int | None:
    return trace.request.status_code if trace.request else None


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


def doctor(repo: TraceRepository) -> str:
    """Check that traces flow from the app to this tool, and say how to fix what doesn't."""
    checks: list[tuple[bool | None, str]] = []
    db_path = settings.get_db_path()
    source = (
        "PROFYLE_DB" if os.getenv("PROFYLE_DB")
        else "plugin project dir" if os.getenv("PROFYLE_PROJECT_DIR")
        else "project root found from the working directory"
    )
    traces = sorted(repo.get_all_traces(), key=lambda t: int(t.id))
    if traces:
        newest = traces[-1]
        checks.append((True, f"Database {db_path} ({source}): {len(traces)} traces, newest "
                             f"#{newest.id} {newest.name} at {newest.timestamp} UTC."))
    else:
        checks.append((False, f"Database {db_path} ({source}) has no traces. Start the app "
                              "from this project with `profyle run <command>` (for example "
                              "`profyle run uvicorn main:app --reload`), or add "
                              "ProfyleMiddleware, then make one request."))

    legacy = _count_traces(settings.get_legacy_db_path())
    if legacy and settings.get_legacy_db_path() != db_path:
        checks.append((False, f"Found {legacy} traces in the old location "
                              f"{settings.get_legacy_db_path()}: the app is probably running an "
                              "older Profyle. Upgrade it in the app's environment and restart."))

    checks += _runtime_checks(repo.get_runtime())

    newest_request = next((t for t in reversed(traces) if t.request), None) if traces else None
    if traces and newest_request is None:
        checks.append((False, "Traces have no recorded request, so they cannot be replayed. "
                              "The app runs an older Profyle: upgrade and restart it."))
    elif newest_request:
        checks.append((True, "Requests are recorded, so they can be replayed."))
        checks.append(_app_reachable(newest_request.request.base_url))

    lines = [f"{'✓' if ok else '✗' if ok is False else '•'} {text}" for ok, text in checks]
    ready = all(ok is not False for ok, _ in checks)
    lines.append("\nReady." if ready else "\nFix the ✗ items above, then run doctor again.")
    return "\n".join(lines)


def _runtime_checks(runtime: dict[str, Any] | None) -> list[tuple[bool | None, str]]:
    """What the app reported about itself when it started writing traces."""
    if not runtime:
        return []
    alive = _process_alive(runtime.get("pid"))
    state = {True: "running", False: "not running", None: "unknown state"}[alive]
    how = "`profyle run`" if runtime.get("mode") == "profyle run" else "ProfyleMiddleware"
    checks: list[tuple[bool | None, str]] = [
        (
            True if alive is not False else None,
            f"App: {runtime.get('framework')} traced via {how} (pid {runtime.get('pid')}, "
            f"{state}; Profyle {runtime.get('profyle')}, Python {runtime.get('python')}).",
        ),
        (None, "Configuration: " + "; ".join(runtime.get("config", []))),
    ]
    if runtime.get("mode") != "profyle run":
        checks.append((None, "Tip: `profyle run <command>` traces the app without code changes."))
    checks.append((
        None,
        "Make sure the app auto-reloads code changes (uvicorn --reload, flask --debug, "
        "manage.py runserver); otherwise it must be restarted before verifying a fix.",
    ))
    return checks


def _process_alive(pid: Any) -> bool | None:
    if not isinstance(pid, int) or os.name == "nt":
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _count_traces(path: str) -> int:
    if not os.path.exists(path):
        return 0
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            return db.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
    except sqlite3.Error:
        return 0


def _app_reachable(base_url: str) -> tuple[bool | None, str]:
    parts = urlsplit(base_url)
    host = parts.hostname or "localhost"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if not replay.is_local(base_url):
        return None, f"The app was reached at {base_url}, which is not local; replay is disabled."
    try:
        with socket.create_connection((host, port), timeout=1):
            return True, f"The app is running at {base_url}."
    except OSError:
        return False, (f"Nothing is listening at {base_url}. Start the app, with auto-reload, "
                       "e.g. `profyle run uvicorn main:app --reload`, so requests can be "
                       "replayed.")


def summary_line(repo: TraceRepository, trace_id: int) -> str:
    """One line describing a stored trace, e.g. for the console of the traced app."""
    trace = _load(repo, trace_id, include_data=False)
    finding = headline(_digest(repo, trace))
    return f"{trace.name} {round(trace.duration / 1000, 1)} ms · #{trace.id} · {finding}"
