from cli.engine.soak import governor_engaged_daily, structural_metrics


def test_structural_metrics_basic():
    bars = [
        {"BTC": 0.10, "ETH": -0.05, "SOL": 0.0},
        {"BTC": 0.20, "ETH": 0.0, "SOL": 0.10},
    ]
    m = structural_metrics(bars, long_cap=0.20, short_cap=0.10)
    assert m["gross"] == [0.15, 0.30]
    assert m["net"][0] == 0.05 and abs(m["net"][1] - 0.30) < 1e-12
    assert m["active_frac"] == [2 / 3, 2 / 3]
    # turnover bar0: |0.10|+|-0.05|+0 = 0.15 (prev=0); bar1: |0.20-0.10|+|0.0-(-0.05)|+|0.10-0.0| = 0.25
    assert abs(m["turnover"][0] - 0.15) < 1e-12
    assert abs(m["turnover"][1] - 0.25) < 1e-12
    # hhi bar0: (0.10/0.15)^2 + (0.05/0.15)^2 = (2/3)^2 + (1/3)^2
    assert abs(m["hhi"][0] - ((2 / 3) ** 2 + (1 / 3) ** 2)) < 1e-12
    assert m["cap_breach"] == [0.0, 0.0]


def test_structural_metrics_cap_breach_flagged():
    bars = [{"BTC": 0.25, "ETH": -0.15}]  # both beyond 0.20 / -0.10
    m = structural_metrics(bars, long_cap=0.20, short_cap=0.10)
    assert m["cap_breach"] == [1.0]


def test_structural_metrics_empty():
    m = structural_metrics([], long_cap=0.20, short_cap=0.10)
    assert m["gross"] == [] and m["turnover"] == [] and m["hhi"] == []


def test_governor_engaged_daily():
    mult = [1.0, 1.0, 0.5, 1.0, 1.0, 1.0]
    day_index = [0, 0, 0, 1, 1, 1]
    assert governor_engaged_daily(mult, day_index) == [1.0, 0.0]  # day 0 engaged, day 1 not
