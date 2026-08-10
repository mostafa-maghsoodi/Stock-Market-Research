from __future__ import annotations

from contextlib import contextmanager
import csv
from datetime import date, datetime
import hashlib
from pathlib import Path
import tempfile
from unittest.mock import patch

from graham_research.datasets import (
    HeldPeriodReturnObservation,
    load_governed_fact_dataset,
    load_governed_held_return_source,
)
from graham_research.domain import FactObservation, PeriodType, ReportingFrequency
from graham_research.governance import (
    ENTRY_001_REQUIRED_KEYS,
    SPECIFICATION_COUNTING_RULES,
    freeze_artifact,
    load_resolved_entry_001,
)


SYNTHETIC_NEAR_ZERO_THRESHOLD = 7.125
SYNTHETIC_MINIMUM_FEATURE_COVERAGE = 0.413
FROZEN_PINS = {"numpy": "2.3.5", "pandas": "2.2.3"}
FROZEN_RUNTIME = {
    "python": "3.12.0",
    "implementation": "CPython",
    "platform": "synthetic-test-platform",
}
SYNTHETIC_RESEARCH_VINTAGE_BUNDLE = "synthetic-research-vintage-bundle"


def denominator_policy(
    *, negative: str = "exclude_feature", near_zero: str = "exclude_feature"
) -> dict[str, object]:
    return {
        "missing": "exclude_feature",
        "zero": "exclude_feature",
        "negative": negative,
        "near_zero": near_zero,
        "near_zero_absolute_threshold": SYNTHETIC_NEAR_ZERO_THRESHOLD,
    }


def _role(name: str, field: str, period_type: str, offset: int) -> dict[str, object]:
    return {
        "role_name": name,
        "source_field": field,
        "role_kind": "accounting_role",
        "period_type": period_type,
        "fiscal_year_offset": offset,
    }


def proxy_payload(name: str) -> dict[str, object]:
    common = {
        "expected_direction": 1,
        "availability_lag": "source-specific public availability timestamp",
        "transformation": "cross_sectional_percentile_rank",
        "sector_treatment": "none",
        "missing_data_treatment": "exclude_feature_for_security",
        "accounting_weaknesses": ["synthetic fixture only"],
        "rationale": "synthetic fixture only",
        "required_reporting_frequency": "annual",
        "frequency_exempt_source_fields": [],
        "fiscal_year_observation_selection_rule": "reject_ambiguous",
    }
    if name == "gross_profitability":
        return {
            **common,
            "name": name,
            "construct": "business_economics",
            "formula": "gross_profit / average(current_total_assets, prior_total_assets)",
            "source_fields": ["gross_profit", "total_assets"],
            "frequency_governed_source_fields": ["gross_profit", "total_assets"],
            "prior_gross_profit_dependency": "do_not_require_prior_gross_profit",
            "same_offset_alignment_rule": "identical_period_end",
            "required_period_structure": [
                _role("current_gross_profit", "gross_profit", "duration", 0),
                _role("current_total_assets", "total_assets", "instant", 0),
                _role("prior_total_assets", "total_assets", "instant", -1),
            ],
            "denominator_definitions": [{
                "denominator_id": "average_total_assets",
                "contributing_roles": ["current_total_assets", "prior_total_assets"],
                "transformation": "average",
                "denominator_policy": denominator_policy(),
            }],
        }
    if name == "roic":
        fields = ["operating_income", "income_tax_expense", "income_before_tax", "invested_capital"]
        return {
            **common,
            "name": name,
            "construct": "business_economics",
            "formula": "operating_income * (1 - income_tax_expense / income_before_tax) / average(current_invested_capital, prior_invested_capital)",
            "source_fields": fields,
            "frequency_governed_source_fields": fields,
            "same_offset_alignment_rule": "identical_period_end",
            "required_period_structure": [
                _role("current_operating_income", "operating_income", "duration", 0),
                _role("current_income_tax_expense", "income_tax_expense", "duration", 0),
                _role("current_income_before_tax", "income_before_tax", "duration", 0),
                _role("current_invested_capital", "invested_capital", "instant", 0),
                _role("prior_invested_capital", "invested_capital", "instant", -1),
            ],
            "denominator_definitions": [
                {
                    "denominator_id": "income_before_tax_for_effective_tax_rate",
                    "contributing_roles": ["current_income_before_tax"],
                    "transformation": "direct_role",
                    "denominator_policy": denominator_policy(),
                },
                {
                    "denominator_id": "average_invested_capital",
                    "contributing_roles": ["current_invested_capital", "prior_invested_capital"],
                    "transformation": "average",
                    "denominator_policy": denominator_policy(),
                },
            ],
        }
    if name == "operating_margin_change":
        return {
            **common,
            "name": name,
            "construct": "fundamental_change",
            "formula": "current(operating_income / revenue) - prior(operating_income / revenue)",
            "source_fields": ["operating_income", "revenue"],
            "frequency_governed_source_fields": ["operating_income", "revenue"],
            "same_offset_alignment_rule": "identical_period_end",
            "required_period_structure": [
                _role("current_operating_income", "operating_income", "duration", 0),
                _role("current_revenue", "revenue", "duration", 0),
                _role("prior_operating_income", "operating_income", "duration", -1),
                _role("prior_revenue", "revenue", "duration", -1),
            ],
            "denominator_definitions": [
                {
                    "denominator_id": "current_revenue",
                    "contributing_roles": ["current_revenue"],
                    "transformation": "direct_role",
                    "denominator_policy": denominator_policy(),
                },
                {
                    "denominator_id": "prior_revenue",
                    "contributing_roles": ["prior_revenue"],
                    "transformation": "direct_role",
                    "denominator_policy": denominator_policy(),
                },
            ],
        }
    if name == "fcf_margin_change":
        fields = ["operating_cash_flow", "capital_expenditures", "revenue"]
        return {
            **common,
            "name": name,
            "construct": "fundamental_change",
            "formula": "current(fcf / revenue) - prior(fcf / revenue)",
            "source_fields": fields,
            "frequency_governed_source_fields": fields,
            "same_offset_alignment_rule": "identical_period_end",
            "required_period_structure": [
                _role("current_operating_cash_flow", "operating_cash_flow", "duration", 0),
                _role("current_capital_expenditures", "capital_expenditures", "duration", 0),
                _role("current_revenue", "revenue", "duration", 0),
                _role("prior_operating_cash_flow", "operating_cash_flow", "duration", -1),
                _role("prior_capital_expenditures", "capital_expenditures", "duration", -1),
                _role("prior_revenue", "revenue", "duration", -1),
            ],
            "denominator_definitions": [
                {
                    "denominator_id": "current_revenue",
                    "contributing_roles": ["current_revenue"],
                    "transformation": "direct_role",
                    "denominator_policy": denominator_policy(),
                },
                {
                    "denominator_id": "prior_revenue",
                    "contributing_roles": ["prior_revenue"],
                    "transformation": "direct_role",
                    "denominator_policy": denominator_policy(),
                },
            ],
        }
    if name == "revenue_acceleration":
        return {
            **common,
            "name": name,
            "construct": "fundamental_change",
            "formula": "current_yoy_revenue_growth - prior_yoy_revenue_growth",
            "source_fields": ["revenue"],
            "frequency_governed_source_fields": ["revenue"],
            "same_offset_alignment_rule": "not_applicable",
            "required_period_structure": [
                _role("current_revenue", "revenue", "duration", 0),
                _role("prior_revenue", "revenue", "duration", -1),
                _role("two_year_prior_revenue", "revenue", "duration", -2),
            ],
            "denominator_definitions": [
                {
                    "denominator_id": "prior_revenue_for_current_growth",
                    "contributing_roles": ["prior_revenue"],
                    "transformation": "prior_period_base",
                    "denominator_policy": denominator_policy(),
                },
                {
                    "denominator_id": "two_year_prior_revenue_for_prior_growth",
                    "contributing_roles": ["two_year_prior_revenue"],
                    "transformation": "prior_period_base",
                    "denominator_policy": denominator_policy(),
                },
            ],
        }
    raise KeyError(name)


def frozen_environment_fixture() -> dict[str, object]:
    return {
        "schema_version": 1,
        **FROZEN_RUNTIME,
        "packages": dict(FROZEN_PINS),
        "pinned_dependencies": dict(FROZEN_PINS),
        "dependency_match": True,
        "mismatches": {},
    }


def complete_entry_001(
    proxy_names: tuple[str, ...] = ("gross_profitability", "revenue_acceleration"),
) -> dict[str, object]:
    payload: dict[str, object] = {
        key: ({"synthetic": True} if key not in {
            "entry_001_schema_version", "architecture_version", "specification_budget"
        } else (
            2 if key == "entry_001_schema_version"
            else "3.1" if key == "architecture_version"
            else 10
        ))
        for key in ENTRY_001_REQUIRED_KEYS
    }
    proxies = [proxy_payload(name) for name in proxy_names]
    payload.update({
        "proxy_registry": proxies,
        "required_dimensions": sorted({str(item["construct"]) for item in proxies}),
        "missing_data_policy": {
            "policy": "exclude",
            "minimum_feature_coverage": SYNTHETIC_MINIMUM_FEATURE_COVERAGE,
            "minimum_features_per_dimension": 1,
        },
        "pit_conventions": {
            "restatement_policy": "first_reported",
            "availability_timestamp": (
                "actual public filing or announcement timestamp"
            ),
        },
        "research_provenance": [{"artifact": "synthetic-test-only"}],
        "sample_boundaries": {
            "development": {
                "start": "2020-01-01",
                "end": "2029-12-31",
                "start_boundary_rule": "included",
                "end_boundary_rule": "included",
            },
            "holdout_a": {
                "start": "2030-01-01",
                "end": "2039-12-31",
                "start_boundary_rule": "included",
                "end_boundary_rule": "included",
            },
            "holdout_b": {
                "start": "2040-01-01",
                "end": "2049-12-31",
                "start_boundary_rule": "included",
                "end_boundary_rule": "included",
            },
            "partition_overlap_policy": "forbid",
            "partition_gap_policy": "allow",
            "shared_boundary_assignment_rule": "not_applicable",
        },
        "portfolio_timing": {
            "calendar_basis": "calendar_months",
            "rebalance_interval_count": 1,
            "rebalance_date_convention": "calendar_month_end",
            "month_end_convention": "civil_calendar_month_end",
            "schedule_anchor_date": "not_applicable",
            "anchor_semantics": "not_applicable",
            "holding_period_equals_rebalance_interval": True,
            "holding_period_rule": "rebalance_interval",
            "holding_period_interval_count": "not_applicable",
            "return_interval_start_rule": "decision_date",
            "return_interval_end_rule": "next_scheduled_decision_date",
            "decision_information_cutoff": "synthetic_test_information_cutoff",
            "portfolio_execution_timing": "synthetic_test_execution_timing",
            "return_measurement_start": "synthetic_test_measurement_start",
            "return_measurement_end": "synthetic_test_measurement_end",
            "market_session_basis": "synthetic_test_session_basis",
            "market_timezone": "America/New_York",
            "return_start_endpoint_inclusion": "included",
            "return_end_endpoint_inclusion": "excluded",
            "held_return_source_convention": "synthetic_test_held_return_convention",
        },
        "portfolio_construction": {
            "selection_rule": "top_n",
            "number_of_positions": 2,
            "sizing_rule": "equal_weight",
            "insufficient_eligible_policy": "fail",
            "unfilled_capacity_policy": "not_applicable",
        },
        "terminal_position_policy": "fail_on_any_terminal_event",
        "data_vintage_identifier": SYNTHETIC_RESEARCH_VINTAGE_BUNDLE,
        "environment_manifest": frozen_environment_fixture(),
        "source_control": {"vcs": "git", "commit": "a" * 40, "dirty": False},
        "transaction_cost_model": {
            "convention": "traded_notional_times_one_way_bps",
            "one_way_cost_bps": 100.0,
        },
        "specification_counting_rules": dict(SPECIFICATION_COUNTING_RULES),
    })
    return payload


@contextmanager
def matching_frozen_runtime():
    versions = dict(FROZEN_PINS)
    with (
        patch(
            "graham_research.governance.importlib.metadata.version",
            side_effect=lambda name: versions[name],
        ),
        patch(
            "graham_research.governance.platform.python_version",
            return_value=FROZEN_RUNTIME["python"],
        ),
        patch(
            "graham_research.governance.platform.python_implementation",
            return_value=FROZEN_RUNTIME["implementation"],
        ),
        patch(
            "graham_research.governance.platform.platform",
            return_value=FROZEN_RUNTIME["platform"],
        ),
    ):
        yield


def resolved_entry(proxy_names: tuple[str, ...]):
    return resolved_entry_from_payload(complete_entry_001(proxy_names))


def resolved_entry_from_payload(payload: dict[str, object]):
    temporary = tempfile.TemporaryDirectory()
    path = Path(temporary.name) / "entry001.json"
    frozen_payload = {**payload, "entry": "001", "created_at": "synthetic"}
    freeze_artifact(path, frozen_payload)
    with matching_frozen_runtime():
        result = load_resolved_entry_001(path)
    temporary.cleanup()
    return result


def fact(
    security_id: str,
    field: str,
    fiscal_year: int,
    value: float,
    *,
    period_type: PeriodType | str = PeriodType.DURATION,
    frequency: ReportingFrequency | str = ReportingFrequency.ANNUAL,
    available_year: int | None = None,
    period_end: date | None = None,
    accession: str | None = None,
) -> FactObservation:
    available_year = available_year or fiscal_year + 1
    return FactObservation(
        security_id=security_id,
        field=field,
        period_end=period_end or date(fiscal_year, 12, 31),
        available_at=datetime.fromisoformat(
            f"{available_year}-02-15T21:00:00+00:00"
        ),
        value=value,
        source="synthetic-test",
        accession=accession or f"{field}-{fiscal_year}-{frequency}",
        unit="USD",
        period_type=period_type,
        reporting_frequency=frequency,
        form_type="10-K" if str(frequency) in {"annual", "ReportingFrequency.ANNUAL"} else "10-Q",
        fiscal_year=fiscal_year,
    )


def governed_fact_dataset(
    rows: list[FactObservation] | tuple[FactObservation, ...],
    *,
    research_vintage_bundle_id: str = SYNTHETIC_RESEARCH_VINTAGE_BUNDLE,
    source_native_vintage_identifier: str = "synthetic-fact-native-vintage",
):
    with tempfile.TemporaryDirectory() as temporary:
        data_path = Path(temporary) / "facts.csv"
        fields = [
            "security_id", "field", "period_end", "available_at", "value",
            "source", "accession", "unit", "period_type",
            "reporting_frequency", "form_type", "fiscal_year", "fiscal_quarter",
        ]
        with data_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "security_id": row.security_id,
                    "field": row.field,
                    "period_end": row.period_end.isoformat(),
                    "available_at": row.available_at.isoformat(),
                    "value": row.value,
                    "source": row.source,
                    "accession": row.accession or "",
                    "unit": row.unit or "",
                    "period_type": row.period_type.value,
                    "reporting_frequency": row.reporting_frequency.value,
                    "form_type": row.form_type or "",
                    "fiscal_year": row.fiscal_year or "",
                    "fiscal_quarter": row.fiscal_quarter or "",
                })
        manifest_path = Path(temporary) / "facts.manifest.json"
        freeze_artifact(manifest_path, {
            "source_manifest_schema_version": 2,
            "source_kind": "pit_facts",
            "source_id": "synthetic-fact-source",
            "research_vintage_bundle_id": research_vintage_bundle_id,
            "source_native_vintage_identifier": source_native_vintage_identifier,
            "content_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
            "audit_artifact_sha256": "f" * 64,
            "provenance": "audited_local_ingest_manifest",
        })
        return load_governed_fact_dataset(data_path, manifest_path)


def governed_return_source(
    rows: list[HeldPeriodReturnObservation],
    *,
    research_vintage_bundle_id: str = SYNTHETIC_RESEARCH_VINTAGE_BUNDLE,
    source_native_vintage_identifier: str = "synthetic-return-native-vintage",
    economic_return_convention: dict[str, str] | None = None,
):
    with tempfile.TemporaryDirectory() as temporary:
        data_path = Path(temporary) / "returns.csv"
        with data_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "security_id", "period_start", "period_end", "total_return",
                "terminal_flag",
            ])
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "security_id": row.security_id,
                    "period_start": row.period_start.isoformat(),
                    "period_end": row.period_end.isoformat(),
                    "total_return": row.total_return,
                    "terminal_flag": str(row.terminal_flag).lower(),
                })
        manifest_path = Path(temporary) / "returns.manifest.json"
        freeze_artifact(manifest_path, {
            "source_manifest_schema_version": 2,
            "source_kind": "held_period_returns",
            "source_id": "synthetic-return-source",
            "research_vintage_bundle_id": research_vintage_bundle_id,
            "source_native_vintage_identifier": source_native_vintage_identifier,
            "content_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
            "audit_artifact_sha256": "e" * 64,
            "provenance": "audited_local_ingest_manifest",
            "economic_return_convention": ({
                "decision_information_cutoff": "synthetic_test_information_cutoff",
                "portfolio_execution_timing": "synthetic_test_execution_timing",
                "return_measurement_start": "synthetic_test_measurement_start",
                "return_measurement_end": "synthetic_test_measurement_end",
                "market_session_basis": "synthetic_test_session_basis",
                "market_timezone": "America/New_York",
                "return_start_endpoint_inclusion": "included",
                "return_end_endpoint_inclusion": "excluded",
                "held_return_source_convention": "synthetic_test_held_return_convention",
            } if economic_return_convention is None else economic_return_convention),
        })
        return load_governed_held_return_source(data_path, manifest_path)
