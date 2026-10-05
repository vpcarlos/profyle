import importlib.machinery
import os
import runpy
import sys

from profyle.settings import settings

BOOTSTRAP = settings.get_path("_run", "sitecustomize.py")


def test_explains_when_profyle_is_not_importable(monkeypatch, capsys):
    monkeypatch.setenv("PROFYLE_RUN", "1")
    monkeypatch.setitem(sys.modules, "profyle.infrastructure.autoinstrument", None)
    monkeypatch.setattr(importlib.machinery.PathFinder, "find_spec", lambda *a, **k: None)

    runpy.run_path(BOOTSTRAP)

    assert "tracing disabled: Profyle is not installed" in capsys.readouterr().err


def test_does_nothing_outside_profyle_run(monkeypatch):
    monkeypatch.delenv("PROFYLE_RUN", raising=False)
    monkeypatch.setattr(importlib.machinery.PathFinder, "find_spec", lambda *a, **k: None)

    runpy.run_path(BOOTSTRAP)


def test_runs_the_environments_own_sitecustomize_too(tmp_path, monkeypatch):
    monkeypatch.delenv("PROFYLE_RUN", raising=False)
    monkeypatch.delenv("PROFYLE_TEST_CHAINED", raising=False)
    (tmp_path / "sitecustomize.py").write_text(
        "import os\nos.environ['PROFYLE_TEST_CHAINED'] = '1'\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    runpy.run_path(BOOTSTRAP)

    assert os.environ.get("PROFYLE_TEST_CHAINED") == "1"
