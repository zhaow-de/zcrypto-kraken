import pytest

import cli.engine.cycle as cycle


@pytest.fixture(autouse=True)
def _reset_metrics_sink():
    """`cycle._metrics_sink` is module-level global state -- leaking a test's sink into the next
    test (or into an unrelated test file sharing this process) would be a real isolation bug of
    its own. Reset it unconditionally after every test in the whole suite: a `run()` test that
    installs a sink and never resets it leaves a live closure behind -- holding a real
    `ExecutionGate` pointed at a `tmp_path` that no longer exists -- for every later test in the
    same pytest process to fire. `cycle.py`'s own sink guard swallows a raising sink by design, so
    the leak is silent: live HTTPS calls to api.kraken.com from the unit suite, plus `exec-*.json`
    written into directories that were deleted with the test that created them.
    """
    yield
    cycle.set_metrics_sink(None)
