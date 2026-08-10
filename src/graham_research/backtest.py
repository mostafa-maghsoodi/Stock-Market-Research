"""Small, governance-gated portfolio test engine for frozen specifications."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

from .governance import require_entry_001


class BacktestInputError(ValueError):
    pass


@dataclass(frozen=True)
class BacktestResult:
    periods: pd.DataFrame
    positions: pd.DataFrame
    mean_gross_return: float
    mean_net_return: float
    cumulative_net_return: float
    mean_traded_notional: float
    runtime_warnings: tuple[str, ...]


def run_equal_weight_backtest(
    ranked_returns: pd.DataFrame,
    entry_001_path: str | Path,
    top_n: int,
) -> BacktestResult:
    """Run only after verifying the complete Entry 001 freeze.

    ``forward_total_return`` must already include delisting returns and be
    aligned to the frozen holding-period convention. This engine deliberately
    refuses to synthesize missing returns or infer an investment universe.
    """

    entry_001, runtime_validation = require_entry_001(entry_001_path)
    if top_n <= 0:
        raise BacktestInputError("top_n must be positive")
    cost_model = entry_001["transaction_cost_model"]
    if not isinstance(cost_model, dict):
        raise BacktestInputError("transaction_cost_model must be an object")
    convention = cost_model.get("convention")
    if convention != "traded_notional_times_one_way_bps":
        raise BacktestInputError(
            "transaction_cost_model.convention must be "
            "'traded_notional_times_one_way_bps'"
        )
    one_way_cost_bps = cost_model.get("one_way_cost_bps")
    if (
        not isinstance(one_way_cost_bps, (int, float))
        or isinstance(one_way_cost_bps, bool)
        or not np.isfinite(one_way_cost_bps)
        or one_way_cost_bps < 0
    ):
        raise BacktestInputError(
            "transaction_cost_model.one_way_cost_bps must be a finite non-negative number"
        )
    required = {"decision_date", "security_id", "composite_score", "forward_total_return"}
    missing = required - set(ranked_returns.columns)
    if missing:
        raise BacktestInputError(f"missing columns: {sorted(missing)}")
    if ranked_returns.duplicated(["decision_date", "security_id"]).any():
        raise BacktestInputError("duplicate security/date rows")
    if ranked_returns[list(required)].isna().any().any():
        raise BacktestInputError("required backtest inputs contain missing values")
    if not np.isfinite(ranked_returns["forward_total_return"].astype(float)).all():
        raise BacktestInputError("returns must be finite")

    ranked = ranked_returns.sort_values(
        ["decision_date", "composite_score", "security_id"],
        ascending=[True, False, True],
    )
    positions = ranked.groupby("decision_date", group_keys=False).head(top_n).copy()
    counts = positions.groupby("decision_date")["security_id"].transform("count")
    positions["weight"] = 1.0 / counts

    prior_weights: dict[str, float] = {}
    period_rows: list[dict[str, object]] = []
    for decision_date, group in positions.groupby("decision_date", sort=True):
        current = dict(zip(group["security_id"], group["weight"], strict=True))
        names = set(prior_weights) | set(current)
        # Convention frozen in Entry 001: charge every dollar bought or sold.
        # From cash, initial deployment trades 1.0 notional. A complete switch
        # between disjoint fully invested portfolios trades 2.0 notional.
        traded_notional = sum(
            abs(current.get(name, 0.0) - prior_weights.get(name, 0.0))
            for name in names
        )
        gross = float((group["weight"] * group["forward_total_return"]).sum())
        cost = traded_notional * float(one_way_cost_bps) / 10_000.0
        period_rows.append({
            "decision_date": decision_date,
            "gross_return": gross,
            "traded_notional": traded_notional,
            "cost": cost,
            "net_return": gross - cost,
            "holdings": len(group),
        })
        prior_weights = current

    periods = pd.DataFrame(period_rows)
    if periods.empty:
        raise BacktestInputError("no eligible portfolio periods")
    cumulative = float((1.0 + periods["net_return"]).prod() - 1.0)
    return BacktestResult(
        periods=periods,
        positions=positions,
        mean_gross_return=float(periods["gross_return"].mean()),
        mean_net_return=float(periods["net_return"].mean()),
        cumulative_net_return=cumulative,
        mean_traded_notional=float(periods["traded_notional"].mean()),
        runtime_warnings=runtime_validation.warnings,
    )
