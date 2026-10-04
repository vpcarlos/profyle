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

### Enhance performance
Analyze the traces and decide which parts of your code should be improved


## Installation

<div class="termy">

```console
$ pip install profyle

---> 100%
```

</div>

That's all you need: there are no extras to choose from. This single package includes:
* The `profyle` CLI and the web UI to browse traces (built on FastAPI and Uvicorn, which are installed with it)
* <a href="https://github.com/gaogaotiantian/viztracer" class="external-link" target="_blank">VizTracer</a>, which records the traces
* The middlewares for FastAPI, Flask and Django

Profyle doesn't install Flask or Django. Its middleware uses the one your project already has.

> **Note**
> Install Profyle in the same Python environment as your app. Traces are stored in a SQLite database inside the installed `profyle` package, so `profyle start` only shows the traces recorded by apps running in that environment.

## Example

### 1. Implement
In order to track all your API requests you must implement the <code>ProfyleMiddleware</code>
#### ProfyleMiddleware
| Attribute | Required | Default | Description | ENV Variable |
| --- | --- | --- | --- | --- |
| `enabled` | No | `True` | Enable or disable Profyle | `PROFYLE_ENABLED` |
| `pattern` | No | `None` | Only trace those paths that match with [pattern](https://en.wikipedia.org/wiki/Glob_(programming))  | `PROFYLE_PATTERN` |
| `max_stack_depth` | No | `-1` | Limit maximum stack trace depth | `PROFYLE_MAX_STACK_DEPTH` |
| `min_duration` | No | `0` (milliseconds) | Only record traces with a greater duration than the limit. | `PROFYLE_MIN_DURATION` |


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
# Trace all requests that start with /users
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

Django reads the options from your `settings.py` instead of environment variables.

```Python
# settings.py

MIDDLEWARE = [
    ...
    "profyle.django.ProfyleMiddleware",
    ...
]

# Optional
PROFYLE_ENABLED = True
PROFYLE_PATTERN = "/api/*"
PROFYLE_MAX_STACK_DEPTH = 20
```
</details>

### 2. Run
* Run the web server and open the URL it prints. By default it picks a free port. Use `--port` to set a fixed one:

<div class="termy">

```console
$ profyle start

INFO:     Started server process [28722]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:38165 (Press CTRL+C to quit)
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
* Works on Linux/MacOS/Windows

![Alt text](https://github.com/vpcarlos/profyle/blob/main/docs/img/trace1.png?raw=true "Trace1")

![Alt text](https://github.com/vpcarlos/profyle/blob/main/docs/img/trace2.png?raw=true "Trace2")



## CLI Commands
### start
* Start the web server and view profile traces

| Options | Type | Default | Description |
| --- | --- | --- | --- |
| --port | INTEGER | 0 | web server port (`0` picks a free port) |
| --host | TEXT | 127.0.0.1 | web server host |

<div class="termy">

```console
$ profyle start --port 8000

INFO:     Started server process [28722]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

</div>

### clean
* Delete all profile traces
<div class="termy">

```console
$ profyle clean

10 records removed
```

</div>

### info
* Show where the traces are stored and the traces DB size
<div class="termy">

```console
$ profyle info

Project → /path/to/venv/lib/python3.11/site-packages/profyle
DB size → 30.0 MB
```

</div>
