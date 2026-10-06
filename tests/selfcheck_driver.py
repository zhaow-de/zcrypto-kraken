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
    now: float,
) -> tuple[int, list[str], str]:
    """`bodies`, `broken` and `refused[0]` are keyed by the URL without its query."""
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

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = module.main(env, opener=opener, now=lambda: now)
    return rc, asked, out.getvalue().strip()
