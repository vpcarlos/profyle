"""Imported at interpreter start-up in processes launched by `profyle run`.

`profyle run` puts this directory first on PYTHONPATH, so Python imports this module
automatically (also in reloader and worker child processes). It enables Profyle's
zero-code tracing, then runs the environment's own sitecustomize, if there is one.
"""

import importlib.machinery
import importlib.util
import os
import sys


def _enable_profyle() -> None:
    if os.environ.get("PROFYLE_RUN") != "1":
        return
    try:
        from profyle.infrastructure.autoinstrument import install
    except ImportError as error:
        sys.stderr.write(
            f"profyle ▸ tracing disabled: Profyle is not installed for {sys.executable} "
            f"({error})\n"
        )
        return
    install()


def _chain_next_sitecustomize() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    paths = [p for p in sys.path if os.path.abspath(p or os.curdir) != here]
    spec = importlib.machinery.PathFinder.find_spec("sitecustomize", paths)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


_enable_profyle()
_chain_next_sitecustomize()
