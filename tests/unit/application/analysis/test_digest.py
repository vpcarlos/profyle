from profyle.application.analysis.digest import (
    build_call_trees,
    build_digest,
    classify_origin,
    compare_digests,
    get_call_details,
    get_function_source,
    render_digest,
)

SOURCE = """import time


def get_user(i):
    return i


@decorator
def handler():
    time.sleep(0.01)
    return [get_user(i) for i in range(12)]
"""

HANDLER = "handler (/app/views.py:8)"
GET_USER = "get_user (/app/views.py:4)"


def event(name, ts, dur, tid=1, args=None):
    return {"ph": "X", "pid": 1, "tid": tid, "ts": ts, "dur": dur, "name": name, "args": args}


def make_trace(get_user_dur=1.0):
    events = [
        {"ph": "M", "pid": 1, "tid": 1, "name": "thread_name", "args": {"name": "Main"}},
        event(HANDLER, 0, 1000),
        event("time.sleep", 10, 500),
    ]
    for i in range(12):
        events.append(
            event(GET_USER, 600 + i * 10, get_user_dur, args={"func_args": {"i": str(i)}})
        )
    return {
        "traceEvents": events,
        "file_info": {
            "files": {"/app/views.py": [SOURCE, SOURCE.count("\n")]},
            "functions": {HANDLER: ["/app/views.py", 8], GET_USER: ["/app/views.py", 4]},
        },
        "viztracer_metadata": {"version": "1.1.1"},
    }


def test_call_tree_nests_children_by_time():
    roots = build_call_trees(make_trace()["traceEvents"])[(1, 1)]

    assert len(roots) == 1
    assert roots[0].name == HANDLER
    assert len(roots[0].children) == 13
    assert roots[0].self_time == 1000 - 500 - 12


def test_digest_reports_totals_hot_path_and_repeated_calls():
    digest = build_digest(make_trace())

    assert digest["total_ms"] == 1.0
    assert digest["hot_path"][0][0]["function"] == "handler"
    assert digest["hot_path"][0][1]["function"] == "time.sleep"
    assert digest["io_wait_self_ms"] == 0.5
    [repeated] = digest["repeated_calls"]
    assert (repeated["parent"], repeated["callee"], repeated["calls"]) == (
        "handler",
        "get_user",
        12,
    )
    assert repeated["sample_args"] == ["i=0", "i=1", "i=2"]
    assert [row["function"] for row in digest["top_user_code"]] == ["handler", "get_user"]


def test_recursive_calls_count_inclusive_time_once():
    trace = {"traceEvents": [event("f (/app/a.py:1)", 0, 100), event("f (/app/a.py:1)", 10, 50)]}

    [row] = build_digest(trace)["top_inclusive"]

    assert row["calls"] == 2
    assert row["inclusive_ms"] == 0.1


def test_classify_origin():
    assert classify_origin("f (/app/views.py:1)") == "user"
    assert classify_origin("f (/venv/lib/python3.11/site-packages/x.py:1)") == "third_party"
    assert classify_origin("f (/usr/lib/python3.11/json/decoder.py:1)") == "stdlib"
    assert classify_origin("builtins.len") == "builtin"


def test_render_digest_is_compact_markdown():
    text = render_digest(build_digest(make_trace()), name="GET /users")

    assert text.startswith("## Trace digest — GET /users")
    assert "handler → get_user ×12" in text


def test_function_source_skips_decorators_and_stops_at_dedent():
    source = get_function_source(make_trace(), "handler")

    assert "@decorator" in source
    assert "def handler():" in source
    assert "return [get_user(i)" in source
    assert "def get_user" not in source


def test_function_source_unknown_function():
    assert get_function_source(make_trace(), "missing") is None


def test_call_details_lists_callers_and_slowest_calls():
    details = get_call_details(make_trace(), "get_user")

    assert details["calls"] == 12
    assert details["callers"][0]["function"] == "handler"
    assert details["slowest_calls"][0]["args"].startswith("i=")


def test_compare_digests_reports_improvement():
    before = build_digest(make_trace(get_user_dur=5.0))
    after = build_digest(make_trace(get_user_dur=1.0))

    diff = compare_digests(before, after)

    get_user = next(d for d in diff["function_deltas"] if d["function"].startswith("get_user"))
    assert get_user["delta_inclusive_ms"] == -0.048


def test_empty_trace():
    digest = build_digest({"traceEvents": []})

    assert digest["total_ms"] == 0
    assert digest["hot_path"] == []
