"""A digest as Markdown, sized for an LLM context window."""

from profyle.application.analysis.call_tree import USER
from profyle.application.analysis.digest import Digest, PathStep


def render_digest(digest: Digest, name: str | None = None) -> str:
    out = [
        f"## Trace digest — {name}" if name else "## Trace digest",
        f"Total {digest.total_ms} ms · {digest.event_count} events · "
        f"{digest.function_count} distinct functions · {digest.threads} thread(s)",
        "Self time by origin: "
        + ", ".join(f"{k} {v} ms" for k, v in digest.time_by_origin_ms.items())
        + f". Likely I/O/wait self time: {digest.io_wait_self_ms} ms.",
        "Note: timings include VizTracer overhead (~1µs per call), so functions with very "
        "high call counts look slower than they are untraced.",
    ]

    for number, path in enumerate(digest.hot_path, start=1):
        thread = f" — thread {number}" if len(digest.hot_path) > 1 else ""
        out.append(f"\n### Critical path (heaviest child at each level){thread}")
        for depth, step in enumerate(_collapse_pass_through(path)):
            indent = "  " * min(depth, 12)
            if isinstance(step, int):
                out.append(f"{indent}- … {step} library frames passing time through …")
            else:
                out.append(
                    f"{indent}- {step.function} — {step.inclusive_ms} ms "
                    f"({step.pct_of_total}%), self {step.self_ms} ms{_at(step.location)}"
                )

    out.append("\n### Top self time (where the CPU/wait actually happens)")
    for row in digest.top_self_time:
        out.append(
            f"- {row.function} [{row.origin}] self {row.self_ms} ms, "
            f"{row.calls} calls, max {row.max_call_ms} ms{_at(row.location)}"
        )

    if digest.top_user_code:
        out.append("\n### Your code by inclusive time")
        for row in digest.top_user_code:
            out.append(
                f"- {row.function} {row.inclusive_ms} ms ({row.pct_of_total}%), "
                f"self {row.self_ms} ms, {row.calls} calls{_at(row.location)}"
            )

    if digest.repeated_calls:
        out.append("\n### Repeated calls from the same caller (possible N+1 / hot loops)")
        for call in digest.repeated_calls:
            samples = f" e.g. ({' | '.join(call.sample_args)})" if call.sample_args else ""
            out.append(
                f"- {call.parent} → {call.callee} ×{call.calls} = {call.total_ms} ms "
                f"({call.pct_of_total}%){samples}"
            )
    return "\n".join(out)


def _at(location: str | None) -> str:
    return f" `{location}`" if location else ""


def _collapse_pass_through(path: list[PathStep]) -> list[PathStep | int]:
    """Replace runs of library frames that only pass time down (middlewares, routers…)
    by the number of frames hidden, keeping the first and last frame of each run."""
    out: list[PathStep | int] = []
    run: list[PathStep] = []

    def end_run():
        out.extend([run[0], len(run) - 2, run[-1]] if len(run) > 3 else run)
        run.clear()

    for step in path:
        passes_time_down = step.origin != USER and step.self_ms < 0.05 * max(
            step.inclusive_ms, 1e-9
        )
        if passes_time_down:
            run.append(step)
        else:
            end_run()
            out.append(step)
    end_run()
    return out
