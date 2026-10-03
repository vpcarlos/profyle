# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.4.0] - Unreleased

### Added
- **`profyle run <command>`**: trace an app without code changes
  (`profyle run uvicorn main:app --reload`, `flask run`, `manage.py runserver`, ...).
  Supports FastAPI/Starlette, Flask and Django under any server, and any ASGI app served
  by uvicorn.
- **One line per traced request in the console** with its main finding, computed in a
  separate process so requests do not wait for it (`console` setting).
- **Generic middlewares** `profyle.asgi` and `profyle.wsgi` for any ASGI/WSGI framework.
- **Tornado support** (#6): `profyle.tornado.instrument(app)`, and `profyle run` for
  Tornado's own server and gunicorn's tornado worker (extra `profyle[tornado]`).
- **Unified configuration** for every integration: environment variables, code, or
  `[tool.profyle]` in `pyproject.toml`; `profyle doctor` shows each value and its source,
  plus the app that is writing traces.
- **Claude Code plugin** (`claude-plugin/`, installable from this repository's
  marketplace) with the `fix-slow-endpoint` skill: diagnose a slow endpoint from its
  traces, fix it, replay the request and verify the result.
- **MCP server** (`profyle mcp`, extra `profyle[mcp]`) with the tools `doctor`,
  `slowest_endpoints`, `list_traces`, `analyze_trace`, `get_call_details`,
  `get_function_source`, `replay_request` and `compare_traces`.
- **Trace digest**: a few-KB summary of a trace (critical path per thread, self time,
  your own code, I/O wait, repeated calls such as N+1 queries), stored with each trace
  together with a one-line main finding shown in listings and in the web UI.
- **Request recording and replay** (`profyle replay`): each trace keeps the request
  that produced it (credentials redacted) and the response status, so it can be sent
  again to the local app.
- **Response fingerprints**: replays and comparisons report whether the response body
  is identical, has the same structure, or changed.
- CLI commands `analyze`, `replay` and `doctor`.

### Changed
- Traces are stored in `<project>/.profyle/profile.db` (git-ignored automatically)
  instead of inside the installed package. Set `PROFYLE_DB` to choose another file.
- Python 3.10 or newer is required. Minimum versions: VizTracer 1.0, FastAPI 0.115,
  pydantic 2, Flask 3.0 (for `profyle[flask]`), MCP 2.0 (for `profyle[mcp]`).
- The CLI no longer depends on Typer and Rich.
- `profyle.fastapi` and `profyle.flask` are now aliases of the generic ASGI and WSGI
  middlewares; middleware settings default to `None` (unset) so the configuration
  sources above apply.
- The trace viewer no longer sends permissive CORS headers.

### Fixed
- Concurrent requests corrupted each other's traces (VizTracer: "Overwrite tracer!").
  A request that arrives while another one is traced is now served untraced, and the
  console says so.
- Code run through `loop.run_in_executor` (Tornado, plain asyncio) was missing from
  traces after the first request on Python < 3.12.
- `profyle --help` crashed with recent Click versions (#8): the CLI no longer uses Typer.
- `PermissionError` on Windows writing a temporary trace file (#4): traces are built in
  memory, without temporary files.
- Dependency ranges were too strict (#5): only minimum versions are declared now.
- `PROFYLE_ENABLED=false` did not disable the FastAPI and Flask middlewares.
- The disabled Django middleware returned no response, breaking every request.
- The Django middleware read `MIN_DURATION` instead of `PROFYLE_MIN_DURATION` (the old
  name still works, with a deprecation warning) and ignored environment variables.
- The WSGI (Flask) middleware ignored HTTPS requests.
- Importing a middleware opened the trace database even when Profyle was disabled.
- `min_duration` was documented in milliseconds; it is in microseconds and filters
  function calls, not requests.
- Sync FastAPI/Starlette endpoints and dependencies, Django async views under ASGI and
  `sync_to_async` code were missing from traces after the first request on Python
  < 3.12, because they run in reused worker threads.
- The FastAPI middleware duplicated the query string in trace names with some
  servers.
- The Flask middleware relied on the server-specific `REQUEST_URI`.

## [0.3.0] - 2024-04-19

Last release before this changelog was introduced.

[0.3.0]: https://pypi.org/project/profyle/0.3.0/
