"""Outcome-free governed-screen contracts and fail-closed preflight.

This module intentionally cannot produce a CandidateSet.  The approved Screen
Specification declares that artifact future and leaves membership, cutoff, and
count decisions unresolved.  The executable surface therefore stops at a
deterministic diagnostic boundary and never accepts outcomes or a specification
register.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Mapping

from .governance import GovernanceError, canonical_json
from .ranked_artifact import RANKED_FRAME_DIGEST_SCOPE


CANONICALIZATION = "CanonicalJSON-v1"
REPOSITORY_ID = "mostafa-maghsoodi/Stock-Market-Research"
REQUIRED_PROXY_ORDER = (
    "fcf_ev",
    "ebit_ev",
    "gross_profitability",
    "roic",
    "operating_margin_change",
    "fcf_margin_change",
    "revenue_acceleration",
)
REQUIRED_DIMENSIONS = (
    "VALUATION",
    "BUSINESS_ECONOMICS",
    "FUNDAMENTAL_CHANGE",
)
REGENERATION_DIMENSIONS = (
    "Valuation",
    "Business Economics",
    "Fundamental Change",
)
UNRESOLVED_STATE = "UNRESOLVED_RESEARCHER_DECISION"
CANDIDATE_ARTIFACT_KIND = "GovernedCandidateSetArtifact"
CANDIDATE_SCHEMA_STATUS = "FUTURE_SEPARATE_GOVERNED_ARTIFACT"
CANDIDATE_REQUIRED_BINDINGS = (
    "frozen_screen_specification_id",
    "governed_ranking_artifact_identity",
    "ranked_content_digest",
    "ranking_configuration_digest",
    "membership_rule_digest",
    "cutoff_rule_digest",
    "tie_break_rule_digest",
    "decision_date_set_digest",
    "candidate_rows_digest",
    "reproduction_lineage_digest",
)

SCREEN_TOP_LEVEL_KEYS = frozenset({
    "screen_specification_schema_version",
    "screen_specification_id",
    "canonicalization_version",
    "entry000_reference",
    "governing_architecture_reference",
    "universe_reference",
    "security_master_reference",
    "pit_fact_sources",
    "accounting_reference",
    "proxy_registry_reference",
    "required_dimensions",
    "ranking_reference",
    "decision_date_set",
    "research_vintage",
    "code_identities",
    "environment_identity",
    "output_contract",
    "candidate_contract",
    "approval_references",
    "attestations",
})
ENTRY000_REFERENCE_KEYS = frozenset({
    "entry_000_package_schema_version",
    "package_id",
    "full_artifact_sha256",
    "publication_path",
})
ARTIFACT_REFERENCE_KEYS = frozenset({
    "repository_id",
    "repository_relative_path",
    "source_commit",
    "git_blob",
    "exact_byte_sha256",
    "schema_or_document_version",
})
APPROVAL_REFERENCE_KEYS = frozenset({
    "repository_id",
    "approval_record_path",
    "approval_record_commit",
    "approval_record_git_blob",
    "approval_record_exact_byte_sha256",
})
UNIVERSE_REFERENCE_KEYS = frozenset({
    "artifact",
    "artifact_digest",
    "eligibility_rule_digest",
    "required_rule_families",
    "operational_values_state",
})
SECURITY_MASTER_REFERENCE_KEYS = frozenset({
    "artifact",
    "artifact_digest",
    "snapshot",
    "manifest",
    "stable_security_id_column",
    "effective_from_column",
    "effective_to_column",
    "listing_type_column",
    "security_type_column",
    "primary_listing_column",
    "terminal_event_column",
    "survivorship_policy",
})
ARCHIVE_REFERENCE_KEYS = frozenset({
    "archive_kind", "archive_uri", "raw_archive_sha256", "byte_length"
})
FIELD_IDENTITY_KEYS = frozenset({
    "field_namespace", "field_id", "field_catalog_digest"
})
COLUMN_RECORD_KEYS = frozenset({
    "column_name",
    "logical_type",
    "nullable",
    "column_role",
    "field_identity",
    "unit_or_currency",
})
SOURCE_MANIFEST_KEYS = frozenset({
    "manifest_schema_version",
    "manifest_id",
    "archive_manifest_sha256",
    "row_count",
    "primary_key_columns",
    "columns",
    "canonical_row_order",
})
PROJECTION_KEYS = frozenset({
    "projection_schema_version",
    "raw_archive",
    "declared_projected_columns",
    "row_order_columns",
    "canonicalization_identity",
    "snapshot_id",
    "snapshot_sha256",
    "projected_byte_length",
})
COLUMN_REFERENCE_KEYS = frozenset({
    "security_id_column",
    "decision_timestamp_column",
    "availability_timestamp_column",
    "reporting_frequency_column",
    "period_type_column",
    "fiscal_year_column",
    "fiscal_quarter_column",
    "form_type_column",
    "accession_id_column",
    "version_id_column",
    "revision_id_column",
    "period_end_column",
    "effective_from_column",
    "effective_to_column",
    "source_native_vintage_column",
    "provenance_id_column",
})
SOURCE_RECORD_KEYS = frozenset({
    "source_id",
    "source_kind",
    "provenance_class",
    "source_native_vintage",
    "research_vintage_id",
    "projection",
    "manifest",
    "column_references",
})
ACCOUNTING_REFERENCE_KEYS = frozenset({
    "artifact",
    "accounting_semantics_digest",
    "field_taxonomy_digest",
    "unit_currency_policy_digest",
    "fiscal_period_policy_digest",
    "restatement_policy_digest",
    "alignment_policy_digest",
    "denominator_policy_digest",
    "missingness_policy_digest",
})
PROXY_REFERENCE_KEYS = frozenset({
    "artifact", "proxy_registry_digest", "proxy_count"
})
REQUIRED_DIMENSION_KEYS = frozenset({"ordered_dimensions", "valuation_required"})
RANKING_REFERENCE_KEYS = frozenset({
    "ranking_configuration_id",
    "ranking_configuration_digest",
    "artifact",
    "ranked_digest_scope",
    "selector_read_scope",
})
DECISION_DATE_SET_KEYS = frozenset({
    "dates", "decision_date_set_digest", "sample_boundary_authority"
})
RESEARCH_VINTAGE_KEYS = frozenset({
    "research_vintage_id", "as_of_utc", "source_native_vintages_digest"
})
CODE_IDENTITIES_KEYS = frozenset({"ordered_identities", "digest"})
CODE_IDENTITY_KEYS = frozenset({"role", "repository_id", "git_commit", "tree_dirty"})
ENVIRONMENT_IDENTITY_KEYS = frozenset({
    "environment_manifest_sha256",
    "lockfile_exact_byte_sha256",
    "runtime_name",
    "runtime_version",
    "platform",
})
OUTPUT_CONTRACT_KEYS = frozenset({
    "governed_ranking_artifact_schema_version",
    "ranked_content_digest_algorithm",
    "ranked_content_columns",
    "row_order_rule",
    "forbidden_field_classes",
})
UNRESOLVED_VALUE_KEYS = frozenset({"state", "decision_id"})
CANDIDATE_CONTRACT_KEYS = frozenset({
    "artifact_kind",
    "artifact_schema_status",
    "membership_rule",
    "cutoff_rule",
    "candidate_count_or_threshold",
    "required_binding_fields",
})
SCREEN_ATTESTATION_KEYS = frozenset({
    "no_realized_outcome_statement_version",
    "no_realized_outcome_statement",
    "no_live_substitution",
    "full_date_effective_survivorship",
    "no_vendor_selected_by_contract",
    "no_deferred_threshold_selected_by_contract",
})

REGENERATION_KEYS = frozenset({
    "screen_regeneration_schema_version",
    "screen_specification_id",
    "screen_specification_sha256",
    "universe_artifact_sha256",
    "security_master_artifact_sha256",
    "source_snapshot_references",
    "accounting_semantics_sha256",
    "proxy_registry_sha256",
    "ranking_configuration_sha256",
    "required_dimensions",
    "decision_date_set_digest",
    "code_identities",
    "environment_manifest_sha256",
    "canonicalization_identity",
    "ranked_artifact_sha256",
    "ranked_content_digest",
    "candidate_set_state",
    "candidate_set_artifact_sha256",
})
SNAPSHOT_REFERENCE_KEYS = frozenset({
    "source_kind",
    "source_id",
    "snapshot_id",
    "snapshot_sha256",
    "archive_manifest_sha256",
})

_SHA256 = re.compile(r"[0-9a-f]{64}")
_GIT_SHA1 = re.compile(r"[0-9a-f]{40}")
_CANONICAL_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}")


class ScreenGovernanceError(GovernanceError):
    """Closed-screen contract or preflight failure."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _exact(value: object, keys: frozenset[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path} must be an object")
    missing = sorted(keys - set(value))
    extra = sorted(set(value) - keys)
    if missing or extra:
        raise ScreenGovernanceError(
            "SCREEN_SCHEMA_INVALID",
            f"{path} has invalid keys; missing={missing}, extra={extra}",
        )
    return value


def _sha(value: object, path: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path} must be SHA-256")
    return value


def _commit(value: object, path: str) -> str:
    if not isinstance(value, str) or _GIT_SHA1.fullmatch(value) is None:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path} must be Git SHA-1")
    return value


def _path(value: object, path: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path} is invalid")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts or str(parsed) != value:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path} is invalid")
    return value


def _canonical_id(value: object, path: str) -> str:
    if not isinstance(value, str) or _CANONICAL_ID.fullmatch(value) is None:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path} is invalid")
    return value


def _artifact_reference(value: object, path: str) -> Mapping[str, Any]:
    item = _exact(value, ARTIFACT_REFERENCE_KEYS, path)
    if item["repository_id"] != REPOSITORY_ID:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.repository_id is invalid")
    _path(item["repository_relative_path"], f"{path}.repository_relative_path")
    _commit(item["source_commit"], f"{path}.source_commit")
    _commit(item["git_blob"], f"{path}.git_blob")
    _sha(item["exact_byte_sha256"], f"{path}.exact_byte_sha256")
    if not isinstance(item["schema_or_document_version"], str):
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.version is invalid")
    return item


def _archive_reference(value: object, path: str) -> Mapping[str, Any]:
    item = _exact(value, ARCHIVE_REFERENCE_KEYS, path)
    if item["archive_kind"] not in {"REPOSITORY_BLOB", "CONTENT_ADDRESSED_ARCHIVE"}:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.archive_kind is invalid")
    if not isinstance(item["archive_uri"], str) or not item["archive_uri"]:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.archive_uri is invalid")
    _sha(item["raw_archive_sha256"], f"{path}.raw_archive_sha256")
    if not isinstance(item["byte_length"], int) or isinstance(item["byte_length"], bool) or item["byte_length"] < 0:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.byte_length is invalid")
    return item


def _source_manifest(value: object, path: str) -> Mapping[str, Any]:
    item = _exact(value, SOURCE_MANIFEST_KEYS, path)
    if item["manifest_schema_version"] != 1:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.version is invalid")
    _canonical_id(item["manifest_id"], f"{path}.manifest_id")
    _sha(item["archive_manifest_sha256"], f"{path}.archive_manifest_sha256")
    if not isinstance(item["row_count"], int) or isinstance(item["row_count"], bool) or item["row_count"] < 0:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.row_count is invalid")
    columns = item["columns"]
    if not isinstance(columns, list) or not columns:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.columns is invalid")
    names: list[str] = []
    role_by_name: dict[str, str] = {}
    for index, raw in enumerate(columns):
        column = _exact(raw, COLUMN_RECORD_KEYS, f"{path}.columns[{index}]")
        name = _canonical_id(column["column_name"], f"{path}.columns[{index}].column_name")
        if name in role_by_name:
            raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path} has duplicate columns")
        if not isinstance(column["nullable"], bool):
            raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.nullable is invalid")
        value_roles = {
            "ACCOUNTING_VALUE": "ACCOUNTING",
            "MARKET_VALUE": "MARKET",
            "SECURITY_MASTER_VALUE": "SECURITY_MASTER",
            "CLASSIFICATION_VALUE": "CLASSIFICATION",
        }
        role = column["column_role"]
        if role in value_roles:
            field = _exact(column["field_identity"], FIELD_IDENTITY_KEYS, f"{path}.field_identity")
            if field["field_namespace"] != value_roles[role]:
                raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "field namespace/role mismatch")
            _canonical_id(field["field_id"], f"{path}.field_id")
            _sha(field["field_catalog_digest"], f"{path}.field_catalog_digest")
        elif column["field_identity"] is not None:
            raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "non-value column has field identity")
        names.append(name)
        role_by_name[name] = str(role)
    for key in ("primary_key_columns", "canonical_row_order"):
        values = item[key]
        if not isinstance(values, list) or not values or len(values) != len(set(values)) or any(name not in role_by_name for name in values):
            raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.{key} is invalid")
    return {**item, "_column_names": names, "_role_by_name": role_by_name}


def _source_record(value: object, path: str) -> Mapping[str, Any]:
    item = _exact(value, SOURCE_RECORD_KEYS, path)
    _canonical_id(item["source_id"], f"{path}.source_id")
    if item["source_kind"] not in {
        "PIT_ACCOUNTING_FACTS",
        "HISTORICAL_MARKET_FACTS",
        "HISTORICAL_SECURITY_MASTER_FACTS",
        "HISTORICAL_CLASSIFICATION_FACTS",
    }:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.source_kind is invalid")
    if item["provenance_class"] not in {"VENDOR_ARCHIVE", "PUBLIC_ARCHIVE", "INTERNAL_ARCHIVE"}:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.provenance_class is invalid")
    manifest = _source_manifest(item["manifest"], f"{path}.manifest")
    projection = _exact(item["projection"], PROJECTION_KEYS, f"{path}.projection")
    if projection["projection_schema_version"] != 1 or projection["canonicalization_identity"] != CANONICALIZATION:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.projection is invalid")
    _archive_reference(projection["raw_archive"], f"{path}.projection.raw_archive")
    _canonical_id(projection["snapshot_id"], f"{path}.projection.snapshot_id")
    _sha(projection["snapshot_sha256"], f"{path}.projection.snapshot_sha256")
    if projection["declared_projected_columns"] != manifest["_column_names"] or projection["row_order_columns"] != manifest["canonical_row_order"]:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.projection columns are invalid")
    refs = _exact(item["column_references"], COLUMN_REFERENCE_KEYS, f"{path}.column_references")
    role_by_name = manifest["_role_by_name"]
    reference_roles = {
        "security_id_column": "SECURITY_ID",
        "decision_timestamp_column": "DECISION_TIMESTAMP",
        "availability_timestamp_column": "AVAILABILITY_TIMESTAMP",
        "reporting_frequency_column": "REPORTING_FREQUENCY",
        "period_type_column": "PERIOD_TYPE",
        "fiscal_year_column": "FISCAL_YEAR",
        "fiscal_quarter_column": "FISCAL_QUARTER",
        "form_type_column": "FORM_TYPE",
        "accession_id_column": "ACCESSION_ID",
        "version_id_column": "VERSION_ID",
        "revision_id_column": "REVISION_ID",
        "period_end_column": "PERIOD_END",
        "effective_from_column": "EFFECTIVE_FROM",
        "effective_to_column": "EFFECTIVE_TO",
        "source_native_vintage_column": "SOURCE_NATIVE_VINTAGE",
        "provenance_id_column": "PROVENANCE_ID",
    }
    for name, expected_role in reference_roles.items():
        referenced = refs[name]
        if referenced is not None and role_by_name.get(referenced) != expected_role:
            raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", f"{path}.{name} role mismatch")
    return item


def validate_frozen_screen_specification(payload: object) -> Mapping[str, Any]:
    """Validate the exact closed Screen Specification v1 representation."""

    screen = _exact(payload, SCREEN_TOP_LEVEL_KEYS, "FrozenScreenSpecification")
    if screen["screen_specification_schema_version"] != 1 or screen["canonicalization_version"] != CANONICALIZATION:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "screen version/canonicalization is invalid")
    _sha(screen["screen_specification_id"], "screen_specification_id")
    entry000 = _exact(screen["entry000_reference"], ENTRY000_REFERENCE_KEYS, "entry000_reference")
    if entry000["entry_000_package_schema_version"] != 2:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "Entry000 reference version is invalid")
    _sha(entry000["package_id"], "entry000_reference.package_id")
    _sha(entry000["full_artifact_sha256"], "entry000_reference.full_artifact_sha256")
    _path(entry000["publication_path"], "entry000_reference.publication_path")
    _artifact_reference(screen["governing_architecture_reference"], "governing_architecture_reference")

    universe = _exact(screen["universe_reference"], UNIVERSE_REFERENCE_KEYS, "universe_reference")
    _artifact_reference(universe["artifact"], "universe_reference.artifact")
    _sha(universe["artifact_digest"], "universe_reference.artifact_digest")
    _sha(universe["eligibility_rule_digest"], "universe_reference.eligibility_rule_digest")
    if universe["required_rule_families"] != ["SIZE", "PRICE", "LIQUIDITY", "SEASONING"] or universe["operational_values_state"] != UNRESOLVED_STATE:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "universe rule state is invalid")

    security = _exact(screen["security_master_reference"], SECURITY_MASTER_REFERENCE_KEYS, "security_master_reference")
    _artifact_reference(security["artifact"], "security_master_reference.artifact")
    _sha(security["artifact_digest"], "security_master_reference.artifact_digest")
    _archive_reference(security["snapshot"], "security_master_reference.snapshot")
    _source_manifest(security["manifest"], "security_master_reference.manifest")
    if security["survivorship_policy"] != "FULL_DATE_EFFECTIVE":
        raise ScreenGovernanceError("CURRENT_SURVIVOR_ONLY_INADMISSIBLE")

    sources = screen["pit_fact_sources"]
    if not isinstance(sources, list) or not sources:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "pit_fact_sources must be non-empty")
    source_ids: set[str] = set()
    snapshots: dict[str, Mapping[str, Any]] = {}
    for index, source in enumerate(sources):
        parsed = _source_record(source, f"pit_fact_sources[{index}]")
        if parsed["source_id"] in source_ids:
            raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "duplicate source_id")
        source_ids.add(str(parsed["source_id"]))
        snapshot_id = str(parsed["projection"]["snapshot_id"])
        prior = snapshots.get(snapshot_id)
        if prior is not None and prior != parsed:
            raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "conflicting snapshot_id")
        snapshots[snapshot_id] = parsed

    accounting = _exact(screen["accounting_reference"], ACCOUNTING_REFERENCE_KEYS, "accounting_reference")
    _artifact_reference(accounting["artifact"], "accounting_reference.artifact")
    for name in ACCOUNTING_REFERENCE_KEYS - {"artifact"}:
        _sha(accounting[name], f"accounting_reference.{name}")
    proxy = _exact(screen["proxy_registry_reference"], PROXY_REFERENCE_KEYS, "proxy_registry_reference")
    _artifact_reference(proxy["artifact"], "proxy_registry_reference.artifact")
    _sha(proxy["proxy_registry_digest"], "proxy_registry_reference.proxy_registry_digest")
    if not isinstance(proxy["proxy_count"], int) or isinstance(proxy["proxy_count"], bool) or proxy["proxy_count"] <= 0:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "proxy_count is invalid")
    dimensions = _exact(screen["required_dimensions"], REQUIRED_DIMENSION_KEYS, "required_dimensions")
    if dimensions != {"ordered_dimensions": list(REQUIRED_DIMENSIONS), "valuation_required": True}:
        raise ScreenGovernanceError("VALUATION_ESSENTIAL_UNAVAILABLE", "required dimensions were altered")
    ranking = _exact(screen["ranking_reference"], RANKING_REFERENCE_KEYS, "ranking_reference")
    _sha(ranking["ranking_configuration_digest"], "ranking_reference.digest")
    _artifact_reference(ranking["artifact"], "ranking_reference.artifact")
    if tuple(ranking["ranked_digest_scope"]) != RANKED_FRAME_DIGEST_SCOPE or tuple(ranking["selector_read_scope"]) != RANKED_FRAME_DIGEST_SCOPE:
        raise ScreenGovernanceError("RANKING_DIGEST_SCOPE_ALTERED")

    dates = _exact(screen["decision_date_set"], DECISION_DATE_SET_KEYS, "decision_date_set")
    if not isinstance(dates["dates"], list) or dates["dates"] != sorted(set(dates["dates"])) or dates["sample_boundary_authority"] != "RESEARCHER_APPROVED":
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "decision-date set is invalid")
    if hashlib.sha256(canonical_json(dates["dates"])).hexdigest() != dates["decision_date_set_digest"]:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "decision-date digest mismatch")
    vintage = _exact(screen["research_vintage"], RESEARCH_VINTAGE_KEYS, "research_vintage")
    _sha(vintage["source_native_vintages_digest"], "research_vintage.digest")

    code = _exact(screen["code_identities"], CODE_IDENTITIES_KEYS, "code_identities")
    identities = code["ordered_identities"]
    if not isinstance(identities, list) or [item.get("role") for item in identities] != ["UNIVERSE", "SECURITY_MASTER", "FEATURE", "ACCOUNTING", "RANKING"]:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "code identity roles are invalid")
    for index, raw in enumerate(identities):
        identity = _exact(raw, CODE_IDENTITY_KEYS, f"code_identities[{index}]")
        if identity["repository_id"] != REPOSITORY_ID or identity["tree_dirty"] is not False:
            raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "code identity is invalid")
        _commit(identity["git_commit"], f"code_identities[{index}].git_commit")
    _sha(code["digest"], "code_identities.digest")
    environment = _exact(screen["environment_identity"], ENVIRONMENT_IDENTITY_KEYS, "environment_identity")
    _sha(environment["environment_manifest_sha256"], "environment_identity.manifest")
    _sha(environment["lockfile_exact_byte_sha256"], "environment_identity.lockfile")

    output = _exact(screen["output_contract"], OUTPUT_CONTRACT_KEYS, "output_contract")
    if output["ranked_content_digest_algorithm"] != "RUN2_RANKED_CONTENT_V1" or tuple(output["ranked_content_columns"]) != RANKED_FRAME_DIGEST_SCOPE:
        raise ScreenGovernanceError("RANKING_DIGEST_SCOPE_ALTERED")
    if output["forbidden_field_classes"] != ["HELD_RETURN", "FORWARD_RETURN", "BENCHMARK_RETURN", "REALIZED_LABEL", "REALIZED_DIAGNOSTIC"]:
        raise ScreenGovernanceError("OUTCOME_FIELD_BOUNDARY_ALTERED")
    candidate = _exact(screen["candidate_contract"], CANDIDATE_CONTRACT_KEYS, "candidate_contract")
    if candidate["artifact_kind"] != CANDIDATE_ARTIFACT_KIND or candidate["artifact_schema_status"] != CANDIDATE_SCHEMA_STATUS:
        raise ScreenGovernanceError("CANDIDATE_CONTRACT_ALTERED")
    for name in ("membership_rule", "cutoff_rule", "candidate_count_or_threshold"):
        unresolved = _exact(candidate[name], UNRESOLVED_VALUE_KEYS, f"candidate_contract.{name}")
        if unresolved["state"] != UNRESOLVED_STATE or not isinstance(unresolved["decision_id"], str) or not unresolved["decision_id"]:
            raise ScreenGovernanceError("CANDIDATE_RULE_UNRESOLVED")
    if tuple(candidate["required_binding_fields"]) != CANDIDATE_REQUIRED_BINDINGS:
        raise ScreenGovernanceError("CANDIDATE_CONTRACT_ALTERED")
    approvals = screen["approval_references"]
    if not isinstance(approvals, list) or not approvals:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "approval_references must be non-empty")
    seen_approvals: set[tuple[object, ...]] = set()
    for index, raw in enumerate(approvals):
        approval = _exact(raw, APPROVAL_REFERENCE_KEYS, f"approval_references[{index}]")
        if approval["repository_id"] != REPOSITORY_ID:
            raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "approval repository is invalid")
        _path(approval["approval_record_path"], "approval path")
        _commit(approval["approval_record_commit"], "approval commit")
        _commit(approval["approval_record_git_blob"], "approval blob")
        _sha(approval["approval_record_exact_byte_sha256"], "approval sha256")
        key = tuple(approval[name] for name in sorted(APPROVAL_REFERENCE_KEYS))
        if key in seen_approvals:
            raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "duplicate approval reference")
        seen_approvals.add(key)
    attestations = _exact(screen["attestations"], SCREEN_ATTESTATION_KEYS, "attestations")
    expected_attestations = {
        "no_realized_outcome_statement_version": 1,
        "no_realized_outcome_statement": "No realized strategy outcome was used in constructing this screen.",
        "no_live_substitution": True,
        "full_date_effective_survivorship": True,
        "no_vendor_selected_by_contract": True,
        "no_deferred_threshold_selected_by_contract": True,
    }
    if dict(attestations) != expected_attestations:
        raise ScreenGovernanceError("SCREEN_SCHEMA_INVALID", "screen attestations are invalid")
    semantic = {key: value for key, value in screen.items() if key != "screen_specification_id"}
    if screen["screen_specification_id"] != hashlib.sha256(canonical_json(semantic)).hexdigest():
        raise ScreenGovernanceError("SCREEN_IDENTITY_MISMATCH")
    return MappingProxyType(dict(screen))


@dataclass(frozen=True)
class ProviderCapabilities:
    """Audited capability assertions; no provider name or default is selected."""

    fundamental_data_mode: str
    fundamental_availability_timestamps: bool
    fundamental_revision_history: bool
    fundamental_fiscal_metadata: bool
    immutable_fundamental_history: bool
    security_master_mode: str
    historical_market_data_mode: str
    historical_price: bool
    historical_volume: bool
    historical_market_cap_or_components: bool
    historical_shares: bool
    historical_enterprise_value_inputs: bool
    corporate_actions: bool
    market_sessions: bool
    market_timezones: bool
    market_timing_policy_approved: bool

    def __post_init__(self) -> None:
        if self.fundamental_data_mode not in {"PIT_ARCHIVE", "CURRENT_OR_LIVE", "UNAVAILABLE"}:
            raise ValueError("fundamental_data_mode is invalid")
        if self.security_master_mode not in {"FULL_DATE_EFFECTIVE", "CURRENT_SURVIVORS_ONLY", "UNAVAILABLE"}:
            raise ValueError("security_master_mode is invalid")
        if self.historical_market_data_mode not in {"HISTORICAL_ARCHIVE", "CURRENT_OR_LIVE", "UNAVAILABLE"}:
            raise ValueError("historical_market_data_mode is invalid")
        for name in self.__dataclass_fields__:
            if name.endswith("_mode"):
                continue
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")


@dataclass(frozen=True)
class UniversePolicy:
    inclusion: tuple[str, ...] = (
        "PRIMARY_LISTED",
        "COMMON_EQUITY",
        "OPERATING_COMPANY",
    )
    exclusions: tuple[str, ...] = (
        "ADR",
        "SECONDARY_LISTING",
        "PREFERRED",
        "ETF",
        "FUND",
    )
    survivorship_policy: str = "FULL_DATE_EFFECTIVE"
    operational_values_state: str = UNRESOLVED_STATE
    required_rule_families: tuple[str, ...] = (
        "SIZE",
        "PRICE",
        "LIQUIDITY",
        "SEASONING",
    )

    def __post_init__(self) -> None:
        if self.inclusion != ("PRIMARY_LISTED", "COMMON_EQUITY", "OPERATING_COMPANY"):
            raise ValueError("universe inclusion intent cannot be altered")
        if self.exclusions != ("ADR", "SECONDARY_LISTING", "PREFERRED", "ETF", "FUND"):
            raise ValueError("universe exclusions cannot be altered")
        if self.survivorship_policy != "FULL_DATE_EFFECTIVE":
            raise ValueError("current-survivor-only universe is inadmissible")
        if self.operational_values_state != UNRESOLVED_STATE:
            raise ValueError("universe thresholds must remain unresolved")
        if self.required_rule_families != ("SIZE", "PRICE", "LIQUIDITY", "SEASONING"):
            raise ValueError("all four universe rule families are required")


@dataclass(frozen=True)
class ScreenPreflightReport:
    diagnostic_codes: tuple[str, ...]
    stage_status: Mapping[str, str]
    candidate_set_state: str
    outcome_budget_effect: str
    outcome_register_events: int
    realized_outcomes_read: bool
    proxy_order: tuple[str, ...]
    required_dimensions: tuple[str, ...]

    @property
    def governed_screen_executable(self) -> bool:
        return not self.diagnostic_codes

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "diagnostic_codes": list(self.diagnostic_codes),
            "stage_status": dict(self.stage_status),
            "candidate_set_state": self.candidate_set_state,
            "outcome_budget_effect": self.outcome_budget_effect,
            "outcome_register_events": self.outcome_register_events,
            "realized_outcomes_read": self.realized_outcomes_read,
            "proxy_order": list(self.proxy_order),
            "required_dimensions": list(self.required_dimensions),
            "governed_screen_executable": self.governed_screen_executable,
        }


def run_outcome_free_screen_preflight(
    *,
    provider_capabilities: ProviderCapabilities,
    universe_policy: UniversePolicy,
    accounting_fixture_prepared: bool,
) -> ScreenPreflightReport:
    """Return deterministic blockers without reading outcomes or opening a run."""

    if not isinstance(provider_capabilities, ProviderCapabilities):
        raise TypeError("ProviderCapabilities is required")
    if not isinstance(universe_policy, UniversePolicy):
        raise TypeError("UniversePolicy is required")
    if not isinstance(accounting_fixture_prepared, bool):
        raise TypeError("accounting_fixture_prepared must be boolean")
    diagnostics: set[str] = {
        "UNIVERSE_SIZE_FLOOR_UNRESOLVED",
        "UNIVERSE_PRICE_FLOOR_UNRESOLVED",
        "UNIVERSE_LIQUIDITY_FLOOR_UNRESOLVED",
        "LISTING_SEASONING_UNRESOLVED",
        "CANDIDATE_MEMBERSHIP_RULE_UNRESOLVED",
        "CANDIDATE_CUTOFF_RULE_UNRESOLVED",
        "CANDIDATE_COUNT_OR_THRESHOLD_UNRESOLVED",
        "PROXY_REGISTRY_UNRESOLVED",
    }
    fundamental_flags = (
        provider_capabilities.fundamental_availability_timestamps,
        provider_capabilities.fundamental_revision_history,
        provider_capabilities.fundamental_fiscal_metadata,
        provider_capabilities.immutable_fundamental_history,
    )
    if provider_capabilities.fundamental_data_mode != "PIT_ARCHIVE" or not all(fundamental_flags):
        diagnostics.add("PIT_FUNDAMENTAL_PROVIDER_CAPABILITY_UNVERIFIED")
    if provider_capabilities.fundamental_data_mode == "CURRENT_OR_LIVE":
        diagnostics.add("CURRENT_LIVE_FUNDAMENTALS_HISTORICALLY_INADMISSIBLE")
    if provider_capabilities.security_master_mode != "FULL_DATE_EFFECTIVE":
        diagnostics.add("SURVIVORSHIP_COMPLETE_SECURITY_MASTER_UNAVAILABLE")
    if provider_capabilities.security_master_mode == "CURRENT_SURVIVORS_ONLY":
        diagnostics.add("CURRENT_SURVIVOR_ONLY_UNIVERSE_INADMISSIBLE")
    market_flags = (
        provider_capabilities.historical_price,
        provider_capabilities.historical_volume,
        provider_capabilities.historical_market_cap_or_components,
        provider_capabilities.historical_shares,
        provider_capabilities.historical_enterprise_value_inputs,
        provider_capabilities.corporate_actions,
        provider_capabilities.market_sessions,
        provider_capabilities.market_timezones,
    )
    if provider_capabilities.historical_market_data_mode != "HISTORICAL_ARCHIVE" or not all(market_flags):
        diagnostics.add("HISTORICAL_MARKET_PROVIDER_CAPABILITY_UNVERIFIED")
    if provider_capabilities.historical_market_data_mode == "CURRENT_OR_LIVE":
        diagnostics.add("CURRENT_LIVE_MARKET_DATA_HISTORICALLY_INADMISSIBLE")
    if not provider_capabilities.market_timing_policy_approved:
        diagnostics.add("HISTORICAL_MARKET_TIMING_UNRESOLVED")
    if (
        "HISTORICAL_MARKET_PROVIDER_CAPABILITY_UNVERIFIED" in diagnostics
        or "HISTORICAL_MARKET_TIMING_UNRESOLVED" in diagnostics
        or "CURRENT_LIVE_MARKET_DATA_HISTORICALLY_INADMISSIBLE" in diagnostics
    ):
        diagnostics.add("VALUATION_ESSENTIAL_UNAVAILABLE")
    stages = {
        "universe": "BLOCKED_BY_UNRESOLVED_RESEARCH_DECISION",
        "pit_fundamentals": (
            "EXECUTABLE_WITH_FIXTURES_ONLY"
            if accounting_fixture_prepared
            else "BLOCKED_BY_DATA_PROVIDER_CAPABILITY"
        ),
        "accounting_preparation": (
            "EXECUTABLE_WITH_FIXTURES_ONLY"
            if accounting_fixture_prepared
            else "BLOCKED_BY_DATA_PROVIDER_CAPABILITY"
        ),
        "business_economics": (
            "EXECUTABLE_WITH_FIXTURES_ONLY"
            if accounting_fixture_prepared
            else "BLOCKED_BY_DATA_PROVIDER_CAPABILITY"
        ),
        "fundamental_change": (
            "EXECUTABLE_WITH_FIXTURES_ONLY"
            if accounting_fixture_prepared
            else "BLOCKED_BY_DATA_PROVIDER_CAPABILITY"
        ),
        "valuation": (
            "BLOCKED_BY_HISTORICAL_TIMING"
            if "HISTORICAL_MARKET_TIMING_UNRESOLVED" in diagnostics
            else (
                "BLOCKED_BY_DATA_PROVIDER_CAPABILITY"
                if "HISTORICAL_MARKET_PROVIDER_CAPABILITY_UNVERIFIED" in diagnostics
                else "BLOCKED_BY_UNRESOLVED_RESEARCH_DECISION"
            )
        ),
        "ranking": "BLOCKED_BY_UNRESOLVED_RESEARCH_DECISION",
        "candidate_set": "BLOCKED_BY_UNRESOLVED_RESEARCH_DECISION",
        "deep_research_handoff": "BLOCKED_BY_UNRESOLVED_RESEARCH_DECISION",
    }
    return ScreenPreflightReport(
        diagnostic_codes=tuple(sorted(diagnostics)),
        stage_status=MappingProxyType(stages),
        candidate_set_state="not_produced",
        outcome_budget_effect="none_no_slot_no_open_close",
        outcome_register_events=0,
        realized_outcomes_read=False,
        proxy_order=REQUIRED_PROXY_ORDER,
        required_dimensions=REQUIRED_DIMENSIONS,
    )


def deterministic_outcome_free_dry_run() -> Mapping[str, Any]:
    """Exercise the strongest fixture-only path without outcome-bearing input."""

    capabilities = ProviderCapabilities(
        fundamental_data_mode="UNAVAILABLE",
        fundamental_availability_timestamps=False,
        fundamental_revision_history=False,
        fundamental_fiscal_metadata=False,
        immutable_fundamental_history=False,
        security_master_mode="UNAVAILABLE",
        historical_market_data_mode="UNAVAILABLE",
        historical_price=False,
        historical_volume=False,
        historical_market_cap_or_components=False,
        historical_shares=False,
        historical_enterprise_value_inputs=False,
        corporate_actions=False,
        market_sessions=False,
        market_timezones=False,
        market_timing_policy_approved=False,
    )
    return run_outcome_free_screen_preflight(
        provider_capabilities=capabilities,
        universe_policy=UniversePolicy(),
        accounting_fixture_prepared=True,
    ).to_dict()


def validate_screen_regeneration_record(record: object) -> Mapping[str, Any]:
    value = _exact(record, REGENERATION_KEYS, "ScreenRegenerationIdentityV1")
    if value["screen_regeneration_schema_version"] != 1:
        raise ScreenGovernanceError("SCREEN_REGENERATION_SCHEMA_INVALID")
    for name in (
        "screen_specification_id",
        "screen_specification_sha256",
        "universe_artifact_sha256",
        "security_master_artifact_sha256",
        "accounting_semantics_sha256",
        "proxy_registry_sha256",
        "ranking_configuration_sha256",
        "decision_date_set_digest",
        "environment_manifest_sha256",
        "ranked_artifact_sha256",
        "ranked_content_digest",
    ):
        _sha(value[name], name)
    if value["required_dimensions"] != list(REGENERATION_DIMENSIONS):
        raise ScreenGovernanceError("SCREEN_REGENERATION_DIMENSIONS_INVALID")
    if value["canonicalization_identity"] != CANONICALIZATION:
        raise ScreenGovernanceError("SCREEN_REGENERATION_CANONICALIZATION_INVALID")
    code = _exact(value["code_identities"], CODE_IDENTITIES_KEYS, "code_identities")
    _sha(code["digest"], "code_identities.digest")
    snapshots = value["source_snapshot_references"]
    if not isinstance(snapshots, list):
        raise ScreenGovernanceError("SCREEN_REGENERATION_SNAPSHOTS_INVALID")
    keys: list[tuple[str, str, str]] = []
    for index, raw in enumerate(snapshots):
        snapshot = _exact(raw, SNAPSHOT_REFERENCE_KEYS, f"source_snapshot_references[{index}]")
        key = (str(snapshot["source_kind"]), str(snapshot["source_id"]), str(snapshot["snapshot_id"]))
        keys.append(key)
        _sha(snapshot["snapshot_sha256"], "snapshot_sha256")
        _sha(snapshot["archive_manifest_sha256"], "archive_manifest_sha256")
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise ScreenGovernanceError("SCREEN_REGENERATION_SNAPSHOTS_INVALID")
    state = value["candidate_set_state"]
    candidate_sha = value["candidate_set_artifact_sha256"]
    if state == "not_produced":
        if candidate_sha is not None:
            raise ScreenGovernanceError("CANDIDATE_STATE_DIGEST_MISMATCH")
    elif state == "produced":
        _sha(candidate_sha, "candidate_set_artifact_sha256")
    else:
        raise ScreenGovernanceError("CANDIDATE_STATE_INVALID")
    digest = hashlib.sha256(canonical_json(value)).hexdigest()
    if digest == value["ranked_content_digest"] or (
        candidate_sha is not None and digest == candidate_sha
    ):
        raise ScreenGovernanceError("SCREEN_REGENERATION_IDENTITY_COLLISION")
    return MappingProxyType(dict(value))


def screen_regeneration_identity(record: object) -> str:
    value = validate_screen_regeneration_record(record)
    return "screen-regeneration-v1:" + hashlib.sha256(
        canonical_json(dict(value))
    ).hexdigest()
