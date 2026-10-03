"""Look closer at one function of a trace: who calls it, what it calls, its slowest
calls, and its source code as it was when the trace was recorded."""

from collections import defaultdict
from typing import Any

from profyle.application.analysis.call_tree import (
    Node,
    build_call_trees,
    function_of,
    location_of,
    ms,
    short_args,
    walk,
)


def matches(frame_name: str, query: str) -> bool:
    """Whether a frame is the function the user asked for. `query` may be the full
    VizTracer name ("handler (/app/views.py:12)"), a bare name ("handler") or a
    qualified one ("views.handler", "UserService.get")."""
    function = function_of(frame_name)
    return (
        frame_name == query
        or function == query
        or function == query.split(".")[-1]
        or function.endswith("." + query)
    )


def get_call_details(
    raw_trace: dict[str, Any], function: str, samples: int = 5
) -> dict[str, Any] | None:
    """Callers, callees and the slowest calls (with arguments and return values)."""
    calls: list[Node] = []
    callers: dict[str, list[float]] = defaultdict(list)
    callees: dict[str, list[float]] = defaultdict(list)
    for roots in build_call_trees(raw_trace.get("traceEvents", [])).values():
        for node, parent, _ in walk(roots):
            if not matches(node.name, function):
                continue
            calls.append(node)
            callers[parent.name if parent else "<root>"].append(node.dur)
            for child in node.children:
                callees[child.name].append(child.dur)
    if not calls:
        return None

    slowest = sorted(calls, key=lambda n: n.dur, reverse=True)[:samples]
    return {
        "function": function_of(calls[0].name),
        "location": location_of(calls[0].name),
        "calls": len(calls),
        "total_ms": ms(sum(n.dur for n in calls)),
        "callers": _added_up(callers),
        "callees": _added_up(callees),
        "slowest_calls": [
            {
                "duration_ms": ms(call.dur),
                "args": short_args(call.args, limit=300),
                "return_value": _return_value(call),
            }
            for call in slowest
        ],
    }


def _added_up(durations_by_name: dict[str, list[float]]) -> list[dict[str, Any]]:
    rows = [
        {
            "function": function_of(name),
            "location": location_of(name),
            "calls": len(durations),
            "total_ms": ms(sum(durations)),
        }
        for name, durations in durations_by_name.items()
    ]
    return sorted(rows, key=lambda r: r["total_ms"], reverse=True)[:15]


def _return_value(call: Node) -> str | None:
    value = (call.args or {}).get("return_value")
    return None if value is None else str(value)[:300]


def get_function_source(
    raw_trace: dict[str, Any], function: str, max_lines: int = 80
) -> str | None:
    """Source of a traced function, with its decorators and line numbers, taken from
    the trace itself (VizTracer's file_info)."""
    file_info = raw_trace.get("file_info") or {}
    functions: dict[str, list] = file_info.get("functions") or {}
    # Exact names first, then the looser matches.
    candidates = sorted(
        (name for name in functions if matches(name, function)), key=lambda n: n != function
    )
    if not candidates:
        return None
    path, reported_line = functions[candidates[0]]
    source = (file_info.get("files") or {}).get(path)
    if not source:
        return None

    lines = source[0].splitlines()
    # VizTracer may report the line of the first decorator instead of the def.
    def_index = _skip_decorators(lines, reported_line - 1)
    first_index = _first_decorator(lines, max(reported_line - 1, 0))
    shown = lines[first_index:def_index] + _function_body(lines, def_index, max_lines)
    numbered = [f"{first_index + 1 + i:>5} | {text}" for i, text in enumerate(shown)]
    more = f" (+{len(candidates) - 1} other matches)" if len(candidates) > 1 else ""
    return "\n".join([f"# {path}:{def_index + 1}{more}", *numbered]).rstrip()


def _is_decorator(line: str) -> bool:
    return line.lstrip().startswith("@")


def _skip_decorators(lines: list[str], index: int) -> int:
    while index < len(lines) and _is_decorator(lines[index]):
        index += 1
    return index


def _first_decorator(lines: list[str], index: int) -> int:
    index = min(index, len(lines))
    while index > 0 and _is_decorator(lines[index - 1]):
        index -= 1
    return index


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _function_body(lines: list[str], def_index: int, max_lines: int) -> list[str]:
    """The def line and every line after it until the code dedents back."""
    if def_index >= len(lines):
        return []
    body = [lines[def_index]]
    for line in lines[def_index + 1 :]:
        dedented = line.strip() and _indent(line) <= _indent(body[0])
        # A closing bracket at the def's level still belongs to the signature.
        if dedented and not line.lstrip().startswith((")", "]", "}")):
            break
        body.append(line)
        if len(body) >= max_lines:
            body.append("    # … truncated")
            break
    return body
