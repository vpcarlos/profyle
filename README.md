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

### check
* Check traces DB size
<div class="termy">

```console
$ profyle check

DB size: 30MB
```

</div>
