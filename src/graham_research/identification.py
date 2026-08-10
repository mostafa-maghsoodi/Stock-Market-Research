"""Identification, redundancy, and Rule #17 diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Rule17Result:
    established: bool
    reason: str
    k: int
    q25: float | None
    q75: float | None
    iqr: float | None
    q75_over_q25: float | None


def rule17(delta_values: Iterable[float]) -> Rule17Result:
    """Apply the exact control-definition robustness criterion.

    NaN and infinite values are rejected, rather than silently reducing k.
    """

    values = np.asarray(tuple(delta_values), dtype=float)
    k = int(values.size)
    if k < 5:
        return Rule17Result(
            established=False,
            reason="k<5: independence is not established for this research cycle",
            k=k,
            q25=None,
            q75=None,
            iqr=None,
            q75_over_q25=None,
        )
    if not np.isfinite(values).all():
        raise ValueError("Rule #17 requires finite delta values")
    q25, q75 = np.percentile(values, [25, 75], method="linear")
    iqr = float(q75 - q25)
    passed = bool(q25 > 0 and q25 > iqr)
    return Rule17Result(
        established=passed,
        reason="passed" if passed else "failed Q25 > 0 and Q25 > IQR",
        k=k,
        q25=float(q25),
        q75=float(q75),
        iqr=iqr,
        q75_over_q25=float(q75 / q25) if q25 != 0 else None,
    )


def spearman_rank_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("series lengths differ")
    frame = pd.DataFrame({"left": left, "right": right}).dropna()
    if len(frame) < 3:
        raise ValueError("at least three paired observations are required")
    # Spearman is Pearson correlation of average ranks. Calculating it
    # directly avoids an undeclared SciPy dependency while preserving ties.
    left_ranks = frame["left"].rank(method="average").to_numpy(dtype=float)
    right_ranks = frame["right"].rank(method="average").to_numpy(dtype=float)
    value = float(np.corrcoef(left_ranks, right_ranks)[0, 1])
    if not np.isfinite(value):
        raise ValueError("correlation is undefined for a constant series")
    return value


@dataclass(frozen=True)
class RankICResult:
    """Per-date cross-sectional ICs and their time-series summary.

    ``diagnostic_iid_t_stat`` uses the plain sample standard error across dates. It is
    unadjusted for autocorrelation or overlapping holding periods and must not
    substitute for the frozen dependence treatment in Entry 001.
    """

    per_date: pd.Series
    mean: float | None
    std: float | None
    count: int
    diagnostic_iid_t_stat: float | None
    dates_total: int
    t_stat_method: str = "unadjusted_iid_time_series_standard_error"


def _summarize_ic_series(values: pd.Series) -> RankICResult:
    numeric = pd.to_numeric(values, errors="coerce").astype(float)
    valid = numeric.dropna()
    count = int(len(valid))
    mean = float(valid.mean()) if count else None
    std = float(valid.std(ddof=1)) if count >= 2 else None
    diagnostic_iid_t_stat = (
        float(mean / (std / np.sqrt(count)))
        if mean is not None and std is not None and std > 0
        else None
    )
    return RankICResult(
        per_date=numeric,
        mean=mean,
        std=std,
        count=count,
        diagnostic_iid_t_stat=diagnostic_iid_t_stat,
        dates_total=int(len(numeric)),
    )


def rank_ic(
    panel: pd.DataFrame,
    signal_col: str = "signal",
    return_col: str = "forward_return",
    date_col: str = "decision_date",
    minimum_cross_section: int = 3,
) -> RankICResult:
    """Calculate Spearman IC independently within each decision date.

    A flat pair of arrays is intentionally not accepted: pooling a panel would
    allow time-series shifts in signal and return levels to masquerade as
    cross-sectional information.
    """

    if not isinstance(panel, pd.DataFrame):
        raise TypeError("rank_ic requires a panel DataFrame with decision dates")
    if minimum_cross_section < 3:
        raise ValueError("minimum_cross_section must be at least 3")
    required = {date_col, signal_col, return_col}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise ValueError(f"rank IC panel is missing columns: {missing}")
    if panel.empty:
        return _summarize_ic_series(pd.Series(dtype=float, name="rank_ic"))

    results: dict[object, float] = {}
    for decision_date, group in panel.groupby(date_col, sort=True, dropna=False):
        paired = group[[signal_col, return_col]].dropna()
        if len(paired) < minimum_cross_section:
            results[decision_date] = np.nan
            continue
        try:
            results[decision_date] = spearman_rank_correlation(
                paired[signal_col].to_numpy(),
                paired[return_col].to_numpy(),
            )
        except ValueError:
            # A constant signal or return cross-section has undefined IC and
            # remains visible as NaN for that date rather than being pooled.
            results[decision_date] = np.nan
    per_date = pd.Series(results, dtype=float, name="rank_ic")
    per_date.index.name = date_col
    return _summarize_ic_series(per_date)


@dataclass(frozen=True)
class TriadResult:
    standalone: RankICResult
    base: RankICResult
    nested: RankICResult
    leave_one_out: RankICResult
    incremental_nested: RankICResult
    incremental_ablation: RankICResult


def standalone_nested_leave_one_out(
    panel: pd.DataFrame,
    candidate_col: str = "candidate_score",
    base_col: str = "base_score",
    full_col: str = "full_score",
    leave_one_out_col: str = "leave_one_out_score",
    return_col: str = "forward_return",
    date_col: str = "decision_date",
    minimum_cross_section: int = 3,
) -> TriadResult:
    """Report four separately supplied model views and paired IC differences.

    ``leave_one_out_col`` must contain a composite recomputed after removing
    the candidate. It is never inferred from the base model.
    """

    if not isinstance(panel, pd.DataFrame):
        raise TypeError("triad diagnostics require a panel DataFrame")
    score_columns = (candidate_col, base_col, full_col, leave_one_out_col)
    missing = sorted({date_col, return_col, *score_columns} - set(panel.columns))
    if missing:
        raise ValueError(f"triad panel is missing columns: {missing}")

    summaries = {
        column: rank_ic(
            panel,
            signal_col=column,
            return_col=return_col,
            date_col=date_col,
            minimum_cross_section=minimum_cross_section,
        )
        for column in score_columns
    }
    standalone = summaries[candidate_col]
    base = summaries[base_col]
    nested = summaries[full_col]
    leave_one_out = summaries[leave_one_out_col]
    nested_difference = nested.per_date.subtract(base.per_date)
    ablation_difference = nested.per_date.subtract(leave_one_out.per_date)
    nested_difference.name = "incremental_nested_ic"
    ablation_difference.name = "incremental_ablation_ic"
    return TriadResult(
        standalone=standalone,
        base=base,
        nested=nested,
        leave_one_out=leave_one_out,
        incremental_nested=_summarize_ic_series(nested_difference),
        incremental_ablation=_summarize_ic_series(ablation_difference),
    )
