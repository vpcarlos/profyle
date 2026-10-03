import pytest

from profyle.config import ENV_NAMES, load_config


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    for env in ENV_NAMES.values():
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("PROFYLE_PROJECT_DIR", str(tmp_path))
    return tmp_path


def test_defaults():
    config = load_config()

    assert (config.enabled, config.pattern, config.max_stack_depth) == (True, None, -1)
    assert config.sources == {}


def test_environment_beats_code_beats_pyproject(project, monkeypatch):
    (project / "pyproject.toml").write_text(
        '[tool.profyle]\npattern = "/from-pyproject*"\nmax-stack-depth = 5\nconsole = false\n'
    )
    monkeypatch.setenv("PROFYLE_PATTERN", "/from-env*")

    config = load_config(pattern="/from-code*", max_stack_depth=10)

    assert config.pattern == "/from-env*"
    assert config.max_stack_depth == 10
    assert config.console is False
    assert config.sources == {
        "pattern": "environment",
        "max_stack_depth": "code",
        "console": "pyproject.toml",
    }
    assert "pattern = '/from-env*' (environment)" in config.describe()


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "False"])
def test_environment_can_disable(monkeypatch, value):
    monkeypatch.setenv("PROFYLE_ENABLED", value)

    assert load_config(enabled=True).enabled is False


def test_invalid_values_name_the_setting(monkeypatch):
    monkeypatch.setenv("PROFYLE_MAX_STACK_DEPTH", "deep")

    with pytest.raises(ValueError, match="max_stack_depth='deep'.*environment"):
        load_config()


def test_unknown_and_invalid_pyproject_settings(project):
    (project / "pyproject.toml").write_text('[tool.profyle]\nunknown = 1\nenabled = "yes"\n')
    config = load_config()
    assert config.enabled is True and config.sources == {"enabled": "pyproject.toml"}

    (project / "pyproject.toml").write_text("[tool.profyle\nbroken")
    assert load_config().sources == {}


def test_boolean_values(monkeypatch):
    monkeypatch.setenv("PROFYLE_CONSOLE", "on")
    assert load_config(console=False).console is True

    monkeypatch.setenv("PROFYLE_CONSOLE", "maybe")
    with pytest.raises(ValueError, match="console='maybe'"):
        load_config()


def test_credentials_are_redacted_unless_capture_secrets_is_on(project, monkeypatch):
    from flask import Flask

    from profyle.wsgi import ProfyleMiddleware
    from tests.unit.repository import InMemoryTraceRepository

    app = Flask("secrets")
    app.get("/me")(lambda: "ok")
    repo = InMemoryTraceRepository()
    app.wsgi_app = ProfyleMiddleware(app.wsgi_app, trace_repo=repo, console=False)
    app.test_client().get("/me", headers={"Authorization": "Bearer secret"}).get_data()

    (project / "pyproject.toml").write_text("[tool.profyle]\ncapture-secrets = true\n")
    app.wsgi_app = ProfyleMiddleware(app.wsgi_app.app, trace_repo=repo, console=False)
    app.test_client().get("/me", headers={"Authorization": "Bearer secret"}).get_data()

    redacted, kept = (t.request.headers["authorization"] for t in repo.traces)
    assert (redacted, kept) == ("[redacted]", "Bearer secret")


def test_replays_to_remote_hosts_only_when_allowed(project, monkeypatch):
    from profyle.application import tools
    from profyle.domain.trace import RecordedRequest
    from tests.unit.repository import InMemoryTraceRepository, store_trace

    repo = InMemoryTraceRepository()
    request = RecordedRequest(method="GET", path="/", base_url="https://api.example.invalid")
    store_trace(raw_trace={"traceEvents": []}, name="GET /", repo=repo, request=request)

    assert "only local hosts are allowed" in tools.replay_trace(repo, 1)
    assert "Replay: replay_allow_remote = False (default)." in tools.doctor(repo)

    monkeypatch.setenv("PROFYLE_REPLAY_ALLOW_REMOTE", "true")
    result = tools.replay_trace(repo, 1, wait_seconds=0)
    assert "Could not reach the app" in result
    assert "replay_allow_remote = True (environment)" in tools.doctor(repo)
