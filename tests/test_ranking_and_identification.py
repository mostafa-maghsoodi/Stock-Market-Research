from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from graham_research.domain import FeatureObservation
from graham_research.features import DEFAULT_PROXY_REGISTRY
from graham_research.identification import (
    rank_ic,
    rule17,
    spearman_rank_correlation,
    standalone_nested_leave_one_out,
)
from graham_research.ranking import CompositeConfig, rank_features


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
        self.assertAlmostEqual(spearman_rank_correlation([1, 2, 3], [10, 20, 30]), 1.0)

    def test_rank_ic_is_cross_sectional_not_pooled(self) -> None:
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
        self.assertTrue((result.per_date.abs() < 1e-12).all())
        self.assertEqual(
            result.t_stat_method,
            "unadjusted_iid_time_series_standard_error",
        )
        with self.assertRaises(TypeError):
            rank_ic([1, 2, 3])

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
        self.assertNotEqual(
            result.incremental_nested.mean,
            result.incremental_ablation.mean,
        )


class RankingTests(unittest.TestCase):
    def test_equal_weight_dimension_composite(self) -> None:
        when = date(2025, 3, 1)
        values = {
            "AAA": {"fcf_ev": 0.10, "ebit_ev": 0.08, "roic": 0.20, "operating_margin_change": 0.03},
            "BBB": {"fcf_ev": 0.05, "ebit_ev": 0.04, "roic": 0.10, "operating_margin_change": 0.01},
        }
        constructs = {item.name: item.construct for item in DEFAULT_PROXY_REGISTRY}
        observations = [
            FeatureObservation(ticker, when, name, constructs[name], value, when, None)
            for ticker, features in values.items()
            for name, value in features.items()
        ]
        ranked = rank_features(observations, DEFAULT_PROXY_REGISTRY)
        scores = ranked.set_index("security_id")["composite_score"]
        self.assertEqual(scores["AAA"], 1.0)
        self.assertEqual(scores["BBB"], 0.0)

    def test_required_missing_dimension_blocks_score(self) -> None:
        when = date(2025, 3, 1)
        observation = FeatureObservation("AAA", when, "fcf_ev", "valuation", 0.1, when, None)
        ranked = rank_features([observation], DEFAULT_PROXY_REGISTRY)
        self.assertTrue(ranked["composite_score"].isna().all())


if __name__ == "__main__":
    unittest.main()
