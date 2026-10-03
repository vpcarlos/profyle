<p align="center">
 <img 
    src="https://github.com/vpcarlos/profyle/blob/main/docs/img/profyle.png?raw=true" 
    width="300"
    alt="Profyle"
 >
</p>

### Trace your Python web requests, find the bottleneck, fix it with Claude Code
[![CI](https://github.com/vpcarlos/profyle/actions/workflows/ci.yml/badge.svg)](https://github.com/vpcarlos/profyle/actions/workflows/ci.yml)
<a href="https://pypi.org/project/profyle" target="_blank">
    <img src="https://img.shields.io/pypi/v/profyle" alt="Package version">
</a>
<a href="https://pypi.org/project/profyle" target="_blank">
    <img src="https://img.shields.io/pypi/pyversions/profyle.svg?color=%2334D058" alt="Supported Python versions">
</a>
<a href="https://github.com/vpcarlos/profyle/blob/main/LICENSE" target="_blank">
    <img src="https://img.shields.io/pypi/l/profyle" alt="License">
</a>

Profyle records a [VizTracer](https://github.com/gaogaotiantian/viztracer) trace of every
request to your FastAPI, Flask or Django app, lets you explore it in
[Perfetto](https://perfetto.dev), and gives Claude Code the tools to find the bottleneck,
fix your code and prove the fix by replaying the request.

> [!WARNING]
> Profyle is a **development tool**. Tracing slows requests down and traces contain
> source code and request data, so do not enable it in production. See
> [SECURITY.md](SECURITY.md).

## Why Profyle?
- **Find the bottleneck, not just a flamegraph**: every traced request gets a one-line
  main finding, such as `repeated: list_orders → get_customer ×100 (83%)`.
- **No code changes**: `profyle run uvicorn main:app --reload` traces FastAPI,
  Starlette, Flask, Django and any ASGI app served by uvicorn.
- **Fixes you can trust**: Claude Code reads the trace, changes your code, replays the
  same request and checks that it is faster *and* returns the same data.

## Installation

<div class="termy">

```console
$ pip install profyle

---> 100%
```

</div>

Requires Python 3.10+. Extras: `profyle[mcp]` (Claude Code / MCP server),
`profyle[flask]`, `profyle[django]`.

## Quick start with Claude Code

```console
$ pip install "profyle[mcp]"                        # in your app's environment
$ claude plugin marketplace add vpcarlos/profyle
$ claude plugin install profyle@profyle
```

Then, in your project, tell Claude Code what feels slow:

> GET /orders is slow, can you fix it?

The `fix-slow-endpoint` skill takes it from there. If the app is not traced yet, Claude
proposes starting your dev server with `profyle run` (no code changes) and, once you
agree, makes the request, reads the trace, fixes the code, replays the request and
reports the measured before/after:

> `GET /orders` now takes about **17 ms** warm instead of **120 ms**. Root cause: N+1
> query, `list_orders` (`main.py:22`) called `get_customer` once per order (50 calls,
> 90% of the request) … Status 200 and response body identical before and after.

The plugin starts `profyle` from your `PATH`; if that is not your project's environment,
set `PROFYLE_COMMAND=/path/to/.venv/bin/profyle`. Without the plugin, register just the
MCP server from your project directory: `claude mcp add profyle -- profyle mcp`.

## Add tracing to your app

### Without code changes: `profyle run`
Put `profyle run` in front of the command that starts your dev server:

```console
$ profyle run uvicorn main:app --reload            # FastAPI, Starlette, any ASGI app
$ profyle run flask --app app run --debug          # Flask
$ profyle run python manage.py runserver           # Django (WSGI)
$ profyle run uvicorn mysite.asgi:application      # Django (ASGI)
```

Each request prints its main finding in the console:

```console
profyle ▸ tracing requests of `uvicorn main:app --reload` → .profyle/profile.db. Each request prints a summary line here; …
profyle ▸ GET /orders 543.3 ms · #1 · repeated: getblock → _tokenize ×44 (64.2%) · first request, includes warm-up
profyle ▸ GET /orders 123.8 ms · #2 · repeated: list_orders → get_customer ×50 (87.1%)
```

`profyle run` adds the middleware when your framework loads: FastAPI/Starlette, Flask
and Django under any server, plus any other ASGI framework (Litestar, Quart, …) served
by uvicorn. For other combinations, add the middleware yourself.

### With a middleware
<details markdown="1" open>
<summary>FastAPI / Starlette</summary>

```python
from fastapi import FastAPI
from profyle.fastapi import ProfyleMiddleware

app = FastAPI()
app.add_middleware(ProfyleMiddleware)                      # trace every request
# app.add_middleware(ProfyleMiddleware, pattern="/users*") # or only some paths
```
</details>

<details markdown="1">
<summary>Flask</summary>

```python
from flask import Flask
from profyle.flask import ProfyleMiddleware

app = Flask(__name__)
app.wsgi_app = ProfyleMiddleware(app.wsgi_app)
```
</details>

<details markdown="1">
<summary>Django</summary>

```python
# settings.py
MIDDLEWARE = [
    "profyle.django.ProfyleMiddleware",  # first, so it traces the other middlewares too
    ...
]
```
</details>

<details markdown="1">
<summary>Any ASGI or WSGI framework (Litestar, Quart, Falcon, Bottle, Pyramid…)</summary>

```python
from profyle.asgi import ProfyleMiddleware   # ASGI apps
app = ProfyleMiddleware(app)

from profyle.wsgi import ProfyleMiddleware   # WSGI apps
app = ProfyleMiddleware(app)
```
</details>

An explicit middleware takes precedence over `profyle run`, so you can keep it and
still use `profyle run`.

## Configuration
Every integration reads the same settings. Each one comes from, in order of priority:
an environment variable, the code (middleware arguments or Django `PROFYLE_*` settings),
`[tool.profyle]` in `pyproject.toml`, or the default. `profyle doctor` shows the values
in use and where each one comes from.

| Setting | Environment variable | Default | Description |
| --- | --- | --- | --- |
| `enabled` | `PROFYLE_ENABLED` | `true` | Trace requests at all |
| `pattern` | `PROFYLE_PATTERN` | all paths | Only trace paths matching this [glob](https://en.wikipedia.org/wiki/Glob_(programming)), e.g. `/api/*` |
| `max_stack_depth` | `PROFYLE_MAX_STACK_DEPTH` | `-1` (unlimited) | Maximum call stack depth to record |
| `min_duration` | `PROFYLE_MIN_DURATION` | `0` | Drop function calls shorter than this, in **microseconds** |
| `console` | `PROFYLE_CONSOLE` | `true` | Print one line per traced request |

```toml
# pyproject.toml
[tool.profyle]
pattern = "/api/*"
max-stack-depth = 30
```

Other environment variables: `PROFYLE_DB` (trace database, see
[Trace database](#trace-database)), `PROFYLE_CAPTURE_SECRETS` and
`PROFYLE_REPLAY_ALLOW_REMOTE` (see [Replay safety](#replay-safety)).

## Browse traces
`profyle start` opens a web UI listing your traces with their main finding; open one to
explore it in Perfetto, with source code, arguments and return values.

```console
$ profyle start
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

![Traces](https://github.com/vpcarlos/profyle/blob/main/docs/img/traces.png?raw=true "Traces")

Profyle stands on the shoulders of giants:
[VizTracer](https://github.com/gaogaotiantian/viztracer) and
[Perfetto](https://github.com/google/perfetto). Traces include threads and async code.

![Trace](https://github.com/vpcarlos/profyle/blob/main/docs/img/trace1.png?raw=true "Trace1")

![Trace detail](https://github.com/vpcarlos/profyle/blob/main/docs/img/trace2.png?raw=true "Trace2")

## How Claude works with your traces
The skill makes Claude:
1. run `doctor` and, if needed, start your app with `profyle run`;
2. take a warm baseline by replaying the request (`replay_request`);
3. read the trace **digest**: critical path per thread, top self time, your own code, I/O
   wait and repeated calls from the same caller (N+1 candidates), each with `file:line`.
   A traced request easily holds 100k+ VizTracer events; the digest is a few KB;
4. drill into the suspicious functions and read your code;
5. fix it, replay the request and `compare_traces` before/after, checking that the
   status code and the **response body** did not change;
6. report root cause, change and measured improvement.

| MCP tool | |
|---|---|
| `doctor` | Checks the trace database, recorded requests and that the app is running |
| `slowest_endpoints` | Endpoints ranked by p95, with the main finding of a typical trace |
| `list_traces` | Recorded traces with their main finding, filterable by name and duration |
| `analyze_trace` | Bottleneck digest of a trace |
| `get_call_details` | Callers, callees, slowest calls with args and return values |
| `get_function_source` | Source of a function as it was when traced |
| `replay_request` | Send the traced request again, return the new traces |
| `compare_traces` | Before/after deltas, plus status and response body verdict |

### Digests are precomputed
Each trace's digest and a one-line **main finding** (e.g. `repeated: list_orders →
get_customer ×100 (83%)`) are stored next to it. They are computed outside your app's
request path: by a separate console process when `console` is on, by the MCP server in
the background, or by any analysis. Listings in the MCP tools and in the web UI show the
finding, and analyzing a trace again is instant.

### Same speed-up, same data
Each trace keeps a fingerprint of the response body, never the body itself: a hash of the
canonical body and, for JSON, a hash of its structure (keys, value types, list lengths).
Replays and `compare_traces` report the body as **identical**, **same structure, values
differ** (e.g. timestamps) or **DIFFERENT**, so a "fix" that returns less data is caught.
FastAPI/Starlette and Django record it on every request; with Flask the first replay
records it.

### Replay safety
- Profyle stores the request behind each trace (method, path, headers, body up to 64 KB,
  response status). `Authorization`, `Cookie`, API key and CSRF headers are stored as
  `[redacted]` unless `PROFYLE_CAPTURE_SECRETS=true`; pass credentials when replaying
  instead (`-H` in the CLI, `headers` in the MCP tool).
- Only local hosts are replayed unless `PROFYLE_REPLAY_ALLOW_REMOTE=true`.
- `POST`/`PUT`/`PATCH`/`DELETE` are only replayed with explicit permission
  (`--allow-unsafe` / `allow_unsafe_method`); the skill asks you first.

### Without Claude Code
```console
$ profyle analyze 42 | claude -p "Find the bottleneck and propose a fix"
$ profyle replay 42 --times 3
$ profyle doctor
```

### Trace database
Traces are stored in `<project>/.profyle/profile.db`, where `<project>` is the closest
parent of the working directory with a `pyproject.toml`, `setup.py`, `manage.py`,
`requirements.txt` or `.git`. The app, `profyle start`, `profyle mcp` and the plugin all
find the same file. Set `PROFYLE_DB=/path/to/profile.db` to use another location.
Versions before 0.4 stored traces inside the installed package; `profyle doctor` warns if
it still finds traces there.

## CLI Commands
### run
* Run the command that starts your app with tracing, no code changes

<div class="termy">

```console
$ profyle run uvicorn main:app --reload
```

</div>

### start
* Start the web server and view profile traces

| Options | Type | Default | Description |
| --- | --- | --- | --- |
| --port | INTEGER | 0 | web server port |                                                                 
| --host | TEXT | 127.0.0.1 | web server host |                                                                 
                                                                  

<div class="termy">

```console
$ profyle start --port 5432

INFO:     Uvicorn running on http://127.0.0.1:5432 (Press CTRL+C to quit)
INFO:     Started reloader process [28720]
INFO:     Started server process [28722]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

</div>

### clean
* Delete all profile traces
<div class="termy">

```console
$ profyle clean

10 traces removed 
```

</div>

### info
* Show the traces DB location and size
<div class="termy">

```console
$ profyle info

DB size → 30.0 MB
```

</div>

### analyze
* Print the LLM-ready digest of a trace (defaults to the selected one)
<div class="termy">

```console
$ profyle analyze 42
```

</div>

### doctor
* Check that traces are recorded, can be replayed and the app is running
<div class="termy">

```console
$ profyle doctor

✓ Database /my/project/.profyle/profile.db: 12 traces, newest #12 GET /orders
✓ Requests are recorded, so they can be replayed.
✓ The app is running at http://localhost:8000.
```

</div>

### replay
* Send the request of a trace again (local app) and record a new trace

| Options | Type | Default | Description |
| --- | --- | --- | --- |
| --times | INTEGER | 1 | Number of replays |
| --base-url | TEXT | recorded host | Where the app listens, e.g. `http://127.0.0.1:8000` |
| -H, --header | TEXT | | Extra header, repeatable, e.g. `'Authorization: Bearer x'` |
| --allow-unsafe | FLAG | | Allow POST/PUT/PATCH/DELETE |

<div class="termy">

```console
$ profyle replay 42 --times 3
$ profyle doctor
```

</div>

### mcp
* Run the MCP server over stdio (for Claude Code / Claude Desktop)
<div class="termy">

```console
$ profyle mcp
```

</div>


## Contributing
Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for the development
setup and guidelines, and [CHANGELOG.md](CHANGELOG.md) for what changed in each release.
Please report security issues privately as described in [SECURITY.md](SECURITY.md).

## License
Profyle is released under the [MIT License](LICENSE).
