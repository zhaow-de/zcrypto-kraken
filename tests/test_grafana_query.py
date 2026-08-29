"""TDD for `infra/scripts/grafana-query.py` — the vaulted Cloud read-back the rollout gate needs.

`continuity.py`'s test file sets the precedent: these are standalone scripts, not package modules,
so they load via `importlib.util.spec_from_file_location`.

Every test here pins something that actually went wrong during the 2026-07-28 capture rollout, when
the decrypt was improvised from prose and took two failed attempts before it worked.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "grafana-query.py"
_spec = importlib.util.spec_from_file_location("grafana_query", _SCRIPT)
gq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gq)

TOKEN = "glsa_TOTALLY_NOT_A_REAL_TOKEN_0123456789"


def test_a_result_shape_without_metric_and_value_does_not_drop_the_later_expressions(monkeypatch, capsys):
    """A scalar (`1`) or a range selector (`up[1m]`) returns a shape with no `metric`/`value`. When
    the render sat outside the try, that raised past the handler and every later expression was
    silently never queried -- while the commit claimed the opposite."""
    monkeypatch.setattr(gq, "vault_var", lambda name: TOKEN)

    def shapes(expr, token):
        if expr == "1":
            return [1.0]  # resultType: scalar -- not subscriptable by "metric"
        return [{"metric": {"host": "zcrypto"}, "value": [0, "1"]}]

    monkeypatch.setattr(gq, "query", shapes)

    rc = gq.main(["1", 'up{job="capture_app"}'])
    out = capsys.readouterr().out

    assert rc == 1, "the malformed shape is a failure, not a pass"
    assert "ERROR" in out
    assert "host=zcrypto" in out, "the expression after the bad one still ran"


def test_the_token_never_reaches_stdout(monkeypatch, capsys):
    """It is a live credential. It may live in a local and in a request header, and nowhere else --
    not stdout, not argv (where `ps` would show it), not a file."""
    monkeypatch.setattr(gq, "vault_var", lambda name: TOKEN)
    monkeypatch.setattr(gq, "query", lambda expr, token, **kw: [{"metric": {"host": "zcrypto"}, "value": [0, "1"]}])

    rc = gq.main(['up{job="capture_app"}'])
    out = capsys.readouterr()

    assert rc == 0
    assert TOKEN not in out.out and TOKEN not in out.err
    assert "host=zcrypto" in out.out and "= 1" in out.out


def test_an_empty_result_is_reported_as_absent_never_as_a_zero(monkeypatch, capsys):
    """A gate reading `up == 1` must be able to tell "the series says 0" from "there is no series".
    They fail differently: one is a down host, the other is a scrape or keep-list that never
    admitted the metric at all."""
    monkeypatch.setattr(gq, "vault_var", lambda name: TOKEN)
    monkeypatch.setattr(gq, "query", lambda expr, token, **kw: [])

    rc = gq.main(["hc_check_up"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "(no series)" in out
    assert " = 0" not in out


def test_one_failing_expression_does_not_hide_the_others(monkeypatch, capsys):
    """The gate asks several questions in one run; a typo in the first must not silently drop the
    rest, and the run must still exit non-zero so nothing reads it as a pass."""
    monkeypatch.setattr(gq, "vault_var", lambda name: TOKEN)

    def flaky(expr, token, **kw):
        if expr == "bad{":
            raise ValueError("parse error")
        return [{"metric": {}, "value": [0, "1"]}]

    monkeypatch.setattr(gq, "query", flaky)

    rc = gq.main(["bad{", "hc_check_up"])
    out = capsys.readouterr().out

    assert rc == 1, "a failed query is not a pass"
    assert "ERROR ValueError" in out
    assert "hc_check_up" in out and "= 1" in out


def test_no_arguments_is_a_usage_error_not_a_silent_success(capsys):
    rc = gq.main([])

    assert rc == 2
    assert "usage:" in capsys.readouterr().out
