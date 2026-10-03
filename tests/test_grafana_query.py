"""`infra/scripts/grafana-query.py` — the vaulted Cloud read-back the rollout gate needs."""

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
_REAL_VAULT_VAR = gq.grafana_auth.vault_var


def test_a_result_shape_without_metric_and_value_does_not_drop_the_later_expressions(monkeypatch, capsys):
    """A shape with no `metric`/`value` -- a scalar, a range selector -- fails the run without
    dropping the expressions after it."""
    monkeypatch.setattr(gq.grafana_auth, "vault_var", lambda name, vault_file: TOKEN)

    def shapes(expr, token, **kw):
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
    """A live credential: it reaches neither stdout nor stderr, while the query still renders."""
    monkeypatch.setattr(gq.grafana_auth, "vault_var", lambda name, vault_file: TOKEN)
    monkeypatch.setattr(gq, "query", lambda expr, token, **kw: [{"metric": {"host": "zcrypto"}, "value": [0, "1"]}])

    rc = gq.main(['up{job="capture_app"}'])
    out = capsys.readouterr()

    assert rc == 0
    assert TOKEN not in out.out and TOKEN not in out.err
    assert "host=zcrypto" in out.out and "= 1" in out.out


def test_an_empty_result_is_reported_as_absent_never_as_a_zero(monkeypatch, capsys):
    """A gate reading `up == 1` must tell "the series says 0" -- a down host -- from "there is no
    series", a scrape or keep-list that never admitted the metric."""
    monkeypatch.setattr(gq.grafana_auth, "vault_var", lambda name, vault_file: TOKEN)
    monkeypatch.setattr(gq, "query", lambda expr, token, **kw: [])

    rc = gq.main(["hc_check_up"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "(no series)" in out
    assert " = 0" not in out


def test_one_failing_expression_does_not_hide_the_others(monkeypatch, capsys):
    """The gate asks several questions in one run; a typo in the first must not silently drop the
    rest, and the run must still exit non-zero so nothing reads it as a pass."""
    monkeypatch.setattr(gq.grafana_auth, "vault_var", lambda name, vault_file: TOKEN)

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


def test_loki_routes_the_query_through_the_loki_datasource_proxy_and_is_not_an_expression(monkeypatch, capsys):
    monkeypatch.setattr(gq.grafana_auth, "vault_var", lambda name, vault_file: TOKEN)
    seen = []
    monkeypatch.setattr(
        gq,
        "query",
        lambda expr, token, loki=False: seen.append((expr, loki)) or [{"metric": {"host": "zcrypto"}, "value": [0, "1"]}],
    )

    rc = gq.main(["--loki", 'count_over_time({host="zcrypto"}[6h])'])

    assert rc == 0
    assert seen == [('count_over_time({host="zcrypto"}[6h])', True)]
    assert "--loki" not in capsys.readouterr().out


def test_query_sends_the_loki_route_and_the_bearer_as_a_header(monkeypatch):
    seen = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"data": {"result": []}}'

    def urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        return _Response()

    monkeypatch.setattr(gq.urllib.request, "urlopen", urlopen)

    assert gq.query("x", TOKEN, loki=True) == []
    assert "/uid/grafanacloud-logs/loki/api/v1/query?" in seen["url"]
    assert seen["auth"] == f"Bearer {TOKEN}"
    gq.query("x", TOKEN)
    assert "/uid/grafanacloud-prom/api/v1/query?" in seen["url"]


# --- one tree, two stacks: the stack is named, and the default is the one that pages ---------------
class _Recorded:
    def __init__(self, monkeypatch):
        self.urls: list[str] = []
        self.vault: list[tuple[str, str]] = []
        monkeypatch.setattr(gq, "GRAFANA_URL", gq.GRAFANA_URL)  # main rebinds it; this puts it back
        monkeypatch.setattr(gq.grafana_auth, "vault_var", lambda name, vault_file: self.vault.append((name, vault_file)) or TOKEN)
        monkeypatch.setattr(gq.urllib.request, "urlopen", self._urlopen)

    def _urlopen(self, request, timeout):
        self.urls.append(request.full_url)

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b'{"data": {"result": []}}'

        return _Response()


def test_no_stack_named_reads_grafana_cloud_with_its_token(monkeypatch, capsys):
    seen = _Recorded(monkeypatch)
    assert gq.main(["up"]) == 0
    assert seen.vault == [("grafana_sa_token", gq.grafana_auth.VAULT_FILE)]
    assert seen.urls == ["https://zcrypto2026.grafana.net/api/datasources/proxy/uid/grafanacloud-prom/api/v1/query?query=up"]


def test_the_mon_stack_is_read_at_its_own_url_with_its_own_token(monkeypatch, capsys):
    seen = _Recorded(monkeypatch)
    assert gq.main(["--stack", "mon", "--loki", "up"]) == 0
    mon = gq.grafana_auth.STACKS["mon"]
    assert seen.vault == [(mon.token_var, mon.vault_file)]
    assert seen.urls == ["https://zcrypto-mon.zhaow.me/api/datasources/proxy/uid/grafanacloud-logs/loki/api/v1/query?query=up"]
    assert "--stack" not in capsys.readouterr().out, "the flag and its value are not expressions"


def test_a_missing_token_cache_is_one_stderr_line_naming_the_stack_and_the_converge_not_a_traceback(monkeypatch, capsys, tmp_path):
    import ansible.parsing.vault as v

    seen = _Recorded(monkeypatch)
    monkeypatch.setattr(gq.grafana_auth, "vault_var", _REAL_VAULT_VAR)  # the real read, over a file that is not there
    monkeypatch.setattr(gq.grafana_auth, "vault_password", lambda: b"pw")
    monkeypatch.setattr(gq.grafana_auth, "_CONTEXT_READY", False)
    monkeypatch.setattr(v.VaultSecretsContext, "initialize", classmethod(lambda cls, ctx: None))
    mon = gq.grafana_auth.STACKS["mon"]
    missing = str(tmp_path / ".config" / "zcrypto" / "grafana-mon.vault.yml")
    monkeypatch.setitem(gq.grafana_auth.STACKS, "mon", mon._replace(vault_file=missing))

    with pytest.raises(SystemExit) as refused:
        gq.main(["--stack", "mon", 'up{host="zcrypto-mon"}'])
    out = capsys.readouterr()

    assert refused.value.code == 1
    assert seen.urls == [], "nothing was queried without a token"
    assert "Traceback" not in out.err and "AnsibleFileNotFound" not in out.err
    assert out.err.count("\n") == 1
    assert "'mon'" in out.err and missing in out.err and "converge" in out.err and "mon-token-rotate" in out.err


@pytest.mark.parametrize(
    "argv", [["--stack", "prod", "up"], ["up", "--stack"]], ids=["an unknown stack", "no stack after the flag"]
)
def test_a_stack_that_cannot_be_resolved_is_a_usage_error_before_any_read(monkeypatch, capsys, argv):
    seen = _Recorded(monkeypatch)
    assert gq.main(argv) == 2
    assert seen.vault == [] and seen.urls == []
    assert "usage: grafana-query.py [--stack cloud|mon] [--loki]" in capsys.readouterr().out
