from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
import inspect
import unittest
from unittest.mock import patch

from graham_research.domain import (
    FactObservation,
    PeriodType,
    ReportingFrequency,
    RestatementPolicy,
)
from graham_research.features import FeatureEngine, GovernedFeatureBatch
from graham_research.governance import GovernanceError
from graham_research.pit import PointInTimeStore, PointInTimeViolation, assert_no_future_facts

from run1_fixtures import (
    complete_entry_001,
    fact,
    governed_fact_dataset,
    resolved_entry,
    resolved_entry_from_payload,
)


DECISION = datetime.fromisoformat("2025-03-01T21:00:00+00:00")
CLEAN_MANIFEST = {"vcs": "git", "commit": "b" * 40, "dirty": False}


def engine(rows, proxies=("gross_profitability",)) -> FeatureEngine:
    return FeatureEngine(governed_fact_dataset(rows), resolved_entry(proxies))


def batch(feature_engine: FeatureEngine, securities=("AAA",)):
    with patch(
        "graham_research.features.source_control_manifest",
        return_value=CLEAN_MANIFEST,
    ):
        return feature_engine.calculate_governed_batch(
            securities, DECISION, "/synthetic/repository"
        )


def gross_rows(security="AAA"):
    return [
        fact(security, "gross_profit", 2024, 60),
        fact(security, "total_assets", 2023, 190, period_type=PeriodType.INSTANT),
        fact(security, "total_assets", 2024, 210, period_type=PeriodType.INSTANT),
    ]


class ParsingAndPointInTimeTests(unittest.TestCase):
    def test_finite_integer_and_float_values_are_accepted_and_normalized(self) -> None:
        for value in (1, 1.25):
            with self.subTest(value=value):
                row = FactObservation(
                    "AAA", "revenue", date(2024, 12, 31),
                    datetime.fromisoformat("2025-02-01T00:00:00+00:00"),
                    value, "test",
                )
                self.assertEqual(row.value, float(value))
                self.assertIsInstance(row.value, float)

    def test_nonfinite_and_boolean_fact_values_are_rejected(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf"), True, False):
            with self.subTest(value=value), self.assertRaises(ValueError):
                FactObservation(
                    "AAA", "revenue", date(2024, 12, 31),
                    datetime.fromisoformat("2025-02-01T00:00:00+00:00"),
                    value, "test",
                )

    def test_mapping_parser_enforces_finite_nonboolean_values(self) -> None:
        base = {
            "security_id": "AAA",
            "field": "revenue",
            "period_end": "2024-12-31",
            "available_at": "2025-02-01T00:00:00+00:00",
            "source": "test",
        }
        for value in ("nan", "inf", "-inf", True, False):
            with self.subTest(value=value), self.assertRaises(ValueError):
                FactObservation.from_mapping({**base, "value": value})
        self.assertEqual(
            FactObservation.from_mapping({**base, "value": "1.25"}).value,
            1.25,
        )

    def test_missing_metadata_parses_to_explicit_unknown(self) -> None:
        row = FactObservation.from_mapping({
            "security_id": "AAA",
            "field": "revenue",
            "period_end": "2024-12-31",
            "available_at": "2025-02-01T00:00:00+00:00",
            "value": "1",
            "source": "test",
        })
        self.assertIs(row.period_type, PeriodType.UNKNOWN)
        self.assertIs(row.reporting_frequency, ReportingFrequency.UNKNOWN)
        self.assertIsNone(row.form_type)
        self.assertIsNone(row.fiscal_year)
        self.assertIsNone(row.fiscal_quarter)

    def test_parser_does_not_infer_from_field_form_or_date(self) -> None:
        row = FactObservation.from_mapping({
            "security_id": "AAA",
            "field": "revenue",
            "period_end": "2024-12-31",
            "available_at": "2025-02-01T00:00:00+00:00",
            "value": "1",
            "source": "SEC",
            "form_type": "10-K",
        })
        self.assertIs(row.period_type, PeriodType.UNKNOWN)
        self.assertIs(row.reporting_frequency, ReportingFrequency.UNKNOWN)
        self.assertIsNone(row.fiscal_year)

    def test_invalid_metadata_enums_and_quarter_are_rejected(self) -> None:
        base = {
            "security_id": "AAA", "field": "revenue", "period_end": "2024-12-31",
            "available_at": "2025-02-01T00:00:00+00:00", "value": "1", "source": "x",
        }
        for change in (
            {"period_type": "point"},
            {"reporting_frequency": "semiannual"},
            {"fiscal_quarter": "5"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                FactObservation.from_mapping({**base, **change})

    def test_first_class_metadata_cannot_be_repeated_in_metadata(self) -> None:
        with self.assertRaises(ValueError):
            FactObservation(
                "AAA", "revenue", date(2024, 12, 31),
                datetime.fromisoformat("2025-02-01T00:00:00+00:00"),
                1, "x", metadata={"period_type": "duration"},
            )

    def test_future_version_is_not_visible(self) -> None:
        first = fact("AAA", "revenue", 2022, 100, available_year=2023, accession="A")
        restated = fact("AAA", "revenue", 2022, 120, available_year=2024, accession="B")
        store = PointInTimeStore([first, restated])
        self.assertEqual(
            store.latest_as_of(
                "AAA", "revenue",
                datetime.fromisoformat("2023-12-31T23:59:00+00:00"),
            ).value,
            100,
        )
        self.assertEqual(
            store.latest_as_of(
                "AAA", "revenue",
                datetime.fromisoformat("2024-12-31T23:59:00+00:00"),
            ).value,
            100,
        )
        self.assertEqual(
            store.latest_as_of(
                "AAA", "revenue",
                datetime.fromisoformat("2024-12-31T23:59:00+00:00"),
                RestatementPolicy.LATEST_KNOWN,
            ).value,
            120,
        )

    def test_future_assertion_fails_closed(self) -> None:
        future = fact("AAA", "revenue", 2024, 100, available_year=2025)
        with self.assertRaises(PointInTimeViolation):
            assert_no_future_facts(
                [future], datetime.fromisoformat("2025-01-31T21:00:00+00:00")
            )


class ComparabilityTests(unittest.TestCase):
    def test_frequency_filter_occurs_before_latest_selection(self) -> None:
        rows = gross_rows() + [
            fact(
                "AAA", "gross_profit", 2025, 15,
                frequency=ReportingFrequency.QUARTERLY,
                period_end=date(2025, 3, 31),
                available_year=2025,
            )
        ]
        result = batch(engine(rows)).observations[0]
        self.assertAlmostEqual(result.value, 0.30)

    def test_unknown_frequency_is_unavailable(self) -> None:
        rows = gross_rows()
        rows[0] = fact(
            "AAA", "gross_profit", 2024, 60,
            frequency=ReportingFrequency.UNKNOWN,
        )
        result = batch(engine(rows)).observations[0]
        self.assertIsNone(result.value)
        self.assertIn("unknown_reporting_frequency", result.exclusion_reason)

    def test_quarterly_frequency_is_unavailable(self) -> None:
        rows = gross_rows()
        rows[0] = fact(
            "AAA", "gross_profit", 2024, 60,
            frequency=ReportingFrequency.QUARTERLY,
        )
        result = batch(engine(rows)).observations[0]
        self.assertIn("reporting_frequency_mismatch", result.exclusion_reason)

    def test_wrong_period_type_is_unavailable(self) -> None:
        rows = gross_rows()
        rows[0] = fact(
            "AAA", "gross_profit", 2024, 60, period_type=PeriodType.INSTANT
        )
        result = batch(engine(rows)).observations[0]
        self.assertIn("incompatible_period_type", result.exclusion_reason)

    def test_missing_fiscal_year_is_unavailable(self) -> None:
        row = gross_rows()[1]
        missing = FactObservation(
            row.security_id, row.field, row.period_end, row.available_at, row.value,
            row.source, row.accession, row.unit, row.period_type,
            row.reporting_frequency, row.form_type, None, None,
        )
        result = batch(engine([gross_rows()[0], missing, gross_rows()[2]])).observations[0]
        self.assertIn("missing_fiscal_year_metadata", result.exclusion_reason)

    def test_nonconsecutive_fiscal_years_are_unavailable(self) -> None:
        rows = [
            fact("AAA", "gross_profit", 2024, 60),
            fact("AAA", "total_assets", 2022, 190, period_type="instant"),
            fact("AAA", "total_assets", 2024, 210, period_type="instant"),
        ]
        result = batch(engine(rows)).observations[0]
        self.assertIn("nonconsecutive_fiscal_years", result.exclusion_reason)

    def test_identical_period_end_alignment_is_enforced(self) -> None:
        rows = gross_rows()
        rows[0] = fact(
            "AAA", "gross_profit", 2024, 60,
            period_end=date(2024, 12, 30),
        )
        result = batch(engine(rows)).observations[0]
        self.assertIn("period_structure_mismatch", result.exclusion_reason)

    def test_ambiguous_period_ends_in_same_fiscal_year_are_rejected(self) -> None:
        rows = gross_rows() + [
            fact(
                "AAA", "gross_profit", 2024, 61,
                period_end=date(2025, 1, 2), accession="alternate-period",
            )
        ]
        result = batch(engine(rows)).observations[0]
        self.assertIn("ambiguous_fiscal_year", result.exclusion_reason)

    def test_fiscal_year_eligibility_precedes_restatement_selection(self) -> None:
        rows = gross_rows()
        rows[2] = fact(
            "AAA", "total_assets", 2024, 210,
            period_type="instant", accession="admissible-version",
        )
        inadmissible = fact(
            "AAA", "total_assets", 2022, 999,
            period_type="instant",
            period_end=date(2024, 12, 31),
            accession="earlier-inadmissible-version",
        )
        inadmissible = replace(
            inadmissible,
            available_at=datetime.fromisoformat("2025-01-15T21:00:00+00:00"),
        )
        feature_engine = engine([inadmissible, *rows])
        internal = feature_engine._calculate_proxy(
            "AAA",
            feature_engine.resolved_entry_001.proxy_registry[0],
            DECISION,
        )
        self.assertAlmostEqual(internal.value, 0.30)
        accessions = {row.accession for row in internal.source_observations}
        self.assertIn("admissible-version", accessions)
        self.assertNotIn("earlier-inadmissible-version", accessions)

    def test_cross_section_does_not_diverge_for_newer_quarterly_filing(self) -> None:
        rows = gross_rows("AAA") + gross_rows("BBB") + [
            fact(
                "BBB", "gross_profit", 2025, 999,
                frequency="quarterly", period_end=date(2025, 3, 31), available_year=2025,
            )
        ]
        observations = batch(engine(rows), ("AAA", "BBB")).observations
        self.assertEqual([item.value for item in observations], [0.30, 0.30])

    def _frequency_exempt_engine(self, rows):
        payload = complete_entry_001(("gross_profitability",))
        proxy = payload["proxy_registry"][0]
        proxy["frequency_governed_source_fields"] = ["gross_profit"]
        proxy["frequency_exempt_source_fields"] = ["total_assets"]
        return FeatureEngine(
            governed_fact_dataset(rows), resolved_entry_from_payload(payload)
        )

    def test_frequency_exempt_field_skips_frequency_equality(self) -> None:
        rows = [
            fact("AAA", "gross_profit", 2024, 60),
            fact("AAA", "total_assets", 2023, 190, period_type="instant", frequency="quarterly"),
            fact("AAA", "total_assets", 2024, 210, period_type="instant", frequency="unknown"),
        ]
        result = batch(self._frequency_exempt_engine(rows)).observations[0]
        self.assertAlmostEqual(result.value, 0.30)

    def test_frequency_exemption_does_not_bypass_period_type(self) -> None:
        rows = [
            fact("AAA", "gross_profit", 2024, 60),
            fact("AAA", "total_assets", 2023, 190, period_type="duration", frequency="quarterly"),
            fact("AAA", "total_assets", 2024, 210, period_type="duration", frequency="quarterly"),
        ]
        result = batch(self._frequency_exempt_engine(rows)).observations[0]
        self.assertIn("incompatible_period_type", result.exclusion_reason)

    def test_frequency_exemption_does_not_bypass_pit_cutoff(self) -> None:
        rows = [
            fact("AAA", "gross_profit", 2024, 60),
            fact("AAA", "total_assets", 2023, 190, period_type="instant"),
            fact("AAA", "total_assets", 2024, 210, period_type="instant", available_year=2026),
        ]
        result = batch(self._frequency_exempt_engine(rows)).observations[0]
        self.assertIn("nonconsecutive_fiscal_years", result.exclusion_reason)


class FormulaAndProvenanceTests(unittest.TestCase):
    def test_gross_profitability_uses_governed_roles(self) -> None:
        result = batch(engine(gross_rows())).observations[0]
        self.assertAlmostEqual(result.value, 0.30)
        self.assertIsNone(result.source_period_end)
        self.assertIsNotNone(result.source_available_at)

    def test_synthetic_registry_can_explicitly_remove_prior_gross_dependency(self) -> None:
        result = batch(engine(gross_rows())).observations[0]
        self.assertIsNotNone(result.value)

    def test_synthetic_registry_can_explicitly_require_prior_gross_dependency(self) -> None:
        payload = complete_entry_001(("gross_profitability",))
        proxy = payload["proxy_registry"][0]
        proxy["prior_gross_profit_dependency"] = "require_prior_gross_profit"
        proxy["required_period_structure"].insert(1, {
            "role_name": "prior_gross_profit",
            "source_field": "gross_profit",
            "role_kind": "accounting_role",
            "period_type": "duration",
            "fiscal_year_offset": -1,
        })
        resolved = resolved_entry_from_payload(payload)
        without_prior = batch(
            FeatureEngine(governed_fact_dataset(gross_rows()), resolved)
        ).observations[0]
        self.assertIn("nonconsecutive_fiscal_years", without_prior.exclusion_reason)
        with_prior_rows = gross_rows() + [fact("AAA", "gross_profit", 2023, 50)]
        with_prior = batch(
            FeatureEngine(governed_fact_dataset(with_prior_rows), resolved)
        ).observations[0]
        self.assertAlmostEqual(with_prior.value, 0.30)

    def test_revenue_acceleration_uses_three_consecutive_roles(self) -> None:
        rows = [
            fact("AAA", "revenue", 2022, 100),
            fact("AAA", "revenue", 2023, 110),
            fact("AAA", "revenue", 2024, 132),
        ]
        result = batch(engine(rows, ("revenue_acceleration",))).observations[0]
        self.assertAlmostEqual(result.value, 0.10)
        self.assertIsNone(result.source_period_end)

    def test_roic_exact_provenance_and_value(self) -> None:
        rows = [
            fact("AAA", "operating_income", 2024, 19.8),
            fact("AAA", "income_tax_expense", 2024, 10),
            fact("AAA", "income_before_tax", 2024, 40),
            fact("AAA", "invested_capital", 2023, 90, period_type="instant"),
            fact("AAA", "invested_capital", 2024, 110, period_type="instant"),
        ]
        feature_engine = engine(rows, ("roic",))
        internal = feature_engine._calculate_proxy(
            "AAA", feature_engine.resolved_entry_001.proxy_registry[0], DECISION
        )
        self.assertAlmostEqual(internal.value, 0.1485)
        self.assertEqual(len(internal.source_observations), 5)
        result = batch(feature_engine).observations[0]
        self.assertAlmostEqual(result.value, 0.1485)

    def test_unused_later_restatement_is_not_provenance(self) -> None:
        rows = gross_rows()
        rows.append(
            fact(
                "AAA", "total_assets", 2024, 999,
                available_year=2026, period_type="instant", accession="late",
            )
        )
        feature_engine = engine(rows)
        internal = feature_engine._calculate_proxy(
            "AAA", feature_engine.resolved_entry_001.proxy_registry[0], DECISION
        )
        self.assertNotIn("late", {row.accession for row in internal.source_observations})

    def test_usable_feature_without_provenance_is_forbidden(self) -> None:
        from graham_research.domain import FeatureObservation

        with self.assertRaises(ValueError):
            FeatureObservation(
                "AAA", DECISION.date(), "x", "x", 1.0, None, None, ()
            )

    def test_unavailable_feature_requires_specific_reason(self) -> None:
        result = batch(engine([])).observations[0]
        self.assertIsNone(result.value)
        self.assertEqual(
            result.exclusion_reason,
            ("denominator_missing", "insufficient_history"),
        )


class DenominatorPolicyTests(unittest.TestCase):
    def _gross(
        self,
        current_assets: float | None,
        prior_assets: float | None,
        *,
        negative="exclude_feature",
        near_zero="exclude_feature",
    ):
        rows = [fact("AAA", "gross_profit", 2024, 60)]
        if prior_assets is not None:
            rows.append(
                fact("AAA", "total_assets", 2023, prior_assets, period_type="instant")
            )
        if current_assets is not None:
            rows.append(
                fact("AAA", "total_assets", 2024, current_assets, period_type="instant")
            )
        payload = complete_entry_001(("gross_profitability",))
        policy = payload["proxy_registry"][0]["denominator_definitions"][0]["denominator_policy"]
        policy["negative"] = negative
        policy["near_zero"] = near_zero
        resolved = resolved_entry_from_payload(payload)
        return batch(FeatureEngine(governed_fact_dataset(rows), resolved)).observations[0]

    def test_denominator_missing_is_distinct(self) -> None:
        result = self._gross(None, None)
        self.assertIn("denominator_missing", result.exclusion_reason)

    def test_zero_derived_denominator_is_excluded_after_transformation(self) -> None:
        result = self._gross(10, -10)
        self.assertIn("denominator_policy_exclusion", result.exclusion_reason)

    def test_negative_derived_denominator_is_excluded(self) -> None:
        result = self._gross(-190, -210)
        self.assertIn("denominator_policy_exclusion", result.exclusion_reason)

    def test_near_zero_positive_denominator_is_excluded(self) -> None:
        result = self._gross(1, 3)
        self.assertIn("denominator_policy_exclusion", result.exclusion_reason)

    def test_near_zero_negative_precedes_negative_policy(self) -> None:
        result = self._gross(
            -1, -3, negative="allow_value", near_zero="exclude_feature"
        )
        self.assertIn("denominator_policy_exclusion", result.exclusion_reason)

    def test_near_zero_allow_value_permits_small_positive_result(self) -> None:
        result = self._gross(1, 3, near_zero="allow_value")
        self.assertAlmostEqual(result.value, 30.0)

    def test_near_zero_allow_value_permits_small_negative_result(self) -> None:
        result = self._gross(-1, -3, near_zero="allow_value")
        self.assertAlmostEqual(result.value, -30.0)

    def test_near_zero_exclusion_applies_to_both_signs(self) -> None:
        for current_assets, prior_assets in ((1, 3), (-1, -3)):
            with self.subTest(
                current_assets=current_assets, prior_assets=prior_assets
            ):
                result = self._gross(
                    current_assets,
                    prior_assets,
                    negative="allow_value",
                    near_zero="exclude_feature",
                )
                self.assertIn(
                    "denominator_policy_exclusion", result.exclusion_reason
                )

    def test_large_negative_denominator_uses_negative_policy(self) -> None:
        result = self._gross(
            -190, -210, negative="allow_value", near_zero="exclude_feature"
        )
        self.assertAlmostEqual(result.value, -0.30)

    def test_normal_positive_denominator_is_usable(self) -> None:
        result = self._gross(190, 210)
        self.assertAlmostEqual(result.value, 0.30)

    def test_supplied_policy_changes_feature_behavior(self) -> None:
        excluded = self._gross(-190, -210)
        allowed = self._gross(-190, -210, negative="allow_value")
        self.assertIsNone(excluded.value)
        self.assertAlmostEqual(allowed.value, -0.30)

    def test_non_ev_revenue_denominator_has_independent_policy(self) -> None:
        payload = complete_entry_001(("operating_margin_change",))
        current_policy = payload["proxy_registry"][0]["denominator_definitions"][0]["denominator_policy"]
        current_policy["negative"] = "allow_value"
        resolved = resolved_entry_from_payload(payload)
        rows = [
            fact("AAA", "operating_income", 2023, 10),
            fact("AAA", "operating_income", 2024, 20),
            fact("AAA", "revenue", 2023, 100),
            fact("AAA", "revenue", 2024, -100),
        ]
        result = batch(
            FeatureEngine(governed_fact_dataset(rows), resolved)
        ).observations[0]
        self.assertAlmostEqual(result.value, -0.30)


class GovernedBatchTests(unittest.TestCase):
    def test_feature_engine_rejects_unverified_registry(self) -> None:
        with self.assertRaises(TypeError):
            FeatureEngine(PointInTimeStore(), ())

    def test_restatement_policy_flows_only_from_resolved_entry(self) -> None:
        resolved = resolved_entry(("gross_profitability",))
        self.assertIs(
            resolved.restatement_policy,
            RestatementPolicy.FIRST_REPORTED,
        )
        rows = gross_rows()
        later_restatement = replace(
            rows[2],
            available_at=datetime.fromisoformat("2025-02-20T21:00:00+00:00"),
            value=999,
            accession="later-restatement",
        )
        feature_engine = FeatureEngine(
            PointInTimeStore([*rows, later_restatement]),
            resolved,
        )
        self.assertIs(
            feature_engine.restatement_policy,
            RestatementPolicy.FIRST_REPORTED,
        )
        result = feature_engine._calculate_proxy(
            "AAA",
            resolved.proxy_registry[0],
            DECISION,
        )
        self.assertAlmostEqual(result.value, 0.30)
        self.assertNotIn(
            "later-restatement",
            {row.accession for row in result.source_observations},
        )
        self.assertNotIn("policy", inspect.signature(FeatureEngine).parameters)
        with self.assertRaises(TypeError):
            FeatureEngine(
                PointInTimeStore(),
                resolved,
                RestatementPolicy.LATEST_KNOWN,
            )

    def test_batch_constructor_cannot_promote_arbitrary_results(self) -> None:
        with self.assertRaises(TypeError):
            GovernedFeatureBatch((), "digest", "c" * 40)

    def test_clean_tree_emits_commit_from_same_manifest(self) -> None:
        feature_engine = engine(gross_rows())
        with patch(
            "graham_research.features.source_control_manifest",
            return_value=CLEAN_MANIFEST,
        ) as manifest:
            result = feature_engine.calculate_governed_batch(
                ("AAA",), DECISION, "/synthetic/repository"
            )
        self.assertEqual(manifest.call_count, 1)
        self.assertEqual(result.feature_generation_code_commit, "b" * 40)

    def test_dirty_tree_rejects_batch_creation(self) -> None:
        feature_engine = engine(gross_rows())
        with (
            patch(
                "graham_research.features.source_control_manifest",
                return_value={"vcs": "git", "commit": "b" * 40, "dirty": True},
            ),
            patch.object(feature_engine, "_calculate_observations") as calculate,
        ):
            with self.assertRaises(GovernanceError):
                feature_engine.calculate_governed_batch(
                    ("AAA",), DECISION, "/synthetic/repository"
                )
        calculate.assert_not_called()

    def test_cleanliness_is_not_checked_at_engine_construction(self) -> None:
        with patch("graham_research.features.source_control_manifest") as manifest:
            engine(gross_rows())
        manifest.assert_not_called()

    def test_registry_digest_is_recorded_once_at_batch_level(self) -> None:
        result = batch(engine(gross_rows()))
        self.assertTrue(result.proxy_registry_digest)
        self.assertFalse(hasattr(result.observations[0], "proxy_registry_digest"))


if __name__ == "__main__":
    unittest.main()
