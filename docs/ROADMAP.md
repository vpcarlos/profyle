# Roadmap and design notes

## Why Profyle works with Claude

A traced request easily contains 100k+ VizTracer events (tens of MB of JSON): no model
can read that, and a developer has to dig through a flamegraph of thousands of frames.
Profyle's job is to turn a trace into the context a coding agent needs, and to close the
loop between measuring and fixing:

```
slow request → trace → compact digest → Claude Code (which has your repository open)
      ↑                                                  ↓
compare_traces  ←  replay the same request  ←  code change
```

## Design notes

- **Digest, not raw traces.** `profyle/application/analysis/digest.py` rebuilds the call
  tree per thread and keeps what matters to find a bottleneck in a few KB: critical path
  per thread (with pass-through framework frames collapsed), top self time by origin
  (your code, stdlib, third party, builtins), your own code by inclusive time, I/O wait,
  and repeated calls from one caller with sample arguments (`id=1 | id=2 | id=3` is the
  signature of an N+1). It is deterministic and needs no LLM.
- **No overhead in the traced app beyond tracing.** Digests are built on the reading
  side (the MCP server warms them in the background; any analysis stores its result)
  and versioned, so a new analysis rebuilds them. Recording the request and the
  response fingerprint happens after the tracer stops, so Profyle does not appear in the
  traces it measures.
- **Verification is part of the workflow.** Every trace keeps the request that produced
  it, so it can be replayed, and a fingerprint of the response (canonical hash plus, for
  JSON, a hash of its structure) so a "fix" that changes the returned data is caught.
- **Safe by default.** Credentials are redacted when recording, response bodies are
  never stored, replays only target local hosts, and requests that may modify data are
  only replayed with explicit permission.
- **Worker threads.** Before Python 3.12, VizTracer only traces threads it hooked when
  they were created. Frameworks run code in reused thread pools (FastAPI sync endpoints
  and dependencies, Django async views under ASGI, `sync_to_async`), so
  `profyle/infrastructure/middleware/threadpool.py` enables tracing in the thread that
  runs the code for the duration of the call (anyio, asgiref and
  `loop.run_in_executor`), using VizTracer's `pause()`/`resume()` in
  the same frame to keep its per-thread stack balanced. Python 3.12+ uses
  `sys.monitoring` and needs none of this.

- **Zero-code integration.** `profyle run` puts `profyle/_run/sitecustomize.py` on
  `PYTHONPATH`; it installs import hooks that add the middleware when FastAPI/Starlette
  (`Starlette.__call__`), Flask (`Flask.__init__`), Django (`load_middleware`), Tornado
  (`RequestHandler._execute`) or uvicorn (`Config.load`, for any other ASGI app) is
  imported. Explicit middlewares win, and a
  marker on the request keeps nested middlewares from tracing it twice.
- **Feedback without overhead.** The one-line console summary is built by a separate
  process that reads the stored trace, so requests never wait for the digest.

## Roadmap

### Next
- **pytest plugin (`--profyle`)** that traces the requests made by test clients, stores
  them under the test name and compares them with a per-test baseline, with a GitHub
  Action that comments regressions on pull requests.
- **More servers for `profyle run`**: generic ASGI apps under hypercorn, granian or
  gunicorn's uvicorn workers (FastAPI, Flask and Django are already covered under any
  server).

### Deterministic detectors (no LLM needed)
- **SQL N+1 detection**: `cursor.execute` arguments are already recorded; normalize the
  SQL (`WHERE id = ?`) and group repeated statements. The same for SQLAlchemy, the
  Django ORM and HTTP clients (`httpx`, `requests`).
- **Event loop blocking**: synchronous I/O (`time.sleep`, `requests`, sync DB drivers)
  running on the asyncio loop thread.
- **Cache candidates**: same function, same arguments and same return value several
  times in one request.
- **Perfetto annotations**: inject findings as instant events so they are marked on the
  timeline.

### Teams and CI
- **"Slow requests only" mode**: keep a trace only when the whole request exceeds a
  threshold (today `min_duration` filters functions, not requests), and 1-in-N sampling.

### Privacy
- **Redaction before data reaches a model**: arguments and return values may contain
  tokens or personal data. Add pattern-based redaction in the tools and an option to send
  digests without argument values.

### Known issues
- One trace at a time per process: concurrent requests are not traced while another one
  is, and work from overlapping requests on the same thread appears in the running
  trace. Filtering events by asyncio task would isolate async requests.
- WSGI (Flask, Django under WSGI): the trace ends when the app returns its response,
  before the body is sent, so work done while streaming a generator body is not traced,
  and Flask traces get their response fingerprint from the first replay. Extending the
  trace over the body needs a safe way to end it when a test client never reads or
  closes the body (ending it from `__del__` crashes VizTracer).
- During development the test suite crashed twice at interpreter shutdown (fatal error
  after all tests passed) in ~30 runs, and never again in ~355 later runs, including 100
  in parallel. The suspected cause is threads still hooked to a tracer during shutdown;
  it has not been isolated. Please report it if you see it.
- VizTracer keeps at most `tracer_entries` (1M by default) events per trace; older events
  are dropped on very long requests (`viztracer_metadata.overflow`). The digest should
  surface this, and the middleware should expose the setting.

## Notes on VizTracer traces

- Chrome Trace Event JSON: `traceEvents` with `ph: "X"` complete events (`ts`, `dur` in
  µs) and `M` metadata events; `file_info.files[path] = [source, line_count]` and
  `file_info.functions[name] = [path, line]`. Function names follow
  `qualname (path:line)`; builtins have no path.
- Tracing adds about 1 µs per call, which inflates functions with very large call counts
  (for example a generator with 200k iterations). The digest warns about it.
- `log_sparse`, `include_files`/`exclude_files` and `max_stack_depth` can reduce
  framework noise at the source.

## How to measure whether it helps

- **Time to diagnosis** with and without the tools on endpoints with seeded problems (N+1,
  `sleep` in async code, hot loop, missing cache).
- **Accuracy**: share of cases where the root cause and `file:line` are right.
- **Verified improvement**: share of proposed fixes that reduce p95 in `compare_traces`
  without changing the response.
- **Cost per diagnosis** in tokens.
