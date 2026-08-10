"""Governed point-in-time feature construction.

The descriptive registry below remains candidate material only.  Governed
execution accepts exclusively a :class:`ResolvedEntry001` loaded from a valid,
frozen Entry 001 v2 artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from statistics import mean
from typing import Mapping, Sequence

from .domain import (
    DenominatorAction,
    DenominatorDefinition,
    DenominatorTransformation,
    FactObservation,
    FeatureExclusionReason,
    FeatureObservation,
    FiscalYearObservationSelection,
    ProxyDefinition,
    SameOffsetAlignment,
)
from .governance import (
    GovernanceError,
    ResolvedEntry001,
    source_control_manifest,
)
from .pit import PointInTimeStore


@dataclass(frozen=True)
class CandidateProxyDefinition:
    """Non-executable description of a calculator candidate."""

    name: str
    construct: str
    formula: str
    source_fields: tuple[str, ...]
    expected_direction: int
    missing_data_treatment: str = "UNRESOLVED"
    accounting_weaknesses: tuple[str, ...] = ()


DEFAULT_PROXY_REGISTRY: tuple[CandidateProxyDefinition, ...] = (
    CandidateProxyDefinition(
        "fcf_ev", "valuation",
        "(operating_cash_flow - abs(capital_expenditures)) / enterprise_value",
        ("operating_cash_flow", "capital_expenditures", "enterprise_value"), 1,
    ),
    CandidateProxyDefinition(
        "ebit_ev", "valuation", "operating_income / enterprise_value",
        ("operating_income", "enterprise_value"), 1,
    ),
    CandidateProxyDefinition(
        "gross_profitability", "business_economics",
        "gross_profit / average(current_total_assets, prior_total_assets)",
        ("gross_profit", "total_assets"), 1,
    ),
    CandidateProxyDefinition(
        "roic", "business_economics",
        "operating_income * (1 - income_tax_expense / income_before_tax) / average(current_invested_capital, prior_invested_capital)",
        ("operating_income", "income_tax_expense", "income_before_tax", "invested_capital"),
        1,
        missing_data_treatment=(
            "UNRESOLVED: tax-rate bounds and dimension-level missingness must be "
            "approved before governed execution; missingness clusters in loss "
            "years, valuation-allowance releases, distress, and cyclical troughs."
        ),
    ),
    CandidateProxyDefinition(
        "operating_margin_change", "fundamental_change",
        "current(operating_income / revenue) - prior(operating_income / revenue)",
        ("operating_income", "revenue"), 1,
    ),
    CandidateProxyDefinition(
        "fcf_margin_change", "fundamental_change",
        "current(fcf / revenue) - prior(fcf / revenue)",
        ("operating_cash_flow", "capital_expenditures", "revenue"), 1,
    ),
    CandidateProxyDefinition(
        "revenue_acceleration", "fundamental_change",
        "current_yoy_revenue_growth - prior_yoy_revenue_growth",
        ("revenue",), 1,
    ),
)


@dataclass(frozen=True)
class FeatureCalculationResult:
    """Internal result retaining exact consumed source objects."""

    value: float | None
    source_observations: tuple[FactObservation, ...]
    derived_inputs: Mapping[str, float]
    exclusion_reasons: tuple[str, ...]


_BATCH_TOKEN = object()


@dataclass(frozen=True, init=False)
class GovernedFeatureBatch:
    observations: tuple[FeatureObservation, ...]
    proxy_registry_digest: str
    feature_generation_code_commit: str

    def __init__(
        self,
        observations: tuple[FeatureObservation, ...],
        proxy_registry_digest: str,
        feature_generation_code_commit: str,
        *,
        _token: object,
    ) -> None:
        if _token is not _BATCH_TOKEN:
            raise TypeError(
                "GovernedFeatureBatch is emitted only by governed feature calculation"
            )
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "proxy_registry_digest", proxy_registry_digest)
        object.__setattr__(
            self, "feature_generation_code_commit", feature_generation_code_commit
        )


@dataclass(frozen=True)
class _RoleResolution:
    observations: Mapping[str, FactObservation]
    exclusion_reasons: tuple[str, ...]


def _reason_values(*reasons: FeatureExclusionReason) -> tuple[str, ...]:
    return tuple(sorted({reason.value for reason in reasons}))


class FeatureEngine:
    """Feature engine gated by a verified and resolved Entry 001 v2."""

    def __init__(
        self,
        store: PointInTimeStore,
        resolved_entry_001: ResolvedEntry001,
    ) -> None:
        if not isinstance(resolved_entry_001, ResolvedEntry001):
            raise TypeError(
                "governed FeatureEngine requires a verified ResolvedEntry001"
            )
        self.store = store
        self.resolved_entry_001 = resolved_entry_001
        self.restatement_policy = resolved_entry_001.restatement_policy

    def _admissible_history(
        self,
        security_id: str,
        proxy: ProxyDefinition,
        source_field: str,
        required_period_type: object,
        as_of: datetime,
    ) -> tuple[tuple[FactObservation, ...], tuple[str, ...]]:
        raw = self.store.eligible_versions_as_of(security_id, source_field, as_of)
        if not raw:
            return (), _reason_values(FeatureExclusionReason.INSUFFICIENT_HISTORY)

        governed = source_field in proxy.frequency_governed_source_fields
        frequency_filtered = tuple(
            row
            for row in raw
            if not governed
            or row.reporting_frequency is proxy.required_reporting_frequency
        )
        if not frequency_filtered:
            if governed and any(row.reporting_frequency.value == "unknown" for row in raw):
                return (), _reason_values(
                    FeatureExclusionReason.UNKNOWN_REPORTING_FREQUENCY
                )
            return (), _reason_values(
                FeatureExclusionReason.REPORTING_FREQUENCY_MISMATCH
            )

        period_filtered = tuple(
            row for row in frequency_filtered if row.period_type is required_period_type
        )
        if not period_filtered:
            return (), _reason_values(FeatureExclusionReason.INCOMPATIBLE_PERIOD_TYPE)

        return period_filtered, ()

    def _select_version(
        self,
        candidates: Sequence[FactObservation],
    ) -> FactObservation:
        selected = PointInTimeStore._select_versions(
            candidates,
            self.restatement_policy,
        )
        if len(selected) != 1:
            raise GovernanceError(
                "role version selection requires one admissible period_end"
            )
        return selected[0]

    def _admissible_role_versions(
        self,
        candidates: Sequence[FactObservation],
        target_fiscal_year: int,
        rule: FiscalYearObservationSelection,
    ) -> tuple[tuple[FactObservation, ...], tuple[str, ...]]:
        matching = [row for row in candidates if row.fiscal_year == target_fiscal_year]
        if not matching:
            return (), _reason_values(FeatureExclusionReason.NONCONSECUTIVE_FISCAL_YEARS)
        distinct_periods = {row.period_end for row in matching}
        if len(distinct_periods) > 1:
            if rule is FiscalYearObservationSelection.REJECT_AMBIGUOUS:
                return (), _reason_values(FeatureExclusionReason.AMBIGUOUS_FISCAL_YEAR)
            latest_period = max(distinct_periods)
            matching = [row for row in matching if row.period_end == latest_period]
        selected_period = matching[0].period_end
        admissible_versions = tuple(
            row for row in matching if row.period_end == selected_period
        )
        return admissible_versions, ()

    def _resolve_roles(
        self,
        security_id: str,
        proxy: ProxyDefinition,
        as_of: datetime,
    ) -> _RoleResolution:
        histories: dict[str, tuple[FactObservation, ...]] = {}
        reasons: set[str] = set()
        denominator_roles = {
            role_name: tuple(
                definition
                for definition in proxy.denominator_definitions
                if role_name in definition.contributing_roles
            )
            for role_name in {
                contributor
                for definition in proxy.denominator_definitions
                for contributor in definition.contributing_roles
            }
        }
        for role in proxy.required_period_structure:
            history, role_reasons = self._admissible_history(
                security_id,
                proxy,
                role.source_field,
                role.period_type,
                as_of,
            )
            histories[role.role_name] = history
            if (
                role.role_name in denominator_roles
                and role_reasons == (FeatureExclusionReason.INSUFFICIENT_HISTORY.value,)
            ):
                definitions = denominator_roles[role.role_name]
                if any(
                    item.denominator_policy.missing is DenominatorAction.EXCLUDE_FEATURE
                    for item in definitions
                ):
                    reasons.add(FeatureExclusionReason.DENOMINATOR_MISSING.value)
                else:
                    reasons.add(FeatureExclusionReason.INCOMPLETE_PROVENANCE.value)
            else:
                reasons.update(role_reasons)
        if reasons:
            return _RoleResolution({}, tuple(sorted(reasons)))

        offsets = {
            int(role.fiscal_year_offset) for role in proxy.required_period_structure
        }
        requires_fiscal_year = (
            len(offsets) > 1
            or proxy.same_offset_alignment_rule is SameOffsetAlignment.SAME_FISCAL_YEAR
        )
        if not requires_fiscal_year:
            common_periods = set.intersection(
                *(
                    {row.period_end for row in histories[role.role_name]}
                    for role in proxy.required_period_structure
                )
            )
            if not common_periods:
                return _RoleResolution(
                    {}, _reason_values(FeatureExclusionReason.PERIOD_STRUCTURE_MISMATCH)
                )
            selected_period = max(common_periods)
            selected = {
                role.role_name: self._select_version(
                    tuple(
                        row
                        for row in histories[role.role_name]
                        if row.period_end == selected_period
                    )
                )
                for role in proxy.required_period_structure
            }
            return _RoleResolution(selected, ())

        all_rows = [row for history in histories.values() for row in history]
        has_missing_fiscal_year = any(row.fiscal_year is None for row in all_rows)
        if any(
            not any(row.fiscal_year is not None for row in history)
            for history in histories.values()
        ):
            return _RoleResolution(
                {}, _reason_values(FeatureExclusionReason.MISSING_FISCAL_YEAR_METADATA)
            )

        possible_anchors: set[int] | None = None
        for role in proxy.required_period_structure:
            anchors = {
                int(row.fiscal_year) - int(role.fiscal_year_offset)
                for row in histories[role.role_name]
                if row.fiscal_year is not None
            }
            possible_anchors = anchors if possible_anchors is None else possible_anchors & anchors
        if not possible_anchors:
            return _RoleResolution(
                {},
                _reason_values(
                    FeatureExclusionReason.MISSING_FISCAL_YEAR_METADATA
                    if has_missing_fiscal_year
                    else FeatureExclusionReason.NONCONSECUTIVE_FISCAL_YEARS
                ),
            )

        accumulated: set[str] = set()
        for anchor in sorted(possible_anchors, reverse=True):
            role_versions: dict[str, tuple[FactObservation, ...]] = {}
            failed = False
            for role in proxy.required_period_structure:
                admissible_versions, selection_reasons = self._admissible_role_versions(
                    histories[role.role_name],
                    anchor + int(role.fiscal_year_offset),
                    proxy.fiscal_year_observation_selection_rule,
                )
                if not admissible_versions:
                    accumulated.update(selection_reasons)
                    failed = True
                    break
                role_versions[role.role_name] = admissible_versions
            if failed:
                continue
            if proxy.same_offset_alignment_rule is SameOffsetAlignment.IDENTICAL_PERIOD_END:
                by_offset: dict[int, set[object]] = {}
                for role in proxy.required_period_structure:
                    by_offset.setdefault(int(role.fiscal_year_offset), set()).add(
                        role_versions[role.role_name][0].period_end
                    )
                if any(len(periods) > 1 for periods in by_offset.values()):
                    accumulated.add(FeatureExclusionReason.PERIOD_STRUCTURE_MISMATCH.value)
                    continue
            selected = {
                role.role_name: self._select_version(role_versions[role.role_name])
                for role in proxy.required_period_structure
            }
            return _RoleResolution(selected, ())
        return _RoleResolution(
            {},
            tuple(sorted(accumulated))
            or _reason_values(FeatureExclusionReason.PERIOD_STRUCTURE_MISMATCH),
        )

    @staticmethod
    def _denominator(
        definition: DenominatorDefinition,
        values: Mapping[str, float],
    ) -> tuple[float | None, tuple[str, ...]]:
        components = [values.get(role) for role in definition.contributing_roles]
        if any(value is None for value in components):
            if definition.denominator_policy.missing is DenominatorAction.EXCLUDE_FEATURE:
                return None, _reason_values(FeatureExclusionReason.DENOMINATOR_MISSING)
            # An explicit allow action cannot manufacture a missing number; the
            # feature remains unavailable under the independent exact-
            # provenance invariant.
            return None, _reason_values(FeatureExclusionReason.INCOMPLETE_PROVENANCE)
        numeric = [float(value) for value in components if value is not None]
        if definition.transformation is DenominatorTransformation.AVERAGE:
            result = mean(numeric)
        else:
            result = numeric[0]
        policy = definition.denominator_policy
        if result == 0:
            action = policy.zero
        elif 0 < abs(result) < policy.near_zero_absolute_threshold:
            action = policy.near_zero
        elif result < 0:
            action = policy.negative
        else:
            return result, ()
        if action is DenominatorAction.EXCLUDE_FEATURE or result == 0:
            return None, _reason_values(
                FeatureExclusionReason.DENOMINATOR_POLICY_EXCLUSION
            )
        return result, ()

    @staticmethod
    def _definition(proxy: ProxyDefinition, denominator_id: str) -> DenominatorDefinition:
        return next(
            item
            for item in proxy.denominator_definitions
            if item.denominator_id == denominator_id
        )

    def _calculate_proxy(
        self,
        security_id: str,
        proxy: ProxyDefinition,
        as_of: datetime,
    ) -> FeatureCalculationResult:
        resolution = self._resolve_roles(security_id, proxy, as_of)
        if resolution.exclusion_reasons:
            return FeatureCalculationResult(None, (), {}, resolution.exclusion_reasons)
        observations = resolution.observations
        values = {name: row.value for name, row in observations.items()}
        reasons: set[str] = set()

        def denominator(identifier: str) -> float | None:
            value, denominator_reasons = self._denominator(
                self._definition(proxy, identifier), values
            )
            reasons.update(denominator_reasons)
            return value

        value: float | None
        if proxy.name == "gross_profitability":
            assets = denominator("average_total_assets")
            value = values["current_gross_profit"] / assets if assets is not None else None
        elif proxy.name == "roic":
            pretax = denominator("income_before_tax_for_effective_tax_rate")
            capital = denominator("average_invested_capital")
            if pretax is None or capital is None:
                value = None
            else:
                tax_rate = values["current_income_tax_expense"] / pretax
                if not 0 <= tax_rate <= 1:
                    reasons.add(FeatureExclusionReason.FORMULA_UNAVAILABLE.value)
                    value = None
                else:
                    nopat = values["current_operating_income"] * (1 - tax_rate)
                    value = nopat / capital
        elif proxy.name == "operating_margin_change":
            current_revenue = denominator("current_revenue")
            prior_revenue = denominator("prior_revenue")
            value = (
                values["current_operating_income"] / current_revenue
                - values["prior_operating_income"] / prior_revenue
                if current_revenue is not None and prior_revenue is not None
                else None
            )
        elif proxy.name == "fcf_margin_change":
            current_revenue = denominator("current_revenue")
            prior_revenue = denominator("prior_revenue")
            current_fcf = values["current_operating_cash_flow"] - abs(
                values["current_capital_expenditures"]
            )
            prior_fcf = values["prior_operating_cash_flow"] - abs(
                values["prior_capital_expenditures"]
            )
            value = (
                current_fcf / current_revenue - prior_fcf / prior_revenue
                if current_revenue is not None and prior_revenue is not None
                else None
            )
        elif proxy.name == "revenue_acceleration":
            prior = denominator("prior_revenue_for_current_growth")
            first = denominator("two_year_prior_revenue_for_prior_growth")
            value = (
                values["current_revenue"] / prior - values["prior_revenue"] / first
                if prior is not None and first is not None
                else None
            )
        else:
            # Market-role proxies cannot enter a ResolvedEntry001 in Run 1.
            reasons.add(FeatureExclusionReason.FORMULA_UNAVAILABLE.value)
            value = None

        source_rows = tuple(
            dict.fromkeys(observations[role.role_name] for role in proxy.required_period_structure)
        )
        if value is not None and (not source_rows or not math.isfinite(value)):
            value = None
            reasons.add(FeatureExclusionReason.INCOMPLETE_PROVENANCE.value)
        if value is None and not reasons:
            reasons.add(FeatureExclusionReason.FORMULA_UNAVAILABLE.value)
        return FeatureCalculationResult(
            value=value,
            source_observations=source_rows,
            derived_inputs=values,
            exclusion_reasons=tuple(sorted(reasons)),
        )

    def _calculate_observations(
        self,
        security_ids: Sequence[str],
        as_of: datetime,
    ) -> tuple[FeatureObservation, ...]:
        output: list[FeatureObservation] = []
        for security_id in security_ids:
            for proxy in self.resolved_entry_001.proxy_registry:
                result = self._calculate_proxy(security_id, proxy, as_of)
                available_at = (
                    max(row.available_at for row in result.source_observations)
                    if result.source_observations
                    else None
                )
                output.append(FeatureObservation(
                    security_id=security_id,
                    decision_date=as_of.date(),
                    feature=proxy.name,
                    construct=proxy.construct,
                    value=result.value,
                    # No scalar derivation has been approved for multi-role or
                    # multi-period provenance.
                    source_period_end=None,
                    source_available_at=available_at,
                    exclusion_reason=result.exclusion_reasons,
                ))
        return tuple(output)

    def calculate_governed_batch(
        self,
        security_ids: Sequence[str],
        as_of: datetime,
        repository: str,
    ) -> GovernedFeatureBatch:
        manifest = source_control_manifest(repository)
        if manifest.get("dirty") is not False:
            raise GovernanceError(
                "governed feature-batch creation requires a clean source tree"
            )
        commit = manifest["commit"]
        observations = self._calculate_observations(security_ids, as_of)
        return GovernedFeatureBatch(
            observations=observations,
            proxy_registry_digest=self.resolved_entry_001.proxy_registry_digest,
            feature_generation_code_commit=commit,
            _token=_BATCH_TOKEN,
        )
