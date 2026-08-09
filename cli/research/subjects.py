"""The evaluable subjects: committed systems, each named by the registry record it reproduces.

A subject declares the series it needs (`assets` x `intervals`) so the command can refuse an
incomplete dataset before opening a single file, and a `build` that runs the system through the
capturing loader — every byte a fit sees is read via `ObservedReader`, which is what makes the
resulting `datasets` block the run's identity rather than a claim about it (spec 00086 D1).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cli.portfolio.builder import build_combined_system
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, build_crossfreq_system_fast
from cli.portfolio.record44_legs import load_union
from cli.registry.observed import ObservedReader
from cli.validation import sharpe

PPY_DAILY = 365
PPY_4H = 2190


@dataclass(frozen=True)
class Subject:
    name: str
    intervals: tuple[int, ...]
    assets: tuple[str, ...]
    build: Callable[[ObservedReader, str, tuple | None], dict]


def required_relpaths(subject: Subject) -> list[str]:
    """Every series the subject reads, as dataset-relative paths."""
    return [f"{a}/EUR/{i}.parquet" for a in subject.assets for i in subject.intervals]


def _capturing_union(reader: ObservedReader, dataset: str, interval: int, window: tuple[str, str] | None):
    """`load_union` reading through the capturing loader, with the window applied at the read.

    The root passed to `load_union` is a bare relative prefix, so the paths it composes ARE the
    dataset-relative keys the reader wants — no data root needs to travel down here. The window MUST
    be forwarded: drop it and the fit silently runs on full history while the recorded block, built
    from the same reads, stays perfectly self-consistent about it.
    """
    return load_union(
        interval,
        root=Path(),
        read=lambda path: reader.read_series(dataset, path.as_posix(), window=window),
    )


def _build_crossfreq(reader: ObservedReader, dataset: str, window: tuple[str, str] | None) -> dict:
    config = CrossfreqSystemConfig()
    daily_ts, daily_prices = _capturing_union(reader, dataset, 1440, window)
    h4_ts, h4_prices = _capturing_union(reader, dataset, 240, window)
    result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=config)
    return {
        "ann_sharpe_noc": sharpe(result.governed_net, periods_per_year=PPY_4H),
        "per_period_sharpe_4h": sharpe(result.governed_net),
        "ann_sharpe_ungoverned": sharpe(result.ungoverned_net, periods_per_year=PPY_4H),
        "cap_breach_bars": result.cap_breach_bars,
        "governor_engaged_bars": result.governor_engaged_bars,
        "n_periods": result.n_periods,
    }


def _build_combined(reader: ObservedReader, dataset: str, window: tuple[str, str] | None) -> dict:
    _, daily_prices = _capturing_union(reader, dataset, 1440, window)
    result = build_combined_system(daily_prices)
    return {
        "ann_sharpe_noc": sharpe(result.net_of_cost, periods_per_year=PPY_DAILY),
        "per_period_sharpe": sharpe(result.net_of_cost),
        "bench_ann_sharpe": sharpe(result.benchmark_net_of_cost, periods_per_year=PPY_DAILY),
        "cap_breach_bars": result.cap_breach_bars,
        "n_periods": result.n_periods,
    }


_ASSETS = CrossfreqSystemConfig().assets

SUBJECTS: dict[str, Subject] = {
    "record44-crossfreq": Subject("record44-crossfreq", (1440, 240), _ASSETS, _build_crossfreq),
    "record33-combined": Subject("record33-combined", (1440,), _ASSETS, _build_combined),
}
