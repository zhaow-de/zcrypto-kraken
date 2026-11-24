from datetime import timedelta
from pathlib import Path

import pytest

from cli.onchain.freeze import SNAPSHOT_RELPATH
from cli.onchain.series import priced
from cli.registry.observed import ObservedReader
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
SUBJECT = "c3-onchain-reading"
DATASET = "btc-onchain-20261124T162656Z"

# Read from the snapshot and ohlc-full by plan 00164's Task 6 and Task 7 rules, never through subjects.py.
FEATURE_BASIS = {
    "mvrv": {
        "first": 20130909,
        "last": 20260330,
        "band_days": {
            "2013": {"low": 0, "mid": 83, "high": 27},
            "2014": {"low": 12, "mid": 353, "high": 0},
            "2015": {"low": 124, "mid": 241, "high": 0},
            "2016": {"low": 0, "mid": 366, "high": 0},
            "2017": {"low": 0, "mid": 288, "high": 77},
            "2018": {"low": 28, "mid": 335, "high": 2},
            "2019": {"low": 43, "mid": 322, "high": 0},
            "2020": {"low": 0, "mid": 360, "high": 6},
            "2021": {"low": 0, "mid": 273, "high": 92},
            "2022": {"low": 65, "mid": 300, "high": 0},
            "2023": {"low": 8, "mid": 357, "high": 0},
            "2024": {"low": 0, "mid": 366, "high": 0},
            "2025": {"low": 0, "mid": 365, "high": 0},
            "2026": {"low": 0, "mid": 89, "high": 0},
        },
    },
    "mvrv_z": {
        "first": 20130909,
        "last": 20260330,
        "band_days": {
            "2013": {"low": 0, "mid": 72, "high": 38},
            "2014": {"low": 38, "mid": 327, "high": 0},
            "2015": {"low": 195, "mid": 170, "high": 0},
            "2016": {"low": 0, "mid": 366, "high": 0},
            "2017": {"low": 0, "mid": 128, "high": 237},
            "2018": {"low": 41, "mid": 314, "high": 10},
            "2019": {"low": 54, "mid": 311, "high": 0},
            "2020": {"low": 1, "mid": 350, "high": 15},
            "2021": {"low": 0, "mid": 253, "high": 112},
            "2022": {"low": 122, "mid": 243, "high": 0},
            "2023": {"low": 10, "mid": 355, "high": 0},
            "2024": {"low": 0, "mid": 366, "high": 0},
            "2025": {"low": 0, "mid": 365, "high": 0},
            "2026": {"low": 0, "mid": 89, "high": 0},
        },
    },
    "asopr": {
        "first": 20130909,
        "last": 20260330,
        "band_days": {
            "2013": {"low": 2, "mid": 82, "high": 26},
            "2014": {"low": 65, "mid": 296, "high": 4},
            "2015": {"low": 39, "mid": 325, "high": 1},
            "2016": {"low": 2, "mid": 363, "high": 1},
            "2017": {"low": 2, "mid": 303, "high": 60},
            "2018": {"low": 73, "mid": 286, "high": 6},
            "2019": {"low": 29, "mid": 316, "high": 20},
            "2020": {"low": 13, "mid": 331, "high": 22},
            "2021": {"low": 12, "mid": 312, "high": 41},
            "2022": {"low": 59, "mid": 306, "high": 0},
            "2023": {"low": 7, "mid": 356, "high": 2},
            "2024": {"low": 1, "mid": 324, "high": 41},
            "2025": {"low": 2, "mid": 351, "high": 12},
            "2026": {"low": 13, "mid": 76, "high": 0},
        },
    },
    "sth_supply_share": {
        "first": 20130909,
        "last": 20260330,
        "band_days": {
            "2013": {"low": 56, "mid": 54, "high": 0},
            "2014": {"low": 231, "mid": 134, "high": 0},
            "2015": {"low": 239, "mid": 126, "high": 0},
            "2016": {"low": 40, "mid": 326, "high": 0},
            "2017": {"low": 3, "mid": 350, "high": 12},
            "2018": {"low": 128, "mid": 237, "high": 0},
            "2019": {"low": 17, "mid": 348, "high": 0},
            "2020": {"low": 191, "mid": 175, "high": 0},
            "2021": {"low": 114, "mid": 251, "high": 0},
            "2022": {"low": 356, "mid": 9, "high": 0},
            "2023": {"low": 356, "mid": 9, "high": 0},
            "2024": {"low": 154, "mid": 212, "high": 0},
            "2025": {"low": 60, "mid": 305, "high": 0},
            "2026": {"low": 0, "mid": 89, "high": 0},
        },
    },
}
ARM_BASIS = {
    "ADA": {"long": 1195, "flat": 1547},
    "AVAX": {"long": 578, "flat": 984},
    "BTC": {"long": 2507, "flat": 2075},
    "DOGE": {"long": 1060, "flat": 1235},
    "DOT": {"long": 849, "flat": 1203},
    "ETH": {"long": 2240, "flat": 1650},
    "LINK": {"long": 1184, "flat": 1196},
    "LTC": {"long": 2138, "flat": 2404},
    "SOL": {"long": 907, "flat": 842},
    "XRP": {"long": 1450, "flat": 1789},
}
COUNT_BASIS = {
    "mvrv|low|long": {
        "ADA": {"events": 0, "others": 1195},
        "AVAX": {"events": 0, "others": 578},
        "BTC": {"events": 2, "others": 2505},
        "DOGE": {"events": 0, "others": 1060},
        "DOT": {"events": 0, "others": 849},
        "ETH": {"events": 0, "others": 2240},
        "LINK": {"events": 0, "others": 1184},
        "LTC": {"events": 2, "others": 2136},
        "SOL": {"events": 0, "others": 907},
        "XRP": {"events": 0, "others": 1450},
    },
    "mvrv|low|flat": {
        "ADA": {"events": 144, "others": 1403},
        "AVAX": {"events": 73, "others": 911},
        "BTC": {"events": 278, "others": 1797},
        "DOGE": {"events": 73, "others": 1162},
        "DOT": {"events": 73, "others": 1130},
        "ETH": {"events": 146, "others": 1504},
        "LINK": {"events": 73, "others": 1123},
        "LTC": {"events": 278, "others": 2126},
        "SOL": {"events": 73, "others": 769},
        "XRP": {"events": 144, "others": 1645},
    },
    "mvrv|high|long": {
        "ADA": {"events": 98, "others": 1097},
        "AVAX": {"events": 0, "others": 578},
        "BTC": {"events": 177, "others": 2330},
        "DOGE": {"events": 98, "others": 962},
        "DOT": {"events": 98, "others": 751},
        "ETH": {"events": 177, "others": 2063},
        "LINK": {"events": 97, "others": 1087},
        "LTC": {"events": 177, "others": 1961},
        "SOL": {"events": 0, "others": 907},
        "XRP": {"events": 133, "others": 1317},
    },
    "mvrv|high|flat": {
        "ADA": {"events": 0, "others": 1547},
        "AVAX": {"events": 0, "others": 984},
        "BTC": {"events": 27, "others": 2048},
        "DOGE": {"events": 0, "others": 1235},
        "DOT": {"events": 0, "others": 1203},
        "ETH": {"events": 0, "others": 1650},
        "LINK": {"events": 1, "others": 1195},
        "LTC": {"events": 27, "others": 2377},
        "SOL": {"events": 0, "others": 842},
        "XRP": {"events": 43, "others": 1746},
    },
    "mvrv_z|low|long": {
        "ADA": {"events": 0, "others": 1195},
        "AVAX": {"events": 0, "others": 578},
        "BTC": {"events": 15, "others": 2492},
        "DOGE": {"events": 0, "others": 1060},
        "DOT": {"events": 0, "others": 849},
        "ETH": {"events": 0, "others": 2240},
        "LINK": {"events": 0, "others": 1184},
        "LTC": {"events": 15, "others": 2123},
        "SOL": {"events": 0, "others": 907},
        "XRP": {"events": 0, "others": 1450},
    },
    "mvrv_z|low|flat": {
        "ADA": {"events": 228, "others": 1319},
        "AVAX": {"events": 132, "others": 852},
        "BTC": {"events": 446, "others": 1629},
        "DOGE": {"events": 133, "others": 1102},
        "DOT": {"events": 132, "others": 1071},
        "ETH": {"events": 253, "others": 1397},
        "LINK": {"events": 133, "others": 1063},
        "LTC": {"events": 446, "others": 1958},
        "SOL": {"events": 132, "others": 710},
        "XRP": {"events": 228, "others": 1561},
    },
    "mvrv_z|high|long": {
        "ADA": {"events": 127, "others": 1068},
        "AVAX": {"events": 0, "others": 578},
        "BTC": {"events": 374, "others": 2133},
        "DOGE": {"events": 127, "others": 933},
        "DOT": {"events": 127, "others": 722},
        "ETH": {"events": 374, "others": 1866},
        "LINK": {"events": 124, "others": 1060},
        "LTC": {"events": 374, "others": 1764},
        "SOL": {"events": 0, "others": 907},
        "XRP": {"events": 231, "others": 1219},
    },
    "mvrv_z|high|flat": {
        "ADA": {"events": 0, "others": 1547},
        "AVAX": {"events": 0, "others": 984},
        "BTC": {"events": 38, "others": 2037},
        "DOGE": {"events": 0, "others": 1235},
        "DOT": {"events": 0, "others": 1203},
        "ETH": {"events": 0, "others": 1650},
        "LINK": {"events": 3, "others": 1193},
        "LTC": {"events": 38, "others": 2366},
        "SOL": {"events": 0, "others": 842},
        "XRP": {"events": 104, "others": 1685},
    },
    "asopr|low|long": {
        "ADA": {"events": 15, "others": 1180},
        "AVAX": {"events": 4, "others": 574},
        "BTC": {"events": 29, "others": 2478},
        "DOGE": {"events": 10, "others": 1050},
        "DOT": {"events": 10, "others": 839},
        "ETH": {"events": 37, "others": 2203},
        "LINK": {"events": 17, "others": 1167},
        "LTC": {"events": 29, "others": 2109},
        "SOL": {"events": 8, "others": 899},
        "XRP": {"events": 17, "others": 1433},
    },
    "asopr|low|flat": {
        "ADA": {"events": 153, "others": 1394},
        "AVAX": {"events": 78, "others": 906},
        "BTC": {"events": 290, "others": 1785},
        "DOGE": {"events": 99, "others": 1136},
        "DOT": {"events": 84, "others": 1119},
        "ETH": {"events": 181, "others": 1469},
        "LINK": {"events": 100, "others": 1096},
        "LTC": {"events": 290, "others": 2114},
        "SOL": {"events": 80, "others": 762},
        "XRP": {"events": 194, "others": 1595},
    },
    "asopr|high|long": {
        "ADA": {"events": 117, "others": 1078},
        "AVAX": {"events": 48, "others": 530},
        "BTC": {"events": 194, "others": 2313},
        "DOGE": {"events": 105, "others": 955},
        "DOT": {"events": 100, "others": 749},
        "ETH": {"events": 188, "others": 2052},
        "LINK": {"events": 102, "others": 1082},
        "LTC": {"events": 188, "others": 1950},
        "SOL": {"events": 53, "others": 854},
        "XRP": {"events": 149, "others": 1301},
    },
    "asopr|high|flat": {
        "ADA": {"events": 22, "others": 1525},
        "AVAX": {"events": 7, "others": 977},
        "BTC": {"events": 42, "others": 2033},
        "DOGE": {"events": 13, "others": 1222},
        "DOT": {"events": 17, "others": 1186},
        "ETH": {"events": 18, "others": 1632},
        "LINK": {"events": 17, "others": 1179},
        "LTC": {"events": 45, "others": 2359},
        "SOL": {"events": 10, "others": 832},
        "XRP": {"events": 53, "others": 1736},
    },
    "sth_supply_share|low|long": {
        "ADA": {"events": 530, "others": 665},
        "AVAX": {"events": 308, "others": 270},
        "BTC": {"events": 879, "others": 1628},
        "DOGE": {"events": 491, "others": 569},
        "DOT": {"events": 389, "others": 460},
        "ETH": {"events": 703, "others": 1537},
        "LINK": {"events": 581, "others": 603},
        "LTC": {"events": 685, "others": 1453},
        "SOL": {"events": 509, "others": 398},
        "XRP": {"events": 594, "others": 856},
    },
    "sth_supply_share|low|flat": {
        "ADA": {"events": 786, "others": 761},
        "AVAX": {"events": 630, "others": 354},
        "BTC": {"events": 1066, "others": 1009},
        "DOGE": {"events": 746, "others": 489},
        "DOT": {"events": 729, "others": 474},
        "ETH": {"events": 814, "others": 836},
        "LINK": {"events": 656, "others": 540},
        "LTC": {"events": 1226, "others": 1178},
        "SOL": {"events": 531, "others": 311},
        "XRP": {"events": 782, "others": 1007},
    },
    "sth_supply_share|high|long": {
        "ADA": {"events": 0, "others": 1195},
        "AVAX": {"events": 0, "others": 578},
        "BTC": {"events": 12, "others": 2495},
        "DOGE": {"events": 0, "others": 1060},
        "DOT": {"events": 0, "others": 849},
        "ETH": {"events": 12, "others": 2228},
        "LINK": {"events": 0, "others": 1184},
        "LTC": {"events": 12, "others": 2126},
        "SOL": {"events": 0, "others": 907},
        "XRP": {"events": 12, "others": 1438},
    },
    "sth_supply_share|high|flat": {
        "ADA": {"events": 0, "others": 1547},
        "AVAX": {"events": 0, "others": 984},
        "BTC": {"events": 0, "others": 2075},
        "DOGE": {"events": 0, "others": 1235},
        "DOT": {"events": 0, "others": 1203},
        "ETH": {"events": 0, "others": 1650},
        "LINK": {"events": 0, "others": 1196},
        "LTC": {"events": 0, "others": 2404},
        "SOL": {"events": 0, "others": 842},
        "XRP": {"events": 0, "others": 1789},
    },
}

IDENTITY_DAYS = 4582
# docs/specs/00164 D12's bound: BRK's realized price held to the cent, mvrv stored in parts per million, and nupl
# rounded to them.
HALF_CENT = 0.005
PPM = 1e-6


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "btc-onchain-*/BTC/onchain.parquet"),
    reason="the frozen btc-onchain snapshot is absent under data/",
)
def test_the_inputs_half_reads_the_snapshots_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    _, snapshot, daily_ts, daily_prices = subjects._c3_reads(ObservedReader(_DATA_ROOT), DATASET, SUBJECT)
    inputs = subjects._c3_reading_inputs(snapshot, daily_ts, daily_prices)
    # Never the computes half here: docs/specs/00164 D12's hash rule.
    assert {f: {k: v for k, v in block.items() if k != "values"} for f, block in inputs.features.items()} == FEATURE_BASIS
    assert inputs.arm == ARM_BASIS
    assert inputs.counts == COUNT_BASIS


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "btc-onchain-*/BTC/onchain.parquet"),
    reason="the frozen btc-onchain snapshot is absent under data/",
)
def test_mvrv_and_nupl_are_the_cap_ratios_within_brks_rounding_on_the_days_the_cells_read():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader = ObservedReader(_DATA_ROOT)
    _, _, daily_ts, _ = subjects._c3_reads(reader, DATASET, SUBJECT)
    snapshot = reader.read_series(DATASET, SNAPSHOT_RELPATH)
    by_day = {row["ts"].date(): row for row in snapshot.iter_rows(named=True)}
    read = [by_day[stamp.date() - timedelta(days=1)] for stamp in daily_ts]
    checked = [row for row in read if priced(row["mvrv"]) and priced(row["realized_cap"])]
    assert len(checked) == IDENTITY_DAYS
    for row in checked:
        ratio = row["market_cap"] / row["realized_cap"]
        bound = ratio * HALF_CENT / (row["realized_cap"] / row["supply"] - HALF_CENT) + PPM
        assert abs(row["mvrv"] - ratio) <= bound, row["ts"]
        assert abs(row["nupl"] - (1 - 1 / row["mvrv"])) <= bound / (row["mvrv"] * ratio) + PPM / 2, row["ts"]
