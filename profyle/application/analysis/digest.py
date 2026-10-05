"""Turn a raw VizTracer trace into a compact, LLM-friendly digest.

A VizTracer trace of a single HTTP request easily holds 100k+ events (tens of MB of
JSON), far too much to hand to a language model. The digest keeps only what is needed
to reason about bottlenecks: where time is spent (inclusive and self time per
function), the critical path, repeated calls (N+1 patterns), time spent waiting on I/O
and which of those frames belong to the user's own code.

All durations in a digest are milliseconds.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from profyle.application.analysis.call_tree import (
    USER,
    Node,
    Thread,
    build_call_trees,
    function_of,
    is_io_like,
    location_of,
    ms,
    origin_of,
    readable,
    short_args,
    walk,
)

# Bump when the digest format or analysis changes: stored digests are rebuilt.
DIGEST_VERSION = 1


class FunctionRow(BaseModel):
    """One function, all its calls in the trace added up."""

    function: str
    location: str | None
    origin: str
    calls: int
    inclusive_ms: float
    self_ms: float
    max_call_ms: float
    pct_of_total: float


class PathStep(BaseModel):
    """One call on the critical path."""

    function: str
    location: str | None
    origin: str
    inclusive_ms: float
    self_ms: float
    pct_of_total: float


class RepeatedCall(BaseModel):
    """A caller that calls the same function many times: an N+1 candidate."""

    parent: str
    parent_location: str | None
    callee: str
    callee_location: str | None
    calls: int
    total_ms: float
    pct_of_total: float
    sample_args: list[str]


class Digest(BaseModel):
    version: int = DIGEST_VERSION
    total_ms: float
    event_count: int
    threads: int
    function_count: int
    time_by_origin_ms: dict[str, float]
    io_wait_self_ms: float
    hot_path: list[list[PathStep]]  # one critical path per busy thread
    top_self_time: list[FunctionRow]
    top_inclusive: list[FunctionRow]
    top_user_code: list[FunctionRow]
    repeated_calls: list[RepeatedCall]
    metadata: dict[str, Any] = {}


@dataclass
class _Totals:
    """What is added up per function while walking the call trees (microseconds)."""

    name: str
    calls: int = 0
    inclusive: float = 0.0
    self_time: float = 0.0
    max_call: float = 0.0


@dataclass
class _Repeats:
    parent: str
    callee: str
    calls: int = 0
    total: float = 0.0
    sample_args: list[str] = field(default_factory=list)


def build_digest(raw_trace: dict[str, Any], top: int = 15, repeated_threshold: int = 10) -> Digest:
    """Walk every call once, adding up time per function, then keep the `top` rows of
    each ranking."""
    events = raw_trace.get("traceEvents", [])
    trees = build_call_trees(events)

    totals: dict[str, _Totals] = {}
    self_time_by_origin: dict[str, float] = defaultdict(float)
    io_self_time = 0.0
    repeats: dict[tuple[str, str], _Repeats] = {}
    start, end = float("inf"), float("-inf")

    for roots in trees.values():
        for root in roots:
            start, end = min(start, root.ts), max(end, root.end)
        for node, _, enclosing in walk(roots):
            item = totals.setdefault(node.name, _Totals(node.name))
            item.calls += 1
            item.self_time += node.self_time
            item.max_call = max(item.max_call, node.dur)
            # In recursion only the outermost call counts, or time would be counted twice.
            if node.name not in enclosing:
                item.inclusive += node.dur
            self_time_by_origin[origin_of(node.name)] += node.self_time
            if is_io_like(node.name):
                io_self_time += node.self_time
            _count_repeats(node, repeats, repeated_threshold)

    total = end - start if totals else 0.0

    def pct(us: float) -> float:
        return round(100 * us / total, 1) if total else 0.0

    def row(item: _Totals) -> FunctionRow:
        return FunctionRow(
            function=function_of(item.name),
            location=location_of(item.name),
            origin=origin_of(item.name),
            calls=item.calls,
            inclusive_ms=ms(item.inclusive),
            self_ms=ms(item.self_time),
            max_call_ms=ms(item.max_call),
            pct_of_total=pct(item.inclusive),
        )

    by_self = sorted(totals.values(), key=lambda t: t.self_time, reverse=True)
    by_inclusive = sorted(totals.values(), key=lambda t: t.inclusive, reverse=True)
    user_code = [t for t in by_inclusive if origin_of(t.name) == USER]
    heaviest_repeats = sorted(repeats.values(), key=lambda r: r.total, reverse=True)

    return Digest(
        total_ms=ms(total),
        event_count=len(events),
        threads=len(trees),
        function_count=len(totals),
        time_by_origin_ms={k: ms(v) for k, v in sorted(self_time_by_origin.items())},
        io_wait_self_ms=ms(io_self_time),
        hot_path=_critical_paths(trees, total),
        top_self_time=[row(t) for t in by_self[:top]],
        top_inclusive=[row(t) for t in by_inclusive[:top]],
        top_user_code=[row(t) for t in user_code[:top]],
        repeated_calls=[
            RepeatedCall(
                parent=function_of(r.parent),
                parent_location=location_of(r.parent),
                callee=function_of(r.callee),
                callee_location=location_of(r.callee),
                calls=r.calls,
                total_ms=ms(r.total),
                pct_of_total=pct(r.total),
                sample_args=r.sample_args,
            )
            for r in heaviest_repeats[:top]
        ],
        metadata=raw_trace.get("viztracer_metadata", {}),
    )


def _count_repeats(node: Node, repeats: dict[tuple[str, str], _Repeats], threshold: int) -> None:
    """Add up the children that `node` calls at least `threshold` times."""
    calls_by_callee: dict[str, list[Node]] = defaultdict(list)
    for child in node.children:
        calls_by_callee[child.name].append(child)
    for callee, calls in calls_by_callee.items():
        if len(calls) < threshold:
            continue
        entry = repeats.setdefault((node.name, callee), _Repeats(node.name, callee))
        entry.calls += len(calls)
        entry.total += sum(call.dur for call in calls)
        for call in calls:
            if len(entry.sample_args) >= 3:
                break
            sample = short_args(call.args)
            if sample and sample not in entry.sample_args:
                entry.sample_args.append(sample)


def _critical_paths(trees: dict[Thread, list[Node]], total: float, max_depth: int = 40):
    """From the heaviest call of each busy thread, follow the most expensive child.

    Frameworks often run the handler in another thread (e.g. sync FastAPI endpoints in a
    threadpool), so every thread that holds >=5% of the request gets its own path.
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
        path: list[PathStep] = []
        node: Node | None = root
        while node is not None and len(path) < max_depth:
            path.append(
                PathStep(
                    function=function_of(node.name),
                    location=location_of(node.name),
                    origin=origin_of(node.name),
                    inclusive_ms=ms(node.dur),
                    self_ms=ms(node.self_time),
                    pct_of_total=round(100 * node.dur / total, 1) if total else 0.0,
                )
            )
            node = max(node.children, key=lambda n: n.dur) if node.children else None
            # Stop once the path is no longer meaningful (<1% of the request).
            if node is not None and total and node.dur / total < 0.01:
                break
        paths.append(path)
    return paths


def headline(digest: Digest) -> str:
    """One line naming the main suspect of a trace (its "main finding")."""
    if not digest.total_ms or not digest.top_self_time:
        return "empty trace"
    # Recursion (a function calling itself, e.g. a serializer walking a tree) is not
    # a repeated-call smell like an N+1.
    repeated = next((r for r in digest.repeated_calls if r.parent != r.callee), None)
    if repeated and repeated.pct_of_total >= 20:
        return (
            f"repeated: {readable(repeated.parent, repeated.parent_location)} → "
            f"{readable(repeated.callee, repeated.callee_location)} "
            f"×{repeated.calls} ({repeated.pct_of_total}%)"
        )
    top = digest.top_self_time[0]
    pct = round(100 * top.self_ms / digest.total_ms, 1)
    kind = "wait" if is_io_like(top.function) else "hot"
    return f"{kind}: {top.function} {top.self_ms} ms ({pct}%)"


def compare_digests(before: Digest, after: Digest, top: int = 15) -> dict[str, Any]:
    """Per-function inclusive-time deltas between two digests (e.g. before/after a fix)."""

    def by_function(digest: Digest) -> dict[str, FunctionRow]:
        rows = digest.top_self_time + digest.top_inclusive + digest.top_user_code
        return {f"{r.function} ({r.location})": r for r in rows}

    old_rows, new_rows = by_function(before), by_function(after)
    deltas = []
    for key in old_rows.keys() | new_rows.keys():
        old, new = old_rows.get(key), new_rows.get(key)
        old_ms, new_ms = (old.inclusive_ms if old else 0), (new.inclusive_ms if new else 0)
        deltas.append(
            {
                "function": key,
                "before_inclusive_ms": old.inclusive_ms if old else None,
                "after_inclusive_ms": new.inclusive_ms if new else None,
                "before_calls": old.calls if old else None,
                "after_calls": new.calls if new else None,
                "delta_inclusive_ms": round(new_ms - old_ms, 3),
            }
        )
    deltas.sort(key=lambda d: abs(d["delta_inclusive_ms"]), reverse=True)
    return {
        "before_total_ms": before.total_ms,
        "after_total_ms": after.total_ms,
        "delta_total_ms": round(after.total_ms - before.total_ms, 3),
        "function_deltas": deltas[:top],
    }
