from cli.validation.bootstrap import bootstrap_ci, stationary_bootstrap_indices
from cli.validation.cpcv import cpcv_splits, make_groups, n_backtest_paths
from cli.validation.dsr import deflated_sharpe_ratio, expected_max_sharpe, probabilistic_sharpe_ratio
from cli.validation.errors import ValidationError
from cli.validation.metrics import annualized_return, max_drawdown, sharpe, volatility
from cli.validation.pbo import pbo
from cli.validation.spa import reality_check_pvalue
from cli.validation.synthetic import (
    linear_signal,
    nn_leak_metric,
    outperformance_matrix,
    overlapping_label_series,
    sign_strategy_returns,
)

__all__ = [
    "ValidationError",
    "annualized_return",
    "bootstrap_ci",
    "cpcv_splits",
    "deflated_sharpe_ratio",
    "expected_max_sharpe",
    "linear_signal",
    "make_groups",
    "max_drawdown",
    "n_backtest_paths",
    "nn_leak_metric",
    "outperformance_matrix",
    "overlapping_label_series",
    "pbo",
    "probabilistic_sharpe_ratio",
    "reality_check_pvalue",
    "sharpe",
    "sign_strategy_returns",
    "stationary_bootstrap_indices",
    "volatility",
]
