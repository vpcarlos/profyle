"""MCP server exposing Profyle traces to Claude Code, Claude Desktop or any MCP client.

    claude mcp add profyle -- profyle mcp

Claude Code already has the project's source open, so pairing it with these tools
lets it go from "this endpoint is slow" to an actual code change in one session.
"""

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
        "Start with slowest_endpoints or list_traces, then analyze_trace on one trace id. "
        "Drill down with get_call_details and get_function_source, then read and change "
        "the user's code. After a fix, ask the user to replay the request and use "
        "compare_traces to verify the improvement. Durations are in milliseconds."
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


@server.prompt()
def diagnose(endpoint: str = "") -> str:
    """Find the bottleneck of an endpoint (or the slowest one) and propose a fix."""
    target = f"the endpoint `{endpoint}`" if endpoint else "the slowest endpoint"
    return (
        f"Use the profyle tools to diagnose {target}. Pick a representative slow trace, "
        "analyze it, drill into the functions that dominate the critical path, and read "
        "the relevant source in this repository. Report the root cause with evidence "
        "(ms, call counts, file:line) and propose a concrete code change, ranked by "
        "expected impact."
    )


def run() -> None:
    server.run("stdio")
