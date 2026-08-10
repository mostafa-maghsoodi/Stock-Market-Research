"""Deterministic MVP feature library.

These proxy definitions are proposed defaults. A research cycle must copy the
chosen subset into Entry 001 and freeze it before inspecting forward returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from statistics import mean
from typing import Mapping, Sequence

from .domain import FeatureObservation, ProxyDefinition, RestatementPolicy
from .pit import PointInTimeStore


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def average_pair(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return mean((current, previous))


DEFAULT_PROXY_REGISTRY: tuple[ProxyDefinition, ...] = (
    ProxyDefinition(
        name="fcf_ev",
        construct="valuation",
        formula="(operating_cash_flow - abs(capital_expenditures)) / enterprise_value",
        source_fields=("operating_cash_flow", "capital_expenditures", "enterprise_value"),
        expected_direction=1,
        availability_lag="source-specific public availability timestamp",
        accounting_weaknesses=("Capex tags are inconsistent across issuers.",),
        rationale="Cash output relative to the market value of operating assets.",
    ),
    ProxyDefinition(
        name="ebit_ev",
        construct="valuation",
        formula="operating_income / enterprise_value",
        source_fields=("operating_income", "enterprise_value"),
        expected_direction=1,
        availability_lag="source-specific public availability timestamp",
        rationale="Operating earnings relative to enterprise value.",
    ),
    ProxyDefinition(
        name="gross_profitability",
        construct="business_economics",
        formula="gross_profit / average(current_total_assets, prior_total_assets)",
        source_fields=("gross_profit", "total_assets"),
        expected_direction=1,
        availability_lag="source-specific public availability timestamp",
        accounting_weaknesses=("Financial-sector revenue and gross profit are not comparable.",),
        rationale="Operating output relative to the asset base.",
    ),
    ProxyDefinition(
        name="roic",
        construct="business_economics",
        formula="operating_income * (1 - income_tax_expense / income_before_tax) / average(current_invested_capital, prior_invested_capital)",
        source_fields=(
            "operating_income",
            "income_tax_expense",
            "income_before_tax",
            "invested_capital",
        ),
        expected_direction=1,
        availability_lag="source-specific public availability timestamp",
        missing_data_treatment=(
            "Return unavailable when pretax income is zero, the derived tax "
            "rate is outside [0, 1], or current/prior invested capital is "
            "missing. Preserve this non-random missingness as a diagnostic "
            "and apply the dimension-level policy frozen in Entry 001."
        ),
        accounting_weaknesses=(
            "Invested-capital definitions require sector routing.",
            "Tax-rate exclusions cluster in loss years, valuation-allowance releases, distress, and cyclical troughs.",
        ),
        rationale="After-tax operating return on the capital employed.",
    ),
    ProxyDefinition(
        name="operating_margin_change",
        construct="fundamental_change",
        formula="current(operating_income / revenue) - prior(operating_income / revenue)",
        source_fields=("operating_income", "revenue"),
        expected_direction=1,
        availability_lag="source-specific public availability timestamp",
        rationale="Realized change in operating profitability.",
    ),
    ProxyDefinition(
        name="fcf_margin_change",
        construct="fundamental_change",
        formula="current(fcf / revenue) - prior(fcf / revenue)",
        source_fields=("operating_cash_flow", "capital_expenditures", "revenue"),
        expected_direction=1,
        availability_lag="source-specific public availability timestamp",
        rationale="Realized change in cash generation relative to sales.",
    ),
    ProxyDefinition(
        name="revenue_acceleration",
        construct="fundamental_change",
        formula="current_yoy_revenue_growth - prior_yoy_revenue_growth",
        source_fields=("revenue",),
        expected_direction=1,
        availability_lag="source-specific public availability timestamp",
        rationale="Change in realized top-line growth.",
    ),
)


@dataclass(frozen=True)
class CalculatedFeature:
    observation: FeatureObservation
    inputs: Mapping[str, float]


class FeatureEngine:
    def __init__(
        self,
        store: PointInTimeStore,
        policy: RestatementPolicy = RestatementPolicy.FIRST_REPORTED,
    ) -> None:
        self.store = store
        self.policy = policy

    def _history(self, security_id: str, field: str, as_of: datetime) -> tuple:
        return self.store.history_as_of(security_id, field, as_of, self.policy)

    def _aligned_period_values(
        self, security_id: str, fields: Sequence[str], as_of: datetime
    ) -> list[tuple[date, dict[str, float]]]:
        histories = {
            field: {row.period_end: row.value for row in self._history(security_id, field, as_of)}
            for field in fields
        }
        common_periods = set.intersection(
            *(set(values) for values in histories.values())
        ) if histories else set()
        return [
            (period, {field: histories[field][period] for field in fields})
            for period in sorted(common_periods)
        ]

    def _latest_inputs(
        self, security_id: str, fields: Sequence[str], as_of: datetime
    ) -> tuple[date | None, dict[str, float]]:
        aligned = self._aligned_period_values(security_id, fields, as_of)
        return aligned[-1] if aligned else (None, {})

    def calculate(self, security_id: str, as_of: datetime) -> tuple[CalculatedFeature, ...]:
        results: list[CalculatedFeature] = []

        def add(name: str, construct: str, value: float | None, period: date | None, inputs: Mapping[str, float]) -> None:
            source_rows = [
                self.store.latest_as_of(security_id, field, as_of, self.policy)
                for field in inputs
            ]
            available = max(
                (row.available_at for row in source_rows if row is not None),
                default=None,
            )
            results.append(CalculatedFeature(
                observation=FeatureObservation(
                    security_id=security_id,
                    decision_date=as_of.date(),
                    feature=name,
                    construct=construct,
                    value=value,
                    source_period_end=period,
                    source_available_at=available,
                ),
                inputs=dict(inputs),
            ))

        period, cash_inputs = self._latest_inputs(
            security_id,
            ("operating_cash_flow", "capital_expenditures"),
            as_of,
        )
        ev_record = self.store.latest_as_of(security_id, "enterprise_value", as_of, self.policy)
        x = {**cash_inputs}
        if ev_record is not None:
            x["enterprise_value"] = ev_record.value
        fcf = cash_inputs.get("operating_cash_flow")
        capex = cash_inputs.get("capital_expenditures")
        fcf = fcf - abs(capex) if fcf is not None and capex is not None else None
        add("fcf_ev", "valuation", safe_divide(fcf, x.get("enterprise_value")), period, x)

        operating_record = self.store.latest_as_of(security_id, "operating_income", as_of, self.policy)
        ev_record = self.store.latest_as_of(security_id, "enterprise_value", as_of, self.policy)
        x = {}
        if operating_record is not None:
            x["operating_income"] = operating_record.value
        if ev_record is not None:
            x["enterprise_value"] = ev_record.value
        period = operating_record.period_end if operating_record is not None else None
        add("ebit_ev", "valuation", safe_divide(x.get("operating_income"), x.get("enterprise_value")), period, x)

        gp = self._aligned_period_values(security_id, ("gross_profit", "total_assets"), as_of)
        if len(gp) >= 2:
            period, current = gp[-1]
            prior = gp[-2][1]
            avg_assets = average_pair(current["total_assets"], prior["total_assets"])
            value = safe_divide(current["gross_profit"], avg_assets)
            inputs = {**current, "prior_total_assets": prior["total_assets"]}
        else:
            period, value, inputs = None, None, {}
        add("gross_profitability", "business_economics", value, period, inputs)

        roic_current = self._aligned_period_values(
            security_id,
            (
                "operating_income",
                "income_tax_expense",
                "income_before_tax",
                "invested_capital",
            ),
            as_of,
        )
        capital_history = self._history(security_id, "invested_capital", as_of)
        if roic_current:
            period, current = roic_current[-1]
            earlier_capital = [
                row for row in capital_history if row.period_end < period
            ]
            tax_rate = safe_divide(
                current["income_tax_expense"],
                current["income_before_tax"],
            )
        else:
            period, current, earlier_capital, tax_rate = None, {}, [], None
        if (
            period is not None
            and earlier_capital
            and tax_rate is not None
            and 0.0 <= tax_rate <= 1.0
        ):
            prior_capital = earlier_capital[-1].value
            avg_capital = average_pair(current["invested_capital"], prior_capital)
            nopat = current["operating_income"] * (1.0 - tax_rate)
            value = safe_divide(nopat, avg_capital)
            inputs = {
                **current,
                "computed_effective_tax_rate": tax_rate,
                "prior_invested_capital": prior_capital,
            }
        else:
            period, value, inputs = None, None, {}
        add("roic", "business_economics", value, period, inputs)

        margins = self._aligned_period_values(security_id, ("operating_income", "revenue"), as_of)
        if len(margins) >= 2:
            period, current = margins[-1]
            prior = margins[-2][1]
            value = (
                safe_divide(current["operating_income"], current["revenue"])
                - safe_divide(prior["operating_income"], prior["revenue"])
                if current["revenue"] and prior["revenue"] else None
            )
            inputs = {**current, "prior_operating_income": prior["operating_income"], "prior_revenue": prior["revenue"]}
        else:
            period, value, inputs = None, None, {}
        add("operating_margin_change", "fundamental_change", value, period, inputs)

        fcf_margins = self._aligned_period_values(
            security_id, ("operating_cash_flow", "capital_expenditures", "revenue"), as_of
        )
        if len(fcf_margins) >= 2:
            period, current = fcf_margins[-1]
            prior = fcf_margins[-2][1]
            current_fcf = current["operating_cash_flow"] - abs(current["capital_expenditures"])
            prior_fcf = prior["operating_cash_flow"] - abs(prior["capital_expenditures"])
            current_margin = safe_divide(current_fcf, current["revenue"])
            prior_margin = safe_divide(prior_fcf, prior["revenue"])
            value = current_margin - prior_margin if current_margin is not None and prior_margin is not None else None
            inputs = {**current, "prior_fcf": prior_fcf, "prior_revenue": prior["revenue"]}
        else:
            period, value, inputs = None, None, {}
        add("fcf_margin_change", "fundamental_change", value, period, inputs)

        revenues = self._history(security_id, "revenue", as_of)
        if len(revenues) >= 3:
            first, prior, current = revenues[-3:]
            current_growth = safe_divide(current.value, prior.value)
            prior_growth = safe_divide(prior.value, first.value)
            value = (
                (current_growth - 1.0) - (prior_growth - 1.0)
                if current_growth is not None and prior_growth is not None else None
            )
            period = current.period_end
            inputs = {"current_revenue": current.value, "prior_revenue": prior.value, "two_year_prior_revenue": first.value}
        else:
            period, value, inputs = None, None, {}
        add("revenue_acceleration", "fundamental_change", value, period, inputs)

        return tuple(results)
