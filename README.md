# Profyle
### Development tool for analysing and managing profile statistics

<a href="https://pypi.org/project/profyle" target="_blank">
    <img src="https://img.shields.io/pypi/v/profyle" alt="Package version">
</a>
<a href="https://pypi.org/project/profyle" target="_blank">
    <img src="https://img.shields.io/pypi/pyversions/profyle.svg?color=%2334D058" alt="Supported Python versions">
</a>

## Installation

<div class="termy">

```console
$ pip install profyle

---> 100%
```

</div>

## Example

### FastApi

#### Implement
* Implement the middleware:

```Python
from fastapi import FastAPI
from profyle.middleware.fastapi import ProfileMiddleware

app = FastAPI()
app.add_middleware(ProfileMiddleware)

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}
```

#### Run
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

#### Search
* Search all requests tracing and click on it:

![Alt text](https://github.com/vpcarlos/profyle/blob/main/docs/img/traces.png?raw=true "Traces")

#### Analyses
* Analyses a request profile:

![Alt text](https://github.com/vpcarlos/profyle/blob/main/docs/img/trace.png?raw=true "Trace")


### Flask
... coming soon


## Commands
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
