"""Transparent cross-sectional ranking and simple composites."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .domain import FeatureObservation, ProxyDefinition


class RankingError(ValueError):
    pass


@dataclass(frozen=True)
class CompositeConfig:
    """Frozen L5 behavior.

    A dimension is an equal-weight average of its available feature ranks.
    The final score is an equal-weight average of available dimension scores.
    """

    minimum_features_per_dimension: int = 1
    required_dimensions: tuple[str, ...] = (
        "valuation",
        "business_economics",
        "fundamental_change",
    )
    missing_policy: str = "exclude"

    def __post_init__(self) -> None:
        if self.minimum_features_per_dimension < 1:
            raise ValueError("minimum_features_per_dimension must be positive")
        if self.missing_policy not in {"exclude", "median", "worst"}:
            raise ValueError("missing_policy must be exclude, median, or worst")


def _percentile_rank(series: pd.Series) -> pd.Series:
    # Average ties are deterministic and prevent arbitrary ticker ordering from
    # becoming an economic signal. A one-security cross-section receives 0.5.
    count = int(series.notna().sum())
    if count == 0:
        return pd.Series(np.nan, index=series.index, dtype=float)
    if count == 1:
        result = pd.Series(np.nan, index=series.index, dtype=float)
        result.loc[series.notna()] = 0.5
        return result
    return (series.rank(method="average") - 1.0) / (count - 1.0)


def rank_features(
    observations: Iterable[FeatureObservation],
    registry: Sequence[ProxyDefinition],
    config: CompositeConfig = CompositeConfig(),
) -> pd.DataFrame:
    """Return feature ranks, dimension scores, and the transparent composite."""

    rows = [
        {
            "security_id": item.security_id,
            "decision_date": item.decision_date,
            "feature": item.feature,
            "construct": item.construct,
            "value": item.value,
        }
        for item in observations
    ]
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    duplicate = frame.duplicated(["security_id", "decision_date", "feature"], keep=False)
    if duplicate.any():
        raise RankingError("duplicate security/date/feature observations")

    directions = {item.name: item.expected_direction for item in registry}
    unknown = sorted(set(frame["feature"]) - set(directions))
    if unknown:
        raise RankingError(f"features missing from proxy registry: {unknown}")
    frame["sign_aligned_value"] = frame.apply(
        lambda row: row["value"] * directions[row["feature"]]
        if pd.notna(row["value"]) else np.nan,
        axis=1,
    )
    frame["feature_rank"] = frame.groupby(
        ["decision_date", "feature"], group_keys=False
    )["sign_aligned_value"].transform(_percentile_rank)

    if config.missing_policy != "exclude":
        fill_value = 0.5 if config.missing_policy == "median" else 0.0
        frame["feature_rank"] = frame["feature_rank"].fillna(fill_value)

    counts = frame.groupby(
        ["security_id", "decision_date", "construct"]
    )["feature_rank"].count()
    dimension = frame.groupby(
        ["security_id", "decision_date", "construct"], as_index=False
    )["feature_rank"].mean().rename(columns={"feature_rank": "dimension_score"})
    dimension["feature_count"] = [counts.loc[tuple(row)] for row in dimension[["security_id", "decision_date", "construct"]].itertuples(index=False, name=None)]
    dimension.loc[
        dimension["feature_count"] < config.minimum_features_per_dimension,
        "dimension_score",
    ] = np.nan

    wide = dimension.pivot(
        index=["security_id", "decision_date"],
        columns="construct",
        values="dimension_score",
    )
    missing_dimensions = [name for name in config.required_dimensions if name not in wide.columns]
    for name in missing_dimensions:
        wide[name] = np.nan
    required = wide[list(config.required_dimensions)]
    wide["composite_score"] = required.mean(axis=1, skipna=False)
    wide = wide.reset_index()

    feature_wide = frame.pivot(
        index=["security_id", "decision_date"],
        columns="feature",
        values="feature_rank",
    ).reset_index()
    return feature_wide.merge(wide, on=["security_id", "decision_date"], how="outer")


def select_top_n(ranked: pd.DataFrame, n: int) -> pd.DataFrame:
    if n <= 0:
        raise ValueError("n must be positive")
    required = {"security_id", "decision_date", "composite_score"}
    if not required.issubset(ranked.columns):
        raise RankingError(f"ranked data requires columns {sorted(required)}")
    eligible = ranked.dropna(subset=["composite_score"]).copy()
    eligible = eligible.sort_values(
        ["decision_date", "composite_score", "security_id"],
        ascending=[True, False, True],
    )
    return eligible.groupby("decision_date", group_keys=False).head(n)
