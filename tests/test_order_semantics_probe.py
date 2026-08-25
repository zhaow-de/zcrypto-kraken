"""The order-semantics harness's pure core — the rails that bound real money on a live account.

`infra/scripts/kraken-order-semantics-probe.py` is a standalone script, not a package module, so it
loads via `importlib.util.spec_from_file_location` (the precedent `test_grafana_query.py` sets).

The harness carries its own `--selftest`, which the operator runs immediately before pointing it at
the venue. These tests are not a duplicate of it: they run in CI on every change to the repo, and
they pin the two properties whose failure is silent and expensive — the leftover classification,
which decides whether a run reports "nothing is resting", and the waiting primitive, which is the
only thing that advances the sequence.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import nautilus_trader
import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "infra" / "scripts" / "kraken-order-semantics-probe.py"
_spec = importlib.util.spec_from_file_location("kraken_order_semantics_probe", _SCRIPT)
probe = importlib.util.module_from_spec(_spec)
# Registered before execution: `@dataclass` resolves its own module out of `sys.modules`, and a
# module absent from it raises during class creation rather than at first use.
sys.modules[_spec.name] = probe
_spec.loader.exec_module(probe)


@dataclass
class _Order:
    """The two fields the classification reads off a cached order."""

    status: str
    is_closed: bool


CLOSED = _Order(status="CANCELED", is_closed=True)
RESTING = _Order(status="ACCEPTED", is_closed=False)
# What the order object a caller keeps reads after submission, forever: every event applies to the
# Cache's copy, never to this one.
HELD_SNAPSHOT = _Order(status="INITIALIZED", is_closed=False)


# ---------------------------------------------------------------------------------------------
# The leftover classification
# ---------------------------------------------------------------------------------------------


def test_a_run_whose_orders_all_closed_is_clean():
    """The true positive. A guard that can only refuse would pass this suite while making every
    healthy run print a cancel-by-hand banner, which is how a banner stops being read."""
    split = probe.classify_submitted(["a", "b"], {"a": CLOSED, "b": CLOSED}.get)

    assert split.closed == ["a", "b"]
    assert split.outstanding == []


def test_a_resting_order_is_outstanding():
    split = probe.classify_submitted(["a", "b"], {"a": CLOSED, "b": RESTING}.get)

    assert split.resting == ["b"]
    assert split.outstanding == ["b"]


def test_an_id_the_cache_has_no_record_of_is_outstanding_rather_than_clean():
    """`submit_order` was called, so the command may have reached the venue. A cache miss is
    therefore the most alarming answer available, not the most reassuring one."""
    split = probe.classify_submitted(["a"], {}.get)

    assert split.unknown == ["a"]
    assert split.outstanding == ["a"]


def test_the_snapshot_a_caller_keeps_is_never_read_as_never_submitted():
    """THE money defect this classification exists to make impossible.

    A held order stays `INITIALIZED` with `is_closed` False for the whole life of the process,
    whatever the venue does. Classified by status, that reads "never submitted, nothing at the
    venue" and the run reports a clean bill while the order rests at Kraken. Classified by whether
    the Cache says it is closed, the same object is outstanding — which is what a cancel sweep and
    a non-zero exit code hang off.
    """
    split = probe.classify_submitted(["a"], {"a": HELD_SNAPSHOT}.get)

    assert split.outstanding == ["a"]
    assert split.closed == []


def test_the_defect_and_the_correct_reading_disagree_on_the_same_order():
    """The fixture the test above stands on is one the defect can actually move.

    Reading the status the way "INITIALIZED means never submitted" would calls this order finished;
    reading `is_closed` off the Cache's copy calls it outstanding. Both readings are computed here,
    on one object, so the fixture cannot degenerate into one where the defect and the correct
    behaviour agree.
    """
    dismissed_by_status = HELD_SNAPSHOT.status == "INITIALIZED"
    outstanding_by_cache = probe.classify_submitted(["a"], {"a": HELD_SNAPSHOT}.get).outstanding == ["a"]

    assert dismissed_by_status and outstanding_by_cache


def test_the_classification_never_infers_never_submitted_from_a_status():
    """Only the caller's own record of what it handed to `submit_order` can say that, and it is the
    input list. An id absent from that list is absent from every bucket."""
    split = probe.classify_submitted([], {"a": RESTING}.get)

    assert split.outstanding == []
    assert split.closed == []


# ---------------------------------------------------------------------------------------------
# The waiting primitive
# ---------------------------------------------------------------------------------------------


class _Alerts:
    def __init__(self) -> None:
        self.armed: list[tuple[str, float]] = []
        self.cancelled: list[str] = []

    def arm(self, name: str, secs: float) -> None:
        self.armed.append((name, secs))

    def cancel(self, name: str) -> None:
        self.cancelled.append(name)


def test_a_wait_whose_predicate_already_holds_continues_without_arming_a_deadline():
    """Nothing re-evaluates a wait except an event or its deadline, so a satisfied wait that armed
    a deadline anyway would stall the whole sequence for the length of that timeout — every probe
    that reads state already present would cost its full budget in wall-clock time."""
    alerts = _Alerts()
    seen: list[bool] = []

    probe.Sequencer(alerts.arm, alerts.cancel).until(lambda: True, 30.0, seen.append)

    assert seen == [True]
    assert alerts.armed == []


def test_an_event_resolves_the_wait_exactly_once_and_cancels_its_deadline():
    alerts = _Alerts()
    ready = {"yes": False}
    seen: list[bool] = []
    seq = probe.Sequencer(alerts.arm, alerts.cancel)

    seq.until(lambda: ready["yes"], 30.0, seen.append)
    assert len(alerts.armed) == 1

    seq.on_event()
    assert seen == []  # the predicate does not hold yet

    ready["yes"] = True
    seq.on_event()
    assert seen == [True]
    assert alerts.cancelled == [alerts.armed[0][0]]

    seq.on_event()
    assert seen == [True]  # a resolved wait is gone, not re-armed


def test_a_deadline_reports_the_predicates_final_answer():
    """The deadline re-reads the predicate rather than assuming failure: an order that reached its
    terminal state between the last event and the alert did satisfy the wait, and recording it as a
    timeout would fail a probe that actually passed."""
    alerts = _Alerts()
    ready = {"yes": False}
    seen: list[bool] = []
    seq = probe.Sequencer(alerts.arm, alerts.cancel)
    seq.until(lambda: ready["yes"], 5.0, seen.append)

    ready["yes"] = True
    assert seq.on_alert(alerts.armed[0][0]) is True

    assert seen == [True]


def test_a_deadline_with_the_predicate_still_false_reports_failure():
    alerts = _Alerts()
    seen: list[bool] = []
    seq = probe.Sequencer(alerts.arm, alerts.cancel)
    seq.until(lambda: False, 5.0, seen.append)

    assert seq.on_alert(alerts.armed[0][0]) is True

    assert seen == [False]


def test_an_alert_that_is_not_the_pending_one_is_ignored():
    """Alerts are named per wait, and a resolved wait's alert can still fire. Advancing the
    sequence on it would run the next probe's step twice."""
    alerts = _Alerts()
    seen: list[bool] = []
    seq = probe.Sequencer(alerts.arm, alerts.cancel)
    seq.until(lambda: False, 5.0, seen.append)

    assert seq.on_alert("probe-wait-999") is False
    assert seen == []

    name = alerts.armed[0][0]
    assert seq.on_alert(name) is True
    assert seq.on_alert(name) is False  # the same alert again resolves nothing
    assert seen == [False]


def test_a_quote_only_reaches_a_wait_that_asked_for_quotes():
    """Quotes arrive in the hundreds per second across the subscribed universe. Only probe 3 waits
    on them; every other predicate is an order read, and re-running those on each quote would burn
    the run's whole budget re-reading the Cache."""
    alerts = _Alerts()
    ready = {"yes": False}
    order_wait: list[bool] = []
    seq = probe.Sequencer(alerts.arm, alerts.cancel)
    seq.until(lambda: ready["yes"], 30.0, order_wait.append)

    ready["yes"] = True
    seq.on_event(from_quote=True)
    assert order_wait == []

    seq.on_event()
    assert order_wait == [True]

    quote_wait: list[bool] = []
    arrived = {"yes": False}
    quote_seq = probe.Sequencer(alerts.arm, alerts.cancel)
    quote_seq.until(lambda: arrived["yes"], 30.0, quote_wait.append, on_quote=True)
    arrived["yes"] = True
    quote_seq.on_event(from_quote=True)
    assert quote_wait == [True]


def test_two_pending_waits_are_refused():
    """Two live waits would fork the sequence: both continuations would eventually run and both
    would advance it, so a probe's step would execute twice — the second time on state the first
    already consumed."""
    alerts = _Alerts()
    seq = probe.Sequencer(alerts.arm, alerts.cancel)
    seq.until(lambda: False, 5.0, lambda _ok: None)

    with pytest.raises(probe.Refusal, match="already pending"):
        seq.until(lambda: False, 5.0, lambda _ok: None)


# ---------------------------------------------------------------------------------------------
# The version the run binds to
# ---------------------------------------------------------------------------------------------


def test_the_expected_version_is_derived_from_the_pin_not_restated(tmp_path):
    """A hand-maintained copy of a nightly pin is stale by default, and this harness's whole
    deliverable is the exact version string it bound to."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\ndependencies = ["nautilus-trader===9.9.9.dev1", "typer>=0.9"]\n')

    assert probe.pinned_nautilus_version(pyproject) == "9.9.9.dev1"


def test_a_pin_that_is_not_arbitrary_equality_is_refused(tmp_path):
    """`==<version>` also matches the `<version>+<build>` form the index publishes and orders it
    above, so it can install a build whose `__version__` is not the string anyone wrote down."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\ndependencies = ["nautilus-trader==9.9.9"]\n')

    with pytest.raises(probe.Refusal, match="must pin with"):
        probe.pinned_nautilus_version(pyproject)


def test_the_harness_expects_the_version_this_interpreter_actually_runs():
    """The harness refuses to probe an interpreter that is not the pinned one, and this is the
    check that both operands are readable and agree in the tree the tests run in."""
    assert probe.pinned_nautilus_version(probe.PYPROJECT) == nautilus_trader.__version__


def test_the_harness_points_at_this_repos_pyproject():
    assert probe.PYPROJECT == _REPO / "pyproject.toml"


# ---------------------------------------------------------------------------------------------
# The whole offline surface, as the operator runs it
# ---------------------------------------------------------------------------------------------


def test_selftest_passes_with_no_credentials_and_no_network():
    """Step 0 of the attended procedure. It must stay runnable with nothing exported: an operator
    who cannot prove the rails before the credentials are in the shell has no way to prove them
    at all."""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(_REPO)}
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--selftest"],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SELFTEST PASSED" in result.stdout
    assert "FAIL" not in result.stdout


def test_probe5_without_apply_is_refused_before_anything_is_built():
    """The money gate, at the layer that cannot be reached by a bug further in: preflight exits
    before a node exists."""
    args = probe.build_parser().parse_args(["--probe5", "--no-exec"])

    with pytest.raises(SystemExit, match="meaningless"):
        probe.preflight(args)


def test_a_notional_ceiling_above_the_absolute_maximum_is_refused():
    args = probe.build_parser().parse_args(["--no-exec", "--max-notional", "60"])

    with pytest.raises(SystemExit, match="absolute ceiling"):
        probe.preflight(args)


def test_a_dry_run_preflight_with_no_credentials_is_accepted():
    """The true positive for preflight: the credential-free smoke test the runbook opens with must
    pass every rail, or the rails are refusing the healthy path."""
    args = probe.build_parser().parse_args(["--probes", "3", "--no-exec"])

    probe.preflight(args)

    assert args.selected_probes == {3}
