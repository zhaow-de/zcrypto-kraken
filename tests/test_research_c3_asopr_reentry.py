import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import polars as pl
import pytest

from cli.alpha import c3 as alpha_c3
from cli.alpha.a1 import _asset_returns
from cli.alpha.c3_reentry import full_long_positions
from cli.onchain.series import COLUMNS, SCHEMA
from cli.portfolio.builder import CombinedSystemConfig
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, _ffill_btc
from cli.portfolio.record44_legs import calendar_year_slices
from cli.research import subjects
from cli.validation import ValidationError, max_drawdown, sharpe
from tests.test_research_command import _COMPUTE_ERRORS, _fake_head_to_head, _fake_kill_bar, _recording

TRIAL, TWIN = "c3-asopr-reentry", "c3-asopr-reentry-preflight"
PAIR = pytest.mark.parametrize("name", [TRIAL, TWIN])
SPEC = "docs/specs/00165-c3-trial-1-asopr-reentry-design.md"
NO_VERDICT = (
    "instrument finding: arm A fails the bar this window sets, or the re-entry holds no asset at any close; no verdict, the "
    "trial unspent"
)
ASSETS = CrossfreqSystemConfig().assets
UNION_START = datetime(2020, 10, 1, tzinfo=UTC)
N_DAYS = 400
LEAD = 800
SOL_LISTED = 100
# The union indices whose decision reads a low aSOPR: four inside the gate's 200-close warm-up, where the sleeve is flat,
# one where it is long, three in the fall that closes the gate, on consecutive closes, and three in the rise after it.
LOW = (50, 120, 121, 150, 210, 310, 311, 312, 330, 360, 395)
ENGAGEMENT_KEYS = {
    "reentry_first_engaged",
    "primary_returns",
    "stamps_positions_differ",
    "positions_differ_per_year",
    "events_per_year",
    "reentered_per_year",
    "reentry_entries",
    "events_without_size",
    "turnover_b",
    "turnover_b_per_year",
    "gross_max",
}
ARM_A_BAR_KEYS = {
    "dsr",
    "dsr_pass",
    "spa_p_value",
    "spa_p_value_full",
    "spa_pass",
    "cost_stress_sharpe",
    "cost_stress_pass",
    "worst_slice_sharpe",
    "worst_slice_pass",
    "passes",
}
ANCHOR_KEYS = {
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "arm_a_max_drawdown_full",
    "turnover_a",
    "arm_a_spot_drag_pct_yr",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
}
TRIAL_KEYS = ENGAGEMENT_KEYS | {
    "ann_sharpe_noc",
    "ann_sharpe_noc_decisive",
    "per_period_sharpe",
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
    "dsr_corrected",
    "dsr_pass",
    "spa_pass",
    "spa_p_full",
    "cost_stress_pass",
    "worst_slice_relative_pass",
    "passes",
    "decisive_start",
    "n_resamples",
    "arm_a_passes",
    "spa_p_decisive_b17_s42",
    "spa_p_decisive_b17_s7",
    "spa_p_decisive_b17_s1234",
    "spa_p_decisive_b102_s42",
    "spa_p_decisive_b102_s7",
    "spa_p_decisive_b102_s1234",
    "head_to_head_mean_outperf_full",
    "head_to_head_spa_p_full",
    "head_to_head_mean_outperf_primary",
    "head_to_head_spa_p_primary",
    "max_drawdown",
    "arm_a_max_drawdown",
    "max_drawdown_per_year",
    "arm_a_max_drawdown_per_year",
    "turnover_a",
    "turnover_a_per_year",
    "max_drawdown_primary",
    "arm_a_max_drawdown_primary",
    "max_drawdown_reduction_pct",
}
ADOPTING = {
    "arm_a_passes": 1,
    "reentered_per_year": {"2020": 0, "2021": 3},
    "passes": 1,
    "head_to_head_mean_outperf_primary": 1e-6,
    "head_to_head_spa_p_primary": 0.049,
    "max_drawdown_reduction_pct": -20.0,
}


def _union() -> tuple[list[datetime], dict[str, list[float | None]]]:
    """Every asset rises to index 260, falls to 320 and rises again, on an alternating step of its own size; SOL lists at
    index 100 and BTC has no close at 300. The sleeve is long from row 200, the row after the gate's first warm close,
    into the fall, and flat on either side."""
    prices: dict[str, list[float | None]] = {}
    for i, asset in enumerate(ASSETS):
        closes = [10.0 * (i + 1)]
        for k in range(N_DAYS - 1):
            drift = 0.004 if k < 260 else -0.012 if k < 320 else 0.003
            closes.append(closes[-1] * math.exp(drift + 0.004 * (1 + i / 10) * (1 if (k + i) % 2 == 0 else -1)))
        prices[asset] = closes
    prices["SOL"] = [None] * SOL_LISTED + prices["SOL"][SOL_LISTED:]
    prices["BTC"][300] = None
    return [UNION_START + timedelta(days=k) for k in range(N_DAYS)], prices


def _snapshot() -> pl.DataFrame:
    """Day LEAD is the union's first day; `asopr` is 0.5 on the day before each index of LOW and 1.0 on every other, so
    those days alone sit in its low band."""
    n = LEAD + N_DAYS
    columns = {column: [1.0] * n for column in COLUMNS[3:]}
    columns["price"] = [10_000.0 + j for j in range(n)]
    columns["market_cap"] = [20_000.0 + j for j in range(n)]
    columns["asopr"] = [0.5 if j - LEAD + 1 in LOW else 1.0 for j in range(n)]
    return pl.DataFrame(
        {
            "ts": [UNION_START - timedelta(days=LEAD - j) for j in range(n)],
            "last_height": list(range(n)),
            "last_hash": [f"{j:064x}" for j in range(n)],
        }
        | columns,
        schema=SCHEMA,
    )


@pytest.fixture(scope="module")
def inputs():
    daily_ts, daily_prices = _union()
    return subjects._c3_reentry_inputs(_snapshot(), daily_ts, daily_prices)


def _own_books() -> tuple[dict, dict, dict, dict]:
    """Arm A by the reading's own function, the events and arm B by hand: an asset flat with a close at an index of LOW
    fires, and holds the size through 7 closes from its last event unless the sleeve holds it."""
    _, prices = _union()
    n = N_DAYS - 1
    arm_a = {a: held[:n] for a, held in alpha_c3.a1_daily_positions(prices).items()}
    size = {a: sized[:n] for a, sized in full_long_positions(prices).items()}
    fires = {a: [k in LOW and arm_a[a][k] == 0 and prices[a][k] is not None for k in range(n)] for a in ASSETS}
    arm_b = {}
    for a in ASSETS:
        row, last = [], None
        for k in range(n):
            if arm_a[a][k] > 0:
                last = None
            elif fires[a][k]:
                last = k
            held = arm_a[a][k] == 0 and last is not None and k - last < 7
            row.append(size[a][k] if held and size[a][k] > 0 else arm_a[a][k])
        arm_b[a] = row
    return arm_a, arm_b, fires, size


def _own_net(positions: dict, returns: dict, cost: float) -> list[float]:
    previous, net = dict.fromkeys(positions, 0.0), []
    for k in range(len(returns["BTC"])):
        gross = turnover = 0.0
        for a, held in positions.items():
            gross += held[k] * (returns[a][k] or 0.0)
            turnover += abs(held[k] - previous[a])
            previous[a] = held[k]
        net.append(gross - turnover * cost)
    return net


def _by_close_year(values: list, close: list[datetime]) -> dict[str, list]:
    out: dict[str, list] = {}
    for value, stamp in zip(values, close, strict=True):
        out.setdefault(str(stamp.year), []).append(value)
    return out


def _fake_system(daily_prices, *, config):
    """The benchmark a function of the prices and the config, so one built on other closes or another cost differs."""
    seed = sum(c for closes in daily_prices.values() for c in closes if c is not None) + 1e6 * config.spot_fee_per_side
    return SimpleNamespace(benchmark_net_of_cost=[math.sin(seed + k) / 100 for k in range(len(daily_prices["BTC"]) - 1)])


def _faked(monkeypatch) -> tuple[list, list]:
    bars, reads = [], []

    def kill_bar(*args, **kwargs):
        bars.append((args, kwargs))
        return _fake_kill_bar(*args, **kwargs)

    def head_to_head(*args, **kwargs):
        reads.append((args, kwargs))
        return _fake_head_to_head(*args, **kwargs)

    monkeypatch.setattr(subjects, "a1_kill_bar", kill_bar)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", head_to_head)
    monkeypatch.setattr(subjects, "build_combined_system", _fake_system)
    # A cost of its own, so a benchmark built on the builder's default config differs.
    monkeypatch.setattr(subjects, "_RECORD33_CONFIG", CombinedSystemConfig(spot_fee_per_side=0.0123))
    return bars, reads


def _own_bar(net, stressed, bench, daily_ts, block, seed) -> dict:
    return _fake_kill_bar(
        net,
        bench,
        n_trials=1,
        var_trials=0.0,
        mean_block=block,
        seed=seed,
        cost_stressed_returns=stressed,
        regime_slices=calendar_year_slices(net, daily_ts),
        benchmark_slices=calendar_year_slices(bench, daily_ts),
        decisive_start=230,
        n_resamples=2000,
    )


@PAIR
def test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count(name):
    subject = subjects.SUBJECTS[name]
    assert (subject.name, subject.spec, subject.intervals, subject.assets) == (name, SPEC, (1440,), ())
    assert subject.incumbent is None
    if name == TRIAL:
        assert subject.metric_keys == TRIAL_KEYS and len(TRIAL_KEYS) == 47
        assert (subject.seeds, subject.verdict, subject.no_verdict) == (
            (42, 7, 1234),
            subjects._c3_asopr_reentry_verdict,
            NO_VERDICT,
        )
        assert (subject.family, subject.n_trials, subject.build) == ("C3", 1, subjects._build_c3_asopr_reentry)
    else:
        assert subject.metric_keys == ENGAGEMENT_KEYS | ARM_A_BAR_KEYS | ANCHOR_KEYS and len(subject.metric_keys) == 28
        assert (subject.seeds, subject.verdict, subject.no_verdict) == ((42,), None, None)
        assert (subject.family, subject.n_trials, subject.build) == (None, None, subjects._build_c3_asopr_reentry_preflight)
    assert subjects._C3_ASOPR_REENTRY_N_TRIALS == 1
    assert (subjects._C3_REENTRY_HOLD, subjects._C3_REENTRY_DECISIVE_START) == (7, 230)
    assert (subjects._C3_REENTRY_BLOCKS, subjects._C3_REENTRY_SEEDS) == ((17, 102), (42, 7, 1234))


@pytest.mark.parametrize("name", [TRIAL])
@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="adopt-at-the-bound"),
        pytest.param({"max_drawdown_reduction_pct": -20.000001}, "park", id="park-past-the-drawdown-bound"),
        pytest.param({"head_to_head_spa_p_primary": 0.05}, "park", id="park-at-p-0.05"),
        pytest.param({"head_to_head_mean_outperf_primary": 0.0}, "reject", id="reject-at-no-outperformance"),
        pytest.param({"passes": 0, "head_to_head_mean_outperf_primary": 1.0}, "reject", id="reject-on-a-failed-bar"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="stop-when-arm-a-fails"),
        pytest.param({"reentered_per_year": {"2020": 0, "2021": 0}, "passes": 0}, None, id="stop-on-the-dead-knob"),
    ],
)
def test_the_c3_reentry_rule_maps_its_metrics_to_a_verdict_or_a_stop(name, change, verdict):
    assert subjects.SUBJECTS[name].verdict({**ADOPTING, **change}) == verdict


class _Unread:
    def __getattr__(self, attribute):
        raise AssertionError(f"a refused run reads nothing, and this one asked for {attribute}")


@PAIR
@pytest.mark.parametrize(
    ("window", "as_of", "refusal"),
    [
        pytest.param(
            None,
            "2026-03-31",
            "{name} evaluates a frozen snapshot whole, never the rolling dataset as of a day: drop --as-of",
            id="as-of",
        ),
        pytest.param(
            ("2021-01-01", "2021-06-01"),
            None,
            "{name} over the window 2021-01-01 .. 2021-06-01: it reads its frozen sets whole, and the bands' history reaches "
            "back past any window's first day; drop --window",
            id="window",
        ),
    ],
)
def test_a_c3_reentry_subject_refuses_as_of_and_a_window_before_any_read(name, window, as_of, refusal):
    with pytest.raises(subjects.SubjectError) as refused:
        subjects.SUBJECTS[name].build(_Unread(), "btc-onchain-test", window, as_of=as_of)
    assert str(refused.value) == refusal.format(name=name)


@PAIR
def test_a_c3_reentry_build_reads_the_readings_sets_and_computes_its_own_half_at_the_count(monkeypatch, name):
    calls = []
    reader, snapshot, daily_ts, daily_prices, built = object(), object(), object(), object(), object()

    def reads(*args):
        calls.append(("reads", args))
        return {}, snapshot, daily_ts, daily_prices

    def half(*args):
        calls.append(("inputs", args))
        return built

    def compute(label):
        def stand_in(*args, **kwargs):
            calls.append((label, args, kwargs))
            return {"computed_by": label}

        return stand_in

    monkeypatch.setattr(subjects, "_c3_reads", reads)
    monkeypatch.setattr(subjects, "_c3_reentry_inputs", half)
    monkeypatch.setattr(subjects, "_c3_reentry_metrics", compute("metrics"))
    monkeypatch.setattr(subjects, "_c3_reentry_preflight_metrics", compute("preflight"))
    monkeypatch.setattr(subjects, "_C3_ASOPR_REENTRY_N_TRIALS", 5)
    own = "metrics" if name == TRIAL else "preflight"

    assert subjects.SUBJECTS[name].build(reader, "btc-onchain-test", None) == {"computed_by": own}
    assert calls == [
        ("reads", (reader, "btc-onchain-test", name)),
        ("inputs", (snapshot, daily_ts, daily_prices)),
        (own, (built,), {"n_trials": 5}),
    ]


@pytest.mark.parametrize(
    ("name", "compute"),
    [(TRIAL, "_c3_reentry_metrics"), (TWIN, "_c3_reentry_preflight_metrics")],
)
def test_each_c3_reentry_builder_names_its_own_subject_and_compute(monkeypatch, name, compute):
    calls = []
    monkeypatch.setattr(subjects, "_c3_reentry_build", lambda *args: calls.append(args) or {"built": name})
    reader = object()

    assert subjects.SUBJECTS[name].build(reader, "btc-onchain-test", ("a", "b"), "2026-03-31", True) == {"built": name}
    assert calls == [(name, getattr(subjects, compute), reader, "btc-onchain-test", ("a", "b"), "2026-03-31")]


@PAIR
@pytest.mark.parametrize("error", _COMPUTE_ERRORS, ids=lambda error: error.__name__)
def test_a_c3_reentry_compute_error_is_refused_over_the_full_history(monkeypatch, name, error):
    monkeypatch.setattr(subjects, "_c3_reads", lambda *args: ({}, None, None, None))

    def raising(*args):
        raise error("the stub's cause")

    monkeypatch.setattr(subjects, "_c3_reentry_inputs", raising)

    with pytest.raises(subjects.SubjectError) as refused:
        subjects.SUBJECTS[name].build(object(), "btc-onchain-test", None)
    assert str(refused.value) == f"{name} over the full history: the stub's cause"


def test_the_c3_reentry_inputs_hold_the_sleeve_the_cells_events_the_size_and_arm_b_and_no_net_series(monkeypatch):
    daily_ts, daily_prices = _union()
    held = _recording(monkeypatch, "reentry_positions", lambda arguments, result: result)

    built = subjects._c3_reentry_inputs(_snapshot(), daily_ts, daily_prices)

    arm_a, arm_b, fires, size = _own_books()
    assert built._fields == ("daily_ts", "daily_prices", "close", "returns", "arm_a", "arm_b", "fires", "size")
    assert (built.daily_ts, built.daily_prices, built.close) == (daily_ts, daily_prices, daily_ts[1:])
    assert built.returns == {a: _asset_returns(_ffill_btc(daily_prices)[a]) for a in ASSETS}
    assert (built.arm_a, built.fires, built.size, built.arm_b) == (arm_a, fires, size, arm_b)
    assert [call[0] for call in held] == [{"asset_positions": arm_a, "full_long": size, "fires": fires, "hold": 7}]
    # The fixture: the sleeve long at 210 and flat at every other index of LOW, SOL unlisted at 50 and unsized at 120 and
    # 121, three overlapping events held as one entry from 310 through 318, and the last hold cut by the set's end.
    assert arm_a["BTC"][210] > 0 and all(arm_a["BTC"][k] == 0 for k in LOW if k != 210)
    assert [k for k, fired in enumerate(fires["BTC"]) if fired] == [k for k in LOW if k != 210]
    assert [k for k, fired in enumerate(fires["SOL"]) if fired] == [k for k in LOW if k not in (50, 210)]
    assert size["SOL"][120] == size["SOL"][121] == 0 and arm_b["SOL"][120:128] == [0.0] * 8
    assert [k for k in range(N_DAYS - 1) if arm_b["BTC"][k] != arm_a["BTC"][k]] == [
        *range(50, 57),
        *range(120, 128),
        *range(150, 157),
        *range(310, 319),
        *range(330, 337),
        *range(360, 367),
        *range(395, 399),
    ]
    assert all(p >= 0 for row in arm_b.values() for p in row)


def test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover(inputs):
    arm_a, arm_b, fires, size = _own_books()
    n, close = N_DAYS - 1, inputs.close
    year = [str(stamp.year) for stamp in close]
    differ = [any(arm_b[a][k] != arm_a[a][k] for a in ASSETS) for k in range(n)]
    reentered = {a: [arm_a[a][k] == 0 and arm_b[a][k] > 0 for k in range(n)] for a in ASSETS}
    turnover = [sum(abs(arm_b[a][k] - (arm_b[a][k - 1] if k else 0.0)) for a in ASSETS) for k in range(n)]

    def per_year(counts: list) -> dict:
        return {y: sum(c for c, at in zip(counts, year, strict=True) if at == y) for y in ("2020", "2021")}

    engagement = subjects._c3_reentry_engagement(inputs)

    assert set(engagement) == ENGAGEMENT_KEYS
    assert engagement["reentry_first_engaged"] == 50 == differ.index(True) and engagement["primary_returns"] == n - 50
    assert engagement["stamps_positions_differ"] == sum(differ) == 49
    assert engagement["positions_differ_per_year"] == per_year(differ) == {"2020": 7, "2021": 42}
    assert (
        engagement["events_per_year"] == per_year([sum(fires[a][k] for a in ASSETS) for k in range(n)]) == {"2020": 9, "2021": 90}
    )
    assert engagement["reentered_per_year"] == per_year([sum(reentered[a][k] for a in ASSETS) for k in range(n)])
    assert engagement["reentered_per_year"] == {"2020": 63, "2021": 412}
    # An entry per asset and hold: seven holds on the nine assets listed at 50, six on SOL, less SOL's unsized one.
    assert engagement["reentry_entries"] == 9 * 7 + 5 == 68
    assert engagement["reentry_entries"] == sum(row[k] and not (k and row[k - 1]) for row in reentered.values() for k in range(n))
    assert engagement["events_without_size"] == 2 == sum(fires[a][k] and size[a][k] == 0 for a in ASSETS for k in range(n))
    assert engagement["turnover_b"] == pytest.approx(sum(turnover), rel=1e-12)
    assert engagement["turnover_b_per_year"] == pytest.approx(per_year(turnover), rel=1e-12)
    assert engagement["gross_max"] == max(math.fsum(arm_b[a][k] for a in ASSETS) for k in range(n))


def test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement(
    monkeypatch, inputs
):
    bars, reads = _faked(monkeypatch)
    arm_a, arm_b, _, _ = _own_books()
    daily_ts, close, returns = inputs.daily_ts, inputs.close, inputs.returns
    net_a, net_b = _own_net(arm_a, returns, 0.006), _own_net(arm_b, returns, 0.006)
    net_a_x15, net_b_x15 = _own_net(arm_a, returns, 1.5 * 0.006), _own_net(arm_b, returns, 1.5 * 0.006)
    bench = _fake_system(inputs.daily_prices, config=subjects._RECORD33_CONFIG).benchmark_net_of_cost
    grid = {(b, s): _own_bar(net_b, net_b_x15, bench, daily_ts, b, s) for b in (17, 102) for s in (42, 7, 1234)}
    bar_a, headline = _own_bar(net_a, net_a_x15, bench, daily_ts, 17, 42), grid[(17, 42)]
    full = _fake_head_to_head(net_b, net_a, mean_block=17, seed=42, n_resamples=2000)
    primary = _fake_head_to_head(net_b[50:], net_a[50:], mean_block=17, seed=42, n_resamples=2000)
    drawdown_a, drawdown_b = max_drawdown(net_a[50:]), max_drawdown(net_b[50:])

    metrics = subjects._c3_reentry_metrics(inputs, n_trials=1)

    assert metrics == {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=365),
        "ann_sharpe_noc_decisive": sharpe(net_b[230:], periods_per_year=365),
        "per_period_sharpe": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=365),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[230:], periods_per_year=365),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=365),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[230:], periods_per_year=365),
        "dsr_corrected": headline["dsr"],
        "dsr_pass": headline["dsr_pass"],
        "spa_pass": headline["spa_pass"],
        "spa_p_full": headline["spa_p_value_full"],
        "cost_stress_pass": headline["cost_stress_pass"],
        "worst_slice_relative_pass": headline["worst_slice_pass"],
        "passes": headline["passes"],
        "decisive_start": 230,
        "n_resamples": 2000,
        "arm_a_passes": bar_a["passes"],
        **{f"spa_p_decisive_b{b}_s{s}": bar["spa_p_value"] for (b, s), bar in grid.items()},
        "head_to_head_mean_outperf_full": full["mean_outperformance"],
        "head_to_head_spa_p_full": full["spa_p_value"],
        "head_to_head_mean_outperf_primary": primary["mean_outperformance"],
        "head_to_head_spa_p_primary": primary["spa_p_value"],
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "max_drawdown_per_year": {y: max_drawdown(r) for y, r in _by_close_year(net_b, close).items()},
        "arm_a_max_drawdown_per_year": {y: max_drawdown(r) for y, r in _by_close_year(net_a, close).items()},
        "turnover_a": subjects.book_turnover(arm_a),
        "turnover_a_per_year": subjects.per_year_turnover(arm_a, close),
        "max_drawdown_primary": drawdown_b,
        "arm_a_max_drawdown_primary": drawdown_a,
        "max_drawdown_reduction_pct": 100 * (drawdown_a - drawdown_b) / drawdown_a,
        **subjects._c3_reentry_engagement(inputs),
    }
    assert set(metrics) == TRIAL_KEYS
    assert len(bars) == 7 and {kwargs["n_trials"] for _, kwargs in bars} == {1} and len(reads) == 2
    assert len({m for m in (full["mean_outperformance"], primary["mean_outperformance"])}) == 2 and drawdown_b != drawdown_a


def test_the_c3_reentry_trial_reads_its_drawdown_pair_from_the_first_engagement_and_not_over_the_window(monkeypatch, inputs):
    _faked(monkeypatch)
    # Both arms long BTC over returns 5 to 39, each a 2 % loss: a drawdown before the first engagement deeper than any
    # after it, the books still one there.
    arm_a, arm_b = ({a: list(held) for a, held in arm.items()} for arm in (inputs.arm_a, inputs.arm_b))
    for arm in (arm_a, arm_b):
        arm["BTC"][5:40] = [0.9] * 35
    returns = inputs.returns | {"BTC": inputs.returns["BTC"][:5] + [-0.02] * 35 + inputs.returns["BTC"][40:]}
    net_a, net_b = _own_net(arm_a, returns, 0.006), _own_net(arm_b, returns, 0.006)
    drawdown_a, drawdown_b = max_drawdown(net_a[50:]), max_drawdown(net_b[50:])

    metrics = subjects._c3_reentry_metrics(inputs._replace(arm_a=arm_a, arm_b=arm_b, returns=returns), n_trials=1)

    assert metrics["reentry_first_engaged"] == 50
    assert (metrics["arm_a_max_drawdown_primary"], metrics["max_drawdown_primary"]) == (drawdown_a, drawdown_b)
    assert metrics["max_drawdown_reduction_pct"] == 100 * (drawdown_a - drawdown_b) / drawdown_a
    assert (metrics["arm_a_max_drawdown"], metrics["max_drawdown"]) == (max_drawdown(net_a), max_drawdown(net_b))
    assert max_drawdown(net_a) > drawdown_a and max_drawdown(net_b) > drawdown_b != drawdown_a


def test_the_c3_reentry_trial_deflates_every_bar_at_the_count_it_is_handed(monkeypatch, inputs):
    bars, _ = _faked(monkeypatch)

    subjects._c3_reentry_metrics(inputs, n_trials=4)

    assert len(bars) == 7 and {kwargs["n_trials"] for _, kwargs in bars} == {4}


@pytest.mark.parametrize(
    ("differing", "refusal"),
    [
        pytest.param(
            0, "0 of its return indices follow the re-entry's first engagement, and the head-to-head from it needs 2", id="none"
        ),
        pytest.param(
            1, "1 of its return indices follow the re-entry's first engagement, and the head-to-head from it needs 2", id="one"
        ),
    ],
)
def test_the_c3_reentry_trial_refuses_a_head_to_head_shorter_than_2_before_any_bar(monkeypatch, inputs, differing, refusal):
    bars, reads = _faked(monkeypatch)
    arm_b = {a: list(held) for a, held in inputs.arm_a.items()}
    if differing:
        arm_b["BTC"][-1] = 0.25

    with pytest.raises(ValidationError) as refused:
        subjects._c3_reentry_metrics(inputs._replace(arm_b=arm_b), n_trials=1)

    assert str(refused.value) == refusal and not bars and not reads


def test_the_c3_reentry_trial_refuses_an_arm_a_that_never_draws_down_before_any_bar(monkeypatch, inputs):
    bars, reads = _faked(monkeypatch)
    n = len(inputs.close)
    flat = {a: [0.0] * n for a in ASSETS}
    arm_b = flat | {"BTC": [0.0] * 300 + [0.25] * (n - 300)}

    with pytest.raises(ValidationError) as refused:
        subjects._c3_reentry_metrics(inputs._replace(arm_a=flat, arm_b=arm_b), n_trials=1)

    assert str(refused.value) == (
        "arm A never draws down from the re-entry's first engagement, so max_drawdown_reduction_pct divides by zero"
    )
    assert not bars and not reads


def test_the_c3_reentry_preflight_reads_arm_as_anchors_and_bar_and_the_engagement_and_costs_no_arm_b(monkeypatch, inputs):
    bars, reads = _faked(monkeypatch)
    costed = _recording(monkeypatch, "net_of_cost", lambda arguments, result: result)
    arm_a = _own_books()[0]
    net_a, net_a_x15 = _own_net(arm_a, inputs.returns, 0.006), _own_net(arm_a, inputs.returns, 1.5 * 0.006)
    bench = _fake_system(inputs.daily_prices, config=subjects._RECORD33_CONFIG).benchmark_net_of_cost
    bar = _own_bar(net_a, net_a_x15, bench, inputs.daily_ts, 17, 42)
    turnover_a = subjects.book_turnover(arm_a)

    metrics = subjects._c3_reentry_preflight_metrics(inputs, n_trials=1)

    assert metrics == {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=365),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[230:], periods_per_year=365),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / (N_DAYS - 1) * 0.006 * 365,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=365),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[230:], periods_per_year=365),
        **{key: bar[key] for key in ARM_A_BAR_KEYS},
        **subjects._c3_reentry_engagement(inputs),
    }
    assert [(call[0]["asset_positions"], call[0]["cost_per_side"]) for call in costed] == [(arm_a, 0.006), (arm_a, 1.5 * 0.006)]
    assert len(bars) == 1 and not reads
