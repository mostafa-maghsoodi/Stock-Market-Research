"""Typed domain objects shared across the research system.

Source facts, calculated features, and governed registry semantics are kept as
separate types.  In particular, a :class:`FeatureObservation` never embeds a
source fact; exact source objects live only inside the calculation pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
import math
from typing import Any, Mapping


UNRESOLVED = "UNRESOLVED"


class RestatementPolicy(str, Enum):
    FIRST_REPORTED = "first_reported"
    LATEST_KNOWN = "latest_known"


class AuditDecision(str, Enum):
    ADMISSIBLE = "admissible"
    ADMISSIBLE_AFTER = "admissible_only_after"
    ADMISSIBLE_RESTRICTED = "admissible_subject_to_restriction"
    EXCLUDED = "excluded"


class PeriodType(str, Enum):
    INSTANT = "instant"
    DURATION = "duration"
    UNKNOWN = "unknown"


class ReportingFrequency(str, Enum):
    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    UNKNOWN = "unknown"


class RoleKind(str, Enum):
    ACCOUNTING = "accounting_role"
    MARKET = "market_role"


class SameOffsetAlignment(str, Enum):
    """Supported meanings are available only to explicitly resolved fixtures.

    Production templates contain ``UNRESOLVED``.  Defining the closed choices
    does not select one for a research cycle.
    """

    SAME_FISCAL_YEAR = "same_fiscal_year"
    IDENTICAL_PERIOD_END = "identical_period_end"
    NOT_APPLICABLE = "not_applicable"


class FiscalYearObservationSelection(str, Enum):
    REJECT_AMBIGUOUS = "reject_ambiguous"
    LATEST_PERIOD_END = "latest_period_end"


class DenominatorTransformation(str, Enum):
    DIRECT_ROLE = "direct_role"
    AVERAGE = "average"
    PRIOR_PERIOD_BASE = "prior_period_base"


class DenominatorAction(str, Enum):
    EXCLUDE_FEATURE = "exclude_feature"
    ALLOW_VALUE = "allow_value"


class FeatureExclusionReason(str, Enum):
    REPORTING_FREQUENCY_MISMATCH = "reporting_frequency_mismatch"
    UNKNOWN_REPORTING_FREQUENCY = "unknown_reporting_frequency"
    MISSING_FISCAL_YEAR_METADATA = "missing_fiscal_year_metadata"
    NONCONSECUTIVE_FISCAL_YEARS = "nonconsecutive_fiscal_years"
    PERIOD_STRUCTURE_MISMATCH = "period_structure_mismatch"
    INCOMPATIBLE_PERIOD_TYPE = "incompatible_period_type"
    INCOMPLETE_PROVENANCE = "incomplete_provenance"
    DENOMINATOR_MISSING = "denominator_missing"
    DENOMINATOR_POLICY_EXCLUSION = "denominator_policy_exclusion"
    INSUFFICIENT_HISTORY = "insufficient_history"
    AMBIGUOUS_FISCAL_YEAR = "ambiguous_fiscal_year"
    FORMULA_UNAVAILABLE = "formula_unavailable"


def _optional_int(value: Any, *, name: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer or blank")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer or blank") from exc
    if str(value).strip() not in {str(parsed), f"{parsed}.0"}:
        raise ValueError(f"{name} must be an integer or blank")
    return parsed


@dataclass(frozen=True, order=True)
class FactObservation:
    """One explicitly described version of a source fact."""

    security_id: str
    field: str
    period_end: date
    available_at: datetime
    value: float
    source: str
    accession: str | None = None
    unit: str | None = None
    period_type: PeriodType = PeriodType.UNKNOWN
    reporting_frequency: ReportingFrequency = ReportingFrequency.UNKNOWN
    form_type: str | None = None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not self.security_id.strip():
            raise ValueError("security_id cannot be blank")
        if not self.field.strip():
            raise ValueError("field cannot be blank")
        if self.available_at.tzinfo is None:
            raise ValueError("available_at must be timezone-aware")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ValueError("value must be a finite numeric observation")
        numeric_value = float(self.value)
        if not math.isfinite(numeric_value):
            raise ValueError("value must be a finite numeric observation")
        object.__setattr__(self, "value", numeric_value)
        object.__setattr__(self, "period_type", PeriodType(self.period_type))
        object.__setattr__(
            self, "reporting_frequency", ReportingFrequency(self.reporting_frequency)
        )
        if self.fiscal_quarter is not None and self.fiscal_quarter not in {1, 2, 3, 4}:
            raise ValueError("fiscal_quarter must be 1, 2, 3, 4, or None")
        reserved = {
            "period_type",
            "reporting_frequency",
            "form_type",
            "fiscal_year",
            "fiscal_quarter",
        }
        duplicate = sorted(reserved.intersection(self.metadata))
        if duplicate:
            raise ValueError(
                f"first-class period metadata cannot be repeated in metadata: {duplicate}"
            )

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "FactObservation":
        available = datetime.fromisoformat(str(row["available_at"]))
        if available.tzinfo is None:
            raise ValueError("available_at input must include an explicit timezone")
        period_type = str(row.get("period_type") or PeriodType.UNKNOWN.value).strip().lower()
        frequency = str(
            row.get("reporting_frequency") or ReportingFrequency.UNKNOWN.value
        ).strip().lower()
        form_type = str(row.get("form_type") or "").strip() or None
        fiscal_year = _optional_int(row.get("fiscal_year"), name="fiscal_year")
        fiscal_quarter = _optional_int(
            row.get("fiscal_quarter"), name="fiscal_quarter"
        )
        raw_value = row["value"]
        if isinstance(raw_value, bool):
            raise ValueError("value must be a finite numeric observation")
        try:
            numeric_value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("value must be a finite numeric observation") from exc
        return cls(
            security_id=str(row["security_id"]),
            field=str(row["field"]),
            period_end=date.fromisoformat(str(row["period_end"])),
            available_at=available,
            value=numeric_value,
            source=str(row["source"]),
            accession=(str(row["accession"]) if row.get("accession") else None),
            unit=(str(row["unit"]) if row.get("unit") else None),
            period_type=PeriodType(period_type),
            reporting_frequency=ReportingFrequency(frequency),
            form_type=form_type,
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter,
        )


@dataclass(frozen=True)
class FeatureObservation:
    security_id: str
    decision_date: date
    feature: str
    construct: str
    value: float | None
    source_period_end: date | None
    source_available_at: datetime | None
    exclusion_reason: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        reasons = tuple(
            sorted(
                {
                    item.value if isinstance(item, FeatureExclusionReason) else str(item)
                    for item in self.exclusion_reason
                }
            )
        )
        object.__setattr__(self, "exclusion_reason", reasons)
        if self.value is not None:
            if not math.isfinite(float(self.value)):
                raise ValueError("usable feature values must be finite")
            if self.source_available_at is None:
                raise ValueError("a usable feature requires source_available_at")
            if reasons:
                raise ValueError("a usable feature cannot carry exclusion reasons")
        elif not reasons:
            raise ValueError("an unavailable feature requires an exclusion reason")


@dataclass(frozen=True)
class PeriodRole:
    role_name: str
    source_field: str
    role_kind: RoleKind
    period_type: PeriodType
    fiscal_year_offset: int | None = None
    alignment_rule: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "role_kind", RoleKind(self.role_kind))
        object.__setattr__(self, "period_type", PeriodType(self.period_type))
        if self.period_type is PeriodType.UNKNOWN:
            raise ValueError("governed period roles cannot require unknown period_type")
        if self.role_kind is RoleKind.ACCOUNTING:
            if not isinstance(self.fiscal_year_offset, int) or isinstance(
                self.fiscal_year_offset, bool
            ):
                raise ValueError("accounting_role requires fiscal_year_offset")
            if self.fiscal_year_offset > 0:
                raise ValueError("fiscal_year_offset cannot be positive")
            if self.alignment_rule is not None:
                raise ValueError("accounting_role cannot carry alignment_rule")
        else:
            if self.fiscal_year_offset is not None:
                raise ValueError("market_role cannot carry fiscal_year_offset")
            if self.alignment_rule != UNRESOLVED:
                raise ValueError(
                    "Run 1 market_role alignment_rule must be UNRESOLVED"
                )


@dataclass(frozen=True)
class DenominatorPolicy:
    missing: DenominatorAction
    zero: DenominatorAction
    negative: DenominatorAction
    near_zero: DenominatorAction
    near_zero_absolute_threshold: float

    def __post_init__(self) -> None:
        for name in ("missing", "zero", "negative", "near_zero"):
            object.__setattr__(self, name, DenominatorAction(getattr(self, name)))
        if self.missing is not DenominatorAction.EXCLUDE_FEATURE:
            raise ValueError("missing denominator supports only exclude_feature")
        if self.zero is not DenominatorAction.EXCLUDE_FEATURE:
            raise ValueError("zero denominator supports only exclude_feature")
        threshold = float(self.near_zero_absolute_threshold)
        if not math.isfinite(threshold) or threshold <= 0:
            raise ValueError("near_zero_absolute_threshold must be finite and positive")
        object.__setattr__(self, "near_zero_absolute_threshold", threshold)


@dataclass(frozen=True)
class DenominatorDefinition:
    denominator_id: str
    contributing_roles: tuple[str, ...]
    transformation: DenominatorTransformation
    denominator_policy: DenominatorPolicy

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "transformation", DenominatorTransformation(self.transformation)
        )
        if not self.denominator_id.strip() or not self.contributing_roles:
            raise ValueError("denominator id and contributing roles are required")
        if len(set(self.contributing_roles)) != len(self.contributing_roles):
            raise ValueError("denominator contributing roles must be unique")
        if self.transformation in {
            DenominatorTransformation.DIRECT_ROLE,
            DenominatorTransformation.PRIOR_PERIOD_BASE,
        } and len(self.contributing_roles) != 1:
            raise ValueError("direct denominators require exactly one role")
        if (
            self.transformation is DenominatorTransformation.AVERAGE
            and len(self.contributing_roles) < 2
        ):
            raise ValueError("average denominators require at least two roles")


@dataclass(frozen=True)
class ProxyDefinition:
    """A fully resolved governed proxy-registry entry."""

    name: str
    construct: str
    formula: str
    source_fields: tuple[str, ...]
    expected_direction: int
    availability_lag: str
    transformation: str
    sector_treatment: str
    missing_data_treatment: str
    accounting_weaknesses: tuple[str, ...]
    rationale: str
    required_reporting_frequency: ReportingFrequency
    frequency_governed_source_fields: tuple[str, ...]
    frequency_exempt_source_fields: tuple[str, ...]
    required_period_structure: tuple[PeriodRole, ...]
    denominator_definitions: tuple[DenominatorDefinition, ...]
    same_offset_alignment_rule: SameOffsetAlignment
    fiscal_year_observation_selection_rule: FiscalYearObservationSelection
    prior_gross_profit_dependency: str | None

    def __post_init__(self) -> None:
        if self.expected_direction not in {-1, 1}:
            raise ValueError("expected_direction must be -1 or 1")
        object.__setattr__(
            self,
            "required_reporting_frequency",
            ReportingFrequency(self.required_reporting_frequency),
        )
        if self.required_reporting_frequency is ReportingFrequency.UNKNOWN:
            raise ValueError("governed required reporting frequency cannot be unknown")
        object.__setattr__(
            self,
            "same_offset_alignment_rule",
            SameOffsetAlignment(self.same_offset_alignment_rule),
        )
        object.__setattr__(
            self,
            "fiscal_year_observation_selection_rule",
            FiscalYearObservationSelection(
                self.fiscal_year_observation_selection_rule
            ),
        )
        if not self.source_fields or len(set(self.source_fields)) != len(self.source_fields):
            raise ValueError("source_fields must be non-empty and unique")
        governed = set(self.frequency_governed_source_fields)
        exempt = set(self.frequency_exempt_source_fields)
        if governed & exempt or governed | exempt != set(self.source_fields):
            raise ValueError("frequency partition must be exhaustive and non-overlapping")
        if not self.required_period_structure:
            raise ValueError("required_period_structure cannot be empty")
        if self.name == "gross_profitability":
            if self.prior_gross_profit_dependency not in {
                "require_prior_gross_profit",
                "do_not_require_prior_gross_profit",
            }:
                raise ValueError(
                    "gross_profitability requires an explicit prior-gross-profit dependency decision"
                )
        elif self.prior_gross_profit_dependency is not None:
            raise ValueError(
                "prior_gross_profit_dependency applies only to gross_profitability"
            )
        if any(role.role_kind is RoleKind.MARKET for role in self.required_period_structure):
            raise ValueError("a Run 1 governed proxy cannot resolve a market_role")
        role_names = {role.role_name for role in self.required_period_structure}
        if len(role_names) != len(self.required_period_structure):
            raise ValueError("period role names must be unique")
        if {role.source_field for role in self.required_period_structure} != set(
            self.source_fields
        ):
            raise ValueError("period roles must cover every declared source field")
        offsets = [role.fiscal_year_offset for role in self.required_period_structure]
        repeated_offsets = len(offsets) != len(set(offsets))
        if repeated_offsets and self.same_offset_alignment_rule is SameOffsetAlignment.NOT_APPLICABLE:
            raise ValueError("same-offset accounting roles require an alignment rule")
        if not repeated_offsets and self.same_offset_alignment_rule is not SameOffsetAlignment.NOT_APPLICABLE:
            raise ValueError("same_offset_alignment_rule must be not_applicable when offsets are distinct")
        for definition in self.denominator_definitions:
            missing = set(definition.contributing_roles) - role_names
            if missing:
                raise ValueError(
                    f"denominator {definition.denominator_id} has unknown roles: {sorted(missing)}"
                )
