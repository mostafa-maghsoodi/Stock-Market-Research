"""Transparent cross-sectional ranking with governed lineage checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from .features import GovernedFeatureBatch
from .governance import ResolvedEntry001, proxy_registry_digest


class RankingError(ValueError):
    pass


@dataclass(frozen=True)
class CompositeConfig:
    minimum_features_per_dimension: int
    minimum_feature_coverage: float
    required_dimensions: tuple[str, ...]
    missing_policy: str

    def __post_init__(self) -> None:
        if self.minimum_features_per_dimension < 1:
            raise ValueError("minimum_features_per_dimension must be positive")
        if not 0 <= self.minimum_feature_coverage <= 1:
            raise ValueError("minimum_feature_coverage must be between 0 and 1")
        if not self.required_dimensions:
            raise ValueError("required_dimensions cannot be empty")
        if self.missing_policy not in {"exclude", "median", "worst"}:
            raise ValueError("missing_policy must be exclude, median, or worst")

    @classmethod
    def from_resolved_entry(cls, value: ResolvedEntry001) -> "CompositeConfig":
        policy = value.missing_data_policy
        return cls(
            minimum_features_per_dimension=int(
                policy["minimum_features_per_dimension"]
            ),
            minimum_feature_coverage=float(policy["minimum_feature_coverage"]),
            required_dimensions=value.required_dimensions,
            missing_policy=str(policy["policy"]),
        )


@dataclass(frozen=True)
class RankingResult:
    ranked: pd.DataFrame
    feature_diagnostics: pd.DataFrame
    dimension_diagnostics: pd.DataFrame
    coverage_diagnostics: pd.DataFrame


def _percentile_rank(series: pd.Series) -> pd.Series:
    count = int(series.notna().sum())
    if count == 0:
        return pd.Series(np.nan, index=series.index, dtype=float)
    if count == 1:
        result = pd.Series(np.nan, index=series.index, dtype=float)
        result.loc[series.notna()] = 0.5
        return result
    return (series.rank(method="average") - 1.0) / (count - 1.0)


def _validate_config(
    config: CompositeConfig,
    resolved_entry: ResolvedEntry001,
) -> None:
    expected = CompositeConfig.from_resolved_entry(resolved_entry)
    if config != expected:
        raise RankingError("CompositeConfig does not match frozen Entry 001")


def rank_features(
    batch: GovernedFeatureBatch,
    resolved_entry: ResolvedEntry001,
    config: CompositeConfig,
) -> RankingResult:
    """Rank a governed batch only under the same frozen proxy registry."""

    if not isinstance(batch, GovernedFeatureBatch):
        raise TypeError("rank_features requires GovernedFeatureBatch")
    if not isinstance(resolved_entry, ResolvedEntry001):
        raise TypeError("rank_features requires a verified ResolvedEntry001")
    _validate_config(config, resolved_entry)
    registry = resolved_entry.proxy_registry
    recomputed = proxy_registry_digest(registry)
    if batch.proxy_registry_digest != recomputed:
        raise RankingError("governed feature batch proxy-registry digest mismatch")
    if any(item.sector_treatment != "none" for item in registry):
        raise RankingError("Run 1 ranking supports only sector_treatment='none'")

    definitions = {item.name: item for item in registry}
    rows: list[dict[str, object]] = []
    for item in batch.observations:
        definition = definitions.get(item.feature)
        if definition is None:
            raise RankingError(f"feature missing from proxy registry: {item.feature}")
        if item.construct != definition.construct:
            raise RankingError(
                f"feature/construct mismatch for {item.feature}: "
                f"{item.construct!r} != {definition.construct!r}"
            )
        rows.append({
            "security_id": item.security_id,
            "decision_date": item.decision_date,
            "feature": item.feature,
            "construct": item.construct,
            "value": item.value,
            "exclusion_reason": item.exclusion_reason,
        })
    if not rows:
        empty = pd.DataFrame()
        return RankingResult(empty, empty, empty, empty)

    frame = pd.DataFrame(rows)
    duplicate = frame.duplicated(
        ["security_id", "decision_date", "feature"], keep=False
    )
    if duplicate.any():
        raise RankingError("duplicate security/date/feature observations")

    directions = {item.name: item.expected_direction for item in registry}
    frame["available"] = frame["value"].notna()
    frame["sign_aligned_value"] = frame.apply(
        lambda row: row["value"] * directions[row["feature"]]
        if pd.notna(row["value"])
        else np.nan,
        axis=1,
    )
    frame["feature_rank"] = frame.groupby(
        ["decision_date", "feature"], group_keys=False
    )["sign_aligned_value"].transform(_percentile_rank)
    if config.missing_policy != "exclude":
        fill_value = 0.5 if config.missing_policy == "median" else 0.0
        frame["feature_rank"] = frame["feature_rank"].fillna(fill_value)

    expected_by_construct = {
        construct: sum(item.construct == construct for item in registry)
        for construct in {item.construct for item in registry}
    }
    dimension_rows: list[dict[str, object]] = []
    for (security_id, decision_date, construct), group in frame.groupby(
        ["security_id", "decision_date", "construct"], sort=True
    ):
        available_count = int(group["available"].sum())
        expected_count = expected_by_construct[construct]
        dimension_coverage = available_count / expected_count
        reasons = sorted(
            {
                reason
                for values in group.loc[~group["available"], "exclusion_reason"]
                for reason in values
            }
        )
        score = group["feature_rank"].mean()
        if available_count < config.minimum_features_per_dimension:
            score = np.nan
            reasons.append("minimum_features_per_dimension_not_met")
        dimension_rows.append({
            "security_id": security_id,
            "decision_date": decision_date,
            "construct": construct,
            "dimension_score": score,
            "available_feature_count": available_count,
            "expected_feature_count": expected_count,
            "dimension_coverage": dimension_coverage,
            "dimension_exclusion_reasons": tuple(sorted(set(reasons))),
        })
    dimension = pd.DataFrame(dimension_rows)

    index = frame[["security_id", "decision_date"]].drop_duplicates()
    for construct in config.required_dimensions:
        present = dimension[dimension["construct"] == construct][
            ["security_id", "decision_date"]
        ]
        missing = index.merge(
            present,
            on=["security_id", "decision_date"],
            how="left",
            indicator=True,
        )
        for row in missing[missing["_merge"] == "left_only"].itertuples(index=False):
            dimension.loc[len(dimension)] = {
                "security_id": row.security_id,
                "decision_date": row.decision_date,
                "construct": construct,
                "dimension_score": np.nan,
                "available_feature_count": 0,
                "expected_feature_count": expected_by_construct.get(construct, 0),
                "dimension_coverage": 0.0,
                "dimension_exclusion_reasons": ("construct_unavailable",),
            }

    wide = dimension.pivot(
        index=["security_id", "decision_date"],
        columns="construct",
        values="dimension_score",
    )
    for construct in config.required_dimensions:
        if construct not in wide.columns:
            wide[construct] = np.nan
    wide["composite_score"] = wide[list(config.required_dimensions)].mean(
        axis=1, skipna=False
    )
    wide = wide.reset_index()

    coverage_rows: list[dict[str, object]] = []
    expected_features = len(registry)
    for (security_id, decision_date), group in frame.groupby(
        ["security_id", "decision_date"], sort=True
    ):
        available_count = int(group["available"].sum())
        coverage = available_count / expected_features
        dimensions_for_security = dimension[
            (dimension["security_id"] == security_id)
            & (dimension["decision_date"] == decision_date)
        ]
        excluded_dimensions = tuple(
            sorted(
                dimensions_for_security.loc[
                    dimensions_for_security["dimension_score"].isna(), "construct"
                ].tolist()
            )
        )
        feature_reasons: Mapping[str, tuple[str, ...]] = {
            str(row.feature): tuple(row.exclusion_reason)
            for row in group.itertuples()
            if not row.available
        }
        dimension_reasons = {
            str(row.construct): tuple(row.dimension_exclusion_reasons)
            for row in dimensions_for_security.itertuples()
            if pd.isna(row.dimension_score)
        }
        coverage_rows.append({
            "security_id": security_id,
            "decision_date": decision_date,
            "available_feature_count": available_count,
            "expected_feature_count": expected_features,
            "feature_coverage_ratio": coverage,
            "excluded_dimensions": excluded_dimensions,
            "feature_exclusion_reasons": feature_reasons,
            "dimension_exclusion_reasons": dimension_reasons,
        })
        if coverage < config.minimum_feature_coverage:
            mask = (
                (wide["security_id"] == security_id)
                & (wide["decision_date"] == decision_date)
            )
            wide.loc[mask, "composite_score"] = np.nan
    coverage_frame = pd.DataFrame(coverage_rows)

    feature_wide = frame.pivot(
        index=["security_id", "decision_date"],
        columns="feature",
        values="feature_rank",
    ).reset_index()
    ranked = feature_wide.merge(
        wide, on=["security_id", "decision_date"], how="outer"
    ).merge(
        coverage_frame[
            [
                "security_id",
                "decision_date",
                "available_feature_count",
                "expected_feature_count",
                "feature_coverage_ratio",
                "excluded_dimensions",
            ]
        ],
        on=["security_id", "decision_date"],
        how="left",
    )
    return RankingResult(
        ranked=ranked,
        feature_diagnostics=frame,
        dimension_diagnostics=dimension.sort_values(
            ["security_id", "decision_date", "construct"]
        ).reset_index(drop=True),
        coverage_diagnostics=coverage_frame,
    )


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
