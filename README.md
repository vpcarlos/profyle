# Profyle
### Development tool for analysing and managing python traces

<a href="https://pypi.org/project/profyle" target="_blank">
    <img src="https://img.shields.io/pypi/v/profyle" alt="Package version">
</a>
<a href="https://pypi.org/project/profyle" target="_blank">
    <img src="https://img.shields.io/pypi/pyversions/profyle.svg?color=%2334D058" alt="Supported Python versions">
</a>

## Why do you need Profyle?
### Bottlenecks
With Profyle you can easily detect where in your code you have a bottleneck, just analize the trace and see what function or operation is taking most of the request execution time

### Enhance performace
Analize the traces and decide which parts of your code should be improved


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
<details markdown="1">
<summary>FastAPI</summary>

```Python
from fastapi import FastAPI
from profyle.middleware.fastapi import ProfyleMiddleware

app = FastAPI()
app.add_middleware(ProfyleMiddleware)

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}
```
</details>

<details markdown="1">
<summary>Flask</summary>

```Python
from flask import Flask
from profyle.middleware.flask import ProfyleMiddleware

app = Flask(__name__)

app.wsgi_app = ProfyleMiddleware(app.wsgi_app)

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"
```
</details>

<details markdown="1">
<summary>Django</summary>
Soon..
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