"""Zero-code tracing for `profyle run`.

`profyle run <command>` starts the command with this package's `_run/sitecustomize.py`
on PYTHONPATH; Python imports it at start-up (also in uvicorn's --reload workers) and it
calls install(). install() hooks the import of supported frameworks and adds the Profyle
middleware to the app when the framework is loaded:

- FastAPI / Starlette: around the middleware stack the app builds;
- Flask: around `app.wsgi_app`;
- Django (WSGI and ASGI): first in MIDDLEWARE;
- Tornado (its own server or gunicorn's tornado worker): around each request handler;
- any other ASGI app served by uvicorn (Litestar, Quart, plain ASGI...): around the app.

An app that already uses a Profyle middleware explicitly keeps it (with its own
settings) and is not wrapped again.
"""

import importlib.abc
import sys
from types import ModuleType

from profyle.infrastructure.middleware.base import PROFYLE_RUN

DJANGO_MIDDLEWARE = "profyle.infrastructure.middleware.django.AutoProfyleMiddleware"

_installed = False
_announced: set[str] = set()


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    sys.meta_path.insert(0, _PostImportHook())
    for name, patch in PATCHES.items():
        if name in sys.modules:
            patch(sys.modules[name])


def _announce(framework: str, integration) -> None:
    """Record the app for `profyle doctor`. The start-up message itself is printed once
    by `profyle run` (here it would repeat in reloader processes)."""
    integration.register()


# --- FastAPI / Starlette -----------------------------------------------------------


def _patch_starlette(module: ModuleType) -> None:
    # Patch __call__, the entry point of every Starlette-based app: FastAPI overrides
    # build_middleware_stack, so wrapping that would miss FastAPI apps.
    from profyle.infrastructure.middleware.asgi import ProfyleMiddleware

    starlette = module.Starlette
    original = starlette.__call__

    async def __call__(self, scope, receive, send):
        wrapper = self.__dict__.get("_profyle_wrapper")
        if wrapper is None:
            wrapper = _starlette_wrapper(self, original, ProfyleMiddleware)
            self.__dict__["_profyle_wrapper"] = wrapper
        if wrapper is False:
            await original(self, scope, receive, send)
        else:
            await wrapper(scope, receive, send)

    starlette.__call__ = __call__


def _starlette_wrapper(app, original, middleware_class):
    explicit = any(
        isinstance(getattr(m, "cls", None), type) and issubclass(m.cls, middleware_class)
        for m in getattr(app, "user_middleware", [])
    )
    if explicit:
        return False

    async def call_app(scope, receive, send):
        await original(app, scope, receive, send)

    framework = "FastAPI" if type(app).__module__.startswith("fastapi") else "Starlette"
    wrapper = middleware_class(call_app, framework=framework, mode=PROFYLE_RUN)
    _announce(framework, wrapper.integration)
    return wrapper


# --- Flask --------------------------------------------------------------------------


def _patch_flask(module: ModuleType) -> None:
    from profyle.infrastructure.middleware.wsgi import ProfyleMiddleware

    flask = module.Flask
    original = flask.__init__

    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        # An explicit `app.wsgi_app = ProfyleMiddleware(...)` added later wraps this one
        # and wins: the inner middleware skips requests already traced.
        self.wsgi_app = ProfyleMiddleware(self.wsgi_app, framework="Flask", mode=PROFYLE_RUN)
        _announce("Flask", self.wsgi_app.integration)

    flask.__init__ = __init__


# --- Django -------------------------------------------------------------------------


def _patch_django(module: ModuleType) -> None:
    handler = module.BaseHandler
    original = handler.load_middleware

    def load_middleware(self, *args, **kwargs):
        from django.conf import settings

        middleware = list(settings.MIDDLEWARE)
        if not any(path.startswith("profyle.") for path in middleware):
            settings.MIDDLEWARE = [DJANGO_MIDDLEWARE, *middleware]
        return original(self, *args, **kwargs)

    handler.load_middleware = load_middleware


# --- Any ASGI app served by uvicorn -------------------------------------------------


def _patch_uvicorn(module: ModuleType) -> None:
    from profyle.infrastructure.middleware.asgi import ProfyleMiddleware

    config = module.Config
    original = config.load

    def load(self):
        # The app object, to tell which framework it is. With --factory (or if the import
        # fails) it is unknown until uvicorn builds it, so it is treated as plain ASGI.
        app = self.app
        if isinstance(app, str):
            app = None if self.factory else _import_or_none(module, app)
        original(self)
        if self.loaded and not _handled_by_framework_hook(app):
            name = _app_name(app)
            self.loaded_app = ProfyleMiddleware(
                self.loaded_app, framework=name, mode=PROFYLE_RUN
            )
            _announce(name, self.loaded_app.integration)

    config.load = load


def _import_or_none(module: ModuleType, path: str):
    try:
        return module.import_from_string(path)
    except Exception:
        return None


def _app_name(app) -> str:
    """"Litestar", "Quart"... or "ASGI" for plain functions and factories."""
    if app is None:
        return "ASGI"
    cls = app if isinstance(app, type) else type(app)
    return "ASGI" if cls.__name__ in ("function", "method", "partial") else cls.__name__


def _handled_by_framework_hook(app) -> bool:
    """Apps that the framework hooks above already trace (or explicitly use Profyle)."""
    from profyle.infrastructure.middleware.asgi import ProfyleMiddleware

    if app is None:
        return False
    if isinstance(app, ProfyleMiddleware):
        return True
    known = [
        ("starlette.applications", "Starlette"),
        ("django.core.handlers.asgi", "ASGIHandler"),
        ("flask.app", "Flask"),
    ]
    for module_name, class_name in known:
        module = sys.modules.get(module_name)
        if module is not None and isinstance(app, getattr(module, class_name)):
            return True
    return False


# --- Tornado ------------------------------------------------------------------------


def _patch_tornado(module: ModuleType) -> None:
    from profyle.infrastructure.middleware.tornado import enable_auto

    enable_auto()


PATCHES = {
    "tornado.web": _patch_tornado,
    "starlette.applications": _patch_starlette,
    "flask.app": _patch_flask,
    "django.core.handlers.base": _patch_django,
    "uvicorn.config": _patch_uvicorn,
}


# --- Import hook --------------------------------------------------------------------


class _PostImportHook(importlib.abc.MetaPathFinder):
    """Patches a module right after it is executed for the first time."""

    def find_spec(self, fullname, path, target=None):
        if fullname not in PATCHES:
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(fullname, path, target)
            if spec is not None:
                break
        else:
            return None
        if spec.loader is not None and hasattr(spec.loader, "exec_module"):
            spec.loader = _PatchingLoader(spec.loader, PATCHES[fullname])
        return spec


class _PatchingLoader(importlib.abc.Loader):
    def __init__(self, loader, patch):
        self._loader = loader
        self._patch = patch

    def create_module(self, spec):
        return self._loader.create_module(spec)

    def exec_module(self, module):
        self._loader.exec_module(module)
        try:
            self._patch(module)
        except Exception as error:  # never break the user's app
            from profyle.infrastructure.console import say

            say(f"could not enable tracing for {module.__name__}: {error}")

    def __getattr__(self, name):
        return getattr(self._loader, name)
