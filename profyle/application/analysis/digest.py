"""Turn a raw VizTracer trace into a compact, LLM-friendly digest.

A VizTracer trace of a single HTTP request easily holds 100k+ events (tens of MB
of JSON), far too much to hand to a language model. The digest keeps only what
is needed to reason about bottlenecks: where time is spent (inclusive and self
time per function), the critical path, repeated calls (N+1 patterns), time spent
waiting on I/O and which of those frames belong to the user's own code.
"""

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

FUNCTION_NAME_RE = re.compile(r"^(?P<func>.+) \((?P<path>.+):(?P<line>\d+)\)$")

# Name fragments that usually mean the thread is blocked waiting rather than computing.
IO_HINTS = (
    "sleep",
    "select",
    "poll",
    "recv",
    "send",
    "connect",
    "socket",
    "ssl",
    "read",
    "write",
    "acquire",
    "wait",
    "execute",
    "fetch",
    "commit",
    "cursor",
    "sqlite3",
    "psycopg",
    "pymysql",
    "asyncpg",
    "redis",
    "requests",
    "httpx",
    "urllib",
    "aiohttp",
    "boto",
)

USER, STDLIB, THIRD_PARTY, BUILTIN = "user", "stdlib", "third_party", "builtin"

# Bump when the digest format or analysis changes: stored digests are rebuilt.
DIGEST_VERSION = 1


@dataclass
class Node:
    name: str
    ts: float
    dur: float
    args: dict[str, Any] | None = None
    children: list["Node"] = field(default_factory=list)

    @property
    def end(self) -> float:
        return self.ts + self.dur

    @property
    def self_time(self) -> float:
        return max(self.dur - sum(child.dur for child in self.children), 0.0)


@dataclass
class FunctionStats:
    name: str
    calls: int = 0
    inclusive: float = 0.0
    self_time: float = 0.0
    max_call: float = 0.0


def parse_function_name(name: str) -> tuple[str, str | None, int | None]:
    """'handler (/app/views.py:12)' -> ('handler', '/app/views.py', 12)."""
    match = FUNCTION_NAME_RE.match(name)
    if not match:
        return name, None, None
    return match["func"], match["path"], int(match["line"])


def classify_origin(name: str) -> str:
    _, path, _ = parse_function_name(name)
    if path is None:
        return BUILTIN
    if "site-packages" in path or "dist-packages" in path:
        return THIRD_PARTY
    if "<frozen" in path or re.search(r"[/\\]lib[/\\]python3\.\d+[/\\]", path):
        return STDLIB
    return USER


def is_io_like(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in IO_HINTS)


def build_call_trees(events: list[dict[str, Any]]) -> dict[tuple[Any, Any], list[Node]]:
    """Rebuild the call tree of every thread from complete ('X') events."""
    by_thread: dict[tuple[Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("ph") == "X" and event.get("ts") is not None:
            by_thread[(event.get("pid"), event.get("tid"))].append(event)

    trees: dict[tuple[Any, Any], list[Node]] = {}
    for thread, thread_events in by_thread.items():
        thread_events.sort(key=lambda e: (e["ts"], -(e.get("dur") or 0)))
        roots: list[Node] = []
        stack: list[Node] = []
        for event in thread_events:
            node = Node(
                name=event.get("name", "?"),
                ts=event["ts"],
                dur=event.get("dur") or 0.0,
                args=event.get("args"),
            )
            # Small tolerance: VizTracer timestamps are float microseconds.
            while stack and node.ts >= stack[-1].end - 1e-3:
                stack.pop()
            if stack:
                stack[-1].children.append(node)
            else:
                roots.append(node)
            stack.append(node)
        trees[thread] = roots
    return trees


def _walk(roots: list[Node]):
    """Yield (node, parent, active_names) depth first, without recursion limits."""
    stack: list[tuple[Node, Node | None, frozenset[str]]] = [
        (root, None, frozenset()) for root in reversed(roots)
    ]
    while stack:
        node, parent, active = stack.pop()
        yield node, parent, active
        child_active = active | {node.name}
        for child in reversed(node.children):
            stack.append((child, node, child_active))


def _short_args(args: dict[str, Any] | None, limit: int = 160) -> str | None:
    if not args or not args.get("func_args"):
        return None
    text = ", ".join(f"{k}={v}" for k, v in args["func_args"].items())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _location(name: str) -> str | None:
    _, path, line = parse_function_name(name)
    return f"{path}:{line}" if path else None


def _ms(us: float) -> float:
    return round(us / 1000, 3)


def _collect_repeated(
    node: Node, repeated: dict[tuple[str, str], dict[str, Any]], threshold: int
) -> None:
    """Accumulate children that one caller invokes >= threshold times (N+1 candidates)."""
    children_by_name: dict[str, list[Node]] = defaultdict(list)
    for child in node.children:
        children_by_name[child.name].append(child)
    for child_name, calls in children_by_name.items():
        if len(calls) < threshold:
            continue
        entry = repeated.setdefault(
            (node.name, child_name),
            {"parent": node.name, "callee": child_name, "calls": 0, "total": 0.0,
             "sample_args": []},
        )
        entry["calls"] += len(calls)
        entry["total"] += sum(c.dur for c in calls)
        for call in calls:
            if len(entry["sample_args"]) >= 3:
                break
            sample = _short_args(call.args)
            if sample and sample not in entry["sample_args"]:
                entry["sample_args"].append(sample)


def build_digest(
    raw_trace: dict[str, Any],
    top: int = 15,
    repeated_threshold: int = 10,
) -> dict[str, Any]:
    """Summarise a VizTracer trace. All durations in the result are milliseconds."""
    events = raw_trace.get("traceEvents", [])
    trees = build_call_trees(events)

    stats: dict[str, FunctionStats] = {}
    origin_self: dict[str, float] = defaultdict(float)
    io_self = 0.0
    repeated: dict[tuple[str, str], dict[str, Any]] = {}
    span_start, span_end = float("inf"), float("-inf")

    for roots in trees.values():
        for root in roots:
            span_start = min(span_start, root.ts)
            span_end = max(span_end, root.end)

        for node, _, active in _walk(roots):
            item = stats.setdefault(node.name, FunctionStats(node.name))
            item.calls += 1
            item.self_time += node.self_time
            item.max_call = max(item.max_call, node.dur)
            # Only the outermost frame of a recursive function counts as inclusive time.
            if node.name not in active:
                item.inclusive += node.dur
            origin_self[classify_origin(node.name)] += node.self_time
            if is_io_like(node.name):
                io_self += node.self_time

            _collect_repeated(node, repeated, repeated_threshold)

    total = span_end - span_start if stats else 0.0

    def function_entry(item: FunctionStats) -> dict[str, Any]:
        return {
            "function": parse_function_name(item.name)[0],
            "location": _location(item.name),
            "origin": classify_origin(item.name),
            "calls": item.calls,
            "inclusive_ms": _ms(item.inclusive),
            "self_ms": _ms(item.self_time),
            "max_call_ms": _ms(item.max_call),
            "pct_of_total": round(100 * item.inclusive / total, 1) if total else 0.0,
        }

    by_self = sorted(stats.values(), key=lambda s: s.self_time, reverse=True)
    by_inclusive = sorted(stats.values(), key=lambda s: s.inclusive, reverse=True)
    user_code = [s for s in by_inclusive if classify_origin(s.name) == USER]

    repeated_list = sorted(repeated.values(), key=lambda r: r["total"], reverse=True)[:top]
    for entry in repeated_list:
        entry["parent_location"] = _location(entry["parent"])
        entry["callee_location"] = _location(entry["callee"])
        entry["parent"] = parse_function_name(entry["parent"])[0]
        entry["callee"] = parse_function_name(entry["callee"])[0]
        entry["total_ms"] = _ms(entry.pop("total"))
        entry["pct_of_total"] = round(100 * entry["total_ms"] * 1000 / total, 1) if total else 0

    return {
        "version": DIGEST_VERSION,
        "total_ms": _ms(total),
        "event_count": len(events),
        "threads": len(trees),
        "function_count": len(stats),
        "time_by_origin_ms": {k: _ms(v) for k, v in sorted(origin_self.items())},
        "io_wait_self_ms": _ms(io_self),
        "hot_path": _hot_path(trees, total),
        "top_self_time": [function_entry(s) for s in by_self[:top]],
        "top_inclusive": [function_entry(s) for s in by_inclusive[:top]],
        "top_user_code": [function_entry(s) for s in user_code[:top]],
        "repeated_calls": repeated_list,
        "metadata": raw_trace.get("viztracer_metadata", {}),
    }


COMPREHENSION = re.compile(r"\.<locals>\.<(listcomp|dictcomp|setcomp|genexpr)>$")
COMPREHENSION_KINDS = {
    "<listcomp>": "list comprehension",
    "<dictcomp>": "dict comprehension",
    "<setcomp>": "set comprehension",
    "<genexpr>": "generator expression",
}


def _readable(function: str, location: str | None = None) -> str:
    # "list_orders.<locals>.<listcomp>" -> "list_orders": the loop lives in that function,
    # and Python 3.12+ inlines comprehensions anyway (PEP 709). Python 3.10 names the
    # frame just "<listcomp>", so point at its file and line instead.
    if function in COMPREHENSION_KINDS:
        where = f" at {os.path.basename(location)}" if location else ""
        return COMPREHENSION_KINDS[function] + where
    return COMPREHENSION.sub("", function)


def headline(digest: dict[str, Any]) -> str:
    """One line naming the main suspect of a trace, for listings."""
    total = digest["total_ms"]
    # A trace with any duration has at least one function in top_self_time.
    if not total or not digest["top_self_time"]:
        return "empty trace"
    # Recursion (a function calling itself, e.g. a serializer walking a tree) is not
    # a repeated-call smell like an N+1.
    repeated = next(
        (r for r in digest["repeated_calls"] if r["parent"] != r["callee"]), None
    )
    if repeated and repeated["pct_of_total"] >= 20:
        return (
            f"repeated: {_readable(repeated['parent'], repeated.get('parent_location'))} → "
            f"{_readable(repeated['callee'], repeated.get('callee_location'))} "
            f"×{repeated['calls']} ({repeated['pct_of_total']}%)"
        )
    top = digest["top_self_time"][0]
    pct = round(100 * top["self_ms"] / total, 1)
    kind = "wait" if is_io_like(top["function"]) else "hot"
    return f"{kind}: {top['function']} {top['self_ms']} ms ({pct}%)"


def _hot_path(trees: dict[tuple[Any, Any], list[Node]], total: float, max_depth: int = 40):
    """Follow the most expensive child from the heaviest roots: the critical path.

    Frameworks often run the handler in another thread (e.g. sync FastAPI endpoints in
    a threadpool), so every thread that holds >=5% of the request gets its own path.
    """
    heaviest = sorted(
        (max(roots, key=lambda n: n.dur) for roots in trees.values() if roots),
        key=lambda n: n.dur,
        reverse=True,
    )
    paths = []
    for index, root in enumerate(heaviest[:3]):
        if index and total and root.dur / total < 0.05:
            break
        node: Node | None = root
        path = []
        while node is not None and len(path) < max_depth:
            path.append(
                {
                    "function": parse_function_name(node.name)[0],
                    "location": _location(node.name),
                    "origin": classify_origin(node.name),
                    "inclusive_ms": _ms(node.dur),
                    "self_ms": _ms(node.self_time),
                    "pct_of_total": round(100 * node.dur / total, 1) if total else 0.0,
                }
            )
            node = max(node.children, key=lambda n: n.dur) if node.children else None
            # Stop once the path is no longer meaningful (<1% of the request).
            if node is not None and total and node.dur / total < 0.01:
                break
        paths.append(path)
    return paths


def _collapse_pass_through(path: list[dict[str, Any]]) -> list[dict[str, Any] | int]:
    """Replace runs of library frames that just pass time down (middlewares, routers…)
    by the number of frames hidden, keeping the first and last frame of the run."""
    out: list[dict[str, Any] | int] = []
    run: list[dict[str, Any]] = []

    def flush():
        if len(run) > 3:
            out.extend([run[0], len(run) - 2, run[-1]])
        else:
            out.extend(run)
        run.clear()

    for row in path:
        if row["origin"] != USER and row["self_ms"] < 0.05 * max(row["inclusive_ms"], 1e-9):
            run.append(row)
        else:
            flush()
            out.append(row)
    flush()
    return out


def compare_digests(before: dict[str, Any], after: dict[str, Any], top: int = 15):
    """Function-level self-time deltas between two digests (e.g. before/after a change)."""

    def index(digest: dict[str, Any]) -> dict[str, dict[str, Any]]:
        rows = digest["top_self_time"] + digest["top_inclusive"] + digest["top_user_code"]
        return {f'{r["function"]} ({r["location"]})': r for r in rows}

    a, b = index(before), index(after)
    deltas = []
    for key in a.keys() | b.keys():
        old, new = a.get(key), b.get(key)
        deltas.append(
            {
                "function": key,
                "before_inclusive_ms": old["inclusive_ms"] if old else None,
                "after_inclusive_ms": new["inclusive_ms"] if new else None,
                "before_calls": old["calls"] if old else None,
                "after_calls": new["calls"] if new else None,
                "delta_inclusive_ms": round(
                    (new["inclusive_ms"] if new else 0) - (old["inclusive_ms"] if old else 0), 3
                ),
            }
        )
    deltas.sort(key=lambda d: abs(d["delta_inclusive_ms"]), reverse=True)
    return {
        "before_total_ms": before["total_ms"],
        "after_total_ms": after["total_ms"],
        "delta_total_ms": round(after["total_ms"] - before["total_ms"], 3),
        "function_deltas": deltas[:top],
    }


def get_function_source(
    raw_trace: dict[str, Any], function: str, max_lines: int = 80
) -> str | None:
    """Source code of a traced function, taken from the trace's own file_info.

    `function` may be the bare name ("handler"), a qualified name, or the full
    VizTracer name ("handler (/app/views.py:12)").
    """
    file_info = raw_trace.get("file_info") or {}
    files = file_info.get("files") or {}
    functions = file_info.get("functions") or {}

    candidates = [name for name in functions if name == function]
    if not candidates:
        candidates = [
            name for name in functions
            if parse_function_name(name)[0] in (function, function.split(".")[-1])
            or parse_function_name(name)[0].endswith("." + function)
        ]
    if not candidates:
        return None

    name = candidates[0]
    path, line = functions[name]
    source = files.get(path)
    if not source:
        return None
    lines = source[0].splitlines()
    start = max(line - 1, 0)
    # VizTracer may point at the first decorator; move to the actual def line.
    while line - 1 < len(lines) and lines[line - 1].lstrip().startswith("@"):
        line += 1
    # Include decorators right above the def.
    while start > 0 and lines[start - 1].lstrip().startswith("@"):
        start -= 1
    body = [lines[line - 1]] if line - 1 < len(lines) else []
    indent = len(body[0]) - len(body[0].lstrip()) if body else 0
    for text in lines[line:]:
        if text.strip() and len(text) - len(text.lstrip()) <= indent and not text.lstrip(
        ).startswith((")", "]", "}")):
            break
        body.append(text)
        if len(body) >= max_lines:
            body.append("    # … truncated")
            break
    header = lines[start : line - 1]
    numbered = [
        f"{start + 1 + i:>5} | {text}" for i, text in enumerate(header + body)
    ]
    more = f" (+{len(candidates) - 1} other matches)" if len(candidates) > 1 else ""
    return f"# {path}:{line}{more}\n" + "\n".join(numbered).rstrip()


def render_digest(digest: dict[str, Any], name: str | None = None) -> str:
    """Markdown rendering of a digest, sized for an LLM context window."""

    def loc(row: dict[str, Any]) -> str:
        return f" `{row['location']}`" if row.get("location") else ""

    out = []
    title = f"Trace digest — {name}" if name else "Trace digest"
    out.append(f"## {title}")
    out.append(
        f"Total {digest['total_ms']} ms · {digest['event_count']} events · "
        f"{digest['function_count']} distinct functions · {digest['threads']} thread(s)"
    )
    origin = ", ".join(f"{k} {v} ms" for k, v in digest["time_by_origin_ms"].items())
    out.append(f"Self time by origin: {origin}. Likely I/O/wait self time: "
               f"{digest['io_wait_self_ms']} ms.")
    out.append(
        "Note: timings include VizTracer overhead (~1µs per call), so functions with very "
        "high call counts look slower than they are untraced."
    )

    for number, path in enumerate(digest["hot_path"], start=1):
        thread = f" — thread {number}" if len(digest["hot_path"]) > 1 else ""
        out.append(f"\n### Critical path (heaviest child at each level){thread}")
        depth = 0
        for row in _collapse_pass_through(path):
            indent = "  " * min(depth, 12)
            if isinstance(row, int):
                out.append(f"{indent}- … {row} library frames passing time through …")
            else:
                out.append(
                    f"{indent}- {row['function']} — {row['inclusive_ms']} ms "
                    f"({row['pct_of_total']}%), self {row['self_ms']} ms{loc(row)}"
                )
            depth += 1

    out.append("\n### Top self time (where the CPU/wait actually happens)")
    for row in digest["top_self_time"]:
        out.append(
            f"- {row['function']} [{row['origin']}] self {row['self_ms']} ms, "
            f"{row['calls']} calls, max {row['max_call_ms']} ms{loc(row)}"
        )

    if digest["top_user_code"]:
        out.append("\n### Your code by inclusive time")
        for row in digest["top_user_code"]:
            out.append(
                f"- {row['function']} {row['inclusive_ms']} ms ({row['pct_of_total']}%), "
                f"self {row['self_ms']} ms, {row['calls']} calls{loc(row)}"
            )

    if digest["repeated_calls"]:
        out.append("\n### Repeated calls from the same caller (possible N+1 / hot loops)")
        for row in digest["repeated_calls"]:
            samples = f" e.g. ({' | '.join(row['sample_args'])})" if row["sample_args"] else ""
            out.append(
                f"- {row['parent']} → {row['callee']} ×{row['calls']} = {row['total_ms']} ms "
                f"({row['pct_of_total']}%){samples}"
            )
    return "\n".join(out)


def get_call_details(
    raw_trace: dict[str, Any], function: str, samples: int = 5
) -> dict[str, Any] | None:
    """Who calls `function`, what it calls, and sample arguments / return values."""

    def matches(name: str) -> bool:
        bare = parse_function_name(name)[0]
        return name == function or bare == function or bare.endswith("." + function)

    trees = build_call_trees(raw_trace.get("traceEvents", []))
    callers: dict[str, list[float]] = defaultdict(list)
    callees: dict[str, list[float]] = defaultdict(list)
    calls: list[Node] = []
    matched_name = None
    for roots in trees.values():
        for node, parent, _ in _walk(roots):
            if not matches(node.name):
                continue
            matched_name = matched_name or node.name
            calls.append(node)
            callers[parent.name if parent else "<root>"].append(node.dur)
            for child in node.children:
                callees[child.name].append(child.dur)
    if not calls:
        return None

    def summary(group: dict[str, list[float]]) -> list[dict[str, Any]]:
        rows = [
            {
                "function": parse_function_name(name)[0],
                "location": _location(name),
                "calls": len(durs),
                "total_ms": _ms(sum(durs)),
            }
            for name, durs in group.items()
        ]
        return sorted(rows, key=lambda r: r["total_ms"], reverse=True)[:15]

    slowest = sorted(calls, key=lambda n: n.dur, reverse=True)[:samples]
    return {
        "function": parse_function_name(matched_name)[0],
        "location": _location(matched_name),
        "calls": len(calls),
        "total_ms": _ms(sum(n.dur for n in calls)),
        "callers": summary(callers),
        "callees": summary(callees),
        "slowest_calls": [
            {
                "duration_ms": _ms(n.dur),
                "args": _short_args(n.args, limit=300),
                "return_value": str((n.args or {}).get("return_value"))[:300]
                if (n.args or {}).get("return_value") is not None
                else None,
            }
            for n in slowest
        ],
    }
