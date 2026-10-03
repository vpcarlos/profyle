"""`profyle run` hooks, applied to stand-in framework modules.

install() patches the real frameworks process-wide, so it only runs in a subprocess;
the patch functions are exercised here against fake modules instead.
"""

import asyncio
import importlib
import subprocess
import sys
import types
from types import SimpleNamespace

import pytest

from profyle.asgi import ProfyleMiddleware as ASGIMiddleware
from profyle.infrastructure import autoinstrument
from profyle.wsgi import ProfyleMiddleware as WSGIMiddleware


@pytest.fixture(autouse=True)
def isolated(project_db, monkeypatch):
    monkeypatch.setenv("PROFYLE_CONSOLE", "false")
    return project_db


def fake_module(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    return module


async def call(app):
    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        pass

    scope = {"type": "http", "method": "GET", "path": "/ping", "headers": [],
             "query_string": b""}
    await app(scope, receive, send)


def test_starlette_apps_are_wrapped_unless_they_use_profyle(isolated):
    calls = []

    class Starlette:
        def __init__(self, user_middleware=()):
            self.user_middleware = list(user_middleware)

        async def __call__(self, scope, receive, send):
            calls.append(self)

    autoinstrument._patch_starlette(fake_module("starlette.applications", Starlette=Starlette))
    plain, explicit = Starlette(), Starlette([SimpleNamespace(cls=ASGIMiddleware)])

    for app in (plain, explicit, plain):
        asyncio.run(call(app))

    assert calls == [plain, explicit, plain]
    assert plain._profyle_wrapper.integration.framework == "Starlette"
    assert explicit._profyle_wrapper is False
    assert [t.name for t in isolated.get_all_traces()].count("GET /ping") == 2
    assert isolated.get_runtime()["mode"] == "profyle run"


def test_flask_apps_get_the_wsgi_middleware():
    class Flask:
        def __init__(self):
            self.wsgi_app = lambda environ, start_response: [b"ok"]

    autoinstrument._patch_flask(fake_module("flask.app", Flask=Flask))

    assert isinstance(Flask().wsgi_app, WSGIMiddleware)


def test_django_middleware_is_inserted_once():
    import os

    from django.conf import settings
    from django.test import override_settings

    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE", "tests.unit.infrastructure.middleware.django.settings"
    )

    class BaseHandler:
        def load_middleware(self):
            return list(settings.MIDDLEWARE)

    autoinstrument._patch_django(fake_module("django.core.handlers.base",
                                             BaseHandler=BaseHandler))
    with override_settings(MIDDLEWARE=["app.Middleware"]):
        assert BaseHandler().load_middleware() == [autoinstrument.DJANGO_MIDDLEWARE,
                                                   "app.Middleware"]
    with override_settings(MIDDLEWARE=["profyle.django.ProfyleMiddleware"]):
        assert BaseHandler().load_middleware() == ["profyle.django.ProfyleMiddleware"]


class Litestar:
    async def __call__(self, scope, receive, send):
        pass


def make_uvicorn():
    apps = {"main:app": Litestar()}

    def import_from_string(path):
        return apps[path]

    class Config:
        def __init__(self, app, factory=False):
            self.app, self.factory, self.loaded = app, factory, False

        def load(self):
            self.loaded = True
            self.loaded_app = apps["main:app"] if isinstance(self.app, str) else self.app

    module = fake_module("uvicorn.config", Config=Config, import_from_string=import_from_string)
    autoinstrument._patch_uvicorn(module)
    return Config


@pytest.mark.parametrize(
    ("app", "factory", "framework"),
    [("main:app", False, "Litestar"), ("main:create_app", True, "ASGI"),
     ("missing:app", False, "ASGI")],
)
def test_uvicorn_wraps_other_asgi_frameworks(app, factory, framework):
    config = make_uvicorn()(app, factory)
    config.load()

    assert isinstance(config.loaded_app, ASGIMiddleware)
    assert config.loaded_app.integration.framework == framework


def test_uvicorn_leaves_known_or_explicit_apps_alone():
    explicit = ASGIMiddleware(Litestar())
    config = make_uvicorn()(explicit)
    config.load()

    assert config.loaded_app is explicit


def test_app_names():
    assert autoinstrument._app_name(None) == "ASGI"
    assert autoinstrument._app_name(lambda scope, receive, send: None) == "ASGI"
    assert autoinstrument._app_name(Litestar) == "Litestar"


def test_import_hook_patches_modules_after_they_load(tmp_path, monkeypatch, capsys):
    (tmp_path / "profyle_fake_framework.py").write_text("VALUE = 1\n")
    (tmp_path / "profyle_fake_broken.py").write_text("VALUE = 2\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    patched = []

    def broken(module):
        raise RuntimeError("unexpected framework version")

    monkeypatch.setattr(autoinstrument, "PATCHES", {
        "profyle_fake_framework": patched.append,
        "profyle_fake_broken": broken,
        "profyle_fake_missing": patched.append,
    })
    hook = autoinstrument._PostImportHook()
    monkeypatch.setattr(sys, "meta_path", [hook, *sys.meta_path])

    module = importlib.import_module("profyle_fake_framework")
    assert patched == [module]
    assert module.__spec__.loader.name == "profyle_fake_framework"  # delegated attribute

    assert importlib.import_module("profyle_fake_broken").VALUE == 2
    assert "could not enable tracing for profyle_fake_broken" in capsys.readouterr().err

    assert hook.find_spec("profyle_fake_missing", None) is None
    assert hook.find_spec("json", None) is None  # not a framework module


def test_import_hook_keeps_specs_without_an_executable_loader(monkeypatch):
    spec = importlib.machinery.ModuleSpec("profyle_fake_namespace", loader=None)
    finder = SimpleNamespace(find_spec=lambda name, path, target=None: spec)
    hook = autoinstrument._PostImportHook()
    monkeypatch.setattr(autoinstrument, "PATCHES", {"profyle_fake_namespace": print})
    monkeypatch.setattr(sys, "meta_path", [hook, finder])

    assert hook.find_spec("profyle_fake_namespace", None) is spec


def test_install_once_and_patch_frameworks_already_imported():
    code = (
        "import sys, starlette.applications as s\n"
        "original = s.Starlette.__call__\n"
        "from profyle.infrastructure import autoinstrument as a\n"
        "a.install(); a.install()\n"
        "hooks = sum(isinstance(f, a._PostImportHook) for f in sys.meta_path)\n"
        "print(hooks, s.Starlette.__call__ is not original)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            check=True)

    assert result.stdout.split() == ["1", "True"]
