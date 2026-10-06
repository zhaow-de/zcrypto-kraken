from __future__ import annotations

import contextlib
import io
import sys
import types
import urllib.error
from collections.abc import Callable, Mapping
from pathlib import Path

SHARED = "zcrypto_selfcheck"


# Never imported by path: a bytecode cache in a role's files/ names the checkout, whose `kraken` test_deploy_log_audit.py flags.
def _exec(path: Path, module: types.ModuleType) -> types.ModuleType:
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    return module


def load(script_path: Path, shared_path: Path | None = None) -> types.ModuleType:
    if shared_path is None:
        return _exec(script_path, types.ModuleType(script_path.stem.replace("-", "_")))
    # Registered only while the script's own `import` runs, so no later import of the name binds this copy.
    before = sys.modules.get(SHARED)
    sys.modules[SHARED] = types.ModuleType(SHARED)
    try:
        _exec(shared_path, sys.modules[SHARED])
        return _exec(script_path, types.ModuleType(script_path.stem.replace("-", "_")))
    finally:
        if before is None:
            del sys.modules[SHARED]
        else:
            sys.modules[SHARED] = before


# A hand run of an installed script, as `python -c HAND_RUN <script> <installed dir> <copy dir>`. The module's install
# directory exists on the node alone, so the run seeds that path entry with a finder over a copy of the module. The
# caller strips PYTHONPATH and runs from a directory without the module, so the script's first import fails and its
# fallback's import is the one that finds it.
HAND_RUN = """
import runpy, sys
from importlib.machinery import FileFinder, SourceFileLoader
script, installed, copy = sys.argv[1:]
sys.path_importer_cache[installed] = FileFinder(copy, (SourceFileLoader, [".py"]))
runpy.run_path(script, run_name="__main__")
"""


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def run(
    module: types.ModuleType,
    env: Mapping[str, str],
    bodies: Mapping[str, str | Callable],
    *,
    broken=(),
    refused: tuple[str, str] | None = None,
    now: float | None = None,
) -> tuple[int, list[str], str]:
    """`bodies`, `broken` and `refused[0]` are keyed by the URL without its query; `now` reaches `main` only when given,
    since only a script whose probe reads a clock takes one."""
    asked: list[str] = []

    def opener(request, timeout):
        url = request.full_url
        asked.append(url)
        base = url.split("?")[0]
        if base in broken:
            raise urllib.error.URLError("connection refused")
        if refused is not None and base == refused[0]:
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, io.BytesIO(refused[1].encode()))
        body = bodies[base]
        return Response((body(request) if callable(body) else body).encode())

    clock = {} if now is None else {"now": lambda: now}
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = module.main(env, opener=opener, **clock)
    return rc, asked, out.getvalue().strip()
