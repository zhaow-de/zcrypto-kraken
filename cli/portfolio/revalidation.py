"""Record 47's revalidation scoring (spec 00152 D3–D6): its governed book on the returns after the spent holdout, against
the band of same-length windows its decisive in-sample window draws. Return `i` runs from bar `i`'s close to bar
`i + 1`'s, the stamps being bar opens."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from cli.validation import deflated_sharpe_ratio, max_drawdown, sharpe

SLICE_START = datetime(2026, 7, 10, tzinfo=UTC)
REFERENCE_LAST_BAR = datetime(2026, 3, 31, 20, tzinfo=UTC)
DECISIVE_START = 1380
BAND_STEP = 6
MIN_SLICE = 180
RECORD_47_RETURNS = 27337
RECORD_47_SHARPE = 1.5609
SHARPE_TOLERANCE = 0.00005
BENCH_COST_PER_SIDE = 0.006
PPY_4H = 2190
# The `var_trials_4h` records 43, 44 and 47 carry (spec D6).
P1_VAR_TRIALS = 1.3058096692086857e-05

METRIC_KEYS: frozenset[str] = frozenset(
    {
        "in_sample_returns",
        "in_sample_sharpe",
        "reference_returns",
        "slice_returns",
        "band_windows",
        "band_sharpe_q05",
        "band_maxdd_q95",
        "slice_sharpe",
        "slice_maxdd",
        "slice_sharpe_rank",
        "slice_sharpe_ungoverned",
        "slice_bench4h_sharpe",
        "slice_mean_diff_vs_bench4h",
        "slice_dsr",
        "leg_sharpe_pass",
        "leg_maxdd_pass",
    }
)


class RevalidationError(Exception):
    pass


@dataclass(frozen=True)
class Band:
    sharpe_q05: float
    maxdd_q95: float
    sharpes: tuple[float, ...]


def slice_bounds(h4_ts: list[datetime], start: datetime) -> tuple[int, int]:
    hi = len(h4_ts) - 1
    lo = next((i for i in range(hi) if h4_ts[i] >= start), hi)
    return lo, hi


def prefix_end(h4_ts: list[datetime], last_bar: datetime) -> int:
    return sum(1 for i in range(len(h4_ts) - 1) if h4_ts[i + 1] <= last_bar)


def band(reference: list[float], length: int, *, step: int) -> Band:
    windows = [reference[s : s + length] for s in range(0, len(reference), step) if s + length <= len(reference)]
    if not windows:
        raise RevalidationError(f"the reference's {len(reference)} returns hold no window of {length}")
    sharpes = tuple(sharpe(w, periods_per_year=PPY_4H) for w in windows)
    # A float, never numpy.float64: the registry's validate_metrics refuses a numpy leaf.
    return Band(
        sharpe_q05=float(np.percentile(sharpes, 5)),
        maxdd_q95=float(np.percentile([max_drawdown(w) for w in windows], 95)),
        sharpes=sharpes,
    )


def legs(slice_sharpe: float, slice_maxdd: float, band: Band) -> tuple[int, int]:
    return int(slice_sharpe >= band.sharpe_q05), int(slice_maxdd <= band.maxdd_q95)


def revalidation_metrics(
    governed: list[float], ungoverned: list[float], bench: list[float], h4_ts: list[datetime], *, n_trials: int
) -> dict:
    lo, hi = slice_bounds(h4_ts, SLICE_START)
    slice_returns = hi - lo
    # Refused before the band: at 0 returns a band of length 0 would raise sharpe's ValidationError instead.
    if slice_returns < MIN_SLICE:
        raise RevalidationError(
            f"the slice from {SLICE_START:%Y-%m-%d %H:%M}Z holds {slice_returns} returns, fewer than the {MIN_SLICE} it needs"
        )
    in_sample_returns = prefix_end(h4_ts, REFERENCE_LAST_BAR)
    reference = governed[DECISIVE_START:in_sample_returns]
    # Not `band`: assigning that name makes this line's call to band() raise UnboundLocalError.
    ref_band = band(reference, slice_returns, step=BAND_STEP)
    band_windows = len(ref_band.sharpes)
    slice_sharpe = sharpe(governed[lo:hi], periods_per_year=PPY_4H)
    slice_maxdd = max_drawdown(governed[lo:hi])
    leg_sharpe_pass, leg_maxdd_pass = legs(slice_sharpe, slice_maxdd, ref_band)
    return {
        "in_sample_returns": in_sample_returns,
        "in_sample_sharpe": sharpe(governed[:in_sample_returns], periods_per_year=PPY_4H),
        "reference_returns": len(reference),
        "slice_returns": slice_returns,
        "band_windows": band_windows,
        "band_sharpe_q05": ref_band.sharpe_q05,
        "band_maxdd_q95": ref_band.maxdd_q95,
        "slice_sharpe": slice_sharpe,
        "slice_maxdd": slice_maxdd,
        "slice_sharpe_rank": sum(s <= slice_sharpe for s in ref_band.sharpes) / band_windows,
        "slice_sharpe_ungoverned": sharpe(ungoverned[lo:hi], periods_per_year=PPY_4H),
        # A flat benchmark slice reads 0.0, decided before sharpe, which refuses zero variance (spec D6).
        "slice_bench4h_sharpe": 0.0 if not any(bench[lo:hi]) else sharpe(bench[lo:hi], periods_per_year=PPY_4H),
        "slice_mean_diff_vs_bench4h": statistics.fmean(governed[lo:hi]) - statistics.fmean(bench[lo:hi]),
        # The per-period Sharpe, never the annualized one.
        "slice_dsr": deflated_sharpe_ratio(sharpe(governed[lo:hi]), slice_returns, n_trials=n_trials, var_trials=P1_VAR_TRIALS),
        "leg_sharpe_pass": leg_sharpe_pass,
        "leg_maxdd_pass": leg_maxdd_pass,
    }


def revalidation_verdict(metrics: dict) -> str | None:
    # Off record 47's prefix the set no longer rebuilds its book: an instrument finding, no verdict (spec D5).
    if metrics["in_sample_returns"] == RECORD_47_RETURNS and abs(metrics["in_sample_sharpe"] - RECORD_47_SHARPE) < SHARPE_TOLERANCE:
        return "adopt" if metrics["leg_sharpe_pass"] and metrics["leg_maxdd_pass"] else "park"
    return None
