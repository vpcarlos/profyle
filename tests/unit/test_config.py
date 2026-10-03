import pytest

from profyle.config import load_config


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    for name in ("ENABLED", "PATTERN", "MAX_STACK_DEPTH", "MIN_DURATION", "CONSOLE"):
        monkeypatch.delenv(f"PROFYLE_{name}", raising=False)
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
