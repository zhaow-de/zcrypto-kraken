"""`infra/scripts/kraken-order-semantics-probe.py` at its command line, before any node exists. `--help` and
`--selftest` need no credentials and touch no venue. Preflight refuses, in this order and each by name: a `--probes`
value outside 1-6 or not a number; an installed nautilus-trader other than the expected version, unless
`--allow-version-mismatch`; a missing `KRAKEN_SPOT_API_KEY` or `KRAKEN_SPOT_API_SECRET` unless `--no-exec`, naming
the variable and never a value; `--probe5` without `--apply`; a `--max-notional` above the absolute ceiling; a
`--notional` above `--max-notional` or under the costmin floor; an `--away` under the protocol floor; a `--leverage`
under 1; an empty `--known-order`. A `Refusal` while the node is built is exit 2 with its message, not a traceback.
`build_node` is replaced for every case, so a preflight that let a run through stops at the stub instead of
connecting. The harness's pure
core is `tests/test_order_semantics_probe.py`'s."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import nautilus_trader
import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "kraken-order-semantics-probe.py"
_spec = importlib.util.spec_from_file_location("kraken_order_semantics_probe_cli", _SCRIPT)
probe = importlib.util.module_from_spec(_spec)
# Registered before exec: `@dataclass` resolves its module through `sys.modules` during class creation.
sys.modules[_spec.name] = probe
_spec.loader.exec_module(probe)

_EXPECT = ["--expect-nautilus", nautilus_trader.__version__]
_STUB = "the test's stub -- preflight let this run through"


@pytest.fixture(autouse=True)
def _no_node(monkeypatch):
    monkeypatch.delenv(probe.API_KEY_VAR, raising=False)
    monkeypatch.delenv(probe.API_SECRET_VAR, raising=False)

    def refuse(args, strategy):
        raise probe.Refusal(_STUB)

    monkeypatch.setattr(probe, "build_node", refuse)


def _refused(argv: list[str], capsys) -> tuple[str, str]:
    """The refusal's message and everything printed before it, which never reaches the mode banner."""
    with pytest.raises(SystemExit) as exc:
        probe.main(argv)
    out = capsys.readouterr().out
    assert "mode: " not in out
    return str(exc.value.code), out


def test_help_names_the_arming_flags(capsys):
    with pytest.raises(SystemExit) as exc:
        probe.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert all(
        flag in out for flag in ("--apply", "--probe5", "--no-exec", "--selftest", "--expect-nautilus", "--allow-version-mismatch")
    )
    assert "Places REAL orders with --apply" in out


def test_selftest_passes_without_credentials(capsys):
    assert probe.main(["--selftest"]) == 0
    out = capsys.readouterr().out
    assert "  FAIL " not in out and re.search(r"^SELFTEST PASSED \(\d+ checks\)$", out, re.M)


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--no-exec", "--probes", "7"], "REFUSING: --probes: 7 is not one of probes 1-6"),
        (["--no-exec", "--probes", "4a"], "REFUSING: --probes: '4a' is not a probe number"),
        (
            ["--no-exec", "--expect-nautilus", "0.0.0"],
            f"REFUSING: installed nautilus-trader is {nautilus_trader.__version__}, not the expected 0.0.0",
        ),
        ([], "REFUSING: KRAKEN_SPOT_API_KEY and KRAKEN_SPOT_API_SECRET not set in the environment."),
        (["--no-exec", "--probe5"], "REFUSING: --probe5 without --apply is meaningless. Both, or neither."),
        (["--no-exec", "--max-notional", "51"], "REFUSING: --max-notional 51.0 is above this harness's absolute ceiling 50.0"),
        (["--no-exec", "--notional", "20"], "REFUSING: --notional 20.0 is above --max-notional 15.0"),
        (["--no-exec", "--notional", "0.5"], "REFUSING: --notional 0.5 is too small to clear the venue's costmin floor"),
        (["--no-exec", "--away", "0.1"], "REFUSING: --away 0.1 is below the protocol's 0.25"),
        (["--no-exec", "--leverage", "0"], "REFUSING: --leverage 0 is not a leverage"),
        (["--no-exec", "--known-order", " "], "REFUSING: --known-order was given an empty txid"),
    ],
)
def test_preflight_refuses_by_name(argv, message, capsys):
    code, _ = _refused([*_EXPECT, *argv], capsys)
    assert code.startswith(message), code


def test_the_credential_refusal_names_the_missing_variable_and_never_a_value(monkeypatch, capsys):
    monkeypatch.setenv(probe.API_KEY_VAR, "sentinel-key-value")
    code, out = _refused(_EXPECT, capsys)
    assert code.startswith("REFUSING: KRAKEN_SPOT_API_SECRET not set in the environment.")
    assert "sentinel-key-value" not in code + out


def test_allow_version_mismatch_continues_to_the_next_gate(capsys):
    code, out = _refused(["--no-exec", "--expect-nautilus", "0.0.0", "--allow-version-mismatch", "--probe5"], capsys)
    assert "-- continuing because --allow-version-mismatch was given" in out
    assert code.startswith("REFUSING: --probe5 without --apply")


def test_a_refusal_while_the_node_is_built_is_exit_2_not_a_traceback(capsys):
    assert probe.main([*_EXPECT, "--no-exec"]) == 2
    out = capsys.readouterr().out
    assert "mode: DRY-RUN -- nothing will be submitted" in out
    assert f"!! REFUSED before the node was built: {_STUB}" in out


def test_the_reconcile_blind_legs_are_the_two_way_spelled_basket_legs():
    """The script restates the list, so a basket change reaches it only through this recompute."""
    from cli.backfill.read import dump_pair_name
    from cli.engine.store import BASKET, PAIR_KEYS

    two_way = {symbol for symbol in BASKET if dump_pair_name(symbol) != PAIR_KEYS[symbol]}
    assert two_way == set(probe.RECONCILE_BLIND_LEGS)
