from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import unittest
from unittest.mock import patch

import pandas as pd

from graham_research.domain import FeatureObservation
from graham_research.features import FeatureEngine, GovernedFeatureBatch
from graham_research.governance import ResolvedEntry001
from graham_research.identification import (
    rank_ic,
    rule17,
    spearman_rank_correlation,
    standalone_nested_leave_one_out,
)
from graham_research.pit import PointInTimeStore
from graham_research.ranking import (
    CompositeConfig,
    RankingError,
    rank_features,
    select_top_n,
)

from run1_fixtures import fact, resolved_entry


DECISION = datetime.fromisoformat("2025-03-01T21:00:00+00:00")
CLEAN = {"vcs": "git", "commit": "c" * 40, "dirty": False}


def rows_for(security: str, multiplier: float = 1.0):
    return [
        fact(security, "gross_profit", 2024, 60 * multiplier),
        fact(security, "total_assets", 2023, 190, period_type="instant"),
        fact(security, "total_assets", 2024, 210, period_type="instant"),
        fact(security, "revenue", 2022, 100),
        fact(security, "revenue", 2023, 110),
        fact(security, "revenue", 2024, 132 * multiplier),
    ]


def governed_inputs(include_bbb_revenue: bool = True):
    entry = resolved_entry(("gross_profitability", "revenue_acceleration"))
    rows = rows_for("AAA", 1.2) + rows_for("BBB", 0.8)
    if not include_bbb_revenue:
        rows = [
            row for row in rows
            if not (row.security_id == "BBB" and row.field == "revenue")
        ]
    engine = FeatureEngine(PointInTimeStore(rows), entry)
    with patch("graham_research.features.source_control_manifest", return_value=CLEAN):
        batch = engine.calculate_governed_batch(
            ("AAA", "BBB"), DECISION, "/synthetic/repo"
        )
    return entry, batch


def clone_batch(
    batch: GovernedFeatureBatch,
    *,
    observations=None,
    digest: str | None = None,
) -> GovernedFeatureBatch:
    value = object.__new__(GovernedFeatureBatch)
    object.__setattr__(value, "observations", observations or batch.observations)
    object.__setattr__(
        value, "proxy_registry_digest", digest or batch.proxy_registry_digest
    )
    object.__setattr__(
        value,
        "feature_generation_code_commit",
        batch.feature_generation_code_commit,
    )
    return value


class IdentificationTests(unittest.TestCase):
    def test_rule17_pass_and_insufficient_k(self) -> None:
        passed = rule17([1.0, 1.1, 1.2, 1.3, 1.4])
        self.assertTrue(passed.established)
        self.assertAlmostEqual(passed.q25, 1.1)
        self.assertFalse(rule17([1.0, 1.1, 1.2, 1.3]).established)

    def test_rule17_rejects_unstable_increment(self) -> None:
        result = rule17([0.01, 0.02, 0.03, 1.0, 2.0])
        self.assertFalse(result.established)
        self.assertGreater(result.iqr, result.q25)

    def test_spearman(self) -> None:
        self.assertAlmostEqual(
            spearman_rank_correlation([1, 2, 3], [10, 20, 30]), 1.0
        )

    def test_rank_ic_is_cross_sectional_and_iid_diagnostic_is_explicit(self) -> None:
        panel = pd.DataFrame({
            "decision_date": ["2020-01-31"] * 4 + ["2020-02-29"] * 4,
            "signal": [1, 2, 3, 4, 101, 102, 103, 104],
            "forward_return": [2, 4, 1, 3, 102, 104, 101, 103],
        })
        pooled = spearman_rank_correlation(panel["signal"], panel["forward_return"])
        result = rank_ic(panel)
        self.assertGreater(pooled, 0.70)
        self.assertEqual(result.count, 2)
        self.assertAlmostEqual(result.mean, 0.0)
        self.assertEqual(
            result.t_stat_method,
            "unadjusted_iid_time_series_standard_error",
        )
        self.assertTrue(hasattr(result, "diagnostic_iid_t_stat"))
        self.assertFalse(hasattr(result, "t_stat"))

    def test_triad_requires_independent_leave_one_out_vector(self) -> None:
        panel = pd.DataFrame({
            "decision_date": ["2020-01-31"] * 5,
            "candidate_score": [1, 2, 3, 4, 5],
            "base_score": [5, 4, 3, 2, 1],
            "full_score": [1, 2, 3, 4, 5],
            "leave_one_out_score": [1, 2, 3, 5, 4],
            "forward_return": [1, 2, 3, 4, 5],
        })
        result = standalone_nested_leave_one_out(panel)
        self.assertAlmostEqual(result.incremental_nested.mean, 2.0)
        self.assertAlmostEqual(result.incremental_ablation.mean, 0.1)


class RankingTests(unittest.TestCase):
    def test_equal_weight_dimension_composite(self) -> None:
        entry, batch = governed_inputs()
        result = rank_features(batch, entry, CompositeConfig.from_resolved_entry(entry))
        scores = result.ranked.set_index("security_id")["composite_score"]
        self.assertEqual(scores["AAA"], 1.0)
        self.assertEqual(scores["BBB"], 0.0)

    def test_raw_observations_cannot_enter_governed_ranking(self) -> None:
        entry, _batch = governed_inputs()
        with self.assertRaises(TypeError):
            rank_features([], entry, CompositeConfig.from_resolved_entry(entry))

    def test_config_must_equal_frozen_entry(self) -> None:
        entry, batch = governed_inputs()
        wrong = CompositeConfig(2, 0.5, entry.required_dimensions, "exclude")
        with self.assertRaises(RankingError):
            rank_features(batch, entry, wrong)

    def test_registry_digest_mismatch_fails_fast(self) -> None:
        entry, batch = governed_inputs()
        changed = clone_batch(batch, digest="0" * 64)
        with self.assertRaises(RankingError):
            rank_features(changed, entry, CompositeConfig.from_resolved_entry(entry))

    def test_construct_mismatch_fails_fast(self) -> None:
        entry, batch = governed_inputs()
        first = batch.observations[0]
        bad = replace(first, construct="wrong")
        changed = clone_batch(batch, observations=(bad, *batch.observations[1:]))
        with self.assertRaises(RankingError):
            rank_features(changed, entry, CompositeConfig.from_resolved_entry(entry))

    def test_unsupported_sector_treatment_fails_fast(self) -> None:
        entry, batch = governed_inputs()
        changed_proxy = replace(entry.proxy_registry[0], sector_treatment="sector_relative")
        fake = object.__new__(ResolvedEntry001)
        object.__setattr__(fake, "proxy_registry", (changed_proxy, *entry.proxy_registry[1:]))
        object.__setattr__(fake, "proxy_registry_digest", entry.proxy_registry_digest)
        object.__setattr__(fake, "entry_001_sha256", entry.entry_001_sha256)
        object.__setattr__(fake, "missing_data_policy", entry.missing_data_policy)
        object.__setattr__(fake, "required_dimensions", entry.required_dimensions)
        changed_batch = clone_batch(
            batch,
            digest=__import__("graham_research.governance", fromlist=["proxy_registry_digest"]).proxy_registry_digest(fake.proxy_registry),
        )
        with self.assertRaises(RankingError):
            rank_features(changed_batch, fake, CompositeConfig.from_resolved_entry(fake))

    def test_feature_and_dimension_exclusion_reasons_propagate(self) -> None:
        entry, batch = governed_inputs(include_bbb_revenue=False)
        result = rank_features(batch, entry, CompositeConfig.from_resolved_entry(entry))
        bbb = result.coverage_diagnostics.set_index("security_id").loc["BBB"]
        self.assertIn("revenue_acceleration", bbb["feature_exclusion_reasons"])
        self.assertIn("fundamental_change", bbb["dimension_exclusion_reasons"])
        ranked_bbb = result.ranked.set_index("security_id").loc["BBB"]
        self.assertTrue(pd.isna(ranked_bbb["composite_score"]))

    def test_coverage_diagnostics_expose_required_counts(self) -> None:
        entry, batch = governed_inputs()
        result = rank_features(batch, entry, CompositeConfig.from_resolved_entry(entry))
        self.assertTrue({
            "available_feature_count", "expected_feature_count",
            "feature_coverage_ratio", "excluded_dimensions",
        }.issubset(result.coverage_diagnostics.columns))
        self.assertTrue({
            "dimension_coverage", "dimension_exclusion_reasons"
        }.issubset(result.dimension_diagnostics.columns))

    def test_select_top_n_does_not_restore_nan_composites(self) -> None:
        entry, batch = governed_inputs(include_bbb_revenue=False)
        ranked = rank_features(
            batch, entry, CompositeConfig.from_resolved_entry(entry)
        ).ranked
        selected = select_top_n(ranked, 10)
        self.assertNotIn("BBB", selected["security_id"].tolist())


if __name__ == "__main__":
    unittest.main()
