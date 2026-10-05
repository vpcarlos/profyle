# Contributing to Profyle

Thanks for your interest in Profyle! Bug reports, ideas, documentation and code are all
welcome.

## Before you start

- For anything larger than a small fix, please open an issue first so we can agree on
  the approach. [docs/ROADMAP.md](docs/ROADMAP.md) lists planned work and explains the
  main design decisions.
- Report security vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).
- Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

Profyle uses [uv](https://docs.astral.sh/uv/) and supports Python 3.10 and newer.

```console
$ git clone https://github.com/vpcarlos/profyle && cd profyle
$ uv sync                  # creates .venv with the dev dependencies
$ uv run pytest            # run the test suite
$ uv run pytest -m "not integration"   # skip the tests that start real servers
$ uv run pytest --cov       # with coverage; fails below 100%
$ uv run ruff check profyle tests examples
$ uv run ruff format profyle tests examples
```

Optionally, install the git hooks so lint runs on every commit:

```console
$ uvx pre-commit install
```

To try your changes against a real app, use the apps in [`examples/`](examples/) (one per
framework, each with an N+1 query and no Profyle code), for example:

```console
$ cd examples/fastapi && uv run profyle run uvicorn main:app --reload
$ curl localhost:8000/orders            # prints a profyle ▸ line in the server console
$ uv run profyle doctor
```

The integration tests in `tests/integration/` run exactly these apps through
`profyle run`.

## Project layout

The code follows the path of a request, from the app being traced to Claude reading
the result:

| Path | What lives there |
|---|---|
| `profyle/domain/` | `Trace`, `RecordedRequest`, and the `TraceRepository` interface |
| `profyle/config.py`, `profyle/settings.py` | Settings shared by every integration (environment, code, `[tool.profyle]`) and where traces are stored |
| `profyle/infrastructure/middleware/` | Generic ASGI and WSGI middlewares (FastAPI and Flask are aliases), Django middleware, Tornado integration, shared `base.py`; `threadpool.py` makes worker threads traceable on Python < 3.12 |
| `profyle/infrastructure/autoinstrument.py`, `profyle/_run/` | `profyle run`: import hooks that add the middleware when a framework loads |
| `profyle/application/request_trace.py` | `RequestTrace`: traces one request with VizTracer and stores it |
| `profyle/application/requests/` | The HTTP side: request capture, response fingerprints, sending a request again |
| `profyle/infrastructure/sqlite3/` | Trace storage |
| `profyle/infrastructure/console.py` | One line per traced request, built in a separate process |
| `profyle/application/analysis/` | From a raw trace to a digest: `call_tree.py`, `digest.py`, `drilldown.py` (one function), `render.py` (Markdown) |
| `profyle/application/tools/` | The text tools shared by the CLI and the MCP server: traces, replay, doctor |
| `profyle/infrastructure/mcp_server.py` | MCP server (`profyle mcp`) |
| `profyle/main.py` | The `profyle` command |
| `profyle/infrastructure/api/`, `profyle/infrastructure/web/` | The trace viewer (`profyle start`) |
| `profyle/claude/SKILL.md`, `profyle/infrastructure/claude_code.py` | The `fix-slow-endpoint` skill and `profyle init`, which installs it with the MCP server into a project |
| `claude-plugin/` | Claude Code plugin: MCP server config and a copy of the skill |
| `examples/` | One app per framework with an N+1 query, used by the integration tests |
| `tests/unit/` | Test suite, mirroring the package |

## Guidelines

- **Tests:** every change in behavior needs a test. Tracing bugs are often thread or
  Python-version specific, so make the test fail without your fix (see the worker-thread
  tests in `tests/unit/infrastructure/middleware/`).
- **Coverage:** CI requires 100% line and branch coverage (measured on Linux with
  Python 3.11, subprocesses included). Cover new code with a test. Only code that cannot
  run there (Windows-only or Python 3.12+ branches) may be excluded, inline with
  `# pragma: no cover - <reason>`.
- **Python versions:** CI runs 3.10 to 3.13. VizTracer uses `sys.setprofile` before 3.12
  and `sys.monitoring` from 3.12, so tracing changes should be checked on both sides.
- **Dependency floors:** CI also runs the tests with the lowest versions allowed in
  `pyproject.toml` (`uv sync --resolution lowest-direct`). If you need a newer
  dependency feature, raise the floor. To reproduce it locally, note that this command
  also rewrites `uv.lock`: restore it afterwards with `git checkout uv.lock && uv sync`.
- **No overhead in the traced app:** work that is not needed to record a request (for
  example analysis) belongs on the reading side (CLI, MCP server), not in the
  middleware.
- **Privacy:** traces contain source code, arguments and request data. Do not store
  credentials or response bodies, and keep replays local by default.
- **MCP tools and the skill:** if you add or change an MCP tool, update
  `profyle/claude/SKILL.md` (copy it to `claude-plugin/skills/fix-slow-endpoint/SKILL.md`;
  a test checks they match) and the tool table in `README.md`.
  You can try the plugin locally with `claude --plugin-dir ./claude-plugin`.
- **Changelog:** add a line under "Unreleased" in [CHANGELOG.md](CHANGELOG.md) for
  user-visible changes.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make your change with tests, then run `uv run pytest`,
   `uv run ruff check` and `uv run ruff format` on `profyle tests examples`.
3. Open a pull request and fill in the template. CI must be green before merging.

## Releasing (maintainers)

1. Update the version in `pyproject.toml` and move the "Unreleased" changelog entries
   under the new version.
2. Merge to `main`, then create a GitHub release with the tag `vX.Y.Z`.
3. The `Release` workflow checks that the tag matches the version, runs the tests, builds
   and publishes to PyPI through trusted publishing.
