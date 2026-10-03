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
$ uv run ruff check profyle tests
```

Optionally, install the git hooks so lint runs on every commit:

```console
$ uvx pre-commit install
```

To try your changes against a real app, install your checkout into the app's
environment (`pip install -e /path/to/profyle[mcp]`), add `ProfyleMiddleware`, make a
request and run `profyle doctor` and `profyle analyze` from the app's directory.

## Project layout

| Path | What lives there |
|---|---|
| `profyle/infrastructure/middleware/` | FastAPI/Starlette (ASGI), Flask (WSGI) and Django middlewares; `threadpool.py` makes worker threads traceable on Python < 3.12 |
| `profyle/application/analysis/` | Trace digest (`digest.py`) and the text tools shared by the CLI and the MCP server (`toolkit.py`) |
| `profyle/application/` | Request capture, response fingerprints and replay |
| `profyle/infrastructure/mcp_server.py` | MCP server (`profyle mcp`) |
| `profyle/infrastructure/sqlite3/` | Trace storage |
| `claude-plugin/` | Claude Code plugin: MCP server config and the `fix-slow-endpoint` skill |
| `tests/unit/` | Test suite |

## Guidelines

- **Tests:** every change in behavior needs a test. Tracing bugs are often thread or
  Python-version specific, so make the test fail without your fix (see the worker-thread
  tests in `tests/unit/infrastructure/middleware/`).
- **Python versions:** CI runs 3.10 to 3.13. VizTracer uses `sys.setprofile` before 3.12
  and `sys.monitoring` from 3.12, so tracing changes should be checked on both sides.
- **Dependency floors:** CI also runs the tests with the lowest versions allowed in
  `pyproject.toml` (`uv sync --resolution lowest-direct`). If you need a newer
  dependency feature, raise the floor.
- **No overhead in the traced app:** work that is not needed to record a request (for
  example analysis) belongs on the reading side (CLI, MCP server), not in the
  middleware.
- **Privacy:** traces contain source code, arguments and request data. Do not store
  credentials or response bodies, and keep replays local by default.
- **MCP tools and the skill:** if you add or change an MCP tool, update
  `claude-plugin/skills/fix-slow-endpoint/SKILL.md` and the tool table in `README.md`.
  You can try the plugin locally with `claude --plugin-dir ./claude-plugin`.
- **Changelog:** add a line under "Unreleased" in [CHANGELOG.md](CHANGELOG.md) for
  user-visible changes.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make your change with tests, then run `uv run pytest` and
   `uv run ruff check profyle tests`.
3. Open a pull request and fill in the template. CI must be green before merging.

## Releasing (maintainers)

1. Update the version in `pyproject.toml` and move the "Unreleased" changelog entries
   under the new version.
2. Merge to `main`, then create a GitHub release with the tag `vX.Y.Z`.
3. The `Release` workflow checks that the tag matches the version, runs the tests, builds
   and publishes to PyPI through trusted publishing.
