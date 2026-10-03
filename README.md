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

## Why do you need Profyle?
### Bottlenecks
With Profyle you can easily detect where in your code you have a bottleneck, simply analyze the trace and see what function or operation is taking most of the execution time of the request

### Enhance performance
Analyze the traces and decide which parts of your code should be improved


## Installation

<div class="termy">

```console
$ pip install profyle

---> 100%
```

</div>

Requires Python 3.10+. Extras: `profyle[mcp]` (Claude Code / MCP server),
`profyle[flask]`, `profyle[django]`.

## Example

### 1. Implement
In order to track all your API requests you must implement the <code>ProfyleMiddleware</code>
#### ProfyleMiddleware
| Attribute | Required | Default | Description | ENV Variable |
| --- | --- | --- | --- | --- |
| `enabled` | No | `True` | Enable or disable Profyle | `PROFYLE_ENABLED` |
| `pattern` | No | `None` | 0nly trace those paths that match with [pattern](https://en.wikipedia.org/wiki/Glob_(programming))  | `PROFYLE_PATTERN` |
| `max_stack_depth` | No | `-1` | Limit maximum stack trace depth | `PROFYLE_MAX_STACK_DEPTH` |
| `min_duration` | No | `0` (milisecons) | Only record traces with a greather duration than the limit. | `PROFYLE_MIN_DURATION` |


<details markdown="1" open>
<summary>FastAPI</summary>

```Python
from fastapi import FastAPI
from profyle.fastapi import ProfyleMiddleware

app = FastAPI()
# Trace all requests
app.add_middleware(ProfyleMiddleware)

@app.get("/")
async def root():
    return {"hello": "world"}
```

```Python
from fastapi import FastAPI
from profyle.fastapi import ProfyleMiddleware

app = FastAPI()
# Trace all requests that match that start with /users 
# with a minimum duration of 100ms and a maximum stack depth of 20
app.add_middleware(
    ProfyleMiddleware,
    pattern="/users*",
    max_stack_depth=20,
    min_duration=100
)

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"hello": "user"}
```
</details>

<details markdown="1">
<summary>Flask</summary>

```Python
from flask import Flask
from profyle.flask import ProfyleMiddleware

app = Flask(__name__)

app.wsgi_app = ProfyleMiddleware(app.wsgi_app, pattern="*/api/products*")

@app.route("/")
def root():
    return "<p>Hello, World!</p>"
```
</details>

<details markdown="1">
<summary>Django</summary>

```Python
# settings.py

MIDDLEWARE = [
    ...
    "profyle.django.ProfyleMiddleware",
    ...
]
```
</details>

### 2. Run
* Run the web server:

<div class="termy">

```console
$ profyle start

INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [28720]
INFO:     Started server process [28722]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

</div>

### 3. List
* List all requests tracing:

![Alt text](https://github.com/vpcarlos/profyle/blob/main/docs/img/traces.png?raw=true "Traces")

### 4. Analyze
* Profyle stands on the shoulder of giants: <a href="https://github.com/gaogaotiantian/viztracer" class="external-link" target="_blank">Viztracer</a> and  <a href="https://github.com/google/perfetto" class="external-link" target="_blank">Perfetto</a>
* Detailed function entry/exit information on timeline with source code
* Super easy to use, no source code change for most features, no package dependency
* Supports threading, multiprocessing, subprocess and async
* Powerful front-end, able to render GB-level trace smoothly
* Works on Linux/MacOS/Window

![Alt text](https://github.com/vpcarlos/profyle/blob/main/docs/img/trace1.png?raw=true "Trace1")

![Alt text](https://github.com/vpcarlos/profyle/blob/main/docs/img/trace2.png?raw=true "Trace2")



## Fix slow endpoints with Claude Code
Tell Claude Code *"GET /orders is slow"* and it finds the bottleneck in the real trace,
fixes your code, replays the same request and shows you the before/after.

### 1. Install
```console
$ pip install "profyle[mcp]"
```
Add `ProfyleMiddleware` to your app (see [Example](#example)) and run it from your
project, ideally with auto-reload:
```console
$ uvicorn main:app --reload
```
Traces go to `<project>/.profyle/profile.db`, a folder git ignores automatically.
`profyle doctor` checks that everything is wired up.

### 2. Add the Claude Code plugin
```console
$ claude plugin marketplace add vpcarlos/profyle
$ claude plugin install profyle@profyle
```
The plugin bundles the `profyle` MCP server and the `fix-slow-endpoint` skill, which
Claude uses automatically when you mention a slow endpoint (or run
`/profyle:fix-slow-endpoint`). It starts `profyle` from your `PATH`; if that is not your
project's environment, set `PROFYLE_COMMAND=/path/to/.venv/bin/profyle`.

Without the plugin, register just the MCP server from your project directory:
`claude mcp add profyle -- profyle mcp`

### 3. Ask
Hit the slow endpoint once, then ask Claude Code about it. The skill makes it:
1. run `doctor` and tell you exactly what to fix if the setup is incomplete;
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
get_customer ×100 (83%)`) are stored next to it. They are computed by the reader side,
never in your app's request path: the MCP server digests new traces in the background,
and any analysis stores its result. Listings in the MCP tools and in the web UI show the
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
