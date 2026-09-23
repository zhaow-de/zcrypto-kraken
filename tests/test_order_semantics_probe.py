"""The order-semantics harness's pure core — the rails that bound real money on a live account, and
not a duplicate of the harness's own `--selftest`: these run in CI on every change to the repo.
`infra/scripts/kraken-order-semantics-probe.py` is a standalone script, not a package module, so it
loads via `importlib.util.spec_from_file_location` (the precedent `test_grafana_query.py` sets)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

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
    """The field the classification reads off a cached order, beside the status the defect reads."""

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
    """THE money defect this classification exists to make impossible: a held order stays
    `INITIALIZED` with `is_closed` False for the whole life of the process, whatever the venue does,
    so classified by status it reads "never submitted, nothing at the venue" and the run reports a
    clean bill while the order rests at Kraken."""
    split = probe.classify_submitted(["a"], {"a": HELD_SNAPSHOT}.get)

    assert split.outstanding == ["a"]
    assert split.closed == []


def test_the_defect_and_the_correct_reading_disagree_on_the_same_order():
    """The fixture the test above stands on is one the defect can actually move: both readings are
    computed here on one object, so it cannot degenerate into one where the defect and the correct
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
# An open order as the operator reads it
# ---------------------------------------------------------------------------------------------


@dataclass
class _Reconciled:
    """An order startup reconciliation put in the Cache: named by its txid, priced at the adapter's 0.0."""

    venue_order_id: str = "OWNERB-TCEUR-000001"
    client_order_id: str = "OWNERB-TCEUR-000001"
    instrument_id: str = "BTC/EUR.KRAKEN"
    side: str = "SELL"
    quantity: str = "0.00010000"
    price: float = 0.0
    status: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(name="ACCEPTED"))


def test_an_open_order_is_named_by_its_txid_and_not_priced_at_the_adapters_zero():
    """A resting limit order read back through the adapter carries price 0.0, which matches nothing
    on Kraken's Open Orders page; the txid is what the operator can look up."""
    line = probe.describe_open_order(_Reconciled())

    assert line.startswith("txid OWNERB-TCEUR-000001 BTC/EUR.KRAKEN SELL 0.00010000")
    assert "@" not in line


# ---------------------------------------------------------------------------------------------
# Whose open orders these are
# ---------------------------------------------------------------------------------------------

_PAIR = "BTC/EUR.KRAKEN"
# An earlier run's probe order as a fresh node adopts it: the report carries no client order id,
# so reconciliation names it by its txid, and the probe infix it went out with is gone.
_LEFTOVER = _Reconciled(venue_order_id="OLEFTO-VERPR-OBE001", client_order_id="OLEFTO-VERPR-OBE001", side="BUY")
_OWNER_BTC = _Reconciled()
_OWNER_SOL = _Reconciled(
    venue_order_id="OWNERS-OLEUR-000002", client_order_id="OWNERS-OLEUR-000002", instrument_id="SOL/EUR.KRAKEN"
)


def _classify(orders, *, submitted=(), ours=(), known=()):
    return probe.classify_open_orders(
        orders, pair=_PAIR, submitted=set(submitted), ours_venue_ids=set(ours), known_venue_ids=set(known)
    )


def test_an_earlier_runs_leftover_is_ours_by_the_txid_its_evidence_recorded():
    """The fresh `--probes 6` read: the leftover carries no probe infix, only its txid."""
    assert probe.PROBE_ORDER_ID_INFIX not in _LEFTOVER.client_order_id

    split = _classify([_LEFTOVER], ours={"OLEFTO-VERPR-OBE001"})

    assert split.ours == [_LEFTOVER]
    assert split.counts() == "ours 1, known 0, unclaimed 0, other 0"


def test_this_invocations_own_order_is_ours_before_the_venue_has_named_it():
    own = _Reconciled(venue_order_id=None, client_order_id="O-20260923-120000-901-P6V-1")

    assert _classify([own], submitted={"O-20260923-120000-901-P6V-1"}).ours == [own]


def test_an_order_named_with_known_order_is_known():
    split = _classify([_OWNER_BTC, _OWNER_SOL], known={"OWNERB-TCEUR-000001", "OWNERS-OLEUR-000002"})

    assert split.known == [_OWNER_BTC, _OWNER_SOL]
    assert split.ours == split.unclaimed == split.other == []


def test_naming_a_probe_leftover_does_not_wave_it_through():
    split = _classify([_LEFTOVER], ours={"OLEFTO-VERPR-OBE001"}, known={"OLEFTO-VERPR-OBE001"})

    assert split.ours == [_LEFTOVER]
    assert split.known == []


def test_an_unnamed_order_on_the_pair_is_unclaimed_and_one_elsewhere_is_other():
    """This invocation's probe orders only go out on `--pair`, so there an unnamed order may be a
    leftover whose evidence file was never written; elsewhere it is not this invocation's."""
    split = _classify([_LEFTOVER, _OWNER_SOL])

    assert split.unclaimed == [_LEFTOVER]
    assert split.other == [_OWNER_SOL]


def test_a_named_order_the_read_does_not_find_is_reported():
    assert _classify([_OWNER_BTC], known={"OWNERB-TCEUR-000001", "OMISTY-PEDTX-000009"}).known_absent == ["OMISTY-PEDTX-000009"]


def test_probe_6_fails_on_an_order_of_ours_or_an_unclaimed_one_even_off_its_anchor():
    assert probe.verdict_after_run(_classify([_LEFTOVER], ours={"OLEFTO-VERPR-OBE001"}), 0, anchored=True) == "FAIL"
    assert probe.verdict_after_run(_classify([_LEFTOVER]), 0, anchored=True) == "FAIL"
    assert probe.verdict_after_run(_classify([_LEFTOVER]), 0, anchored=False) == "FAIL"


def test_probe_6_passes_with_only_named_orders_open():
    """The true positive: the owner's orders, named, rest through the pass without a verdict to adjudicate."""
    split = _classify([_OWNER_BTC, _OWNER_SOL], known={"OWNERB-TCEUR-000001", "OWNERS-OLEUR-000002"})

    assert probe.verdict_after_run(split, 0, anchored=True) == "PASS"


@pytest.mark.parametrize(
    ("orders", "known", "positions", "anchored"),
    [
        ([_OWNER_SOL], (), 0, True),
        ([], (), 1, True),
        ([], ("OMISTY-PEDTX-000009",), 0, True),
        ([], (), 0, False),
    ],
    ids=["other-open", "a-position", "named-but-absent", "read-predates-the-run"],
)
def test_probe_6_reviews_what_is_not_ours_but_not_clean(orders, known, positions, anchored):
    assert probe.verdict_after_run(_classify(orders, known=known), positions, anchored=anchored) == "REVIEW"


def test_probe_2_passes_on_named_orders_and_reviews_anything_else():
    named = _classify([_OWNER_BTC], known={"OWNERB-TCEUR-000001"})

    assert probe.verdict_at_start(named, 0) == "PASS"
    assert probe.verdict_at_start(_classify([]), 0) == "PASS"
    assert probe.verdict_at_start(_classify([_OWNER_BTC]), 0) == "REVIEW"
    assert probe.verdict_at_start(named, 1) == "REVIEW"
    assert probe.verdict_at_start(_classify([], known={"OMISTY-PEDTX-000009"}), 0) == "REVIEW"


def test_an_evidence_file_yields_the_txids_of_the_orders_its_run_submitted():
    evidence = {
        "submitted_client_order_ids": ["O-1-901-P6V-1", "O-1-901-P6V-2"],
        "events": [
            {"client_order_id": "O-1-901-P6V-1", "venue_order_id": "OLEFTO-VERPR-OBE001"},
            {"client_order_id": "O-1-901-P6V-2", "venue_order_id": None},
            {"client_order_id": "SOMEONE-ELSE", "venue_order_id": "OOTHER-XXXXX-000003"},
        ],
    }

    assert probe.probe_venue_order_ids(evidence) == {"OLEFTO-VERPR-OBE001"}


def test_the_evidence_dir_is_read_whole_and_an_unreadable_file_is_named(tmp_path):
    good = {"submitted_client_order_ids": ["c"], "events": [{"client_order_id": "c", "venue_order_id": "OAAAAA-BBBBB-CCCCC1"}]}
    (tmp_path / "evidence-20260923-100000.json").write_text(json.dumps(good))
    (tmp_path / "evidence-20260923-110000.json").write_text("{not json")
    (tmp_path / "other.json").write_text(json.dumps({**good, "events": [{"client_order_id": "c", "venue_order_id": "OZZZZZ"}]}))

    ids, unreadable = probe.load_probe_venue_order_ids(tmp_path)

    assert ids == {"OAAAAA-BBBBB-CCCCC1"}
    assert len(unreadable) == 1 and "evidence-20260923-110000.json" in unreadable[0]


class _NodeOpen:
    """A node whose Cache holds a fixed set of open orders, found by their client order id."""

    def __init__(self, open_orders) -> None:
        self.cache = self
        self._open = list(open_orders)

    def order(self, coid):
        return next((o for o in self._open if o.client_order_id == str(coid)), None)

    def orders_open(self, venue=None):
        return list(self._open)

    def run(self) -> None:
        pass

    def dispose(self) -> None:
        pass


def test_the_final_read_holds_an_earlier_runs_leftover_and_an_unclaimed_order_for_exit_3():
    state = probe.RunState(sequence_complete=True, pair=_PAIR, prior_venue_order_ids={"OLEFTO-VERPR-OBE001"})
    unclaimed = _Reconciled(venue_order_id="OUNCLA-IMEDX-000004", client_order_id="OUNCLA-IMEDX-000004")

    split = probe.final_read(_NodeOpen([_LEFTOVER, unclaimed, _OWNER_SOL]), state)

    assert split.outstanding == ["OLEFTO-VERPR-OBE001"]
    assert split.unclaimed == ["OUNCLA-IMEDX-000004"]


class _DisposingNode(_NodeOpen):
    """Disposing a node empties its Cache, as a real node's does."""

    def dispose(self) -> None:
        self._open = []


def _main_against(open_orders, tmp_path, monkeypatch, *extra: str) -> int:
    monkeypatch.setattr(probe, "build_node", lambda args, strategy: _DisposingNode(open_orders))
    argv = ["--no-exec", "--probes", "6", "--evidence-dir", str(tmp_path), *extra]
    return probe.main(["--expect-nautilus", nautilus_trader.__version__, *argv])


def test_an_unnamed_open_order_on_the_pair_exits_3(tmp_path, monkeypatch, capsys):
    assert _main_against([_OWNER_BTC], tmp_path, monkeypatch) == 3
    assert f"OPEN ORDERS ON {_PAIR} THAT NOTHING CLAIMS" in capsys.readouterr().out


def test_the_same_order_named_with_known_order_exits_0(tmp_path, monkeypatch):
    """The true positive for the exit-3 rule: the owner's order, named, leaves the run clean."""
    assert _main_against([_OWNER_BTC], tmp_path, monkeypatch, "--known-order", "OWNERB-TCEUR-000001") == 0


def test_a_leftover_an_earlier_evidence_file_records_exits_3(tmp_path, monkeypatch, capsys):
    earlier = {
        "submitted_client_order_ids": ["O-20260923-210010-901-P6V-1"],
        "events": [{"client_order_id": "O-20260923-210010-901-P6V-1", "venue_order_id": "OLEFTO-VERPR-OBE001"}],
    }
    (tmp_path / "evidence-20260923-210010.json").write_text(json.dumps(earlier))

    assert _main_against([_LEFTOVER], tmp_path, monkeypatch, "--known-order", "OLEFTO-VERPR-OBE001") == 3
    assert "ORDERS THIS HARNESS PLACED ARE STILL OPEN" in capsys.readouterr().out


def test_the_cancel_by_hand_banner_names_each_order_from_the_cache_before_it_is_disposed(tmp_path, monkeypatch, capsys):
    """The banner is what the operator cancels from; an entry reading "no cache record" leaves them
    to find the order at Kraken with nothing but an id."""
    earlier = {"submitted_client_order_ids": ["c"], "events": [{"client_order_id": "c", "venue_order_id": "OLEFTO-VERPR-OBE001"}]}
    (tmp_path / "evidence-20260923-210010.json").write_text(json.dumps(earlier))
    unclaimed = _Reconciled(venue_order_id="OUNCLA-IMEDX-000004", client_order_id="OUNCLA-IMEDX-000004")

    assert _main_against([_LEFTOVER, unclaimed], tmp_path, monkeypatch) == 3

    out = capsys.readouterr().out
    assert "client_order_id=OLEFTO-VERPR-OBE001 venue_order_id=OLEFTO-VERPR-OBE001 BTC/EUR.KRAKEN BUY" in out
    assert "!!   txid OUNCLA-IMEDX-000004 BTC/EUR.KRAKEN SELL 0.00010000" in out
    assert "no cache record" not in out


# ---------------------------------------------------------------------------------------------
# Probes 2 and 6 as the strategy runs them
# ---------------------------------------------------------------------------------------------


class _Venue:
    """What a started node's Cache and Portfolio answer: fixed open orders, no position, no account."""

    def __init__(self, open_orders) -> None:
        self._open = list(open_orders)

    def orders_open(self, venue=None):
        return list(self._open)

    def positions_open(self, venue=None):
        return []

    def account(self, venue):
        return None


class _ReadingStrategy(probe.ProbeStrategy):
    cache = property(lambda s: s._venue)
    portfolio = property(lambda s: s._venue)


def _row(label: str, open_orders, *, prior=(), known=(), submitted=()):
    """Probe 2's or 6's row as the strategy records it over `open_orders`, with an exec client."""
    args = probe.build_parser().parse_args([])
    args.selected_probes = {int(label)}
    state = probe.RunState(submitted=list(submitted), prior_venue_order_ids=set(prior), known_venue_order_ids=set(known))
    strategy = _ReadingStrategy(args, state)
    strategy._venue = _Venue(open_orders)
    strategy._advance = lambda: None
    getattr(strategy, f"_probe{label}")()
    (row,) = state.results
    return row


def test_probe_6s_row_fails_on_an_earlier_runs_leftover_named_or_not():
    """The row §5.4 reads and the write-up pastes, over the leftover its evidence file records."""
    assert _row("6", [_LEFTOVER], prior={"OLEFTO-VERPR-OBE001"}).verdict == "FAIL"
    assert _row("6", [_LEFTOVER], prior={"OLEFTO-VERPR-OBE001"}, known={"OLEFTO-VERPR-OBE001"}).verdict == "FAIL"


def test_probe_6s_row_passes_with_only_named_orders_open():
    row = _row("6", [_OWNER_BTC, _OWNER_SOL], known={"OWNERB-TCEUR-000001", "OWNERS-OLEUR-000002"})

    assert row.verdict == "PASS"
    assert "(ours 0, known 2, unclaimed 0, other 0)" in row.observed


def test_probe_6s_row_reviews_a_read_that_predates_this_runs_orders():
    row = _row("6", [], submitted=["O-20260923-120000-901-P6V-1"])

    assert row.verdict == "REVIEW"
    assert "NOT re-read" in row.observed


def test_probe_2s_row_reviews_an_unnamed_order_and_passes_a_named_one():
    assert _row("2", [_OWNER_BTC]).verdict == "REVIEW"
    assert _row("2", [_OWNER_BTC], known={"OWNERB-TCEUR-000001"}).verdict == "PASS"


def test_probe_2_prints_an_open_order_by_its_txid_and_no_price(capsys):
    _row("2", [_OWNER_BTC])

    out = capsys.readouterr().out
    assert "pre-existing open order: txid OWNERB-TCEUR-000001 BTC/EUR.KRAKEN SELL" in out
    assert [line for line in out.splitlines() if "@" in line] == []


# ---------------------------------------------------------------------------------------------
# A node start that fails at startup reconciliation
# ---------------------------------------------------------------------------------------------

# The refusal as the binding raises it: the node's prefix, then the manager's per-position reasons.
_REFUSAL = (
    "Unresolved positions during startup reconciliation for KRAKEN: account=KRAKEN-901, instrument=SOL/EUR.KRAKEN, "
    "venue_position_id=None, venue_quantity=0.06000000: missing avg_px_open for position recovery"
)


def test_the_start_refusal_is_read_into_each_position_it_could_not_adopt():
    two = (
        f"{_REFUSAL}; account=KRAKEN-901, instrument=BTC/EUR.KRAKEN, venue_position_id=None, "
        "venue_quantity=-0.00100000: missing avg_px_open for position recovery"
    )

    assert probe.unresolved_positions(two) == [
        probe.UnresolvedPosition("SOL/EUR.KRAKEN", "0.06000000", "missing avg_px_open for position recovery"),
        probe.UnresolvedPosition("BTC/EUR.KRAKEN", "-0.00100000", "missing avg_px_open for position recovery"),
    ]


def test_another_start_failure_is_not_read_as_the_position_refusal():
    assert probe.unresolved_positions("Failed to get mass status from KRAKEN") is None


class _RaisingNode(_NodeOpen):
    """A node whose start fails the way `LiveNode.run` raises it."""

    def __init__(self, exc: BaseException) -> None:
        super().__init__([])
        self._exc = exc

    def run(self) -> None:
        raise self._exc


def _main_raising(exc, tmp_path, monkeypatch, probes: str) -> int:
    monkeypatch.setattr(probe, "build_node", lambda args, strategy: _RaisingNode(exc))
    argv = ["--no-exec", "--probes", probes, "--evidence-dir", str(tmp_path)]
    return probe.main(["--expect-nautilus", nautilus_trader.__version__, *argv])


def _rows(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("| ") and not line.startswith(("| #", "| --"))]


def test_a_start_refused_over_an_open_position_fails_each_reconciliation_probe_and_names_it(tmp_path, monkeypatch, capsys):
    """Not an abnormal stop: that reading sends the operator to flatten a position of the harness's
    own, and nothing was submitted -- the position is somebody else's, and the row names it."""
    assert _main_raising(RuntimeError(_REFUSAL), tmp_path, monkeypatch, probes="1,2,6") == 1

    out = capsys.readouterr().out
    rows = _rows(out)
    assert [r.split(" | ")[0] for r in rows] == ["| 2", "| 6"]
    assert all("SOL/EUR.KRAKEN quantity 0.06000000" in r and r.endswith("| FAIL |") for r in rows)
    assert "stopped abnormally" not in out


def test_the_refusal_lands_on_probe_2_when_no_reconciliation_probe_was_selected(tmp_path, monkeypatch, capsys):
    assert _main_raising(RuntimeError(_REFUSAL), tmp_path, monkeypatch, probes="3") == 1

    assert [r.split(" | ")[0] for r in _rows(capsys.readouterr().out)] == ["| 2"]


def test_a_failed_mass_status_stays_exit_2_and_names_its_likely_causes(tmp_path, monkeypatch, capsys):
    assert _main_raising(RuntimeError("Failed to get mass status from KRAKEN"), tmp_path, monkeypatch, probes="6") == 2

    out = capsys.readouterr().out
    assert "nothing was submitted" in out
    assert "the key lacks a query permission" in out


def test_any_other_start_failure_is_still_an_abnormal_stop(tmp_path, monkeypatch, capsys):
    """The true positive for both readings above: an unrecognised failure keeps the generic path."""
    exc = RuntimeError("readiness timeout while waiting for engine connections")

    assert _main_raising(exc, tmp_path, monkeypatch, probes="6") == 2

    out = capsys.readouterr().out
    assert "the node stopped abnormally" in out
    assert "query permission" not in out and _rows(out) == []


# ---------------------------------------------------------------------------------------------
# The run's file log, and what it says about the credentialed listing's fee rates
# ---------------------------------------------------------------------------------------------

# Lines as the file log writes them.
_NONCE = "2026-09-23T21:06:30.627000002Z [DEBUG] P6PROBE-901.nautilus_kraken::http::spot::client: Generated nonce 1790197590626999753 for /0/private/TradeVolume"
_FELL_BACK = (
    "2026-09-23T21:06:30.627754997Z [WARN] P6PROBE-901.nautilus_kraken::http::spot::client: Failed to request Kraken "
    "account fee rates, falling back to public rates: API error: EGeneral:Permission denied"
)
_LOADED = "2026-09-23T21:06:30.629024319Z [DEBUG] P6PROBE-901.nautilus_kraken::execution::spot: Loaded 4 Spot instruments"


def test_every_run_logs_at_debug_into_the_evidence_dir_beside_its_evidence():
    args = probe.build_parser().parse_args(["--evidence-dir", "/evid"])

    config = probe.logger_config(args, "20260923-120000")

    assert config.fileout_level == probe.LogLevel.DEBUG
    assert (config.file_config.directory, config.file_config.file_name) == ("/evid", "probe-20260923-120000")
    assert probe.run_log_path("/evid", "20260923-120000") == Path("/evid/probe-20260923-120000.log")


def test_a_fallback_warn_reads_as_fell_back_with_its_reason_and_its_call_count():
    got = probe.tradevolume_fallback("\n".join([_NONCE, _FELL_BACK, _NONCE, _FELL_BACK, _LOADED]))

    assert got["fell_back"] is True
    assert got["tradevolume_calls"] == 2
    assert got["warnings"] == [_FELL_BACK[_FELL_BACK.index("Failed to request") :]] * 2


def test_a_listing_that_finished_without_the_warn_did_not_fall_back():
    assert probe.tradevolume_fallback("\n".join([_NONCE, _LOADED]))["fell_back"] is False


def test_a_log_that_never_saw_the_listing_finish_cannot_say():
    """A partial TradeVolume answer fails the exec client's connect outright; no WARN there is not "no fallback"."""
    assert probe.tradevolume_fallback(_NONCE)["fell_back"] is None


def test_without_an_exec_client_or_a_readable_log_the_reading_is_none(tmp_path):
    missing = tmp_path / "probe-x.log"

    assert probe.read_tradevolume_fallback(missing, exec_client=False)["fell_back"] is None
    assert probe.read_tradevolume_fallback(missing, exec_client=True)["fell_back"] is None


def test_the_evidence_json_records_what_the_runs_log_says(tmp_path, monkeypatch):
    monkeypatch.setenv(probe.API_KEY_VAR, "k")
    monkeypatch.setenv(probe.API_SECRET_VAR, "s")

    def node_that_logged(args, strategy):
        probe.run_log_path(args.evidence_dir, strategy.stamp).write_text("\n".join([_NONCE, _FELL_BACK, _LOADED]))
        return _NodeOpen([])

    monkeypatch.setattr(probe, "build_node", node_that_logged)
    argv = ["--expect-nautilus", nautilus_trader.__version__, "--probes", "6", "--evidence-dir", str(tmp_path)]

    assert probe.main(argv) == 0

    (evidence,) = tmp_path.glob("evidence-*.json")
    recorded = json.loads(evidence.read_text())["tradevolume_fallback"]
    assert recorded["fell_back"] is True and recorded["log_file"].endswith(".log")


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
# Nothing new reaches the venue once the run is going down
# ---------------------------------------------------------------------------------------------


def _strategy(*argv: str):
    """A probe strategy with no node behind it."""
    args = probe.build_parser().parse_args([*argv, "--no-exec"])
    args.selected_probes = {4}
    state = probe.RunState()
    return probe.ProbeStrategy(args, state), state


class _FactoryOrder:
    client_order_id = "O-20260823-120000-901-P6V-1"


def test_submit_hands_the_order_over_and_keeps_only_its_id():
    """The true positive, and the record the leftover sweep runs on: `state.submitted` is what says
    an id may have reached the venue, so it must be written on the healthy path."""
    strategy, state = _strategy()
    calls: list = []
    strategy.submit_order = lambda *a, **k: calls.append((a, k))

    coid = strategy.submit(_FactoryOrder())

    assert coid == _FactoryOrder.client_order_id
    assert state.submitted == [coid]
    assert len(calls) == 1


def test_submit_refuses_once_the_node_is_stopping():
    """Commands issued from a stopped strategy still reach the execution engine, so a continuation
    resumed during the shutdown could open a position after the operator asked the run to end.
    `submit` is the single choke point every probe order passes through."""
    strategy, state = _strategy()
    calls: list = []
    strategy.submit_order = lambda *a, **k: calls.append((a, k))
    strategy._stopping = True

    with pytest.raises(probe.Refusal, match="stopping"):
        strategy.submit(_FactoryOrder())

    assert calls == []
    assert state.submitted == []


def test_a_stopping_run_abandons_the_probes_it_has_not_reached():
    """Stopping the node FLUSHES its pending clock alerts, so an interrupted run's settle alert fires
    during the shutdown, and without this the whole remaining sequence ran there (measured)."""
    strategy, state = _strategy()
    ran: list[str] = []
    strategy._steps = [("4a", "n", lambda: ran.append("4a")), ("4b", "n", lambda: ran.append("4b"))]
    strategy._stopping = True

    strategy._advance()

    assert ran == []
    assert strategy._steps == []
    assert any("abandoned" in n for n in state.notes)


def test_a_running_sequence_still_advances():
    """The true positive for the same guard: an always-abandoning `_advance` would ship a harness
    that runs no probes at all and reports a clean, empty table."""
    strategy, state = _strategy()
    ran: list[str] = []
    strategy._steps = [("4a", "n", lambda: ran.append("4a"))]

    strategy._advance()

    assert ran == ["4a"]
    assert state.notes == []


# ---------------------------------------------------------------------------------------------
# The version the run binds to
# ---------------------------------------------------------------------------------------------


class _FilledOrder:
    """A cached order that filled -- `is_closed` for the classification, `filled_qty` for the position warning."""

    filled_qty = 0.001
    is_closed = True
    status = "FILLED"


class _NodeWith:
    """A node whose cache answers for a fixed set of ids and holds nothing else open."""

    def __init__(self, orders):
        self.cache = self
        self._orders = orders

    def order(self, coid):
        return self._orders.get(str(coid))

    def orders_open(self, venue=None):
        return []


def test_a_run_that_finished_its_sequence_does_not_cry_open_position_over_its_own_round_trip():
    """The true positive, and the one that makes this guard non-vacuous: probe 5 buys and SELLS, so
    a healthy run always ends with filled orders. A warning keyed on "was there a fill" would fire
    on every successful pass and train the operator to ignore it."""
    coid = "O-20260823-120000-901-P6V-1"
    state = probe.RunState(submitted=[coid], sequence_complete=True)
    node = _NodeWith({coid: _FilledOrder()})

    probe.final_read(node, state)

    assert state.notes == []


def test_a_run_that_stopped_mid_sequence_after_a_fill_names_the_open_position():
    """A fill whose closing leg never ran is an OPEN POSITION, and no order read can see it -- the
    order is CLOSED and reports nothing resting. Keyed on the sequence not finishing rather than on
    a signal: an exec client that dies takes the node down without one, leaving the same position."""
    coid = "O-20260823-120000-901-P6V-1"
    state = probe.RunState(submitted=[coid], sequence_complete=False)
    node = _NodeWith({coid: _FilledOrder()})

    probe.final_read(node, state)

    assert any("flatten by hand" in n for n in state.notes), state.notes


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
