"""Typed domain objects shared across the research system.

The objects intentionally keep data observations separate from calculated
features. This makes it difficult to accidentally present a calculation as a
vendor-supplied historical fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping


class RestatementPolicy(str, Enum):
    """Which version of a fact is eligible at a historical decision time."""

    FIRST_REPORTED = "first_reported"
    LATEST_KNOWN = "latest_known"


class AuditDecision(str, Enum):
    ADMISSIBLE = "admissible"
    ADMISSIBLE_AFTER = "admissible_only_after"
    ADMISSIBLE_RESTRICTED = "admissible_subject_to_restriction"
    EXCLUDED = "excluded"


@dataclass(frozen=True, order=True)
class FactObservation:
    """One version of a source fact.

    ``available_at`` is the first timestamp at which the exact version could
    have been known. It must be derived from a filing, announcement, or vendor
    vintage—not from the fiscal period end.
    """

    security_id: str
    field: str
    period_end: date
    available_at: datetime
    value: float
    source: str
    accession: str | None = None
    unit: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not self.security_id.strip():
            raise ValueError("security_id cannot be blank")
        if not self.field.strip():
            raise ValueError("field cannot be blank")
        if self.available_at.tzinfo is None:
            raise ValueError("available_at must be timezone-aware")

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "FactObservation":
        available = datetime.fromisoformat(str(row["available_at"]))
        if available.tzinfo is None:
            raise ValueError("available_at input must include an explicit timezone")
        return cls(
            security_id=str(row["security_id"]),
            field=str(row["field"]),
            period_end=date.fromisoformat(str(row["period_end"])),
            available_at=available,
            value=float(row["value"]),
            source=str(row["source"]),
            accession=(str(row["accession"]) if row.get("accession") else None),
            unit=(str(row["unit"]) if row.get("unit") else None),
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


@dataclass(frozen=True)
class ProxyDefinition:
    """Frozen proxy-registry entry."""

    name: str
    construct: str
    formula: str
    source_fields: tuple[str, ...]
    expected_direction: int
    availability_lag: str
    transformation: str = "cross_sectional_percentile_rank"
    sector_treatment: str = "none"
    missing_data_treatment: str = "exclude_feature_for_security"
    accounting_weaknesses: tuple[str, ...] = ()
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.expected_direction not in {-1, 1}:
            raise ValueError("expected_direction must be -1 or 1")
