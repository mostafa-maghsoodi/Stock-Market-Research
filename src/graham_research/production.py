"""Provider-neutral Screen v2 production contracts and fail-closed run gate.

This module implements deterministic mechanics only.  It does not select a
provider, bless a field mapping, or contain production observations.  Positive
production state can only be reached with a closed evidence manifest whose
referenced bytes and capabilities validate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from .domain import FactObservation, PeriodType, ReportingFrequency
from .governance import canonical_json
from .ranked_artifact import RANKED_FRAME_DIGEST_SCOPE, canonical_ranked_frame_digest


class ProductionContractError(ValueError):
    """A closed production contract or deterministic rule was violated."""


REPOSITORY_ID = "mostafa-maghsoodi/Stock-Market-Research"
SCREEN_V2_PATH = "docs/architecture/Screen_Specification_v2_Final.md"
SCREEN_V2_MERGE_COMMIT = "2363b96b490e805ed5d50392fa476100ffdbbcf3"
SCREEN_V2_APPROVAL_PATH = "docs/approvals/v1/screen-specification-v2-approval-001.json"
SCREEN_V2_CONFIG = {
    "accounting_reporting_basis": "ANNUAL",
    "accounting_restatement_policy": "FIRST_REPORTED",
    "market_alignment_policy": "PRIOR_COMPLETED_PRIMARY_MARKET_SESSION",
    "market_country": "UNITED_STATES",
    "included_primary_exchanges": ["NYSE", "NASDAQ", "NYSE_AMERICAN"],
    "base_currency": "USD",
    "minimum_total_market_capitalization_usd": 500_000_000,
    "minimum_raw_primary_listing_close_usd": 5,
    "liquidity_window_completed_sessions": 60,
    "minimum_median_daily_dollar_volume_usd": 2_000_000,
    "minimum_seasoning_completed_sessions": 126,
    "required_proxy_order": [
        "fcf_ev",
        "ebit_ev",
        "gross_profitability",
        "roic",
        "operating_margin_change",
        "fcf_margin_change",
        "revenue_acceleration",
    ],
    "required_dimensions": [
        "VALUATION",
        "BUSINESS_ECONOMICS",
        "FUNDAMENTAL_CHANGE",
    ],
    "mandatory_valuation_proxies": ["fcf_ev", "ebit_ev"],
    "candidate_count": 100,
    "candidate_order": ["composite_score descending", "security_id ascending"],
}
SCREEN_V2_CONFIG_DIGEST = hashlib.sha256(canonical_json(SCREEN_V2_CONFIG)).hexdigest()

REQUIRED_CANONICAL_FIELDS = frozenset({
    "revenue",
    "gross_profit",
    "operating_income",
    "operating_cash_flow",
    "capital_expenditures",
    "total_assets",
    "income_before_tax",
    "income_tax_expense",
    "invested_capital",
    "shares_outstanding",
    "raw_close",
    "raw_volume",
    "total_market_capitalization",
    "enterprise_value",
})
CANONICAL_FIELD_UNITS = {
    "revenue": "USD",
    "gross_profit": "USD",
    "operating_income": "USD",
    "operating_cash_flow": "USD",
    "capital_expenditures": "USD",
    "total_assets": "USD",
    "income_before_tax": "USD",
    "income_tax_expense": "USD",
    "invested_capital": "USD",
    "shares_outstanding": "SHARES",
    "raw_close": "USD_PER_SHARE",
    "raw_volume": "SHARES",
    "total_market_capitalization": "USD",
    "enterprise_value": "USD",
}
REQUIRED_CAPABILITIES = (
    "historical_pit_fundamentals",
    "first_reported_revision_history",
    "filing_public_availability_timestamps",
    "historical_security_master",
    "inactive_and_delisted_coverage",
    "historical_primary_listing",
    "provider_native_immutable_identifiers",
    "raw_historical_close_and_volume",
    "historical_corporate_actions",
    "historical_shares_outstanding",
    "total_market_capitalization",
    "enterprise_value",
    "historical_exchange_sessions",
    "archive_reproducibility_rights",
    "entitlement_and_access",
)
PRODUCTION_FACT_KEYS = frozenset({
    "security_id", "field", "period_start", "period_end", "available_at", "value",
    "source", "accession", "unit", "period_type", "reporting_frequency", "form_type",
    "fiscal_year", "fiscal_quarter", "provider", "provider_product",
    "native_observation_id", "source_native_vintage_identifier",
})
PREREQUISITE_KEYS = (
    "approved_governing_screen_v2_identity",
    "required_architecture_and_ledger_authority_verified",
    "provider_and_data_evidence_resolved",
    "pit_provider_capability_verified",
    "security_master_verified",
    "historical_universe_evidence_verified",
    "field_catalog_verified",
    "market_timing_and_session_evidence_verified",
    "source_native_mappings_verified",
    "exact_provenance_verified",
    "mandatory_proxy_coverage_verified",
    "required_valuation_coverage_verified",
    "implementation_and_configuration_identities_consistent",
)

EXCLUDED_SECURITY_TYPES = frozenset({
    "ADR", "PREFERRED_EQUITY", "ETF", "MUTUAL_FUND", "CLOSED_END_FUND",
    "BDC", "REIT", "PRE_COMBINATION_SPAC", "RIGHT", "WARRANT", "UNIT",
    "WHEN_ISSUED", "NON_COMMON_EQUITY",
})


def _exact_keys(value: Mapping[str, Any], expected: Iterable[str], label: str) -> None:
    expected_set = set(expected)
    missing = sorted(expected_set - set(value))
    extra = sorted(set(value) - expected_set)
    if missing or extra:
        raise ProductionContractError(
            f"{label} has invalid keys; missing={missing}, extra={extra}"
        )


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductionContractError(f"{label} must be a non-empty string")
    return value


def _sha256(value: object, label: str) -> str:
    text = _nonempty(value, label)
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise ProductionContractError(f"{label} must be lowercase SHA-256")
    return text


def _aware(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProductionContractError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ProductionContractError(f"{label} must be timezone-aware")
    return parsed


@dataclass(frozen=True)
class EvidenceIdentity:
    evidence_id: str
    provider: str
    provider_product: str
    content_sha256: str
    source_native_vintage_identifier: str
    acquired_at_utc: datetime
    repository_relative_path: str | None = None

    def __post_init__(self) -> None:
        for name in ("evidence_id", "provider", "provider_product", "source_native_vintage_identifier"):
            _nonempty(getattr(self, name), name)
        _sha256(self.content_sha256, "content_sha256")
        _aware(self.acquired_at_utc, "acquired_at_utc")
        if self.repository_relative_path is not None:
            path = Path(_nonempty(self.repository_relative_path, "repository_relative_path"))
            if path.is_absolute() or ".." in path.parts:
                raise ProductionContractError("evidence path must be repository-relative")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceIdentity":
        _exact_keys(value, {
            "evidence_id", "provider", "provider_product", "content_sha256",
            "source_native_vintage_identifier", "acquired_at_utc",
            "repository_relative_path",
        }, "evidence identity")
        return cls(
            evidence_id=value["evidence_id"], provider=value["provider"],
            provider_product=value["provider_product"],
            content_sha256=value["content_sha256"],
            source_native_vintage_identifier=value["source_native_vintage_identifier"],
            acquired_at_utc=_aware(value["acquired_at_utc"], "acquired_at_utc"),
            repository_relative_path=value["repository_relative_path"],
        )

    def verify_content(self, repository: str | Path) -> bool:
        if self.repository_relative_path is None:
            return False
        path = Path(repository) / self.repository_relative_path
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == self.content_sha256


@dataclass(frozen=True)
class FieldCatalogEntry:
    canonical_field_id: str
    economic_meaning: str
    period_type: str
    reporting_frequency: str
    native_unit: str
    canonical_unit: str
    scaling_factor_to_canonical: float
    currency_semantics: str
    provider: str
    provider_product: str
    native_field_id: str
    mapping_evidence_identity: EvidenceIdentity
    effective_start: date
    effective_end: date | None
    public_availability_semantics: str
    revision_restatement_semantics: str
    allowed_proxy_roles: tuple[str, ...]
    source_provenance: EvidenceIdentity

    def __post_init__(self) -> None:
        for name in (
            "canonical_field_id", "economic_meaning", "native_unit",
            "canonical_unit", "currency_semantics", "provider",
            "provider_product", "native_field_id", "public_availability_semantics",
            "revision_restatement_semantics",
        ):
            _nonempty(getattr(self, name), name)
        if (
            isinstance(self.scaling_factor_to_canonical, bool)
            or not isinstance(self.scaling_factor_to_canonical, (int, float))
            or not math.isfinite(float(self.scaling_factor_to_canonical))
            or self.scaling_factor_to_canonical <= 0
        ):
            raise ProductionContractError(
                "scaling_factor_to_canonical must be finite and positive"
            )
        expected_unit = CANONICAL_FIELD_UNITS.get(self.canonical_field_id)
        if expected_unit is not None and self.canonical_unit != expected_unit:
            raise ProductionContractError(
                f"canonical unit mismatch for {self.canonical_field_id}: "
                f"{self.canonical_unit!r} != {expected_unit!r}"
            )
        if self.period_type not in {"INSTANT", "DURATION", "MARKET_SESSION"}:
            raise ProductionContractError("unsupported field period_type")
        if self.reporting_frequency not in {"ANNUAL", "DAILY", "INSTANT"}:
            raise ProductionContractError("unsupported field reporting_frequency")
        if self.effective_end is not None and self.effective_end < self.effective_start:
            raise ProductionContractError("field effective range is inverted")
        if not self.allowed_proxy_roles or len(set(self.allowed_proxy_roles)) != len(self.allowed_proxy_roles):
            raise ProductionContractError("allowed_proxy_roles must be non-empty and unique")
        for evidence in (self.mapping_evidence_identity, self.source_provenance):
            if evidence.provider != self.provider or evidence.provider_product != self.provider_product:
                raise ProductionContractError("field mapping/provider evidence mismatch")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FieldCatalogEntry":
        _exact_keys(value, {
            "canonical_field_id", "economic_meaning", "period_type",
            "reporting_frequency", "native_unit", "canonical_unit",
            "scaling_factor_to_canonical", "currency_semantics",
            "provider", "provider_product",
            "native_field_id", "mapping_evidence_identity", "effective_start",
            "effective_end", "public_availability_semantics",
            "revision_restatement_semantics", "allowed_proxy_roles", "source_provenance",
        }, "field catalog entry")
        return cls(
            canonical_field_id=value["canonical_field_id"],
            economic_meaning=value["economic_meaning"], period_type=value["period_type"],
            reporting_frequency=value["reporting_frequency"],
            native_unit=value["native_unit"], canonical_unit=value["canonical_unit"],
            scaling_factor_to_canonical=value["scaling_factor_to_canonical"],
            currency_semantics=value["currency_semantics"],
            provider=value["provider"], provider_product=value["provider_product"],
            native_field_id=value["native_field_id"],
            mapping_evidence_identity=EvidenceIdentity.from_mapping(value["mapping_evidence_identity"]),
            effective_start=date.fromisoformat(value["effective_start"]),
            effective_end=date.fromisoformat(value["effective_end"]) if value["effective_end"] else None,
            public_availability_semantics=value["public_availability_semantics"],
            revision_restatement_semantics=value["revision_restatement_semantics"],
            allowed_proxy_roles=tuple(value["allowed_proxy_roles"]),
            source_provenance=EvidenceIdentity.from_mapping(value["source_provenance"]),
        )


@dataclass(frozen=True)
class FieldCatalog:
    schema_version: int
    identity: EvidenceIdentity
    entries: tuple[FieldCatalogEntry, ...]

    def validate(self, repository: str | Path) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.schema_version != 1:
            blockers.append("FIELD_CATALOG_SCHEMA_UNSUPPORTED")
        ids = [entry.canonical_field_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            blockers.append("FIELD_CATALOG_DUPLICATE_CANONICAL_FIELD")
        for field in sorted(REQUIRED_CANONICAL_FIELDS - set(ids)):
            blockers.append(f"FIELD_MAPPING_MISSING:{field}")
        if not self.identity.verify_content(repository):
            blockers.append("FIELD_CATALOG_IDENTITY_UNVERIFIED")
        elif self.identity.repository_relative_path is not None:
            try:
                payload = json.loads((Path(repository) / self.identity.repository_relative_path).read_text(encoding="utf-8"))
                _exact_keys(payload, {"schema_version", "entries"}, "detached field catalog")
                detached = tuple(FieldCatalogEntry.from_mapping(item) for item in payload["entries"])
                if payload["schema_version"] != self.schema_version or detached != self.entries:
                    blockers.append("FIELD_CATALOG_CONTENT_MISMATCH")
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, ProductionContractError):
                blockers.append("FIELD_CATALOG_CONTENT_INVALID")
        for entry in self.entries:
            if not entry.mapping_evidence_identity.verify_content(repository):
                blockers.append(f"FIELD_MAPPING_EVIDENCE_UNVERIFIED:{entry.canonical_field_id}")
            if not entry.source_provenance.verify_content(repository):
                blockers.append(f"FIELD_SOURCE_PROVENANCE_UNVERIFIED:{entry.canonical_field_id}")
        return tuple(sorted(set(blockers)))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FieldCatalog":
        _exact_keys(value, {"schema_version", "identity", "entries"}, "field catalog")
        return cls(value["schema_version"], EvidenceIdentity.from_mapping(value["identity"]),
                   tuple(FieldCatalogEntry.from_mapping(item) for item in value["entries"]))


@dataclass(frozen=True)
class SecurityMasterRecord:
    issuer_id: str
    security_id: str
    listing_id: str
    provider_native_issuer_id: str
    provider_native_security_id: str
    provider_native_listing_id: str
    exchange: str
    currency: str
    security_type: str
    is_common_equity: bool
    is_operating_company: bool
    is_primary_listing: bool
    effective_start: date
    effective_end: date | None
    is_inactive_or_delisted: bool
    corporate_action_predecessor_security_id: str | None
    is_pre_combination_spac: bool
    post_combination_boundary: date | None
    share_class_id: str
    issuer_crosswalk_id: str
    evidence_identity: EvidenceIdentity

    def __post_init__(self) -> None:
        for name in (
                     "issuer_id", "security_id", "listing_id",
                     "provider_native_issuer_id", "provider_native_security_id",
                     "provider_native_listing_id", "exchange", "currency",
                     "security_type", "share_class_id", "issuer_crosswalk_id"):
            _nonempty(getattr(self, name), name)
        for name in ("is_common_equity", "is_operating_company", "is_primary_listing",
                     "is_inactive_or_delisted", "is_pre_combination_spac"):
            if not isinstance(getattr(self, name), bool):
                raise ProductionContractError(f"{name} must be boolean")
        if self.effective_end is not None and self.effective_end < self.effective_start:
            raise ProductionContractError("security-master effective range is inverted")
        if self.is_pre_combination_spac and self.post_combination_boundary is not None:
            raise ProductionContractError("pre-combination SPAC cannot have post boundary")

    def effective_on(self, decision_date: date) -> bool:
        return self.effective_start <= decision_date and (
            self.effective_end is None or decision_date <= self.effective_end
        )

    def eligible_classification(self, decision_date: date) -> bool:
        return (
            self.effective_on(decision_date)
            and self.exchange in SCREEN_V2_CONFIG["included_primary_exchanges"]
            and self.currency == "USD"
            and self.security_type not in EXCLUDED_SECURITY_TYPES
            and self.security_type == "COMMON_OPERATING_COMPANY_EQUITY"
            and self.is_common_equity and self.is_operating_company
            and not self.is_pre_combination_spac
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SecurityMasterRecord":
        _exact_keys(value, {
            "issuer_id", "security_id", "listing_id", "exchange", "currency",
            "provider_native_issuer_id", "provider_native_security_id",
            "provider_native_listing_id",
            "security_type", "is_common_equity", "is_operating_company",
            "is_primary_listing", "effective_start", "effective_end",
            "is_inactive_or_delisted", "corporate_action_predecessor_security_id",
            "is_pre_combination_spac", "post_combination_boundary", "share_class_id",
            "issuer_crosswalk_id", "evidence_identity",
        }, "security master record")
        return cls(
            issuer_id=value["issuer_id"], security_id=value["security_id"],
            listing_id=value["listing_id"], exchange=value["exchange"], currency=value["currency"],
            provider_native_issuer_id=value["provider_native_issuer_id"],
            provider_native_security_id=value["provider_native_security_id"],
            provider_native_listing_id=value["provider_native_listing_id"],
            security_type=value["security_type"], is_common_equity=value["is_common_equity"],
            is_operating_company=value["is_operating_company"], is_primary_listing=value["is_primary_listing"],
            effective_start=date.fromisoformat(value["effective_start"]),
            effective_end=date.fromisoformat(value["effective_end"]) if value["effective_end"] else None,
            is_inactive_or_delisted=value["is_inactive_or_delisted"],
            corporate_action_predecessor_security_id=value["corporate_action_predecessor_security_id"],
            is_pre_combination_spac=value["is_pre_combination_spac"],
            post_combination_boundary=(date.fromisoformat(value["post_combination_boundary"])
                                       if value["post_combination_boundary"] else None),
            share_class_id=value["share_class_id"], issuer_crosswalk_id=value["issuer_crosswalk_id"],
            evidence_identity=EvidenceIdentity.from_mapping(value["evidence_identity"]),
        )


@dataclass(frozen=True)
class ExchangeSessionEvidence:
    exchange: str
    timezone_name: str
    session_date: date
    session_open: datetime
    session_close: datetime
    session_status: str
    provider: str
    provider_product: str
    evidence_identity: EvidenceIdentity

    def __post_init__(self) -> None:
        if self.exchange not in SCREEN_V2_CONFIG["included_primary_exchanges"]:
            raise ProductionContractError("session exchange is outside Screen v2")
        _nonempty(self.timezone_name, "timezone_name")
        _aware(self.session_open, "session_open")
        _aware(self.session_close, "session_close")
        if self.session_close <= self.session_open:
            raise ProductionContractError("session close must follow open")
        if self.session_status not in {"COMPLETED", "HOLIDAY", "CANCELLED"}:
            raise ProductionContractError("unsupported session status")
        if self.session_status == "COMPLETED" and self.session_close.date() not in {
            self.session_date, self.session_open.date()
        }:
            raise ProductionContractError("session date/open/close are inconsistent")
        if self.provider != self.evidence_identity.provider or self.provider_product != self.evidence_identity.provider_product:
            raise ProductionContractError("session provider/evidence mismatch")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExchangeSessionEvidence":
        _exact_keys(value, {
            "exchange", "timezone_name", "session_date", "session_open", "session_close",
            "session_status", "provider", "provider_product", "evidence_identity",
        }, "exchange session evidence")
        return cls(
            exchange=value["exchange"], timezone_name=value["timezone_name"],
            session_date=date.fromisoformat(value["session_date"]),
            session_open=_aware(value["session_open"], "session_open"),
            session_close=_aware(value["session_close"], "session_close"),
            session_status=value["session_status"], provider=value["provider"],
            provider_product=value["provider_product"],
            evidence_identity=EvidenceIdentity.from_mapping(value["evidence_identity"]),
        )


@dataclass(frozen=True)
class MarketObservation:
    security_id: str
    listing_id: str
    session_date: date
    observed_at: datetime
    raw_close: float
    raw_volume: float
    currency: str
    provider: str
    provider_product: str
    native_observation_id: str
    evidence_identity: EvidenceIdentity

    def __post_init__(self) -> None:
        for name in ("security_id", "listing_id", "currency", "provider", "provider_product", "native_observation_id"):
            _nonempty(getattr(self, name), name)
        _aware(self.observed_at, "observed_at")
        for name in ("raw_close", "raw_volume"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(float(value)) or value < 0:
                raise ProductionContractError(f"{name} must be finite and non-negative")
        if self.provider != self.evidence_identity.provider or self.provider_product != self.evidence_identity.provider_product:
            raise ProductionContractError("market observation provider/evidence mismatch")

    def validate_against_session(self, session: ExchangeSessionEvidence) -> None:
        if self.session_date != session.session_date:
            raise ProductionContractError("MARKET_OBSERVATION_SESSION_DATE_MISMATCH")
        if self.provider != session.provider or self.provider_product != session.provider_product:
            raise ProductionContractError("MARKET_OBSERVATION_SESSION_PROVIDER_MISMATCH")
        if self.observed_at != session.session_close:
            raise ProductionContractError("MARKET_OBSERVATION_NOT_AT_SESSION_CLOSE")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MarketObservation":
        _exact_keys(value, {
            "security_id", "listing_id", "session_date", "observed_at", "raw_close",
            "raw_volume", "currency", "provider", "provider_product",
            "native_observation_id", "evidence_identity",
        }, "market observation")
        return cls(
            security_id=value["security_id"], listing_id=value["listing_id"],
            session_date=date.fromisoformat(value["session_date"]),
            observed_at=_aware(value["observed_at"], "observed_at"),
            raw_close=value["raw_close"], raw_volume=value["raw_volume"],
            currency=value["currency"], provider=value["provider"],
            provider_product=value["provider_product"], native_observation_id=value["native_observation_id"],
            evidence_identity=EvidenceIdentity.from_mapping(value["evidence_identity"]),
        )


def prior_completed_primary_market_session(
    sessions: Sequence[ExchangeSessionEvidence], *, exchange: str, decision_cutoff: datetime,
    expected_session_date: date | None = None,
) -> ExchangeSessionEvidence:
    _aware(decision_cutoff, "decision_cutoff")
    candidates = [
        item for item in sessions
        if item.exchange == exchange and item.session_status == "COMPLETED"
        and item.session_close <= decision_cutoff
    ]
    if not candidates:
        raise ProductionContractError("NO_PRIOR_COMPLETED_PRIMARY_MARKET_SESSION")
    selected = max(candidates, key=lambda item: (item.session_close, item.evidence_identity.evidence_id))
    if any(item.session_close == selected.session_close and item != selected for item in candidates):
        raise ProductionContractError("AMBIGUOUS_PRIOR_COMPLETED_PRIMARY_MARKET_SESSION")
    if expected_session_date is not None and selected.session_date != expected_session_date:
        raise ProductionContractError("STALE_PRIMARY_MARKET_SESSION")
    return selected


def validate_production_fact(fact: FactObservation, *, session: ExchangeSessionEvidence) -> None:
    if fact.period_type is PeriodType.DURATION and fact.period_start is None:
        raise ProductionContractError("DURATION_FACT_MISSING_PERIOD_START")
    if fact.reporting_frequency is not ReportingFrequency.ANNUAL:
        raise ProductionContractError("ACCOUNTING_FACT_NOT_ANNUAL")
    for name in ("provider", "provider_product", "native_observation_id", "source_native_vintage_identifier"):
        if not getattr(fact, name):
            raise ProductionContractError(f"FACT_{name.upper()}_MISSING")
    if fact.provider != session.provider:
        raise ProductionContractError("FACT_AND_MARKET_PROVIDER_MISMATCH")
    if fact.available_at > session.session_close:
        raise ProductionContractError("AFTER_CLOSE_ACCOUNTING_INFORMATION")


@dataclass(frozen=True)
class UniverseObservation:
    issuer_id: str
    security_id: str
    decision_date: date
    total_market_capitalization_usd: float
    raw_primary_close_usd: float
    completed_session_dollar_volumes_usd: tuple[float, ...]
    completed_sessions_since_seasoning_boundary: int
    security_master: SecurityMasterRecord
    market_evidence_identity: EvidenceIdentity

    @property
    def median_dollar_volume_usd(self) -> float:
        values = sorted(self.completed_session_dollar_volumes_usd)
        if len(values) != 60:
            raise ProductionContractError("LIQUIDITY_REQUIRES_EXACTLY_60_COMPLETED_SESSIONS")
        return (values[29] + values[30]) / 2

    def exclusion_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.security_id != self.security_master.security_id or self.issuer_id != self.security_master.issuer_id:
            reasons.append("SECURITY_MASTER_CROSSWALK_MISMATCH")
        if not self.security_master.eligible_classification(self.decision_date):
            reasons.append("INELIGIBLE_HISTORICAL_SECURITY_CLASSIFICATION")
        if self.security_master.post_combination_boundary is not None and self.completed_sessions_since_seasoning_boundary < 126:
            reasons.append("POST_COMBINATION_SPAC_NOT_SEASONED")
        if not math.isfinite(self.total_market_capitalization_usd) or self.total_market_capitalization_usd < 500_000_000:
            reasons.append("MARKET_CAPITALIZATION_BELOW_MINIMUM")
        if not math.isfinite(self.raw_primary_close_usd) or self.raw_primary_close_usd < 5:
            reasons.append("RAW_CLOSE_BELOW_MINIMUM")
        try:
            median = self.median_dollar_volume_usd
        except ProductionContractError as exc:
            reasons.append(str(exc))
        else:
            if not math.isfinite(median) or median < 2_000_000:
                reasons.append("MEDIAN_DOLLAR_VOLUME_BELOW_MINIMUM")
        if self.completed_sessions_since_seasoning_boundary < 126:
            reasons.append("INSUFFICIENT_SEASONING")
        return tuple(sorted(set(reasons)))


def build_point_in_time_universe(observations: Sequence[UniverseObservation]) -> tuple[UniverseObservation, ...]:
    eligible = [item for item in observations if not item.exclusion_reasons()]
    by_issuer: dict[str, list[UniverseObservation]] = {}
    for item in eligible:
        by_issuer.setdefault(item.issuer_id, []).append(item)
    selected: list[UniverseObservation] = []
    for issuer_id in sorted(by_issuer):
        candidates = by_issuer[issuer_id]
        authoritative = [item for item in candidates if item.security_master.is_primary_listing]
        pool = authoritative if authoritative else candidates
        pool.sort(key=lambda item: (-item.median_dollar_volume_usd, item.security_id))
        selected.append(pool[0])
    return tuple(sorted(selected, key=lambda item: item.security_id))


@dataclass(frozen=True)
class ScreenV2ReadinessState:
    research_policy_state: str
    provider_and_data_evidence_state: str | None
    repository_identity_state: str | None
    production_execution_state: str | None
    production_prerequisite_results: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.research_policy_state != "RESOLVED_RESEARCH_POLICY":
            raise ProductionContractError("research policy state is closed")
        if self.provider_and_data_evidence_state not in {None, "RESOLVED_PROVIDER_AND_DATA_EVIDENCE"}:
            raise ProductionContractError("provider/data evidence state is closed")
        if self.repository_identity_state not in {None, "VERIFIED_REPOSITORY_IDENTITIES"}:
            raise ProductionContractError("repository identity state is closed")
        if self.production_execution_state not in {None, "PRODUCTION_EXECUTION_READY"}:
            raise ProductionContractError("production execution state is closed")
        _exact_keys(self.production_prerequisite_results, PREREQUISITE_KEYS, "production prerequisites")
        if any(not isinstance(value, bool) for value in self.production_prerequisite_results.values()):
            raise ProductionContractError("production prerequisites must be boolean")
        ready = (
            self.provider_and_data_evidence_state == "RESOLVED_PROVIDER_AND_DATA_EVIDENCE"
            and self.repository_identity_state == "VERIFIED_REPOSITORY_IDENTITIES"
            and all(self.production_prerequisite_results.values())
        )
        if (self.production_execution_state == "PRODUCTION_EXECUTION_READY") != ready:
            raise ProductionContractError("PRODUCTION_EXECUTION_READY equivalence violated")

    @property
    def production_execution_ready(self) -> bool:
        return self.production_execution_state == "PRODUCTION_EXECUTION_READY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_policy_state": self.research_policy_state,
            "provider_and_data_evidence_state": self.provider_and_data_evidence_state,
            "repository_identity_state": self.repository_identity_state,
            "production_execution_state": self.production_execution_state,
            "production_prerequisite_results": dict(self.production_prerequisite_results),
        }


@dataclass(frozen=True)
class CandidateSet:
    schema_version: int
    screen_v2_configuration_digest: str
    ranked_frame_digest: str
    governed_batch_lineage_sha256: str
    decision_date: str
    members: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ProductionContractError("unsupported CandidateSet schema")
        for value, name in ((self.screen_v2_configuration_digest, "configuration digest"),
                            (self.ranked_frame_digest, "ranked digest"),
                            (self.governed_batch_lineage_sha256, "batch lineage")):
            _sha256(value, name)
        if len(self.members) != 100:
            raise ProductionContractError("CandidateSet requires exactly 100 members")
        for member in self.members:
            _exact_keys(member, {"security_id", "composite_score"}, "CandidateSet member")
            _nonempty(member["security_id"], "CandidateSet member security_id")
            score = member["composite_score"]
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(float(score))
            ):
                raise ProductionContractError(
                    "CandidateSet member composite_score must be finite"
                )
        try:
            date.fromisoformat(self.decision_date[:10])
        except (TypeError, ValueError) as exc:
            raise ProductionContractError("CandidateSet decision_date is invalid") from exc
        expected = sorted(self.members, key=lambda row: (-float(row["composite_score"]), row["security_id"]))
        if list(self.members) != expected:
            raise ProductionContractError("CandidateSet ordering is invalid")
        if len({row["security_id"] for row in self.members}) != 100:
            raise ProductionContractError("CandidateSet security IDs must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": "CandidateSet", "schema_version": self.schema_version,
            "screen_v2_configuration_digest": self.screen_v2_configuration_digest,
            "ranked_frame_digest": self.ranked_frame_digest,
            "governed_batch_lineage_sha256": self.governed_batch_lineage_sha256,
            "decision_date": self.decision_date, "selection_rule": "TOP 100",
            "ordering": ["composite_score descending", "security_id ascending"],
            "members": [dict(item) for item in self.members],
            "transaction_authority": False,
        }

    def canonical_bytes(self) -> bytes:
        """Return deterministic CandidateSet bytes without changing ranking scope."""

        return canonical_json(self.to_dict()) + b"\n"


CANDIDATE_SELECTION_RULE = {
    "candidate_sets": 1,
    "candidate_count": 100,
    "ordering": ["composite_score descending", "security_id ascending"],
    "tiers": None,
}
CANDIDATE_SELECTION_RULE_DIGEST = hashlib.sha256(
    canonical_json(CANDIDATE_SELECTION_RULE)
).hexdigest()


@dataclass(frozen=True)
class CandidateSetDerivedIdentity:
    """Non-governing, mechanically derived CandidateSet evidence envelope.

    Screen v2 leaves the exact *governing* production CandidateSet identity
    contract unresolved.  This envelope closes only the deterministic hashing
    implementation and cannot manufacture that missing authority.
    """

    artifact_type: str
    identity_schema_version: int
    authority_status: str
    canonicalization: str
    candidate_set_exact_byte_sha256: str
    candidate_set_byte_length: int
    ranked_frame_digest: str
    screen_v2_configuration_digest: str
    governed_batch_lineage_sha256: str
    eligible_population_digest: str
    selection_rule_digest: str
    production_evidence_manifest_sha256: str
    decision_date: str
    derived_identity_sha256: str

    def __post_init__(self) -> None:
        if self.artifact_type != "CANDIDATE_SET_DERIVED_IDENTITY":
            raise ProductionContractError("candidate identity artifact type is closed")
        if self.identity_schema_version != 1:
            raise ProductionContractError("candidate identity schema is unsupported")
        if self.authority_status != "NON_GOVERNING_DERIVED_IDENTITY":
            raise ProductionContractError("candidate identity cannot self-assert authority")
        if self.canonicalization != "canonical_json_v1_plus_lf":
            raise ProductionContractError("candidate canonicalization is unsupported")
        if not isinstance(self.candidate_set_byte_length, int) or self.candidate_set_byte_length <= 0:
            raise ProductionContractError("candidate byte length must be positive")
        for name in (
            "candidate_set_exact_byte_sha256", "ranked_frame_digest",
            "screen_v2_configuration_digest", "governed_batch_lineage_sha256",
            "eligible_population_digest", "selection_rule_digest",
            "production_evidence_manifest_sha256", "derived_identity_sha256",
        ):
            _sha256(getattr(self, name), name)
        if self.selection_rule_digest != CANDIDATE_SELECTION_RULE_DIGEST:
            raise ProductionContractError("candidate selection-rule identity mismatch")
        date.fromisoformat(self.decision_date[:10])
        expected_identity = hashlib.sha256(
            canonical_json(self.identity_payload())
        ).hexdigest()
        if self.derived_identity_sha256 != expected_identity:
            raise ProductionContractError("candidate derived identity digest mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "identity_schema_version": self.identity_schema_version,
            "authority_status": self.authority_status,
            "canonicalization": self.canonicalization,
            "candidate_set_exact_byte_sha256": self.candidate_set_exact_byte_sha256,
            "candidate_set_byte_length": self.candidate_set_byte_length,
            "ranked_frame_digest": self.ranked_frame_digest,
            "screen_v2_configuration_digest": self.screen_v2_configuration_digest,
            "governed_batch_lineage_sha256": self.governed_batch_lineage_sha256,
            "eligible_population_digest": self.eligible_population_digest,
            "selection_rule_digest": self.selection_rule_digest,
            "production_evidence_manifest_sha256": self.production_evidence_manifest_sha256,
            "decision_date": self.decision_date,
        }

    def verify(
        self,
        candidate_set: CandidateSet,
        *,
        eligible_population_digest: str,
        production_evidence_manifest_sha256: str,
    ) -> None:
        expected = derive_candidate_set_identity(
            candidate_set,
            eligible_population_digest=eligible_population_digest,
            production_evidence_manifest_sha256=production_evidence_manifest_sha256,
        )
        if self != expected:
            raise ProductionContractError("CANDIDATE_SET_DERIVED_IDENTITY_MISMATCH")


def derive_candidate_set_identity(
    candidate_set: CandidateSet,
    *,
    eligible_population_digest: str,
    production_evidence_manifest_sha256: str,
) -> CandidateSetDerivedIdentity:
    """Derive reproducible evidence identity; does not resolve EXT-022 authority."""

    _sha256(eligible_population_digest, "eligible_population_digest")
    _sha256(production_evidence_manifest_sha256, "production_evidence_manifest_sha256")
    candidate_bytes = candidate_set.canonical_bytes()
    payload = {
        "artifact_type": "CANDIDATE_SET_DERIVED_IDENTITY",
        "identity_schema_version": 1,
        "authority_status": "NON_GOVERNING_DERIVED_IDENTITY",
        "canonicalization": "canonical_json_v1_plus_lf",
        "candidate_set_exact_byte_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "candidate_set_byte_length": len(candidate_bytes),
        "ranked_frame_digest": candidate_set.ranked_frame_digest,
        "screen_v2_configuration_digest": candidate_set.screen_v2_configuration_digest,
        "governed_batch_lineage_sha256": candidate_set.governed_batch_lineage_sha256,
        "eligible_population_digest": eligible_population_digest,
        "selection_rule_digest": CANDIDATE_SELECTION_RULE_DIGEST,
        "production_evidence_manifest_sha256": production_evidence_manifest_sha256,
        "decision_date": candidate_set.decision_date,
    }
    return CandidateSetDerivedIdentity(
        **payload,
        derived_identity_sha256=hashlib.sha256(canonical_json(payload)).hexdigest(),
    )


def create_candidate_set(
    ranked_frame: pd.DataFrame, *, readiness: ScreenV2ReadinessState,
    governed_batch_lineage_sha256: str,
) -> CandidateSet:
    if not readiness.production_execution_ready:
        raise ProductionContractError("CANDIDATESET_PUBLICATION_BLOCKED_NOT_READY")
    if tuple(RANKED_FRAME_DIGEST_SCOPE) != ("security_id", "decision_date", "composite_score"):
        raise ProductionContractError("RANKING_DIGEST_SCOPE_CHANGED")
    missing_valuation = {"fcf_ev", "ebit_ev"} - set(ranked_frame.columns)
    if missing_valuation:
        raise ProductionContractError(
            f"MANDATORY_VALUATION_COVERAGE_COLUMNS_MISSING:{sorted(missing_valuation)}"
        )
    required_columns = (
        set(RANKED_FRAME_DIGEST_SCOPE)
        | set(SCREEN_V2_CONFIG["required_proxy_order"])
        | set(SCREEN_V2_CONFIG["required_dimensions"])
    )
    missing = required_columns - set(ranked_frame.columns)
    if missing:
        raise ProductionContractError(f"ranked frame missing columns: {sorted(missing)}")
    eligible = ranked_frame.dropna(subset=["composite_score"]).copy()
    dimensions = list(SCREEN_V2_CONFIG["required_dimensions"])
    if eligible[dimensions].isna().any(axis=None):
        raise ProductionContractError("REQUIRED_DIMENSION_COVERAGE_MISSING")
    expected_composite = eligible[dimensions].mean(axis=1, skipna=False)
    if not expected_composite.equals(eligible["composite_score"]):
        difference = (expected_composite - eligible["composite_score"]).abs()
        if (difference > 1e-12).any():
            raise ProductionContractError("COMPOSITE_NOT_EQUAL_WEIGHTED_ACROSS_DIMENSIONS")
    eligible = eligible.dropna(subset=["fcf_ev", "ebit_ev"])
    if len(eligible) < 100:
        raise ProductionContractError("INSUFFICIENT_ELIGIBLE_POPULATION")
    decision_dates = {str(item) for item in eligible["decision_date"]}
    if len(decision_dates) != 1:
        raise ProductionContractError("CandidateSet requires one decision date")
    ordered = eligible.sort_values(
        ["composite_score", "security_id"], ascending=[False, True], kind="mergesort"
    ).head(100)
    members = tuple({"security_id": row.security_id, "composite_score": float(row.composite_score)}
                    for row in ordered.itertuples(index=False))
    return CandidateSet(
        1, SCREEN_V2_CONFIG_DIGEST, canonical_ranked_frame_digest(ranked_frame),
        governed_batch_lineage_sha256, next(iter(decision_dates)), members,
    )


def canonical_eligible_population_digest(ranked_frame: pd.DataFrame) -> str:
    """Bind the eligible population separately from protected ranking scope."""

    required = set(RANKED_FRAME_DIGEST_SCOPE) | {"fcf_ev", "ebit_ev"}
    missing = required - set(ranked_frame.columns)
    if missing:
        raise ProductionContractError(
            f"eligible population is missing columns: {sorted(missing)}"
        )
    eligible = ranked_frame.dropna(
        subset=["composite_score", "fcf_ev", "ebit_ev"]
    )
    if eligible.empty:
        raise ProductionContractError("ELIGIBLE_POPULATION_EMPTY")
    return canonical_ranked_frame_digest(
        eligible.loc[:, list(RANKED_FRAME_DIGEST_SCOPE)]
    )


@dataclass(frozen=True)
class ProductionEvidenceManifest:
    schema_version: int
    manifest_identity: EvidenceIdentity
    capabilities: Mapping[str, bool]
    field_catalog: FieldCatalog
    security_master_identity: EvidenceIdentity
    market_data_identity: EvidenceIdentity
    fundamentals_identity: EvidenceIdentity
    implementation_commit: str
    screen_v2_configuration_digest: str
    proxy_input_mappings_resolved: bool
    denominator_governance_resolved: bool
    exact_provenance_chain_valid: bool

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            return
        for name in REQUIRED_CAPABILITIES:
            if name not in self.capabilities or not isinstance(self.capabilities[name], bool):
                raise ProductionContractError(f"capability {name} must be boolean")
        for name in (
            "proxy_input_mappings_resolved", "denominator_governance_resolved",
            "exact_provenance_chain_valid",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ProductionContractError(f"{name} must be boolean")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProductionEvidenceManifest":
        _exact_keys(value, {
            "schema_version", "manifest_identity", "capabilities", "field_catalog",
            "security_master_identity", "market_data_identity", "fundamentals_identity",
            "implementation_commit", "screen_v2_configuration_digest",
            "proxy_input_mappings_resolved", "denominator_governance_resolved",
            "exact_provenance_chain_valid",
        }, "production evidence manifest")
        _exact_keys(value["capabilities"], REQUIRED_CAPABILITIES, "provider capabilities")
        return cls(
            value["schema_version"], EvidenceIdentity.from_mapping(value["manifest_identity"]),
            dict(value["capabilities"]), FieldCatalog.from_mapping(value["field_catalog"]),
            EvidenceIdentity.from_mapping(value["security_master_identity"]),
            EvidenceIdentity.from_mapping(value["market_data_identity"]),
            EvidenceIdentity.from_mapping(value["fundamentals_identity"]),
            value["implementation_commit"], value["screen_v2_configuration_digest"],
            value["proxy_input_mappings_resolved"], value["denominator_governance_resolved"],
            value["exact_provenance_chain_valid"],
        )

    @classmethod
    def load(cls, path: str | Path) -> "ProductionEvidenceManifest":
        return cls.from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))

    def blockers(self, repository: str | Path) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.schema_version != 1:
            blockers.append("PRODUCTION_EVIDENCE_SCHEMA_UNSUPPORTED")
        for name in REQUIRED_CAPABILITIES:
            if self.capabilities.get(name) is not True:
                blockers.append(f"PROVIDER_CAPABILITY_UNRESOLVED:{name}")
        for label, identity in (
            ("PRODUCTION_MANIFEST", self.manifest_identity),
            ("SECURITY_MASTER", self.security_master_identity),
            ("MARKET_DATA", self.market_data_identity),
            ("FUNDAMENTALS", self.fundamentals_identity),
        ):
            if not identity.verify_content(repository):
                blockers.append(f"{label}_IDENTITY_UNVERIFIED")
        blockers.extend(self._validate_detached_datasets(repository))
        blockers.extend(self.field_catalog.validate(repository))
        if self.screen_v2_configuration_digest != SCREEN_V2_CONFIG_DIGEST:
            blockers.append("SCREEN_V2_CONFIGURATION_DIGEST_MISMATCH")
        if len(self.implementation_commit) != 40 or any(c not in "0123456789abcdef" for c in self.implementation_commit):
            blockers.append("IMPLEMENTATION_COMMIT_INVALID")
        else:
            try:
                _git(repository, "cat-file", "-e", f"{self.implementation_commit}^{{commit}}")
            except ProductionContractError:
                blockers.append("IMPLEMENTATION_COMMIT_UNVERIFIED")
            else:
                if subprocess.run(
                    ["git", "merge-base", "--is-ancestor", self.implementation_commit, "HEAD"],
                    cwd=repository, capture_output=True,
                ).returncode != 0:
                    blockers.append("IMPLEMENTATION_COMMIT_NOT_IN_ANCESTRY")
        try:
            if _git(repository, "status", "--porcelain").strip():
                blockers.append("WORKTREE_NOT_CLEAN")
        except ProductionContractError:
            blockers.append("CLEAN_TREE_UNVERIFIED")
        if not self.proxy_input_mappings_resolved:
            blockers.append("EXACT_PROXY_INPUT_MAPPINGS_UNRESOLVED")
        if not self.denominator_governance_resolved:
            blockers.append("DENOMINATOR_SPECIFIC_GOVERNANCE_UNRESOLVED")
        if not self.exact_provenance_chain_valid:
            blockers.append("EXACT_PROVENANCE_CHAIN_UNRESOLVED")
        return tuple(sorted(set(blockers)))

    def _validate_detached_datasets(self, repository: str | Path) -> list[str]:
        blockers: list[str] = []
        specifications = (
            ("SECURITY_MASTER", self.security_master_identity, {"schema_version", "records"}),
            ("MARKET_DATA", self.market_data_identity, {"schema_version", "sessions", "observations"}),
            ("FUNDAMENTALS", self.fundamentals_identity, {"schema_version", "observations"}),
        )
        for label, identity, keys in specifications:
            if identity.repository_relative_path is None:
                blockers.append(f"{label}_PATH_ABSENT")
                continue
            try:
                payload = json.loads(
                    (Path(repository) / identity.repository_relative_path).read_text(encoding="utf-8")
                )
                _exact_keys(payload, keys, f"{label.lower()} dataset")
                if payload["schema_version"] != 1:
                    raise ProductionContractError("unsupported dataset schema")
                if label == "SECURITY_MASTER":
                    records = tuple(SecurityMasterRecord.from_mapping(item) for item in payload["records"])
                    if not records:
                        raise ProductionContractError("security master is empty")
                    if len({(item.security_id, item.listing_id, item.effective_start) for item in records}) != len(records):
                        raise ProductionContractError("security master has duplicate PIT identities")
                elif label == "MARKET_DATA":
                    sessions = tuple(ExchangeSessionEvidence.from_mapping(item) for item in payload["sessions"])
                    observations = tuple(MarketObservation.from_mapping(item) for item in payload["observations"])
                    if not sessions or not observations:
                        raise ProductionContractError("market evidence is empty")
                    session_index = {(item.exchange, item.session_date, item.provider, item.provider_product): item for item in sessions}
                    for observation in observations:
                        matches = [item for item in sessions if item.session_date == observation.session_date
                                   and item.provider == observation.provider
                                   and item.provider_product == observation.provider_product]
                        if len(matches) != 1:
                            raise ProductionContractError("market observation lacks one explicit session")
                        observation.validate_against_session(matches[0])
                    if len(session_index) != len(sessions):
                        raise ProductionContractError("market sessions are duplicated")
                else:
                    for item in payload["observations"]:
                        _exact_keys(item, PRODUCTION_FACT_KEYS, "production fundamental observation")
                    facts = tuple(FactObservation.from_mapping(item) for item in payload["observations"])
                    if not facts:
                        raise ProductionContractError("fundamental evidence is empty")
                    for fact in facts:
                        if fact.period_type is PeriodType.DURATION and fact.period_start is None:
                            raise ProductionContractError("duration fact lacks period_start")
                        if fact.reporting_frequency is not ReportingFrequency.ANNUAL:
                            raise ProductionContractError("fundamental fact is not annual")
                        for name in ("provider", "provider_product", "native_observation_id", "source_native_vintage_identifier"):
                            if not getattr(fact, name):
                                raise ProductionContractError(f"fundamental fact lacks {name}")
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, ProductionContractError):
                blockers.append(f"{label}_CONTENT_INVALID")
        return blockers


@dataclass(frozen=True)
class AuthorityCheck:
    name: str
    path: str
    commit: str
    expected_blob: str
    expected_sha256: str


AUTHORITY_CHECKS = (
    AuthorityCheck("architecture_v3_2_subject", "docs/architecture/Architecture_v3.2_Final.md",
                   "65f1b13257402c255d51991bebb3fd74683c2b5e", "4c2d2fc57e78785cd3c89c72e9641dfcb0c7ba5e",
                   "cb542a7efe4a9c809f78aa578f21d2f24c41a4dcfd2df0e38a7ee2950243f3a7"),
    AuthorityCheck("architecture_v3_2_approval", "docs/approvals/v1/architecture-v3-2-approval-001.json",
                   "0e0a7a4abd3f8e1ba84da7c03c41145ccd5e451f", "6ceaddeda4f8f2c18e99e741cbb4b687cbc65bdb",
                   "e03f39bbf628fd89fc50463518f4de121313b1d805ce1422088ef8a26c9af700"),
    AuthorityCheck("screen_v1_subject", "docs/architecture/Screen_Specification_v1_Final.md",
                   "65f1b13257402c255d51991bebb3fd74683c2b5e", "f1f6b1acebdeadfa54f45772df6d04dd48ead38d",
                   "309072e7d442b41f8b11a7cb5c43eab92b5e2d1e4e6cd0dccd41bc7fc0227230"),
    AuthorityCheck("screen_v1_approval", "docs/approvals/v1/screen-specification-v1-approval-001.json",
                   "0e0a7a4abd3f8e1ba84da7c03c41145ccd5e451f", "ed8100a4b69ff5790233b534f60bc4e5b1a83dee",
                   "488e1d2f9143d37ceeb6bcd46c0c6d34c7bff52510874e2ce961ad71df8610de"),
    AuthorityCheck("entry000_contract", "docs/architecture/Entry000_Package_v2_Final.md",
                   "65f1b13257402c255d51991bebb3fd74683c2b5e", "d778976da3e606e63e9dc8d48c5ef5f30ae951d8",
                   "01b55bb74efe2194b798137eec90aaf8528b6814abdd554a83da45c1ead4b17d"),
    AuthorityCheck("entry000_approval", "docs/approvals/v1/entry000-package-v2-approval-001.json",
                   "0e0a7a4abd3f8e1ba84da7c03c41145ccd5e451f", "080563d4cfc975539c1fc6b608ecdae8ae87e19b",
                   "b408e81ca414ad897263a5cc1ee9de2791736fde52f3817ff6486f96a0583ff1"),
    AuthorityCheck("entry000_package", "artifacts/entry000/v2/f7ee66db47f1ebd0b4258507995b2f57e1c7e3b1f8c5139492a0005957bdb914/entry000.package.json",
                   "fe404e52ea9f73665da947fd5359c579e0976fa8", "1e92c216641349c419f02e172e2ab4b13ac21e4d",
                   "5896b8cac53c820cb40e4c8b983eec3cdabd74fd4d0dc6bda9fdfffb7bb8cb0b"),
    AuthorityCheck("screen_v2_subject", SCREEN_V2_PATH,
                   "00d599a6c85cc8452a31463e643eb515327218d5", "549e047fe7cd7a306e9f0f81daaa021aa8ad2794",
                   "0bd82754056f6bdff978064cb094d1d8971f5d0116b2062fc4161da326b5ae4c"),
    AuthorityCheck("screen_v2_approval", SCREEN_V2_APPROVAL_PATH, SCREEN_V2_MERGE_COMMIT,
                   "67f6db0005179a88152df7817065c8b2c4251595", "b9bc27f57a386ae635ba67dac210f33f1db67258589bfc6e88005de0babe3570"),
    AuthorityCheck("v1_policy_subject", "docs/research/V1_Research_Policy_Final.md",
                   "e7203620c7a452cf82bcf032072e4237062fd156", "a77866c5b8f9bca5982b3fbbc3c117120017e43c",
                   "183b27f1058bd89d9616f71660b42160fadacc144639abab635c205b853a26de"),
    AuthorityCheck("v1_policy_approval", "docs/approvals/v1/v1-research-policy-approval-001.json",
                   "a450e4faf86ade46f44d27609f413c41e169f17d", "f210ae96f6308ffef871b3c180ece4a4a631b694",
                   "10dbf5a21ee6525ff3ab7e0f7df56c503d9f55387a70d3380e8c630370155783"),
    AuthorityCheck("adr005_subject", "docs/architecture/adr/ADR-005_Final.md",
                   "76e90e16b56efcefc3917c4b8f90452a1ba717ff", "7295884030bd6fafce5a61446e3d2e2d130385a2",
                   "fad80ff32b8ffdb137bc84e417e0253ac67a0221d1f664c5d3847a7fed077f0a"),
    AuthorityCheck("adr005_approval", "docs/approvals/v1/adr-005-approval-001.json",
                   "7174753bf6e829ab411b63c2854a0b0b0c0c2a57", "de0285465a9e9e6d0f3ff821849ae08bbe68dd17",
                   "73fc3a9c6c9510dd9ecb590c8d23cbd0183f097a681227f039ea68a024a4b535"),
    AuthorityCheck("ledger_subject", "docs/architecture/amendments/Amendment_Ledger_v1.1.0.json",
                   "ee59804fcab50a05702f6d0b9dca7cac831f9998", "182e97396455a63ed085a7fd8b14c5fc688a53ed",
                   "806d1bc8cf0597ba37e8dd71879dd35f46758ac508aaf1459faa6df9d6e3e686"),
    AuthorityCheck("ledger_approval", "docs/approvals/v1/amendment-ledger-v1-1-0-approval-001.json",
                   "435237524ae5131cde8aafe8f40bfd838a97cf40", "61bed41de87be0a8ee198631a0bc6a65243478fc",
                   "9259bde004e08a9189db497925f484caec55cdb3139c379531d247c1e26f9305"),
)


def _git(repository: str | Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", *args], cwd=repository, check=True, capture_output=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProductionContractError(f"Git verification failed: {' '.join(args)}") from exc


def verify_repository_authority(repository: str | Path) -> Mapping[str, bool]:
    results: dict[str, bool] = {}
    for item in AUTHORITY_CHECKS:
        try:
            blob = _git(repository, "rev-parse", f"{item.commit}:{item.path}").decode().strip()
            content = _git(repository, "show", f"{item.commit}:{item.path}")
            results[item.name] = blob == item.expected_blob and hashlib.sha256(content).hexdigest() == item.expected_sha256
        except ProductionContractError:
            results[item.name] = False
    try:
        results["screen_v2_merge_ancestry"] = all(
            subprocess.run(["git", "merge-base", "--is-ancestor", commit, SCREEN_V2_MERGE_COMMIT],
                           cwd=repository, capture_output=True).returncode == 0
            for commit in ("00d599a6c85cc8452a31463e643eb515327218d5",
                           "dea97d66a319a9808ce111a3b43ec794566d2305",
                           "435237524ae5131cde8aafe8f40bfd838a97cf40")
        )
    except OSError:
        results["screen_v2_merge_ancestry"] = False
    return results


EXTERNAL_BLOCKERS = (
    ("EXT-001", "production provider/product topology", "provider and data evidence"),
    ("EXT-002", "exact historical sample boundaries", "historical universe evidence"),
    ("EXT-003", "provider-native immutable security identifiers", "security master"),
    ("EXT-004", "vendor/native field mappings", "source/native mappings"),
    ("EXT-005", "production field-catalog identity", "field catalog"),
    ("EXT-006", "survivorship-complete historical security master", "security master"),
    ("EXT-007", "issuer/security/listing crosswalk", "security master"),
    ("EXT-008", "exact historical market-data product", "market timing and universe"),
    ("EXT-009", "provider/archive evidence identities", "exact provenance"),
    ("EXT-010", "archive and reproducibility rights", "provider capability"),
    ("EXT-011", "entitlement and access evidence", "provider capability"),
    ("EXT-012", "historical exchange calendars and sessions", "market timing"),
    ("EXT-013", "missing-session and stale-price bound", "historical universe evidence"),
    ("EXT-014", "corporate-action timing/effective treatment", "security master"),
    ("EXT-015", "point-in-time shares construction", "market capitalization"),
    ("EXT-016", "total market-capitalization construction", "universe size gate"),
    ("EXT-017", "enterprise-value construction", "valuation proxies"),
    ("EXT-018", "historical operating-company taxonomy", "security eligibility"),
    ("EXT-019", "invested-capital construction", "ROIC"),
    ("EXT-020", "denominator-specific near-zero values", "denominator governance"),
    ("EXT-021", "unit-normalization details", "field catalog"),
    ("EXT-022", "production CandidateSet evidence identities", "CandidateSet publication"),
    ("EXT-023", "exact provider capability verification", "provider/data evidence"),
)

# These are the researcher decisions required for a first production run.  The
# mapping remains deliberately empty until a later normal Approval Record v1
# process has completed and the researcher has explicitly approved each exact
# committed record identity.  Record existence alone must never populate it.
REQUIRED_FIRST_RUN_RESEARCHER_DECISION_IDS = (
    "RD-001", "RD-002B", "RD-004", "RD-008", "RD-013", "RD-014",
    "RD-015", "RD-016", "RD-017", "RD-018", "RD-019", "RD-020",
    "RD-021", "RD-022",
)
APPROVED_PRODUCTION_DECISION_AUTHORITIES: Mapping[str, Mapping[str, str]] = {}
APPROVAL_RECORD_IDENTITY_KEYS = frozenset({
    "repository_id", "approval_record_path", "approval_record_commit",
    "approval_record_git_blob", "approval_record_exact_byte_sha256",
})


def production_decision_authority_blockers(
    repository: str | Path,
) -> tuple[str, ...]:
    """Return unresolved externally approved decision identities.

    This intentionally does not discover Approval Records from the filesystem:
    under Approval Record v1, committed bytes do not prove the human approval
    event.  A later implementation may add only exact identities that have
    completed that external process.
    """

    unexpected = sorted(
        set(APPROVED_PRODUCTION_DECISION_AUTHORITIES)
        - set(REQUIRED_FIRST_RUN_RESEARCHER_DECISION_IDS)
    )
    blockers = [f"UNEXPECTED_PRODUCTION_DECISION_AUTHORITY:{item}" for item in unexpected]
    for decision_id in REQUIRED_FIRST_RUN_RESEARCHER_DECISION_IDS:
        identity = APPROVED_PRODUCTION_DECISION_AUTHORITIES.get(decision_id)
        if identity is None:
            blockers.append(
                f"RESEARCHER_DECISION_AUTHORITY_UNRESOLVED:{decision_id}"
            )
            continue
        try:
            _exact_keys(identity, APPROVAL_RECORD_IDENTITY_KEYS, "ApprovalRecordIdentity")
            if identity["repository_id"] != REPOSITORY_ID:
                raise ProductionContractError("approval repository identity mismatch")
            path = Path(identity["approval_record_path"])
            if (
                path.is_absolute()
                or ".." in path.parts
                or path.parent != Path("docs/approvals/v1")
                or path.suffix != ".json"
            ):
                raise ProductionContractError("approval record path is invalid")
            commit = identity["approval_record_commit"]
            blob = identity["approval_record_git_blob"]
            if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
                raise ProductionContractError("approval record commit is invalid")
            if len(blob) != 40 or any(c not in "0123456789abcdef" for c in blob):
                raise ProductionContractError("approval record blob is invalid")
            expected_sha = _sha256(
                identity["approval_record_exact_byte_sha256"],
                "approval_record_exact_byte_sha256",
            )
            content = _git(repository, "show", f"{commit}:{path.as_posix()}")
            actual_blob = _git(
                repository, "rev-parse", f"{commit}:{path.as_posix()}"
            ).decode().strip()
            payload = json.loads(content)
            if (
                actual_blob != blob
                or hashlib.sha256(content).hexdigest() != expected_sha
                or payload.get("approval_type") != "APPROVE"
                or payload.get("status") != "APPROVED"
                or payload.get("no_realized_outcome_attestation", {}).get("statement")
                != "No realized strategy outcome was examined in making this approval."
            ):
                raise ProductionContractError("approval record identity is unverified")
        except (
            KeyError, TypeError, json.JSONDecodeError, ProductionContractError
        ):
            blockers.append(
                f"RESEARCHER_DECISION_AUTHORITY_UNVERIFIED:{decision_id}"
            )
    return tuple(blockers)


def consolidated_external_blockers() -> list[dict[str, Any]]:
    output = []
    for blocker_id, requirement, blocked in EXTERNAL_BLOCKERS:
        output.append({
            "blocker_id": blocker_id,
            "required_fact_or_evidence": requirement,
            "why_required": "Screen Specification v2 Section 12/14 requires explicit, verified evidence; no default or inference is permitted.",
            "exact_contract_or_state_blocked": blocked,
            "researcher_decision_required": blocker_id in {
                "EXT-001", "EXT-002", "EXT-004", "EXT-008", "EXT-013",
                "EXT-014", "EXT-015", "EXT-016", "EXT-017", "EXT-018",
                "EXT-019", "EXT-020", "EXT-021", "EXT-022",
            },
            "provider_documentation_required": blocker_id not in {"EXT-002", "EXT-020", "EXT-022"},
            "sample_data_required": blocker_id not in {"EXT-010", "EXT-011", "EXT-020", "EXT-022"},
            "credentials_or_entitlement_required": blocker_id in {"EXT-001", "EXT-008", "EXT-010", "EXT-011", "EXT-023"},
            "minimum_evidence_needed": "immutable content bytes plus provider/product/native-vintage identity, SHA-256, effective range, public-availability semantics, and reproducible entitlement/archive evidence applicable to this requirement",
        })
    return output


def evaluate_production_readiness(
    repository: str | Path, manifest: ProductionEvidenceManifest | None = None
) -> tuple[ScreenV2ReadinessState, tuple[str, ...], Mapping[str, bool]]:
    authority = verify_repository_authority(repository)
    screen_ok = all(authority.get(name, False) for name in ("screen_v2_subject", "screen_v2_approval", "screen_v2_merge_ancestry"))
    governing_ok = all(authority.values())
    evidence_blockers = ("PRODUCTION_EVIDENCE_MANIFEST_ABSENT",) if manifest is None else manifest.blockers(repository)
    decision_authority_blockers = production_decision_authority_blockers(repository)
    evidence_ok = (
        manifest is not None
        and not evidence_blockers
        and not decision_authority_blockers
    )
    capabilities_ok = evidence_ok and all(manifest.capabilities.values())
    fields_ok = evidence_ok and not manifest.field_catalog.validate(repository)
    prerequisites = {
        "approved_governing_screen_v2_identity": screen_ok,
        "required_architecture_and_ledger_authority_verified": governing_ok,
        "provider_and_data_evidence_resolved": evidence_ok,
        "pit_provider_capability_verified": capabilities_ok,
        "security_master_verified": evidence_ok,
        "historical_universe_evidence_verified": evidence_ok,
        "field_catalog_verified": fields_ok,
        "market_timing_and_session_evidence_verified": evidence_ok,
        "source_native_mappings_verified": evidence_ok and manifest.proxy_input_mappings_resolved if manifest else False,
        "exact_provenance_verified": evidence_ok and manifest.exact_provenance_chain_valid if manifest else False,
        "mandatory_proxy_coverage_verified": evidence_ok and manifest.proxy_input_mappings_resolved and manifest.denominator_governance_resolved if manifest else False,
        "required_valuation_coverage_verified": evidence_ok and manifest.proxy_input_mappings_resolved if manifest else False,
        "implementation_and_configuration_identities_consistent": evidence_ok and manifest.screen_v2_configuration_digest == SCREEN_V2_CONFIG_DIGEST if manifest else False,
    }
    all_ready = all(prerequisites.values())
    state = ScreenV2ReadinessState(
        "RESOLVED_RESEARCH_POLICY",
        "RESOLVED_PROVIDER_AND_DATA_EVIDENCE" if evidence_ok else None,
        "VERIFIED_REPOSITORY_IDENTITIES" if governing_ok else None,
        "PRODUCTION_EXECUTION_READY" if all_ready else None,
        prerequisites,
    )
    blockers = [*evidence_blockers, *decision_authority_blockers]
    blockers.extend(f"PREREQUISITE_FALSE:{name}" for name, value in prerequisites.items() if not value)
    return state, tuple(sorted(set(blockers))), authority


def production_readiness_preflight(
    repository: str | Path, evidence_manifest_path: str | Path | None = None
) -> dict[str, Any]:
    manifest = ProductionEvidenceManifest.load(evidence_manifest_path) if evidence_manifest_path else None
    state, blockers, authority = evaluate_production_readiness(repository, manifest)
    return {
        "research_policy_resolved": True,
        "provider_data_evidence_resolved": state.provider_and_data_evidence_state is not None,
        "researcher_decision_authority_resolved": not production_decision_authority_blockers(repository),
        "repository_identities_verified": state.repository_identity_state is not None,
        "production_execution_ready": state.production_execution_ready,
        "readiness_state": state.to_dict(),
        "authority_checks": dict(authority),
        "blockers": list(blockers),
        "candidate_set_created": False,
        "first_real_governed_run": "READY_FOR_EXECUTION" if state.production_execution_ready else "FIRST_REAL_RUN_BLOCKED",
        "realized_outcomes_inspected": False,
        "transaction_authority": False,
        "external_requirements": [] if state.production_execution_ready else consolidated_external_blockers(),
    }


def run_governed_screen_v2(
    repository: str | Path,
    *,
    evidence_manifest_path: str | Path | None,
    universe_observations: Sequence[UniverseObservation] | None = None,
    governed_ranked_frame: pd.DataFrame | None = None,
    governed_batch_lineage_sha256: str | None = None,
) -> dict[str, Any]:
    """Apply the final no-outcome publication gate to admitted run inputs.

    Provider adapters and the existing governed feature/ranking pipeline create
    the inputs.  This boundary rechecks readiness, point-in-time universe
    membership, mandatory valuation coverage, ranking scope, population, and
    CandidateSet identity.  It never reads returns or creates trading output.
    """

    preflight = production_readiness_preflight(repository, evidence_manifest_path)
    if not preflight["production_execution_ready"]:
        return preflight
    if universe_observations is None or governed_ranked_frame is None or governed_batch_lineage_sha256 is None:
        return {
            **preflight,
            "production_execution_ready": False,
            "first_real_governed_run": "FIRST_REAL_RUN_BLOCKED",
            "blockers": [*preflight["blockers"], "PRODUCTION_RUN_INPUTS_ABSENT"],
        }
    manifest = ProductionEvidenceManifest.load(evidence_manifest_path)
    state, blockers, _ = evaluate_production_readiness(repository, manifest)
    if blockers or not state.production_execution_ready:
        raise ProductionContractError("readiness changed during governed run")
    universe = build_point_in_time_universe(universe_observations)
    universe_ids = {item.security_id for item in universe}
    ranked_ids = set(governed_ranked_frame["security_id"])
    if not ranked_ids <= universe_ids:
        raise ProductionContractError("RANKED_SECURITY_OUTSIDE_POINT_IN_TIME_UNIVERSE")
    candidate = create_candidate_set(
        governed_ranked_frame,
        readiness=state,
        governed_batch_lineage_sha256=governed_batch_lineage_sha256,
    )
    return {
        **preflight,
        "candidate_set_created": True,
        "first_real_governed_run": "COMPLETED",
        "candidate_set": candidate.to_dict(),
        "realized_outcomes_inspected": False,
        "transaction_authority": False,
    }


AUDIT_ITEM_NAMES = (
    "FactObservation schema", "explicit period_start support", "explicit period_end support",
    "first-reported observation identity", "public-availability timestamps",
    "provider/native observation IDs", "source vintage manifest", "field catalog",
    "canonical-field mapping", "XBRL/vendor mapping governance", "historical security master",
    "issuer identity", "security identity", "listing identity", "issuer/security/listing crosswalk",
    "historical primary-listing state", "security-type historical classification", "SPAC combination boundary",
    "multi-class issuer deduplication", "seasoning calculation", "primary exchange calendar",
    "completed-session counting", "prior-completed-primary-market-session alignment",
    "historical holiday/session evidence", "raw close", "raw volume", "60-session median dollar volume",
    "historical shares outstanding", "total market capitalization", "enterprise value", "market-role provenance",
    "accounting-role provenance", "annual FIRST_REPORTED selection", "consecutive annual-period validation",
    "fcf_ev", "ebit_ev", "gross_profitability", "roic", "operating_margin_change", "fcf_margin_change",
    "revenue_acceleration", "denominator policy", "missingness policy", "mandatory valuation coverage",
    "dimensions", "percentile ranking", "within-dimension equal weighting", "across-dimension equal weighting",
    "GovernedRankingArtifact digest protection", "CandidateSet schema", "CandidateSet Top-100 selection",
    "deterministic tie-break", "insufficient-population failure", "production-readiness state machine",
    "repository identity verification", "provider evidence verification", "field-catalog identity verification",
    "security-master identity verification", "market-data identity verification", "full provenance chain",
    "executable configuration digest", "governed batch lineage", "clean-tree requirement",
    "CandidateSet publication gate", "outcome-free screen construction boundary",
)


def implementation_gap_audit() -> list[dict[str, Any]]:
    external = {8, 9, 10, 11, 15, 16, 17, 18, 21, 24, 28, 29, 30, 31, 32, 56, 57, 58, 59, 60}
    incomplete = {33, 34, 35, 36, 37, 38, 39, 40, 41, 42}
    output = []
    for number, name in enumerate(AUDIT_ITEM_NAMES, 1):
        if number in external:
            status = "BLOCKED_BY_EXTERNAL_EVIDENCE"
            note = "closed validator is implemented; positive production state requires external immutable evidence"
        elif number in incomplete:
            status = "IMPLEMENTED_BUT_INCOMPLETE"
            note = "deterministic behavior exists; production availability remains conditional on governed mappings or evidence"
        else:
            status = "IMPLEMENTED_AND_VERIFIED"
            note = "provider-neutral deterministic implementation and tests are present"
        output.append({"item": number, "capability": name, "classification": status, "note": note})
    return output
