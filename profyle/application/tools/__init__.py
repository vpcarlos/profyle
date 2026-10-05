"""The tools behind the MCP server and the CLI.

Each returns plain text (Markdown or JSON) that can be handed to a model as is:

- doctor: is everything set up for traces to flow from the app to these tools?
- list_traces, slowest_endpoints: find the slow requests;
- analyze_trace: where the time of one request goes (its digest);
- call_details, function_source: look closer at one function;
- replay_trace, compare_traces: send a request again after a fix and compare.
"""

from profyle.application.tools.common import TraceNotFound, precompute_digests
from profyle.application.tools.doctor import doctor
from profyle.application.tools.replay import replay_trace
from profyle.application.tools.traces import (
    analyze_trace,
    call_details,
    compare_traces,
    function_source,
    list_traces,
    slowest_endpoints,
    summary_line,
)

__all__ = [
    "TraceNotFound",
    "analyze_trace",
    "call_details",
    "compare_traces",
    "doctor",
    "function_source",
    "list_traces",
    "precompute_digests",
    "replay_trace",
    "slowest_endpoints",
    "summary_line",
]
