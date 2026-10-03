<p align="center">
 <img 
    src="https://github.com/vpcarlos/profyle/blob/main/docs/img/profyle.png?raw=true" 
    width="300"
    alt="Profyle"
 >
</p>

<h3 align="center">Tell Claude Code which endpoint is slow. Get back a measured, verified fix.</h3>

<p align="center">
<a href="https://github.com/vpcarlos/profyle/actions/workflows/ci.yml" target="_blank">
    <img src="https://github.com/vpcarlos/profyle/actions/workflows/ci.yml/badge.svg" alt="CI">
</a>
<a href="https://pypi.org/project/profyle" target="_blank">
    <img src="https://img.shields.io/pypi/v/profyle" alt="Package version">
</a>
<a href="https://pypi.org/project/profyle" target="_blank">
    <img src="https://img.shields.io/pypi/pyversions/profyle.svg?color=%2334D058" alt="Supported Python versions">
</a>
<a href="https://github.com/vpcarlos/profyle/blob/main/LICENSE" target="_blank">
    <img src="https://img.shields.io/pypi/l/profyle" alt="License">
</a>
</p>

Profyle traces the requests of your **FastAPI, Flask, Django or Tornado** app with
[VizTracer](https://github.com/gaogaotiantian/viztracer) and gives Claude Code what it
needs to find the bottleneck, fix your code and **prove** the fix by replaying the same
request.

## Three steps

**1. Install, once**

```console
$ pip install "profyle[mcp]"
$ claude plugin marketplace add vpcarlos/profyle
$ claude plugin install profyle@profyle
```

**2. Ask Claude Code**

> GET /orders is slow, can you fix it?

**3. Get a verified fix**

> `GET /orders` now takes about **17 ms** warm, down from about **120 ms**.
>
> **Root cause:** an N+1 query. `list_orders` (`main.py:22`) called `get_customer`
> (`main.py:17`) once per order: 50 calls, 107 ms, 90% of the request.
>
> **Change:** `get_customers` fetches all the names with one `WHERE id IN (...)` query.
>
> | | Before | After |
> |---|---|---|
> | Median request time | 119.9 ms | 16.9 ms |
> | Lookup calls | 50 | 1 |
>
> **Behavior check:** status 200 and an identical response body before and after.

*A real Claude Code session on a project with no Profyle code and the server stopped.*

<details markdown="1">
<summary>What Claude did between steps 2 and 3</summary>

1. Checked the setup with `doctor`: nothing traced yet.
2. Found the dev server command in the README and, with your OK, started it with
   `profyle run uvicorn main:app --reload`, which traces without code changes.
3. Called the endpoint and replayed it 3 times for a warm baseline (the first request
   of a server includes warm-up).
4. Read the trace digest: `list_orders → get_customer ×50`, 90% of the request.
5. Fixed the code, waited for the reload, replayed the same request and compared the
   traces: 7× faster, same status, same response body.
</details>

### What you don't have to do
- ✗ Edit your app or add a middleware: `profyle run` adds tracing when the app starts.
- ✗ Write configuration or set environment variables: traces go to
  `<project>/.profyle/`, which git ignores automatically.
- ✗ Read a flamegraph of thousands of frames: each trace has a one-line main finding.
- ✗ Benchmark by hand: the same request is replayed and compared before and after.

### Prefer to look yourself?
Start your dev server through `profyle run` and every request tells you where its time
went:

```console
$ profyle run uvicorn main:app --reload
profyle ▸ GET /orders 123.8 ms · #2 · repeated: list_orders → get_customer ×50 (87.1%)
```

Then `profyle start` lets you browse the traces in Perfetto.

> [!WARNING]
> Profyle is a **development tool**. Tracing slows requests down and traces contain
> source code and request data, so do not enable it in production. See
> [SECURITY.md](SECURITY.md).

Requires Python 3.10+. The plugin starts `profyle` from your `PATH`; if that is not your
project's environment, set `PROFYLE_COMMAND=/path/to/.venv/bin/profyle`. Without the
plugin, register just the MCP server from your project directory:
`claude mcp add profyle -- profyle mcp`.

## Add tracing to your app

### Without code changes: `profyle run`
Put `profyle run` in front of the command that starts your dev server:

```console
$ profyle run uvicorn main:app --reload            # FastAPI, Starlette, any ASGI app
$ profyle run flask --app app run --debug          # Flask
$ profyle run python manage.py runserver           # Django (WSGI)
$ profyle run gunicorn -k tornado app:app          # Tornado (or: profyle run python app.py)
$ profyle run uvicorn mysite.asgi:application      # Django (ASGI)
```

Each request prints its main finding in the console:

```console
profyle ▸ tracing requests of `uvicorn main:app --reload` → .profyle/profile.db. Each request prints a summary line here; …
profyle ▸ GET /orders 543.3 ms · #1 · repeated: getblock → _tokenize ×44 (64.2%) · first request, includes warm-up
profyle ▸ GET /orders 123.8 ms · #2 · repeated: list_orders → get_customer ×50 (87.1%)
```

`profyle run` adds the middleware when your framework loads: FastAPI/Starlette, Flask,
Django and Tornado under any server, plus any other ASGI framework (Litestar, Quart, …)
served by uvicorn. For other combinations, add the middleware yourself.

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
<summary>Tornado</summary>

```python
import tornado.web
from profyle.tornado import instrument

app = instrument(tornado.web.Application([(r"/orders", OrdersHandler)]))
```
Works with Tornado's own server and with gunicorn's tornado worker.
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

VizTracer records one trace at a time per process. A request that arrives while another
one is being traced is served normally but not traced (the console says so), and work
done by overlapping requests on the same thread can show up in the trace being
recorded. Profyle is meant for requests you make one at a time while developing.

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
