"""The call tree of a VizTracer trace, and what a frame's name tells about it.

VizTracer names a frame "function (path:line)", e.g. "handler (/app/views.py:12)";
built-ins have no location ("builtins.len", "time.sleep").
"""

import os
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

# Where a frame's code lives.
USER, STDLIB, THIRD_PARTY, BUILTIN = "user", "stdlib", "third_party", "builtin"

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

FRAME_NAME = re.compile(r"^(?P<func>.+) \((?P<path>.+):(?P<line>\d+)\)$")


@dataclass
class Node:
    """One call. Times are in microseconds, VizTracer's unit."""

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
        """Time spent in this call itself, not in the calls it made."""
        return max(self.dur - sum(child.dur for child in self.children), 0.0)


Thread = tuple[Any, Any]  # (pid, tid)


def build_call_trees(events: list[dict[str, Any]]) -> dict[Thread, list[Node]]:
    """Rebuild the call tree of every thread from complete ('X') events."""
    by_thread: dict[Thread, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("ph") == "X" and event.get("ts") is not None:
            by_thread[(event.get("pid"), event.get("tid"))].append(event)

    trees: dict[Thread, list[Node]] = {}
    for thread, thread_events in by_thread.items():
        # A parent starts before its children; at the same time, the longer one is outer.
        thread_events.sort(key=lambda e: (e["ts"], -(e.get("dur") or 0)))
        roots: list[Node] = []
        open_calls: list[Node] = []
        for event in thread_events:
            node = Node(
                name=event.get("name", "?"),
                ts=event["ts"],
                dur=event.get("dur") or 0.0,
                args=event.get("args"),
            )
            # Close the calls that ended before this one started (with a small
            # tolerance: VizTracer timestamps are float microseconds).
            while open_calls and node.ts >= open_calls[-1].end - 1e-3:
                open_calls.pop()
            (open_calls[-1].children if open_calls else roots).append(node)
            open_calls.append(node)
        trees[thread] = roots
    return trees


def walk(roots: list[Node]) -> Iterator[tuple[Node, Node | None, frozenset[str]]]:
    """Every call, depth first, with its caller and the names of the calls it runs
    inside (to spot recursion). Iterative, so deep traces cannot hit the recursion limit."""
    pending: list[tuple[Node, Node | None, frozenset[str]]] = [
        (root, None, frozenset()) for root in reversed(roots)
    ]
    while pending:
        node, parent, enclosing = pending.pop()
        yield node, parent, enclosing
        inside = enclosing | {node.name}
        for child in reversed(node.children):
            pending.append((child, node, inside))


def ms(us: float) -> float:
    """Microseconds (VizTracer) to milliseconds (everything Profyle shows)."""
    return round(us / 1000, 3)


def short_args(args: dict[str, Any] | None, limit: int = 160) -> str | None:
    """'id=1, page=2' from the arguments VizTracer recorded for a call."""
    if not args or not args.get("func_args"):
        return None
    text = ", ".join(f"{k}={v}" for k, v in args["func_args"].items())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --- Frame names --------------------------------------------------------------------


def parse_frame_name(name: str) -> tuple[str, str | None, int | None]:
    """'handler (/app/views.py:12)' -> ('handler', '/app/views.py', 12)."""
    match = FRAME_NAME.match(name)
    if not match:
        return name, None, None
    return match["func"], match["path"], int(match["line"])


def function_of(name: str) -> str:
    return parse_frame_name(name)[0]


def location_of(name: str) -> str | None:
    """'path:line', or None for built-ins."""
    _, path, line = parse_frame_name(name)
    return f"{path}:{line}" if path else None


def origin_of(name: str) -> str:
    _, path, _ = parse_frame_name(name)
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


COMPREHENSION_SUFFIX = re.compile(r"\.<locals>\.<(listcomp|dictcomp|setcomp|genexpr)>$")
COMPREHENSION_KINDS = {
    "<listcomp>": "list comprehension",
    "<dictcomp>": "dict comprehension",
    "<setcomp>": "set comprehension",
    "<genexpr>": "generator expression",
}


def readable(function: str, location: str | None = None) -> str:
    """A function name as a person would say it.

    "list_orders.<locals>.<listcomp>" -> "list_orders": the loop lives in that function,
    and Python 3.12+ inlines comprehensions anyway (PEP 709). Python 3.10 names the
    frame just "<listcomp>", so point at its file and line instead.
    """
    if function in COMPREHENSION_KINDS:
        where = f" at {os.path.basename(location)}" if location else ""
        return COMPREHENSION_KINDS[function] + where
    return COMPREHENSION_SUFFIX.sub("", function)
