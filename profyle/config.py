"""One configuration for every integration (middlewares, `profyle run`, pytest).

Each setting is resolved, highest priority first, from:

1. environment variables (`PROFYLE_ENABLED`, `PROFYLE_PATTERN`, ...), so a setting can
   always be changed without touching code;
2. arguments given in code (middleware keyword arguments, Django `PROFYLE_*` settings);
3. `[tool.profyle]` in the project's pyproject.toml;
4. defaults.

The source of every value is kept so `profyle doctor` can explain the configuration.
"""

import os
import sys
from dataclasses import dataclass, field, fields
from typing import Any

from profyle.settings import find_project_root

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

TRUE = {"1", "true", "yes", "on"}
FALSE = {"0", "false", "no", "off"}


@dataclass
class ProfyleConfig:
    # Trace requests at all.
    enabled: bool = True
    # Glob matched against the request path, e.g. "/api/*". None traces every path.
    pattern: str | None = None
    # Maximum call stack depth to record; -1 means unlimited.
    max_stack_depth: int = -1
    # Drop function calls shorter than this many microseconds (VizTracer's unit).
    min_duration: float = 0
    # Print a one-line summary of each traced request.
    console: bool = True
    sources: dict[str, str] = field(default_factory=dict, compare=False, repr=False)

    def describe(self) -> list[str]:
        return [
            f"{f.name} = {getattr(self, f.name)!r} ({self.sources.get(f.name, 'default')})"
            for f in fields(self)
            if f.name != "sources"
        ]


def load_config(**code: Any) -> ProfyleConfig:
    """Resolve the configuration. `code` holds values passed in code; None means unset."""
    config = ProfyleConfig()
    config.sources = {}
    layers = [
        ("pyproject.toml", _pyproject_values()),
        ("code", {k: v for k, v in code.items() if v is not None}),
        ("environment", _environment_values()),
    ]
    for source, values in layers:
        for name, raw in values.items():
            if not hasattr(config, name) or name == "sources":
                continue
            setattr(config, name, _coerce(name, raw, source))
            config.sources[name] = source
    return config


ENV_NAMES = {
    "enabled": "PROFYLE_ENABLED",
    "pattern": "PROFYLE_PATTERN",
    "max_stack_depth": "PROFYLE_MAX_STACK_DEPTH",
    "min_duration": "PROFYLE_MIN_DURATION",
    "console": "PROFYLE_CONSOLE",
}


def _environment_values() -> dict[str, str]:
    return {name: os.environ[env] for name, env in ENV_NAMES.items() if os.environ.get(env)}


def _pyproject_values() -> dict[str, Any]:
    root = os.getenv("PROFYLE_PROJECT_DIR") or find_project_root(os.getcwd())
    path = os.path.join(root, "pyproject.toml")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    section = data.get("tool", {}).get("profyle", {})
    return {key.replace("-", "_"): value for key, value in section.items()}


def _coerce(name: str, value: Any, source: str) -> Any:
    kind = {f.name: f.type for f in fields(ProfyleConfig)}[name]
    try:
        if kind is bool or kind == "bool":
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in TRUE:
                return True
            if text in FALSE:
                return False
            raise ValueError(value)
        if kind is int or kind == "int":
            return int(value)
        if kind is float or kind == "float":
            return float(value)
        return None if value in ("", None) else str(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid Profyle setting {name}={value!r} (from {source})") from error
