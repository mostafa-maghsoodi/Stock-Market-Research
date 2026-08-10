from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from graham_research.domain import FactObservation, RestatementPolicy
from graham_research.features import DEFAULT_PROXY_REGISTRY, FeatureEngine
from graham_research.pit import PointInTimeStore, PointInTimeViolation, assert_no_future_facts


def fact(field: str, period: str, available: str, value: float, accession: str) -> FactObservation:
    return FactObservation(
        security_id="AAA",
        field=field,
        period_end=date.fromisoformat(period),
        available_at=datetime.fromisoformat(available),
        value=value,
        source="test",
        accession=accession,
        unit="USD",
    )


class PointInTimeTests(unittest.TestCase):
    def test_future_version_is_not_visible(self) -> None:
        first = fact("revenue", "2022-12-31", "2023-02-10T12:00:00+00:00", 100, "A")
        restated = fact("revenue", "2022-12-31", "2024-02-10T12:00:00+00:00", 120, "B")
        store = PointInTimeStore([first, restated])
        self.assertEqual(store.latest_as_of("AAA", "revenue", datetime.fromisoformat("2023-12-31T23:59:00+00:00")).value, 100)
        self.assertEqual(
            store.latest_as_of("AAA", "revenue", datetime.fromisoformat("2024-12-31T23:59:00+00:00"), RestatementPolicy.FIRST_REPORTED).value,
            100,
        )
        self.assertEqual(
            store.latest_as_of("AAA", "revenue", datetime.fromisoformat("2024-12-31T23:59:00+00:00"), RestatementPolicy.LATEST_KNOWN).value,
            120,
        )

    def test_future_assertion_fails_closed(self) -> None:
        future = fact("revenue", "2024-12-31", "2025-02-10T12:00:00+00:00", 100, "A")
        with self.assertRaises(PointInTimeViolation):
            assert_no_future_facts([future], datetime.fromisoformat("2025-01-31T21:00:00+00:00"))


class FeatureTests(unittest.TestCase):
    def test_roic_registry_discloses_non_random_missingness(self) -> None:
        roic = next(item for item in DEFAULT_PROXY_REGISTRY if item.name == "roic")
        self.assertIn("outside [0, 1]", roic.missing_data_treatment)
        self.assertIn("non-random missingness", roic.missing_data_treatment)

    def test_mvp_formulas(self) -> None:
        rows = [
            fact("revenue", "2022-12-31", "2023-02-01T00:00:00+00:00", 100, "1"),
            fact("revenue", "2023-12-31", "2024-02-01T00:00:00+00:00", 110, "2"),
            fact("revenue", "2024-12-31", "2025-02-01T00:00:00+00:00", 132, "3"),
            fact("operating_income", "2023-12-31", "2024-02-01T00:00:00+00:00", 11, "2"),
            fact("operating_income", "2024-12-31", "2025-02-01T00:00:00+00:00", 19.8, "3"),
            fact("operating_cash_flow", "2023-12-31", "2024-02-01T00:00:00+00:00", 20, "2"),
            fact("operating_cash_flow", "2024-12-31", "2025-02-01T00:00:00+00:00", 30, "3"),
            fact("capital_expenditures", "2023-12-31", "2024-02-01T00:00:00+00:00", 5, "2"),
            fact("capital_expenditures", "2024-12-31", "2025-02-01T00:00:00+00:00", 6, "3"),
            fact("enterprise_value", "2024-12-31", "2025-02-01T00:00:00+00:00", 240, "3"),
            fact("gross_profit", "2023-12-31", "2024-02-01T00:00:00+00:00", 44, "2"),
            fact("gross_profit", "2024-12-31", "2025-02-01T00:00:00+00:00", 60, "3"),
            fact("total_assets", "2023-12-31", "2024-02-01T00:00:00+00:00", 190, "2"),
            fact("total_assets", "2024-12-31", "2025-02-01T00:00:00+00:00", 210, "3"),
            fact("income_tax_expense", "2023-12-31", "2024-02-01T00:00:00+00:00", 7.5, "2"),
            fact("income_tax_expense", "2024-12-31", "2025-02-01T00:00:00+00:00", 10, "3"),
            fact("income_before_tax", "2023-12-31", "2024-02-01T00:00:00+00:00", 30, "2"),
            fact("income_before_tax", "2024-12-31", "2025-02-01T00:00:00+00:00", 40, "3"),
            fact("invested_capital", "2023-12-31", "2024-02-01T00:00:00+00:00", 90, "2"),
            fact("invested_capital", "2024-12-31", "2025-02-01T00:00:00+00:00", 110, "3"),
        ]
        output = {
            item.observation.feature: item.observation.value
            for item in FeatureEngine(PointInTimeStore(rows)).calculate("AAA", datetime.fromisoformat("2025-03-01T21:00:00+00:00"))
        }
        self.assertAlmostEqual(output["fcf_ev"], 0.10)
        self.assertAlmostEqual(output["ebit_ev"], 0.0825)
        self.assertAlmostEqual(output["gross_profitability"], 0.30)
        self.assertAlmostEqual(output["roic"], 0.1485)
        self.assertAlmostEqual(output["operating_margin_change"], 0.05)
        self.assertAlmostEqual(output["revenue_acceleration"], 0.10)


if __name__ == "__main__":
    unittest.main()
