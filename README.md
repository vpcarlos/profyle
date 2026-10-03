<p align="center">
 <img 
    src="https://github.com/vpcarlos/profyle/blob/main/docs/img/profyle.png?raw=true" 
    width="300"
    alt="Profyle"
 >
</p>

### Development tool for analysing and managing python traces
[![Tests](https://github.com/vpcarlos/profyle/actions/workflows/test.yml/badge.svg)](https://github.com/vpcarlos/profyle/actions/workflows/test.yml)
<a href="https://pypi.org/project/profyle" target="_blank">
    <img src="https://img.shields.io/pypi/v/profyle" alt="Package version">
</a>
<a href="https://pypi.org/project/profyle" target="_blank">
    <img src="https://img.shields.io/pypi/pyversions/profyle.svg?color=%2334D058" alt="Supported Python versions">
</a>

## Why do you need Profyle?
### Bottlenecks
With Profyle you can easily detect where in your code you have a bottleneck, simply analyze the trace and see what function or operation is taking most of the execution time of the request

### Enhance performace
Analyze the traces and decide which parts of your code should be improved


## Installation

<div class="termy">

```console
$ pip install profyle

---> 100%
```

</div>

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



## AI analysis with Claude
A single traced request easily holds 100k+ VizTracer events (tens of MB), far more than a
model can read. Profyle condenses each trace into a **digest** of a few KB: critical path
per thread, top self time, your own code by inclusive time, I/O wait and repeated calls
from the same caller (N+1 candidates), each with `file:line`.

### Claude Code / Claude Desktop (MCP)
```console
$ pip install "profyle[mcp]"
$ claude mcp add profyle -e PROFYLE_DB=$PWD/profile.db -- profyle mcp
```
Then ask Claude Code *"why is GET /users slow? fix it"*. It gets read-only tools
(`slowest_endpoints`, `list_traces`, `analyze_trace`, `get_call_details`,
`get_function_source`, `compare_traces`) and, since it already has your repository open,
can go from trace to code change, and verify the fix by comparing a new trace.

### In-app chat
```console
$ pip install "profyle[ai]"
$ export ANTHROPIC_API_KEY=...   # or `ant auth login`
$ profyle start
```
Open a trace and use the chat bubble. Model and effort can be changed with
`PROFYLE_CLAUDE_MODEL` (default `claude-opus-5-5`) and `PROFYLE_CLAUDE_EFFORT`
(default `medium`). Function arguments and return values recorded in the trace are sent
to the Claude API when the model asks for them.

### Any LLM / scripts
```console
$ profyle analyze 42 | claude -p "Find the bottleneck and propose a fix"
```

### Trace database
Traces are stored in a SQLite file inside the installed package by default. Set
`PROFYLE_DB=/path/to/profile.db` (in the app **and** for `profyle start` / `profyle mcp`)
to keep one database per project.

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

### mcp
* Run the MCP server over stdio (for Claude Code / Claude Desktop)
<div class="termy">

```console
$ profyle mcp
```

</div>
