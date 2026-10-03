# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.4.0] - Unreleased

### Added
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
- The trace viewer no longer sends permissive CORS headers.

### Fixed
- Sync FastAPI/Starlette endpoints and dependencies, Django async views under ASGI and
  `sync_to_async` code were missing from traces after the first request on Python
  < 3.12, because they run in reused worker threads.
- The FastAPI middleware duplicated the query string in trace names with some
  servers.
- The Flask middleware relied on the server-specific `REQUEST_URI`.

## [0.3.0] - 2024-04-19

Last release before this changelog was introduced.

[0.3.0]: https://pypi.org/project/profyle/0.3.0/
