"""MCP server exposing Profyle traces to Claude Code, Claude Desktop or any MCP client.

    claude mcp add profyle -- profyle mcp

Claude Code already has the project's source open, so pairing it with these tools
lets it go from "this endpoint is slow" to an actual code change in one session.
"""

import threading
import time

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from profyle.application.analysis import toolkit
from profyle.infrastructure.sqlite3.get_connection import get_connection
from profyle.infrastructure.sqlite3.repository import SQLiteTraceRepository

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

server = MCPServer(
    name="profyle",
    instructions=(
        "Profyle records VizTracer traces of HTTP requests (FastAPI, Flask, Django). "
        "If anything looks off (no traces, replay fails), call doctor. "
        "Start with slowest_endpoints or list_traces, then analyze_trace on one trace id. "
        "Drill down with get_call_details and get_function_source, then read and change "
        "the user's code. After a fix, use replay_request to send the same request again "
        "and compare_traces to verify the improvement. Never replay POST/PUT/PATCH/DELETE "
        "without the user's explicit permission. Durations are in milliseconds."
    ),
)


def _repo() -> SQLiteTraceRepository:
    return SQLiteTraceRepository(get_connection())


def _safe(func, *args) -> str:
    try:
        return func(_repo(), *args)
    except toolkit.TraceNotFound as error:
        return str(error)


@server.tool(annotations=READ_ONLY)
def doctor() -> str:
    """Check the Profyle setup: which trace database is read, whether traces and their
    requests are being recorded, and whether the app is running. Says how to fix each
    problem."""
    return _safe(toolkit.doctor)


@server.tool(annotations=READ_ONLY)
def list_traces(limit: int = 20, name_contains: str = "", min_duration_ms: float = 0) -> str:
    """List recorded request traces, newest first.

    Args:
        limit: Maximum number of traces to return.
        name_contains: Only traces whose request name (e.g. "GET /users/1") contains this text.
        min_duration_ms: Only traces at least this slow.
    """
    return _safe(toolkit.list_traces, limit, name_contains or None, min_duration_ms)


@server.tool(annotations=READ_ONLY)
def slowest_endpoints(limit: int = 15) -> str:
    """Rank endpoints by p95 duration across all recorded traces (count, median, p95, max)."""
    return _safe(toolkit.slowest_endpoints, limit)


@server.tool(annotations=READ_ONLY)
def analyze_trace(trace_id: int) -> str:
    """Bottleneck digest of one trace: critical path, top self time, the user's own code
    by inclusive time, I/O wait and repeated calls from one caller (N+1 candidates)."""
    return _safe(toolkit.analyze_trace, trace_id)


@server.tool(annotations=READ_ONLY)
def get_call_details(trace_id: int, function: str) -> str:
    """Callers, callees and the slowest invocations (with arguments and return values)
    of a function in a trace. `function` can be a bare or qualified name."""
    return _safe(toolkit.call_details, trace_id, function)


@server.tool(annotations=READ_ONLY)
def get_function_source(trace_id: int, function: str) -> str:
    """Source code of a function exactly as it was when the trace was recorded."""
    return _safe(toolkit.function_source, trace_id, function)


@server.tool(annotations=READ_ONLY)
def compare_traces(before_id: int, after_id: int) -> str:
    """Compare two traces (e.g. before and after a fix): total and per-function deltas."""
    return _safe(toolkit.compare_traces, before_id, after_id)


@server.tool(
    annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=False,
        open_world_hint=False,
    )
)
def replay_request(
    trace_id: int,
    times: int = 1,
    base_url: str = "",
    headers: dict[str, str] | None = None,
    allow_unsafe_method: bool = False,
) -> str:
    """Send the HTTP request recorded in a trace again (to the local app) and return the
    new trace ids, so a fix can be verified with compare_traces.

    Args:
        trace_id: Trace whose request should be replayed.
        times: How many times to send it (1-10); use 3+ to get a stable median.
        base_url: Override where the app listens, e.g. "http://127.0.0.1:8000".
        headers: Extra headers, e.g. credentials the user provided (auth headers and
            cookies are redacted when recording).
        allow_unsafe_method: Required for POST/PUT/PATCH/DELETE. Only set it after the
            user explicitly agreed, since the request may modify data.
    """
    return _safe(
        toolkit.replay_trace, trace_id, times, base_url or None, headers, allow_unsafe_method
    )


def _precompute_digests_forever(interval: float = 5.0) -> None:
    """Digest new traces in the background so listings show their main finding and
    analysis is instant. Runs here, in the reader, never in the traced app."""
    repo = _repo()
    while True:
        try:
            toolkit.precompute_digests(repo, limit=20)
        except Exception:  # never let a bad trace kill the server
            pass
        time.sleep(interval)


def run() -> None:
    threading.Thread(target=_precompute_digests_forever, daemon=True).start()
    server.run("stdio")
