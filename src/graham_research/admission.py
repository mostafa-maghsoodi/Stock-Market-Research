"""A22 provider-neutral evidence admission and decision-packet contracts.

Nothing in this module selects a provider or turns a sample into production
evidence.  It supplies closed structures, exhaustive diagnostics, and machine-
verifiable acceptance tests that future evidence must pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from .domain import FactObservation, PeriodType, ReportingFrequency
from .production import (
    EvidenceIdentity,
    ExchangeSessionEvidence,
    FieldCatalogEntry,
    MarketObservation,
    ProductionContractError,
    SecurityMasterRecord,
    _aware,
    _exact_keys,
    _nonempty,
)


BLOCKER_DEPENDENCY_CLASSES = frozenset({
    "INTERNAL_DETERMINISTIC",
    "RESEARCHER_DECISION",
    "PROVIDER_DOCUMENTATION",
    "PROVIDER_SAMPLE_DATA",
    "PROVIDER_ENTITLEMENT",
    "DERIVED_AFTER_PROVIDER_ADMISSION",
    "MIXED",
    "NOT_ACTUALLY_REQUIRED",
})

BLOCKER_RECLASSIFICATION: Mapping[str, tuple[str, ...]] = {
    "EXT-001": ("MIXED", "RESEARCHER_DECISION", "PROVIDER_DOCUMENTATION", "PROVIDER_ENTITLEMENT"),
    "EXT-002": ("MIXED", "RESEARCHER_DECISION", "DERIVED_AFTER_PROVIDER_ADMISSION"),
    "EXT-003": ("PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA"),
    "EXT-004": ("MIXED", "RESEARCHER_DECISION", "PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA"),
    "EXT-005": ("DERIVED_AFTER_PROVIDER_ADMISSION",),
    "EXT-006": ("PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA"),
    "EXT-007": ("PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA"),
    "EXT-008": ("MIXED", "RESEARCHER_DECISION", "PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA", "PROVIDER_ENTITLEMENT"),
    "EXT-009": ("MIXED", "PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA", "DERIVED_AFTER_PROVIDER_ADMISSION"),
    "EXT-010": ("PROVIDER_DOCUMENTATION", "PROVIDER_ENTITLEMENT"),
    "EXT-011": ("PROVIDER_ENTITLEMENT",),
    "EXT-012": ("PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA"),
    "EXT-013": ("MIXED", "RESEARCHER_DECISION", "PROVIDER_SAMPLE_DATA"),
    "EXT-014": ("MIXED", "RESEARCHER_DECISION", "PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA"),
    "EXT-015": ("MIXED", "RESEARCHER_DECISION", "PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA"),
    "EXT-016": ("MIXED", "RESEARCHER_DECISION", "PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA"),
    "EXT-017": ("MIXED", "RESEARCHER_DECISION", "PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA"),
    "EXT-018": ("MIXED", "RESEARCHER_DECISION", "PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA"),
    "EXT-019": ("MIXED", "RESEARCHER_DECISION", "PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA"),
    "EXT-020": ("RESEARCHER_DECISION",),
    "EXT-021": ("MIXED", "RESEARCHER_DECISION", "PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA"),
    "EXT-022": ("MIXED", "INTERNAL_DETERMINISTIC", "RESEARCHER_DECISION", "DERIVED_AFTER_PROVIDER_ADMISSION"),
    "EXT-023": ("PROVIDER_DOCUMENTATION", "PROVIDER_SAMPLE_DATA", "PROVIDER_ENTITLEMENT"),
}


def blocker_reclassification() -> list[dict[str, Any]]:
    if set(BLOCKER_RECLASSIFICATION) != {f"EXT-{number:03d}" for number in range(1, 24)}:
        raise ProductionContractError("A22 blocker register is incomplete")
    output = []
    for blocker_id, classes in BLOCKER_RECLASSIFICATION.items():
        if not set(classes) <= BLOCKER_DEPENDENCY_CLASSES:
            raise ProductionContractError(f"invalid blocker class for {blocker_id}")
        output.append({"blocker_id": blocker_id, "dependency_classes": list(classes)})
    return output


def _capability(
    capability_id: str,
    name: str,
    evidence_type: str,
    minimum_documentation: str,
    minimum_sample: str,
    acceptance_test: str,
) -> dict[str, Any]:
    return {
        "capability_id": capability_id,
        "capability_name": name,
        "required": True,
        "evidence_type": evidence_type,
        "minimum_documentation": minimum_documentation,
        "minimum_sample": minimum_sample,
        "machine_verifiable_acceptance_test": acceptance_test,
        "failure_behavior": f"fail closed with {capability_id}_UNRESOLVED; no production admission or CandidateSet",
    }


PROVIDER_CAPABILITY_SPECIFICATION = (
    _capability("CAP-001", "provider legal/product identity", "documentation", "legal entity, product name, product ID", "metadata header naming provider/product", "non-empty stable provider and product identities"),
    _capability("CAP-002", "stable product/version identifier", "documentation+sample", "version/vintage semantics", "native product/version value", "version is non-empty and content-bound"),
    _capability("CAP-003", "entitlement/access", "entitlement", "dated entitlement scope", "successful authorized extract receipt", "identity bytes verify and entitlement flag is explicit"),
    _capability("CAP-004", "archive/reproducibility rights", "rights documentation", "right to retain/reproduce governed extracts", "re-fetch or archive demonstration", "rights evidence identity verifies"),
    _capability("CAP-005", "historical PIT fundamentals", "documentation+sample", "PIT/as-reported methodology", "multiple historical annual observations", "annual observations carry period boundaries and vintage"),
    _capability("CAP-006", "first-reported/revision history", "documentation+sample", "revision sequence semantics", "first report and later restatement for one fact", "distinct native IDs/timestamps establish revision ordering"),
    _capability("CAP-007", "public availability timestamps", "documentation+sample", "timestamp source and timezone", "timestamped filings/facts", "every fact has aware available_at"),
    _capability("CAP-008", "filing/accession/native observation identity", "documentation+sample", "identifier stability semantics", "non-empty accession/native IDs", "IDs are present and unique in their native scope"),
    _capability("CAP-009", "inactive and delisted securities", "documentation+sample", "coverage of inactive/delisted history", "at least one inactive or delisted record", "sample contains effective-dated inactive/delisted record"),
    _capability("CAP-010", "historical security master", "documentation+sample", "PIT master methodology", "effective-dated security records", "closed records parse without current-status fallback"),
    _capability("CAP-011", "issuer/security/listing crosswalk", "documentation+sample", "crosswalk key semantics", "effective-dated linked native IDs", "issuer/security/listing IDs and crosswalk are non-empty"),
    _capability("CAP-012", "historical primary-listing state", "documentation+sample", "primary-listing methodology", "primary and non-primary examples", "is_primary_listing is explicit and effective-dated"),
    _capability("CAP-013", "historical security classification", "documentation+sample", "taxonomy definitions/history", "historically effective classifications", "classification effective range covers sample date"),
    _capability("CAP-014", "corporate actions", "documentation+sample", "event types and effective timestamp semantics", "split, identifier/listing change, and terminal-event examples where available", "closed corporate-action records parse with native IDs"),
    _capability("CAP-015", "raw unadjusted close", "documentation+sample", "raw/unadjusted price definition", "session close observations", "raw_close is finite, nonnegative, and session-aligned"),
    _capability("CAP-016", "raw volume", "documentation+sample", "volume definition and correction policy", "session volume observations", "raw_volume is finite, nonnegative, and session-aligned"),
    _capability("CAP-017", "historical shares", "documentation+sample", "share concept, timing, adjustment semantics", "effective-dated share observations", "native concept and PIT timestamp are explicit"),
    _capability("CAP-018", "exchange sessions", "documentation+sample", "timezone/holiday/session methodology", "completed sessions and holidays", "closed session records parse with aware open/close"),
    _capability("CAP-019", "immutable provider-native identifiers", "documentation+sample", "identifier stability/reuse semantics", "native issuer/security/listing IDs", "all three native IDs are non-empty"),
    _capability("CAP-020", "native field definitions", "documentation+sample", "economic definition for every mapped field", "field dictionary entries", "mapping evidence bytes verify; no name-similarity inference"),
    _capability("CAP-021", "unit/scaling semantics", "documentation+sample", "native unit, scaling, currency rules", "values using declared units/scales", "positive finite scale and exact canonical unit"),
    _capability("CAP-022", "historical coverage boundaries", "documentation+sample", "first/last availability by dataset", "boundary dates with coverage counts", "effective ranges cover requested validation/run dates"),
    _capability("CAP-023", "extract vintage/archive identity", "documentation+sample", "vintage creation and immutability semantics", "native vintage ID", "vintage ID is non-empty and stable"),
    _capability("CAP-024", "reproducible content identity", "derived evidence", "content export/canonical bytes rules", "exact detached dataset bytes", "repository bytes match declared SHA-256"),
    _capability("CAP-025", "exact field mapping evidence", "documentation+sample", "native-to-canonical equivalence evidence", "mapped fields across effective range", "catalog entry and detached evidence identities agree"),
)
CAPABILITY_IDS = tuple(item["capability_id"] for item in PROVIDER_CAPABILITY_SPECIFICATION)


@dataclass(frozen=True)
class CapabilityEvidence:
    capability_id: str
    supported: bool
    documentation_identities: tuple[EvidenceIdentity, ...]
    sample_identities: tuple[EvidenceIdentity, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CapabilityEvidence":
        _exact_keys(value, {
            "capability_id", "supported", "documentation_identities", "sample_identities"
        }, "capability evidence")
        if not isinstance(value["supported"], bool):
            raise ProductionContractError("capability supported must be boolean")
        return cls(
            capability_id=value["capability_id"], supported=value["supported"],
            documentation_identities=tuple(
                EvidenceIdentity.from_mapping(item) for item in value["documentation_identities"]
            ),
            sample_identities=tuple(
                EvidenceIdentity.from_mapping(item) for item in value["sample_identities"]
            ),
        )


@dataclass(frozen=True)
class CorporateActionRecord:
    native_action_id: str
    issuer_id: str
    security_id: str
    listing_id: str
    action_type: str
    announced_at: datetime
    effective_at: datetime
    predecessor_security_id: str | None
    successor_security_id: str | None
    split_ratio: float | None
    evidence_identity: EvidenceIdentity

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CorporateActionRecord":
        _exact_keys(value, {
            "native_action_id", "issuer_id", "security_id", "listing_id", "action_type",
            "announced_at", "effective_at", "predecessor_security_id",
            "successor_security_id", "split_ratio", "evidence_identity",
        }, "corporate action")
        action_type = value["action_type"]
        if action_type not in {
            "TICKER_CHANGE", "SPLIT", "REVERSE_SPLIT", "MERGER", "SPINOFF",
            "DELISTING", "EXCHANGE_TRANSFER", "SPAC_BUSINESS_COMBINATION",
            "SHARE_CLASS_CHANGE",
        }:
            raise ProductionContractError("unsupported corporate action type")
        ratio = value["split_ratio"]
        if ratio is not None and (
            isinstance(ratio, bool) or not math.isfinite(float(ratio)) or ratio <= 0
        ):
            raise ProductionContractError("split_ratio must be positive when present")
        announced = _aware(value["announced_at"], "announced_at")
        effective = _aware(value["effective_at"], "effective_at")
        return cls(
            native_action_id=_nonempty(value["native_action_id"], "native_action_id"),
            issuer_id=_nonempty(value["issuer_id"], "issuer_id"),
            security_id=_nonempty(value["security_id"], "security_id"),
            listing_id=_nonempty(value["listing_id"], "listing_id"),
            action_type=action_type, announced_at=announced, effective_at=effective,
            predecessor_security_id=value["predecessor_security_id"],
            successor_security_id=value["successor_security_id"], split_ratio=ratio,
            evidence_identity=EvidenceIdentity.from_mapping(value["evidence_identity"]),
        )


SAMPLE_DATASET_KEYS = (
    "fundamentals", "security_master", "market_data", "exchange_sessions",
    "corporate_actions", "field_definitions", "identifiers_crosswalks",
)


@dataclass(frozen=True)
class ProviderSampleAdmissionPack:
    schema_version: int
    artifact_status: str
    provider_legal_name: str
    provider: str
    provider_product: str
    product_version: str
    validation_start: date
    validation_end: date
    declared_at_utc: datetime
    entitlement_identity: EvidenceIdentity
    archive_rights_identity: EvidenceIdentity
    extract_identity: EvidenceIdentity
    dataset_identities: Mapping[str, EvidenceIdentity]
    capabilities: tuple[CapabilityEvidence, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProviderSampleAdmissionPack":
        _exact_keys(value, {
            "schema_version", "artifact_status", "provider_legal_name", "provider",
            "provider_product", "product_version", "validation_start", "validation_end",
            "declared_at_utc", "entitlement_identity", "archive_rights_identity",
            "extract_identity", "dataset_identities", "capabilities",
        }, "provider sample admission pack")
        _exact_keys(value["dataset_identities"], SAMPLE_DATASET_KEYS, "sample dataset identities")
        return cls(
            schema_version=value["schema_version"], artifact_status=value["artifact_status"],
            provider_legal_name=value["provider_legal_name"], provider=value["provider"],
            provider_product=value["provider_product"], product_version=value["product_version"],
            validation_start=date.fromisoformat(value["validation_start"]),
            validation_end=date.fromisoformat(value["validation_end"]),
            declared_at_utc=_aware(value["declared_at_utc"], "declared_at_utc"),
            entitlement_identity=EvidenceIdentity.from_mapping(value["entitlement_identity"]),
            archive_rights_identity=EvidenceIdentity.from_mapping(value["archive_rights_identity"]),
            extract_identity=EvidenceIdentity.from_mapping(value["extract_identity"]),
            dataset_identities={
                key: EvidenceIdentity.from_mapping(identity)
                for key, identity in value["dataset_identities"].items()
            },
            capabilities=tuple(CapabilityEvidence.from_mapping(item) for item in value["capabilities"]),
        )

    @classmethod
    def load(cls, path: str | Path) -> "ProviderSampleAdmissionPack":
        return cls.from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))

    def validate(self, repository: str | Path) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.schema_version != 1:
            blockers.append("SAMPLE_PACK_SCHEMA_UNSUPPORTED")
        if self.artifact_status != "PROVIDER_SAMPLE_CANDIDATE_NOT_ADMITTED":
            blockers.append("SAMPLE_PACK_STATUS_INVALID")
        for name in ("provider_legal_name", "provider", "provider_product", "product_version"):
            try:
                _nonempty(getattr(self, name), name)
            except ProductionContractError:
                blockers.append(f"{name.upper()}_MISSING")
        if self.validation_end < self.validation_start:
            blockers.append("VALIDATION_RANGE_INVERTED")
        identities = {
            "ENTITLEMENT": self.entitlement_identity,
            "ARCHIVE_RIGHTS": self.archive_rights_identity,
            "EXTRACT": self.extract_identity,
            **{f"DATASET_{key.upper()}": identity for key, identity in self.dataset_identities.items()},
        }
        for label, identity in identities.items():
            if (
                identity.provider != self.provider
                or identity.provider_product != self.provider_product
            ):
                blockers.append(f"{label}_PROVIDER_PRODUCT_MISMATCH")
            if not identity.verify_content(repository):
                blockers.append(f"{label}_IDENTITY_UNVERIFIED")
        by_id = {item.capability_id: item for item in self.capabilities}
        if len(by_id) != len(self.capabilities):
            blockers.append("DUPLICATE_CAPABILITY_EVIDENCE")
        for extra in sorted(set(by_id) - set(CAPABILITY_IDS)):
            blockers.append(f"UNEXPECTED_CAPABILITY:{extra}")
        for spec in PROVIDER_CAPABILITY_SPECIFICATION:
            item = by_id.get(spec["capability_id"])
            if item is None:
                blockers.append(f"{spec['capability_id']}_MISSING")
                continue
            if not item.supported:
                blockers.append(f"{spec['capability_id']}_UNSUPPORTED")
            evidence_type = spec["evidence_type"]
            if "documentation" in evidence_type and not item.documentation_identities:
                blockers.append(f"{spec['capability_id']}_DOCUMENTATION_MISSING")
            if "sample" in evidence_type and not item.sample_identities:
                blockers.append(f"{spec['capability_id']}_SAMPLE_MISSING")
            for identity in (*item.documentation_identities, *item.sample_identities):
                if (
                    identity.provider != self.provider
                    or identity.provider_product != self.provider_product
                ):
                    blockers.append(f"{spec['capability_id']}_PROVIDER_PRODUCT_MISMATCH")
                if not identity.verify_content(repository):
                    blockers.append(f"{spec['capability_id']}_EVIDENCE_IDENTITY_UNVERIFIED")
        blockers.extend(self._validate_dataset_content(repository))
        return tuple(sorted(set(blockers)))

    def _load_dataset(self, repository: str | Path, name: str) -> Mapping[str, Any]:
        identity = self.dataset_identities[name]
        if identity.repository_relative_path is None:
            raise ProductionContractError(f"{name} path absent")
        return json.loads(
            (Path(repository) / identity.repository_relative_path).read_text(encoding="utf-8")
        )

    def _validate_dataset_content(self, repository: str | Path) -> list[str]:
        blockers: list[str] = []
        for name in SAMPLE_DATASET_KEYS:
            try:
                payload = self._load_dataset(repository, name)
                if payload.get("schema_version") != 1:
                    raise ProductionContractError("schema version")
                records = payload.get("records")
                if not isinstance(records, list) or not records:
                    raise ProductionContractError("records absent")
                if name == "security_master":
                    parsed = tuple(SecurityMasterRecord.from_mapping(item) for item in records)
                    if not any(item.is_inactive_or_delisted for item in parsed):
                        blockers.append("SAMPLE_MISSING_INACTIVE_OR_DELISTED_SECURITY")
                    for item in parsed:
                        if (
                            item.evidence_identity.provider != self.provider
                            or item.evidence_identity.provider_product
                            != self.provider_product
                            or not item.evidence_identity.verify_content(repository)
                        ):
                            blockers.append(
                                "SAMPLE_SECURITY_MASTER_RECORD_EVIDENCE_UNVERIFIED"
                            )
                elif name == "fundamentals":
                    facts = tuple(FactObservation.from_mapping(item) for item in records)
                    for fact in facts:
                        if fact.reporting_frequency is not ReportingFrequency.ANNUAL:
                            blockers.append("SAMPLE_FUNDAMENTAL_NOT_ANNUAL")
                        if fact.period_type is PeriodType.DURATION and fact.period_start is None:
                            blockers.append("SAMPLE_FUNDAMENTAL_PERIOD_START_MISSING")
                        if not fact.native_observation_id:
                            blockers.append("SAMPLE_FUNDAMENTAL_NATIVE_ID_MISSING")
                        if fact.available_at.tzinfo is None:
                            blockers.append("SAMPLE_FUNDAMENTAL_TIMESTAMP_MISSING")
                        if (
                            fact.provider != self.provider
                            or fact.provider_product != self.provider_product
                            or not fact.source_native_vintage_identifier
                        ):
                            blockers.append(
                                "SAMPLE_FUNDAMENTAL_PROVIDER_LINEAGE_INVALID"
                            )
                    revision_groups: dict[tuple[str, str, date], set[str]] = {}
                    for fact in facts:
                        revision_groups.setdefault(
                            (fact.security_id, fact.field, fact.period_end), set()
                        ).add(fact.native_observation_id or "")
                    if not any(len(ids) >= 2 for ids in revision_groups.values()):
                        blockers.append("SAMPLE_MISSING_FIRST_REPORTED_AND_RESTATEMENT_PAIR")
                elif name == "market_data":
                    parsed = tuple(MarketObservation.from_mapping(item) for item in records)
                    for item in parsed:
                        if (
                            item.provider != self.provider
                            or item.provider_product != self.provider_product
                            or not item.evidence_identity.verify_content(repository)
                        ):
                            blockers.append("SAMPLE_MARKET_RECORD_EVIDENCE_UNVERIFIED")
                elif name == "exchange_sessions":
                    parsed = tuple(ExchangeSessionEvidence.from_mapping(item) for item in records)
                    for item in parsed:
                        if (
                            item.provider != self.provider
                            or item.provider_product != self.provider_product
                            or not item.evidence_identity.verify_content(repository)
                        ):
                            blockers.append("SAMPLE_SESSION_RECORD_EVIDENCE_UNVERIFIED")
                elif name == "corporate_actions":
                    parsed = tuple(CorporateActionRecord.from_mapping(item) for item in records)
                    for item in parsed:
                        if (
                            item.evidence_identity.provider != self.provider
                            or item.evidence_identity.provider_product
                            != self.provider_product
                            or not item.evidence_identity.verify_content(repository)
                        ):
                            blockers.append(
                                "SAMPLE_CORPORATE_ACTION_RECORD_EVIDENCE_UNVERIFIED"
                            )
                elif name == "field_definitions":
                    parsed = tuple(FieldCatalogEntry.from_mapping(item) for item in records)
                    for item in parsed:
                        if (
                            item.provider != self.provider
                            or item.provider_product != self.provider_product
                            or not item.mapping_evidence_identity.verify_content(repository)
                            or not item.source_provenance.verify_content(repository)
                        ):
                            blockers.append("SAMPLE_FIELD_MAPPING_EVIDENCE_UNVERIFIED")
                else:
                    required = {
                        "issuer_id", "security_id", "listing_id",
                        "provider_native_issuer_id", "provider_native_security_id",
                        "provider_native_listing_id", "effective_start", "effective_end",
                    }
                    for record in records:
                        _exact_keys(record, required, "identifier crosswalk")
                        for key in required - {"effective_end"}:
                            if record[key] in (None, ""):
                                raise ProductionContractError(f"crosswalk {key} missing")
                        start = date.fromisoformat(record["effective_start"])
                        end = date.fromisoformat(record["effective_end"]) if record["effective_end"] else None
                        if end is not None and end < start:
                            blockers.append("SAMPLE_CROSSWALK_EFFECTIVE_RANGE_INVALID")
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, ProductionContractError):
                blockers.append(f"SAMPLE_{name.upper()}_CONTENT_INVALID")
        return blockers


def validate_provider_sample_pack(
    path: str | Path, *, repository: str | Path
) -> dict[str, Any]:
    try:
        pack = ProviderSampleAdmissionPack.load(path)
        blockers = pack.validate(repository)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, ProductionContractError) as exc:
        return {
            "admitted": False,
            "artifact_status": "NOT_ADMITTED",
            "blockers": [f"SAMPLE_PACK_INVALID:{exc}"],
            "production_evidence": False,
        }
    return {
        "admitted": not blockers,
        "artifact_status": "VALIDATED_SAMPLE_NOT_PRODUCTION_ADMITTED" if not blockers else "NOT_ADMITTED",
        "blockers": list(blockers),
        "production_evidence": False,
    }


RESEARCHER_DECISIONS = (
    {
        "decision_id": "RD-001", "decision_name": "production provider/product topology",
        "why_required": "no production provider or product combination is selected",
        "governing_clause": "Architecture v3.2 U-001; Screen v2 Sections 12 item 1 and 13",
        "allowed_domain": "one or more named legal providers and stable products whose admitted capabilities cover every required input",
        "options": "single-provider topology or explicit multi-provider topology with governed crosswalks",
        "tradeoffs": "fewer joins reduce crosswalk risk; multiple products may improve capability coverage",
        "framing": "choose only after capability, rights, entitlement, sample, and archive evidence is available",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "production evidence manifest provider/product identities and joins",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-002A", "decision_name": "initial production-validation range",
        "why_required": "bounds sample validation; it does not select the first governed run",
        "governing_clause": "Architecture v3.2 U-005; Screen v2 Section 12 item 2",
        "allowed_domain": "inclusive UTC start/end dates with start <= end",
        "options": "any ex-ante range supported by admitted PIT coverage",
        "tradeoffs": "longer ranges test more history but demand more valid archive coverage",
        "framing": "state the validation purpose and dates without using realized outcomes",
        "successor_governance_if_changed": False,
        "authority_path": "EXISTING_PRODUCTION_FREEZE_MECHANISM",
        "timestamp_or_attestation_required": True,
        "downstream_field": "ProviderSampleAdmissionPack.validation_start/validation_end",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-002B", "decision_name": "first governed screen decision date",
        "why_required": "the first CandidateSet must bind one admissible decision date",
        "governing_clause": "Architecture v3.2 U-005; Screen v2 Sections 5 and 12 item 2",
        "allowed_domain": "one date with complete admitted PIT lookback and completed-session evidence",
        "options": "any admissible date established by provider coverage; no performance-based choice",
        "tradeoffs": "later dates may improve coverage but do not relax PIT requirements",
        "framing": "select from coverage-qualified dates before any future returns are inspected",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "governed run decision_date and CandidateSet identity",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-002C", "decision_name": "full intended historical research range",
        "why_required": "future multi-date research needs frozen full sample boundaries",
        "governing_clause": "Architecture v3.2 U-005; V1 Policy Section 15",
        "allowed_domain": "inclusive start/end dates within admitted PIT coverage",
        "options": "any outcome-free coverage-qualified range",
        "tradeoffs": "breadth versus consistent historical data quality",
        "framing": "defer until coverage audit; not required for the first single-date run",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "future historical run configuration",
        "required_before_first_run": False,
    },
    {
        "decision_id": "RD-004", "decision_name": "native/canonical field mappings and governed field catalog",
        "why_required": "field-name similarity is forbidden and exact mappings must be separately governed",
        "governing_clause": "Screen v2 Sections 7 and 12 items 4-5",
        "allowed_domain": "an exact effective-dated mapping for every required canonical concept, backed by semantic evidence",
        "options": "approve a supported native field or an explicitly governed construction; unsupported concepts remain unavailable",
        "tradeoffs": "direct mappings are simpler; constructions demand more component, timing, and unit evidence",
        "framing": "decide economic equivalence from definitions and samples before outcomes",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "FieldCatalog entries, catalog identity, and proxy input mappings",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-008", "decision_name": "production historical market-data product",
        "why_required": "the exact raw historical close/volume product remains unselected",
        "governing_clause": "Architecture v3.2 U-001/U-008; Screen v2 Sections 12 item 8 and 13",
        "allowed_domain": "an admitted product with raw unadjusted close, raw volume, sessions, identifiers, archive, and entitlement evidence",
        "options": "any evidence-qualified product; multi-product use requires explicit crosswalks",
        "tradeoffs": "coverage, timestamp fidelity, correction history, and reproducibility may differ",
        "framing": "select from capability-qualified products without inspecting strategy outcomes",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "market-data provider/product and evidence identities",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-013", "decision_name": "missing-session/stale-price bound",
        "why_required": "PRIOR_COMPLETED selects a session but does not define maximum acceptable age",
        "governing_clause": "Screen v2 Section 12 item 13",
        "allowed_domain": "explicit age metric, nonnegative bound, and fail behavior by market role",
        "options": "calendar-time bound, completed-session-count bound, or both; each must fail closed",
        "tradeoffs": "tight bounds reduce stale inputs; looser bounds retain more observations",
        "framing": "choose an economic data-quality limit ex ante, not from returns",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "resolved production configuration stale_session_policy",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-014", "decision_name": "corporate-action continuity/effective-event policy",
        "why_required": "raw prices and PIT identities dictate evidence, but not every continuity treatment",
        "governing_clause": "Screen v2 Section 12 item 14",
        "allowed_domain": "per-event identity/listing/share-class continuity and timestamp rules",
        "options": "explicit treatment for ticker/class changes, splits, mergers, spinoffs, delisting, transfers, SPAC combination",
        "tradeoffs": "continuity preserves lineage; new identities avoid false historical equivalence",
        "framing": "bind event-source timestamps and fail when effective treatment is ambiguous",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "corporate_action_policy and security-master lineage",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-015", "decision_name": "PIT shares construction",
        "why_required": "historical total shares must be defined without float-share substitution",
        "governing_clause": "Screen v2 Section 12 item 15",
        "allowed_domain": "explicit canonical total-shares concept, source hierarchy, effective/public timing",
        "options": "direct native total-shares observation or separately governed component construction",
        "tradeoffs": "direct fields simplify lineage; constructions require more mappings and timing checks",
        "framing": "require total, PIT shares and exact evidence; never infer from current shares",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "shares_outstanding mapping/construction",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-016", "decision_name": "total market-capitalization construction",
        "why_required": "TOTAL_MARKET_CAPITALIZATION is fixed, but its admitted source construction is not",
        "governing_clause": "Screen v2 Sections 6 and 12 item 16",
        "allowed_domain": "provider-native total market cap mapping or exact raw-close × PIT-total-shares construction",
        "options": "either path only with exact mapping, units, and prior-session timing",
        "tradeoffs": "native value depends on definition evidence; constructed value depends on shares alignment",
        "framing": "exclude float-adjusted market cap and bind USD total-market-cap semantics",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "total_market_capitalization construction",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-017", "decision_name": "enterprise-value construction",
        "why_required": "both valuation proxies require one exact historical EV meaning",
        "governing_clause": "Screen v2 Sections 7.1, 7.2, and 12 item 17",
        "allowed_domain": "exact provider-native EV mapping or separately enumerated component formula",
        "options": "native field with definition evidence, or governed component construction",
        "tradeoffs": "native EV is simpler; component EV is transparent but mapping-intensive",
        "framing": "do not substitute a vendor EV value without exact economic/timing equivalence",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "enterprise_value mapping/construction",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-019", "decision_name": "invested-capital canonical construction",
        "why_required": "ROIC expects current/prior invested capital but its economics are deferred",
        "governing_clause": "Screen v2 Sections 7.4 and 12 item 19",
        "allowed_domain": "explicit balance-sheet component formula or exact native invested-capital mapping",
        "options": "must specify components, signs, averaging inputs, timing, units, and mappings",
        "tradeoffs": "native fields reduce mechanics; component formulas improve transparency",
        "framing": "preserve current/prior arithmetic mean and decide only the canonical field construction",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "invested_capital canonical field/proxy catalog",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-018", "decision_name": "historical operating-company taxonomy source/mapping",
        "why_required": "Screen v2 fixes the eligible economic class but not the production taxonomy source or exact native mapping",
        "governing_clause": "Screen v2 Sections 5 and 12 item 18",
        "allowed_domain": "effective-dated native classifications mapped exactly to the frozen included/excluded classes",
        "options": "any evidence-backed taxonomy with explicit unmapped/ambiguous fail-closed treatment",
        "tradeoffs": "broader taxonomies need more mapping evidence; narrower sources may reduce coverage",
        "framing": "map economic definitions, not labels, and preserve historical classifications",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "SecurityMasterRecord.security_type/is_operating_company mapping",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-020", "decision_name": "denominator-specific near-zero materiality",
        "why_required": "runtime schema requires a positive threshold and Screen v2 forbids a universal default",
        "governing_clause": "Screen v2 Section 8 and Section 12 item 20",
        "allowed_domain": "one positive finite absolute threshold per denominator in its canonical units, plus action",
        "options": "threshold/action separately for EV, assets, pretax income, invested capital, and each revenue denominator",
        "tradeoffs": "higher thresholds reject more economically unstable ratios",
        "framing": "set ex ante from economic materiality; zero threshold is not executable under current schema",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "DenominatorPolicy.near_zero_absolute_threshold/action",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-021", "decision_name": "unit/currency normalization policy",
        "why_required": "native scales/currencies must reach exact canonical units without inference",
        "governing_clause": "Screen v2 Section 12 item 21",
        "allowed_domain": "per-field native unit, positive scale, canonical unit, currency rule, and effective range",
        "options": "identity scaling or documented conversion; any FX path needs separately explicit PIT evidence",
        "tradeoffs": "normalization broadens coverage but adds mapping and timing dependencies",
        "framing": "use canonical USD, shares, or USD/share targets; never guess vendor scale factors",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "FieldCatalogEntry unit/scaling/currency fields",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-022", "decision_name": "governing CandidateSet evidence identity contract",
        "why_required": "derived hashing is mechanical, but V1 Policy explicitly leaves the exact production identity unresolved",
        "governing_clause": "V1 Policy Section 15; Screen v2 Section 12 item 22",
        "allowed_domain": "approved closed identity schema that preserves the three-column ranking digest",
        "options": "approve/revise the non-governing derived envelope fields; never expand ranking digest scope",
        "tradeoffs": "more bindings improve auditability but increase regeneration sensitivity",
        "framing": "approve exact identity fields before publication; bytes/hashes are then derived",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "CandidateSet governing evidence identity schema",
        "required_before_first_run": True,
    },
    {
        "decision_id": "RD-CROSSWALK-001",
        "decision_name": "Massive-to-Databento identity and listing crosswalk",
        "why_required": "date, ticker, and venue can identify one Databento instrument but do not themselves authorize stable internal issuer/security/listing identities",
        "governing_clause": "Screen v2 Section 12 items 3, 7, and 14",
        "allowed_domain": "a closed, content-bound identity scheme using admitted CIK, share-class FIGI, MIC, Databento dataset, historical symbology interval, instrument ID, definition interval, and evidence identities",
        "options": "approve the proposed content-bound scheme or another exact scheme that never treats ticker alone as identity",
        "tradeoffs": "provider-native identifiers improve auditability; successor events and missing FIGIs require explicit fail-closed handling",
        "framing": "require one and only one date-effective venue match and reject missing or ambiguous joins",
        "successor_governance_if_changed": True,
        "authority_path": "NEW_AUTHORITY_REQUIRED",
        "timestamp_or_attestation_required": True,
        "downstream_field": "issuer_id, security_id, listing_id, and issuer_crosswalk_id",
        "required_before_first_run": True,
    },
)


def researcher_decision_packet() -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in sorted(RESEARCHER_DECISIONS, key=lambda value: value["decision_id"])
    ]
