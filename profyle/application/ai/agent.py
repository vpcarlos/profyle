"""In-app trace analyst powered by Claude (the chat bubble in the trace viewer).

Requires the `ai` extra (`pip install 'profyle[ai]'`) and an Anthropic credential
(`ANTHROPIC_API_KEY`, or a profile from `ant auth login`).

Claude never sees raw traces: it works through the same read-only tools as the MCP
server, which return compact digests instead of megabytes of VizTracer events.
"""

import asyncio
import os
from typing import Any

from profyle.application.analysis import toolkit
from profyle.domain.trace_repository import TraceRepository

MODEL = os.getenv("PROFYLE_CLAUDE_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("PROFYLE_CLAUDE_EFFORT", "medium")
MAX_HISTORY_MESSAGES = 20
NO_CREDENTIALS = (
    "No Anthropic credentials found. Set ANTHROPIC_API_KEY or run `ant auth login`, "
    "then restart `profyle start`."
)

SYSTEM_PROMPT = """You are a Python performance engineer embedded in Profyle, a tool that \
records VizTracer traces of HTTP requests (FastAPI, Flask, Django).

Investigate with the tools; never guess numbers. A good investigation usually goes:
analyze_trace for the trace in question, get_call_details on the functions that dominate \
the critical path or repeat many times, get_function_source to read the code involved.

Look especially for: N+1 queries or repeated I/O in loops, blocking calls (sleep, sync \
HTTP/DB) inside async code, redundant work that could be cached or batched, and hot \
pure-Python loops. Tracing adds ~1µs per call, so high call counts are inflated.

Answer with the root cause backed by evidence (ms, % of request, call counts, file:line), \
then concrete fixes ranked by expected impact, with code where it helps. Be concise."""


class ClaudeNotConfigured(RuntimeError):
    pass


def _build_tools(repo: TraceRepository) -> list[Any]:
    from anthropic import beta_tool

    def safe(func, *args) -> str:
        try:
            return func(repo, *args)
        except toolkit.TraceNotFound as error:
            return str(error)

    @beta_tool
    def list_traces(limit: int = 20, name_contains: str = "", min_duration_ms: float = 0) -> str:
        """List recorded request traces, newest first.

        Args:
            limit: Maximum number of traces to return.
            name_contains: Only traces whose request name contains this text.
            min_duration_ms: Only traces at least this slow.
        """
        return safe(toolkit.list_traces, limit, name_contains or None, min_duration_ms)

    @beta_tool
    def slowest_endpoints(limit: int = 15) -> str:
        """Rank endpoints by p95 duration across all recorded traces.

        Args:
            limit: Maximum number of endpoints to return.
        """
        return safe(toolkit.slowest_endpoints, limit)

    @beta_tool
    def analyze_trace(trace_id: int) -> str:
        """Bottleneck digest of one trace: critical path, top self time, the user's own
        code, I/O wait and repeated calls from one caller (N+1 candidates).

        Args:
            trace_id: Id of the trace.
        """
        return safe(toolkit.analyze_trace, trace_id)

    @beta_tool
    def get_call_details(trace_id: int, function: str) -> str:
        """Callers, callees and slowest invocations (args and return values) of a function.

        Args:
            trace_id: Id of the trace.
            function: Bare or qualified function name, e.g. "get_user" or "UserRepo.get".
        """
        return safe(toolkit.call_details, trace_id, function)

    @beta_tool
    def get_function_source(trace_id: int, function: str) -> str:
        """Source code of a function as it was when the trace was recorded.

        Args:
            trace_id: Id of the trace.
            function: Bare or qualified function name.
        """
        return safe(toolkit.function_source, trace_id, function)

    @beta_tool
    def compare_traces(before_id: int, after_id: int) -> str:
        """Compare two traces (e.g. before/after a fix): total and per-function deltas.

        Args:
            before_id: Id of the baseline trace.
            after_id: Id of the trace to compare against the baseline.
        """
        return safe(toolkit.compare_traces, before_id, after_id)

    return [
        list_traces,
        slowest_endpoints,
        analyze_trace,
        get_call_details,
        get_function_source,
        compare_traces,
    ]


def _prepare_messages(
    history: list[dict[str, str]], trace_id: int | None
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": m["role"], "content": m["content"]}
        for m in history[-MAX_HISTORY_MESSAGES:]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    if messages and trace_id is not None:
        # Mid-conversation operator context: which trace the user has open right now.
        messages.append(
            {"role": "system", "content": f"The user is currently viewing trace id {trace_id}."}
        )
    return messages


def _final_text(final: Any) -> str:
    if final is None:
        return "No response generated."
    if final.stop_reason == "refusal":
        return "Claude declined to answer this request."
    text = "\n".join(block.text for block in final.content if block.type == "text").strip()
    if final.stop_reason == "max_tokens":
        text += "\n\n_(answer truncated)_"
    return text or "No response generated."


def run_agent(
    repo: TraceRepository,
    history: list[dict[str, str]],
    trace_id: int | None = None,
) -> str:
    try:
        import anthropic
    except ImportError as error:
        raise ClaudeNotConfigured(
            "The AI chat needs the 'ai' extra: pip install 'profyle[ai]'"
        ) from error

    messages = _prepare_messages(history, trace_id)
    if not messages:
        return "Ask me something about your traces."

    try:
        client = anthropic.Anthropic()
        runner = client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=16000,
            system=[
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
            ],
            output_config={"effort": EFFORT},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            tools=_build_tools(repo),
            messages=messages,
            max_iterations=12,
        )
        final = None
        for message in runner:
            final = message
    except anthropic.AuthenticationError as error:
        raise ClaudeNotConfigured(NO_CREDENTIALS) from error
    except TypeError as error:
        # Raised by the SDK when no credential source can be resolved at all.
        if "authentication" not in str(error):
            raise
        raise ClaudeNotConfigured(NO_CREDENTIALS) from error
    except anthropic.RateLimitError:
        return "Claude is rate limited right now, please retry in a moment."
    except anthropic.APIStatusError as error:
        return f"Claude API error ({error.status_code}): {error.message}"
    except anthropic.APIConnectionError:
        return "Could not reach the Claude API. Check your network connection."

    return _final_text(final)


async def get_agent_response(
    repo: TraceRepository,
    history: list[dict[str, str]],
    trace_id: int | None = None,
) -> str:
    # The Anthropic client and the SQLite repo are blocking: keep them off the event loop.
    return await asyncio.to_thread(run_agent, repo, history, trace_id)
