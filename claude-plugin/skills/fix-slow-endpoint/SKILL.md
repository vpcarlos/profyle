---
name: fix-slow-endpoint
description: Diagnose and fix a slow endpoint or request in a Python web app (FastAPI, Flask, Django) using real Profyle/VizTracer traces, then prove the fix by replaying the request and comparing traces. Use when the user says an endpoint, API call, page or request is slow, has high latency, times out, or asks where a bottleneck is.
---

# Fix a slow endpoint with Profyle traces

Work from measurements, not intuition: every claim you make about where time goes must
come from a trace, and every fix must be verified with a new trace of the same request.

The `profyle` MCP server provides: `doctor`, `slowest_endpoints`, `list_traces`,
`analyze_trace`, `get_call_details`, `get_function_source`, `replay_request`,
`compare_traces`. All durations are in milliseconds.

## 0. Check the setup

Call `doctor` first. It reports which trace database is read, whether traces and their
requests are recorded, and whether the app is running. If it lists ✗ items, relay the
fixes to the user in plain words and wait for them before going on. Typical fixes:
- `pip install "profyle[mcp]"` and add `ProfyleMiddleware` (`profyle.fastapi`,
  `profyle.flask`, or `"profyle.django.ProfyleMiddleware"` in `MIDDLEWARE`).
- Start the app from inside the project, preferably with auto-reload. Traces are stored
  in `<project>/.profyle/profile.db` automatically, and git ignores that folder.
- Make the slow request once (browser, curl or the frontend).

## 1. Find the endpoint and its traces

- If the user named the endpoint, call `list_traces(name_contains=...)`. Otherwise call
  `slowest_endpoints` and confirm with the user which one to work on.
- Listings show each trace's **main finding** (for example `repeated: a → b ×100 (83%)`).
  It is a starting point, not the diagnosis: confirm it with `analyze_trace`. A first,
  much slower trace usually shows warm-up (imports, regex compiling) instead.

## 2. Get a trustworthy baseline

- The first request after the server starts includes warm-up (imports, regex compiling,
  connection setup). Do not diagnose that trace if a later one exists.
- For a GET request, call `replay_request(trace_id, times=3)` before changing anything.
  This gives warm traces and a median baseline, and confirms that replay works (the app is
  reachable and credentials are not missing). If the app is not reachable, ask the user
  to start it, preferably with auto-reload (`uvicorn --reload`, `flask --debug`,
  `manage.py runserver`).
- **Never replay POST, PUT, PATCH or DELETE without the user's explicit permission.** These
  requests may create or delete data. Ask first; only then pass `allow_unsafe_method=true`.
- Auth headers and cookies are redacted when recording. If the replay returns 401 or 403,
  ask the user for a token or session for local testing and pass it in `headers`. Never
  print credentials back.

## 3. Diagnose

Call `analyze_trace` on a representative warm trace and read it in this order:

1. **Critical path per thread.** Sync endpoints often run in a worker thread, so the
   handler can appear under a second thread.
2. **Repeated calls from the same caller.** `parent → callee ×N` together with
   different sample arguments (`id=1 | id=2 | id=3`) is the signature of an N+1.
3. **Top self time.** Look for where the time actually goes: waiting on I/O (sleep,
   socket, DB driver, HTTP client) or computing.
4. **Your code by inclusive time.** This is the code that can be changed.

Then drill down:
- `get_call_details(trace_id, function)` shows the callers, callees and slowest
  invocations with arguments and return values.
- Read the real file in the repository with your file tools. `get_function_source` shows
  the code as it was when the trace was recorded; the repository is the source of truth.

Typical root causes and fixes:

| Signal in the trace | Likely cause | Fix |
|---|---|---|
| Same query or fetch ×N with different ids | N+1 | One batched query (`IN`, join), ORM `selectinload`/`joinedload`, `select_related`/`prefetch_related`, or a dataloader |
| `time.sleep`, `requests`, or a sync DB driver inside an `async def` | Blocking the event loop | Use an async client, or make the endpoint `def` / use `run_in_threadpool` |
| Several independent HTTP or DB calls in sequence | Sequential I/O | Run them concurrently (`asyncio.gather`), reuse a client/session for connection pooling |
| Same function with the same arguments and the same result many times | Redundant work | Hoist it out of the loop, memoize, or cache per request |
| Connection or client created on every request | Missing pooling | Create it once at startup and reuse it |
| Large time in serialization (`jsonable_encoder`, pydantic validation) | Payload too big | Paginate, select fewer fields, return a `response_model` tailored to the endpoint |
| Pure-Python loop with a huge call count | CPU hot loop | Better algorithm or data structure, builtins, or vectorization |

Caveat: tracing adds about 1µs per function call, so functions with very large call counts
look slower than they are untraced. Waits (sleep, network, DB) are measured accurately.

Before you edit anything, tell the user the root cause in two or three sentences, with
the evidence: ms, % of the request, call counts and `file:line`.

## 4. Fix

- Make the smallest change that removes the bottleneck. Keep the response identical:
  same status, same data, same order. Never make the endpoint "faster" by returning less,
  changing defaults such as page size, or skipping work the caller relies on.
- Run the project's existing tests for the code you touched.

## 5. Verify

- Make sure the app is running the new code. With auto-reload, wait a moment; otherwise
  ask the user to restart it.
- Call `replay_request(baseline_trace_id, times=3)`. Read two columns before the timings:
  - **status:** a status change means the fix broke something.
  - **body:** `identical` is the goal. `same structure, values differ` is fine when the
    replay notes that values already vary between runs (timestamps, ids). `DIFFERENT`
    means the endpoint now returns other data: fix that before claiming any speed-up.
  If the baseline trace has no recorded body (Flask), compare against the first
  baseline replay instead.
- Call `compare_traces(baseline_id, new_id)`. Its `response_body` and `status` fields
  must hold. Then confirm that the bottleneck went away (for example, the N+1 callee drops
  from ×100 calls to ×1). Use `analyze_trace` on the new trace to see what dominates now.
- If the improvement is small or the time moved somewhere else, go back to step 3.

## 6. Report

Finish with a short summary:
- **Root cause**, with `file:line`.
- **The change.**
- **Before → after**, using median ms and the call counts that changed.
- **Behavior check:** status and response body (identical, or same structure).
- **What dominates the request now**, if more can be gained.
