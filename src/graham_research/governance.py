"""Frozen artifacts, environment manifests, and append-only specification logs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tomllib
from typing import Any, Mapping
import warnings as python_warnings

from .domain import (
    DenominatorDefinition,
    DenominatorPolicy,
    FiscalYearObservationSelection,
    PeriodRole,
    ProxyDefinition,
    ReportingFrequency,
    RestatementPolicy,
    RoleKind,
    SameOffsetAlignment,
    UNRESOLVED,
)
from .timing import (
    ECONOMIC_RETURN_DESCRIPTOR_FIELDS,
    ResolvedPortfolioTiming,
    TIMING_KEYS,
    TimingError,
)


ENTRY_001_REQUIRED_KEYS = frozenset({
    "entry_001_schema_version",
    "architecture_version",
    "data_audit",
    "investable_universe",
    "sample_boundaries",
    "proxy_registry",
    "pit_conventions",
    "missing_data_policy",
    "required_dimensions",
    "sector_history_convention",
    "estimates_decision",
    "research_provenance",
    "primary_signal_metric",
    "primary_portfolio_metric",
    "statistical_decision_procedure",
    "multiplicity_procedure",
    "transaction_cost_model",
    "specification_budget",
    "specification_counting_rules",
    "construct_kill_conditions",
    "system_kill_condition",
    "rule_17",
    "portfolio_timing",
    "portfolio_construction",
    "terminal_position_policy",
    "data_vintage_identifier",
    "robustness_alternatives",
    "environment_manifest",
    "source_control",
})

ENTRY_001_NON_EMPTY_COLLECTIONS = frozenset({
    "proxy_registry",
    "research_provenance",
    "environment_manifest",
    "source_control",
})
_ENTRY_001_WRAPPER_KEYS = frozenset({"entry", "created_at"})

_ENVIRONMENT_MANIFEST_TEMPLATE = {
    "status": "REPLACE_WITH_OUTPUT_FROM_GRAHAM_RESEARCH_MANIFEST",
}
_SOURCE_CONTROL_TEMPLATE = {
    "status": "REPLACE_WITH_OUTPUT_FROM_GRAHAM_RESEARCH_MANIFEST_REPOSITORY",
}
_ENVIRONMENT_MANIFEST_REQUIRED_FIELDS = frozenset({
    "schema_version",
    "python",
    "implementation",
    "platform",
    "packages",
    "pinned_dependencies",
    "dependency_match",
    "mismatches",
})
_SOURCE_CONTROL_KEYS = frozenset({"vcs", "commit", "dirty"})
_TRANSACTION_COST_MODEL_KEYS = frozenset({
    "convention",
    "one_way_cost_bps",
})
_PIT_CONVENTION_KEYS = frozenset({
    "restatement_policy",
    "availability_timestamp",
})
_SAMPLE_BOUNDARY_KEYS = frozenset({
    "development",
    "holdout_a",
    "holdout_b",
    "partition_overlap_policy",
    "partition_gap_policy",
    "shared_boundary_assignment_rule",
})
_SAMPLE_PARTITION_KEYS = frozenset({
    "start",
    "end",
    "start_boundary_rule",
    "end_boundary_rule",
})
_PORTFOLIO_CONSTRUCTION_KEYS = frozenset({
    "selection_rule",
    "number_of_positions",
    "sizing_rule",
    "insufficient_eligible_policy",
    "unfilled_capacity_policy",
})
SPECIFICATION_COUNTING_RULES = {
    "research_specification": "reserve_one_slot_at_open",
    "diagnostic": "no_research_slot",
    "data_correction": "no_research_slot_requires_invalidated_specification",
    "blocked_pre_open": "no_research_slot",
    "post_open_failure": (
        "retain_reservation_no_release_mechanism_pending_researcher_resolution"
    ),
}
_AVAILABILITY_TIMESTAMP_CONVENTION = (
    "actual public filing or announcement timestamp"
)

PROJECT_DISTRIBUTION = "graham-systematic-research"


def _pins_from_requirements(requirements: list[str]) -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in requirements:
        requirement, _, marker = raw.partition(";")
        if marker and "extra ==" in marker:
            continue
        match = re.fullmatch(
            r"\s*([A-Za-z0-9_.-]+)==([^\s]+)\s*",
            requirement,
        )
        if match is None:
            raise RuntimeError(
                f"research dependency is not exactly pinned: {raw}"
            )
        pins[match.group(1).lower().replace("_", "-")] = match.group(2)
    if not pins:
        raise RuntimeError("no pinned research dependencies were found")
    return pins


def _normalized_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _pins_from_pyproject_candidate(path: Path) -> dict[str, str] | None:
    """Accept a nearby pyproject only when it identifies this distribution."""

    if not path.is_file():
        return None
    project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
    name = project.get("name")
    if (
        not isinstance(name, str)
        or _normalized_distribution_name(name)
        != _normalized_distribution_name(PROJECT_DISTRIBUTION)
    ):
        return None
    return _pins_from_requirements(list(project.get("dependencies", ())))


def _load_project_dependency_pins() -> dict[str, str]:
    """Use trusted metadata/source pins and reject editable-install staleness."""

    try:
        requirements = importlib.metadata.requires(PROJECT_DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError:
        requirements = None
    metadata_pins = (
        _pins_from_requirements(requirements)
        if requirements is not None
        else None
    )
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    source_pins = _pins_from_pyproject_candidate(pyproject)
    if (
        metadata_pins is not None
        and source_pins is not None
        and metadata_pins != source_pins
    ):
        raise RuntimeError(
            "installed package metadata disagrees with the matching source "
            "pyproject.toml; reinstall the editable package before freezing"
        )
    if metadata_pins is not None:
        return metadata_pins
    if source_pins is not None:
        return source_pins
    raise RuntimeError(
        f"neither trusted package metadata nor a matching pyproject.toml "
        f"was found for {PROJECT_DISTRIBUTION}"
    )


def project_dependency_pins() -> dict[str, str]:
    """Resolve current project pins only for manifest/freeze operations."""

    return dict(_load_project_dependency_pins())


class GovernanceError(RuntimeError):
    pass


class Entry001SchemaError(GovernanceError):
    """Base class for schema failures, distinct from artifact corruption."""


class MissingEntry001SchemaVersion(Entry001SchemaError):
    pass


class UnsupportedEntry001SchemaVersion(Entry001SchemaError):
    pass


class MalformedEntry001V2(Entry001SchemaError):
    pass


class UnresolvedEntry001(GovernanceError):
    pass


@dataclass(frozen=True)
class RuntimeValidationResult:
    """Runtime attestation with vetoes separated from incidental drift."""

    warnings: tuple[str, ...]
    recorded: Mapping[str, Any]
    installed: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "matched_with_warnings" if self.warnings else "matched",
            "warnings": list(self.warnings),
            "recorded": dict(self.recorded),
            "installed": dict(self.installed),
            "blocking_policy": {
                "packages": "exact",
                "implementation": "exact",
                "python_major_minor": "exact",
            },
            "warning_policy": ["python_patch", "platform"],
        }


_RESOLVED_ENTRY_TOKEN = object()


@dataclass(frozen=True, init=False)
class ResolvedEntry001:
    """Verified Entry 001 execution inputs.

    Instances are issued only by :func:`load_resolved_entry_001`; callers
    cannot turn an unresolved mapping into governed execution metadata.
    """

    proxy_registry: tuple[ProxyDefinition, ...]
    proxy_registry_digest: str
    entry_001_sha256: str
    missing_data_policy: Mapping[str, Any]
    required_dimensions: tuple[str, ...]
    restatement_policy: RestatementPolicy
    portfolio_timing: ResolvedPortfolioTiming
    sample_boundaries: Mapping[str, Any]
    portfolio_construction: Mapping[str, Any]
    terminal_position_policy: str
    data_vintage_identifier: str
    specification_budget: int
    transaction_cost_model: Mapping[str, Any]
    specification_counting_rules: Mapping[str, Any]

    def __init__(
        self,
        proxy_registry: tuple[ProxyDefinition, ...],
        proxy_registry_digest_value: str,
        entry_001_sha256: str,
        missing_data_policy: Mapping[str, Any],
        required_dimensions: tuple[str, ...],
        restatement_policy: RestatementPolicy,
        portfolio_timing: ResolvedPortfolioTiming,
        sample_boundaries: Mapping[str, Any],
        portfolio_construction: Mapping[str, Any],
        terminal_position_policy: str,
        data_vintage_identifier: str,
        specification_budget: int,
        transaction_cost_model: Mapping[str, Any],
        specification_counting_rules: Mapping[str, Any],
        *,
        _token: object,
    ) -> None:
        if _token is not _RESOLVED_ENTRY_TOKEN:
            raise TypeError("ResolvedEntry001 must be loaded from a frozen Entry 001")
        object.__setattr__(self, "proxy_registry", proxy_registry)
        object.__setattr__(self, "proxy_registry_digest", proxy_registry_digest_value)
        object.__setattr__(self, "entry_001_sha256", entry_001_sha256)
        object.__setattr__(self, "missing_data_policy", dict(missing_data_policy))
        object.__setattr__(self, "required_dimensions", required_dimensions)
        object.__setattr__(
            self,
            "restatement_policy",
            RestatementPolicy(restatement_policy),
        )
        object.__setattr__(self, "portfolio_timing", portfolio_timing)
        object.__setattr__(self, "sample_boundaries", dict(sample_boundaries))
        object.__setattr__(
            self, "portfolio_construction", dict(portfolio_construction)
        )
        object.__setattr__(
            self, "terminal_position_policy", terminal_position_policy
        )
        object.__setattr__(
            self, "data_vintage_identifier", data_vintage_identifier
        )
        object.__setattr__(self, "specification_budget", specification_budget)
        object.__setattr__(
            self, "transaction_cost_model", dict(transaction_cost_model)
        )
        object.__setattr__(
            self,
            "specification_counting_rules",
            dict(specification_counting_rules),
        )


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        default=_json_default,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def freeze_artifact(path: str | Path, payload: Mapping[str, Any]) -> str:
    """Write canonical JSON and a companion digest, refusing overwrite."""

    target = Path(path)
    digest_path = target.with_suffix(target.suffix + ".sha256")
    if target.exists() or digest_path.exists():
        raise GovernanceError(f"frozen artifact already exists: {target}")
    content = canonical_json(payload) + b"\n"
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()
    _atomic_write(target, content)
    try:
        _atomic_write(digest_path, f"{digest}  {target.name}\n".encode("ascii"))
    except Exception:
        # The artifact itself remains verifiable; surface the failed freeze so
        # the caller can quarantine this incomplete package.
        raise GovernanceError(f"digest file could not be written for {target}")
    return digest


def verify_artifact(path: str | Path) -> str:
    target = Path(path)
    digest_path = target.with_suffix(target.suffix + ".sha256")
    if not target.exists() or not digest_path.exists():
        raise GovernanceError(f"artifact or digest is missing: {target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    actual = sha256_payload(payload)
    expected = digest_path.read_text(encoding="ascii").split()[0]
    if actual != expected:
        raise GovernanceError(f"artifact hash mismatch: {target}")
    if payload.get("entry") == "001":
        _validate_entry_001(payload, validate_against_project_pins=False)
    return actual


def freeze_entry_000(path: str | Path, architecture_text: str) -> str:
    payload = {
        "entry": "000",
        "architecture_version": "3.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "architecture_sha256": hashlib.sha256(architecture_text.encode("utf-8")).hexdigest(),
        "architecture_text": architecture_text,
        "statement": "No strategy-return results were examined in designing Architecture v3.1.",
        "unresolved_operational_items": [
            "data-audit findings",
            "exact investable-universe values",
            "proxy-registry formulas selected for the cycle",
            "estimate-data admissibility",
            "sample boundaries",
            "numeric specification budget",
            "transaction costs",
            "rebalance frequency and holding period",
            "audit-dependent statistical implementation details",
        ],
    }
    return freeze_artifact(path, payload)


ENTRY_001_SCHEMA_VERSION = 2

PROXY_REQUIRED_KEYS = frozenset({
    "name",
    "construct",
    "formula",
    "source_fields",
    "expected_direction",
    "availability_lag",
    "transformation",
    "sector_treatment",
    "missing_data_treatment",
    "accounting_weaknesses",
    "rationale",
    "required_reporting_frequency",
    "frequency_governed_source_fields",
    "frequency_exempt_source_fields",
    "required_period_structure",
    "denominator_definitions",
    "same_offset_alignment_rule",
    "fiscal_year_observation_selection_rule",
})
GROSS_PROFITABILITY_EXTRA_KEYS = frozenset({"prior_gross_profit_dependency"})
ACCOUNTING_ROLE_KEYS = frozenset({
    "role_name", "source_field", "role_kind", "period_type", "fiscal_year_offset"
})
MARKET_ROLE_KEYS = frozenset({
    "role_name", "source_field", "role_kind", "period_type", "alignment_rule"
})
DENOMINATOR_KEYS = frozenset({
    "denominator_id", "contributing_roles", "transformation", "denominator_policy"
})
DENOMINATOR_POLICY_KEYS = frozenset({
    "missing", "zero", "negative", "near_zero", "near_zero_absolute_threshold"
})

# These describe calculators already present in the software.  They are not a
# resolved production registry: the shipped template leaves their research
# semantics unresolved and no Entry 001 can freeze until a researcher supplies
# and approves them.
SUPPORTED_PROXY_SHAPES: dict[str, dict[str, tuple[str, ...]]] = {
    "fcf_ev": {
        "source_fields": ("operating_cash_flow", "capital_expenditures", "enterprise_value"),
        "roles": ("operating_cash_flow", "capital_expenditures", "enterprise_value"),
        "denominators": ("enterprise_value",),
    },
    "ebit_ev": {
        "source_fields": ("operating_income", "enterprise_value"),
        "roles": ("operating_income", "enterprise_value"),
        "denominators": ("enterprise_value",),
    },
    "gross_profitability": {
        "source_fields": ("gross_profit", "total_assets"),
        "roles": ("current_gross_profit", "current_total_assets", "prior_total_assets"),
        "denominators": ("average_total_assets",),
    },
    "roic": {
        "source_fields": ("operating_income", "income_tax_expense", "income_before_tax", "invested_capital"),
        "roles": (
            "current_operating_income", "current_income_tax_expense",
            "current_income_before_tax", "current_invested_capital",
            "prior_invested_capital",
        ),
        "denominators": (
            "income_before_tax_for_effective_tax_rate", "average_invested_capital"
        ),
    },
    "operating_margin_change": {
        "source_fields": ("operating_income", "revenue"),
        "roles": (
            "current_operating_income", "current_revenue",
            "prior_operating_income", "prior_revenue",
        ),
        "denominators": ("current_revenue", "prior_revenue"),
    },
    "fcf_margin_change": {
        "source_fields": ("operating_cash_flow", "capital_expenditures", "revenue"),
        "roles": (
            "current_operating_cash_flow", "current_capital_expenditures", "current_revenue",
            "prior_operating_cash_flow", "prior_capital_expenditures", "prior_revenue",
        ),
        "denominators": ("current_revenue", "prior_revenue"),
    },
    "revenue_acceleration": {
        "source_fields": ("revenue",),
        "roles": ("current_revenue", "prior_revenue", "two_year_prior_revenue"),
        "denominators": (
            "prior_revenue_for_current_growth", "two_year_prior_revenue_for_prior_growth"
        ),
    },
}

SUPPORTED_PROXY_FORMULAS = {
    "fcf_ev": "(operating_cash_flow - abs(capital_expenditures)) / enterprise_value",
    "ebit_ev": "operating_income / enterprise_value",
    "gross_profitability": "gross_profit / average(current_total_assets, prior_total_assets)",
    "roic": "operating_income * (1 - income_tax_expense / income_before_tax) / average(current_invested_capital, prior_invested_capital)",
    "operating_margin_change": "current(operating_income / revenue) - prior(operating_income / revenue)",
    "fcf_margin_change": "current(fcf / revenue) - prior(fcf / revenue)",
    "revenue_acceleration": "current_yoy_revenue_growth - prior_yoy_revenue_growth",
}

SUPPORTED_PROXY_EXECUTION_LITERALS = {
    "availability_lag": "source-specific public availability timestamp",
    "transformation": "cross_sectional_percentile_rank",
    "sector_treatment": "none",
    "missing_data_treatment": "exclude_feature_for_security",
}


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], path: str) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        raise MalformedEntry001V2(
            f"{path} has invalid keys; missing={missing}, extra={extra}"
        )


def _validate_entry_001_version(payload: Mapping[str, Any]) -> None:
    if "entry_001_schema_version" not in payload:
        raise MissingEntry001SchemaVersion("Entry 001 schema version is missing")
    version = payload["entry_001_schema_version"]
    if version != ENTRY_001_SCHEMA_VERSION:
        raise UnsupportedEntry001SchemaVersion(
            f"unsupported Entry 001 schema version: {version!r}; only v2 is supported"
        )


def _validate_proxy_registry_structure(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise MalformedEntry001V2("proxy_registry must be a non-empty list")
    names: set[str] = set()
    for index, proxy in enumerate(value):
        path = f"proxy_registry[{index}]"
        if not isinstance(proxy, Mapping):
            raise MalformedEntry001V2(f"{path} must be an object")
        name = proxy.get("name")
        if not isinstance(name, str) or name not in SUPPORTED_PROXY_SHAPES:
            raise MalformedEntry001V2(f"{path}.name is unsupported: {name!r}")
        expected_keys = (
            PROXY_REQUIRED_KEYS | GROSS_PROFITABILITY_EXTRA_KEYS
            if name == "gross_profitability"
            else PROXY_REQUIRED_KEYS
        )
        _require_exact_keys(proxy, expected_keys, path)
        if name in names:
            raise MalformedEntry001V2(f"duplicate proxy name: {name}")
        names.add(name)
        for field_name, supported_literal in SUPPORTED_PROXY_EXECUTION_LITERALS.items():
            if (
                proxy[field_name] != UNRESOLVED
                and proxy[field_name] != supported_literal
            ):
                raise MalformedEntry001V2(
                    f"{path}.{field_name} is not supported by Run 1 execution"
                )
        expected = SUPPORTED_PROXY_SHAPES[name]
        formula = proxy["formula"]
        if formula != UNRESOLVED and formula != SUPPORTED_PROXY_FORMULAS[name]:
            raise MalformedEntry001V2(
                f"{path}.formula is not implemented by the supported calculator"
            )
        source_fields = proxy["source_fields"]
        if not isinstance(source_fields, list) or tuple(source_fields) != expected["source_fields"]:
            raise MalformedEntry001V2(
                f"{path}.source_fields do not match the supported calculator"
            )
        for partition_name in (
            "frequency_governed_source_fields", "frequency_exempt_source_fields"
        ):
            if not isinstance(proxy[partition_name], list):
                raise MalformedEntry001V2(f"{path}.{partition_name} must be a list")
        governed_items = proxy["frequency_governed_source_fields"]
        exempt_items = proxy["frequency_exempt_source_fields"]
        concrete_partitions: dict[str, list[str]] = {}
        for partition_name, partition_items in (
            ("frequency_governed_source_fields", governed_items),
            ("frequency_exempt_source_fields", exempt_items),
        ):
            concrete = [item for item in partition_items if item != UNRESOLVED]
            undeclared = [item for item in concrete if item not in source_fields]
            if undeclared:
                raise MalformedEntry001V2(
                    f"{path}.{partition_name} has undeclared source fields: {undeclared}"
                )
            if len(concrete) != len(set(concrete)):
                raise MalformedEntry001V2(
                    f"{path}.{partition_name} has duplicate concrete source fields"
                )
            concrete_partitions[partition_name] = concrete
        governed = set(concrete_partitions["frequency_governed_source_fields"])
        exempt = set(concrete_partitions["frequency_exempt_source_fields"])
        if governed & exempt:
            raise MalformedEntry001V2(
                f"{path} frequency partition has concrete governed/exempt overlap"
            )
        has_unresolved = UNRESOLVED in governed_items or UNRESOLVED in exempt_items
        if not has_unresolved and governed | exempt != set(source_fields):
            raise MalformedEntry001V2(
                f"{path} frequency partition must be exhaustive and non-overlapping"
            )
        roles = proxy["required_period_structure"]
        if not isinstance(roles, list) or not roles:
            raise MalformedEntry001V2(f"{path}.required_period_structure must be non-empty")
        role_names: list[str] = []
        accounting_pairs: set[tuple[str, int]] = set()
        for role_index, role in enumerate(roles):
            role_path = f"{path}.required_period_structure[{role_index}]"
            if not isinstance(role, Mapping):
                raise MalformedEntry001V2(f"{role_path} must be an object")
            role_kind = role.get("role_kind")
            if role_kind == RoleKind.ACCOUNTING.value:
                _require_exact_keys(role, ACCOUNTING_ROLE_KEYS, role_path)
                offset = role["fiscal_year_offset"]
                if offset != UNRESOLVED and (
                    not isinstance(offset, int) or isinstance(offset, bool) or offset > 0
                ):
                    raise MalformedEntry001V2(
                        f"{role_path}.fiscal_year_offset must be a non-positive integer"
                    )
                if offset != UNRESOLVED:
                    pair = (str(role["source_field"]), offset)
                    if pair in accounting_pairs:
                        raise MalformedEntry001V2(f"duplicate accounting role pair at {role_path}")
                    accounting_pairs.add(pair)
            elif role_kind == RoleKind.MARKET.value:
                _require_exact_keys(role, MARKET_ROLE_KEYS, role_path)
                if role["alignment_rule"] != UNRESOLVED:
                    raise MalformedEntry001V2(
                        f"{role_path}.alignment_rule supports only UNRESOLVED in Run 1"
                    )
            else:
                raise MalformedEntry001V2(f"{role_path}.role_kind is invalid")
            if role["source_field"] not in source_fields:
                raise MalformedEntry001V2(f"{role_path}.source_field is undeclared")
            role_names.append(str(role["role_name"]))
        if len(set(role_names)) != len(role_names):
            raise MalformedEntry001V2(f"{path} has duplicate role names")
        expected_roles = expected["roles"]
        if name == "gross_profitability":
            dependency = proxy["prior_gross_profit_dependency"]
            if dependency not in {
                UNRESOLVED,
                "require_prior_gross_profit",
                "do_not_require_prior_gross_profit",
            }:
                raise MalformedEntry001V2(
                    f"{path}.prior_gross_profit_dependency is invalid"
                )
            with_prior = (
                "current_gross_profit",
                "prior_gross_profit",
                "current_total_assets",
                "prior_total_assets",
            )
            if dependency == "require_prior_gross_profit":
                expected_roles = with_prior
            elif dependency == UNRESOLVED and tuple(role_names) == with_prior:
                expected_roles = with_prior
        if tuple(role_names) != expected_roles:
            raise MalformedEntry001V2(
                f"{path} roles do not match the supported calculator"
            )
        if {role["source_field"] for role in roles} != set(source_fields):
            raise MalformedEntry001V2(f"{path} roles must cover every source field")
        denominators = proxy["denominator_definitions"]
        if not isinstance(denominators, list):
            raise MalformedEntry001V2(f"{path}.denominator_definitions must be a list")
        denominator_ids: list[str] = []
        for denominator_index, denominator in enumerate(denominators):
            denominator_path = f"{path}.denominator_definitions[{denominator_index}]"
            if not isinstance(denominator, Mapping):
                raise MalformedEntry001V2(f"{denominator_path} must be an object")
            _require_exact_keys(denominator, DENOMINATOR_KEYS, denominator_path)
            contributors = denominator["contributing_roles"]
            if not isinstance(contributors, list) or not contributors:
                raise MalformedEntry001V2(
                    f"{denominator_path}.contributing_roles must be non-empty"
                )
            unknown_roles = set(contributors) - set(role_names)
            if unknown_roles:
                raise MalformedEntry001V2(
                    f"{denominator_path} has undeclared roles: {sorted(unknown_roles)}"
                )
            policy = denominator["denominator_policy"]
            if not isinstance(policy, Mapping):
                raise MalformedEntry001V2(f"{denominator_path}.denominator_policy must be an object")
            _require_exact_keys(policy, DENOMINATOR_POLICY_KEYS, f"{denominator_path}.denominator_policy")
            supported_actions = {
                UNRESOLVED,
                "exclude_feature",
                "allow_value",
            }
            for action_name in ("missing", "zero", "negative", "near_zero"):
                if policy[action_name] not in supported_actions:
                    raise MalformedEntry001V2(
                        f"{denominator_path}.denominator_policy.{action_name} "
                        "is unsupported"
                    )
            for action_name in ("missing", "zero"):
                if policy[action_name] not in {UNRESOLVED, "exclude_feature"}:
                    raise MalformedEntry001V2(
                        f"{denominator_path}.denominator_policy.{action_name} "
                        "supports only exclude_feature"
                    )
            denominator_ids.append(str(denominator["denominator_id"]))
        if tuple(denominator_ids) != expected["denominators"]:
            raise MalformedEntry001V2(
                f"{path} denominators do not match the supported calculator"
            )


def _parse_proxy_registry(value: Any) -> tuple[ProxyDefinition, ...]:
    """Convert a structurally validated, fully resolved v2 registry."""

    definitions: list[ProxyDefinition] = []
    for proxy in value:
        roles = tuple(
            PeriodRole(
                role_name=role["role_name"],
                source_field=role["source_field"],
                role_kind=role["role_kind"],
                period_type=role["period_type"],
                fiscal_year_offset=role.get("fiscal_year_offset"),
                alignment_rule=role.get("alignment_rule"),
            )
            for role in proxy["required_period_structure"]
        )
        denominators = tuple(
            DenominatorDefinition(
                denominator_id=item["denominator_id"],
                contributing_roles=tuple(item["contributing_roles"]),
                transformation=item["transformation"],
                denominator_policy=DenominatorPolicy(**item["denominator_policy"]),
            )
            for item in proxy["denominator_definitions"]
        )
        definitions.append(ProxyDefinition(
            name=proxy["name"],
            construct=proxy["construct"],
            formula=proxy["formula"],
            source_fields=tuple(proxy["source_fields"]),
            expected_direction=proxy["expected_direction"],
            availability_lag=proxy["availability_lag"],
            transformation=proxy["transformation"],
            sector_treatment=proxy["sector_treatment"],
            missing_data_treatment=proxy["missing_data_treatment"],
            accounting_weaknesses=tuple(proxy["accounting_weaknesses"]),
            rationale=proxy["rationale"],
            required_reporting_frequency=proxy["required_reporting_frequency"],
            frequency_governed_source_fields=tuple(proxy["frequency_governed_source_fields"]),
            frequency_exempt_source_fields=tuple(proxy["frequency_exempt_source_fields"]),
            required_period_structure=roles,
            denominator_definitions=denominators,
            same_offset_alignment_rule=proxy["same_offset_alignment_rule"],
            fiscal_year_observation_selection_rule=proxy["fiscal_year_observation_selection_rule"],
            prior_gross_profit_dependency=proxy.get("prior_gross_profit_dependency"),
        ))
    return tuple(definitions)


def proxy_registry_digest(registry: tuple[ProxyDefinition, ...]) -> str:
    ordered = tuple(sorted(registry, key=lambda item: item.name))
    return sha256_payload(ordered)


def freeze_entry_001(
    path: str | Path,
    payload: Mapping[str, Any],
    *,
    repository: str | Path,
) -> str:
    _validate_entry_001(
        payload,
        validate_against_project_pins=True,
        validate_source_control_attestation=False,
        allow_artifact_wrapper=False,
    )
    actual_source_control = source_control_manifest(repository)
    if actual_source_control.get("dirty") is not False:
        raise GovernanceError(
            "Entry 001 requires the explicitly attested repository to be clean"
        )
    _validate_source_control(actual_source_control)
    attestation_keys = ("vcs", "commit", "dirty")
    payload_attestation = {
        key: payload["source_control"].get(key) for key in attestation_keys
    }
    actual_attestation = {
        key: actual_source_control.get(key) for key in attestation_keys
    }
    if payload_attestation != actual_attestation:
        mismatches = {
            key: {
                "payload": payload_attestation[key],
                "actual": actual_attestation[key],
            }
            for key in attestation_keys
            if payload_attestation[key] != actual_attestation[key]
        }
        raise GovernanceError(
            "Entry 001 source_control does not match the actual repository "
            f"manifest: {mismatches}"
        )
    runtime = _validate_runtime_against_manifest(payload["environment_manifest"])
    for message in runtime.warnings:
        python_warnings.warn(message, RuntimeWarning, stacklevel=2)
    wrapped = {
        **dict(payload),
        "entry": "001",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return freeze_artifact(path, wrapped)


def _validate_portfolio_timing_structure(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise MalformedEntry001V2("portfolio_timing must be an object")
    _require_exact_keys(value, TIMING_KEYS, "portfolio_timing")
    closed_fields = {
        "calendar_basis": {UNRESOLVED, "calendar_days", "calendar_months"},
        "rebalance_date_convention": {
            UNRESOLVED,
            "calendar_month_end",
            "calendar_quarter_end",
            "fixed_n_calendar_days",
        },
        "month_end_convention": {
            UNRESOLVED,
            "civil_calendar_month_end",
            "not_applicable",
        },
        "anchor_semantics": {
            UNRESOLVED,
            "first_valid_date",
            "cadence_epoch",
            "not_applicable",
        },
        "holding_period_rule": {
            UNRESOLVED,
            "rebalance_interval",
            "fixed_calendar_days",
            "fixed_calendar_months",
        },
        "return_interval_start_rule": {UNRESOLVED, "decision_date"},
        "return_interval_end_rule": {
            UNRESOLVED,
            "next_scheduled_decision_date",
            "fixed_calendar_days_after_decision",
            "fixed_calendar_months_after_decision",
        },
        "return_start_endpoint_inclusion": {UNRESOLVED, "included", "excluded"},
        "return_end_endpoint_inclusion": {UNRESOLVED, "included", "excluded"},
    }
    for name, supported in closed_fields.items():
        if not isinstance(value[name], str) or value[name] not in supported:
            raise MalformedEntry001V2(
                f"portfolio_timing.{name} is unsupported"
            )
    for name in ECONOMIC_RETURN_DESCRIPTOR_FIELDS:
        item = value[name]
        if item != UNRESOLVED and (
            not isinstance(item, str) or not item.strip()
        ):
            raise MalformedEntry001V2(
                f"portfolio_timing.{name} must be a non-empty descriptor"
            )
    for name in ("rebalance_interval_count", "holding_period_interval_count"):
        item = value[name]
        if item != UNRESOLVED and item != "not_applicable" and (
            not isinstance(item, int) or isinstance(item, bool) or item <= 0
        ):
            raise MalformedEntry001V2(
                f"portfolio_timing.{name} must be a positive integer"
            )
    equals = value["holding_period_equals_rebalance_interval"]
    if equals != UNRESOLVED and not isinstance(equals, bool):
        raise MalformedEntry001V2(
            "holding_period_equals_rebalance_interval must be boolean"
        )
    anchor = value["schedule_anchor_date"]
    if anchor != UNRESOLVED and anchor != "not_applicable":
        try:
            date.fromisoformat(str(anchor))
        except (TypeError, ValueError) as exc:
            raise MalformedEntry001V2(
                "schedule_anchor_date must be an ISO date"
            ) from exc
    market_timezone = value["market_timezone"]
    if market_timezone != UNRESOLVED and (
        not isinstance(market_timezone, str) or not market_timezone.strip()
    ):
        raise MalformedEntry001V2(
            "portfolio_timing.market_timezone must be a non-empty IANA zone"
        )
    if _find_unresolved(value):
        return
    try:
        ResolvedPortfolioTiming.from_mapping(value)
    except TimingError as exc:
        raise MalformedEntry001V2(str(exc)) from exc


def _validate_sample_boundaries_structure(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise MalformedEntry001V2("sample_boundaries must be an object")
    _require_exact_keys(value, _SAMPLE_BOUNDARY_KEYS, "sample_boundaries")
    for name in ("development", "holdout_a", "holdout_b"):
        partition = value[name]
        if not isinstance(partition, Mapping):
            raise MalformedEntry001V2(f"sample_boundaries.{name} must be an object")
        _require_exact_keys(
            partition,
            _SAMPLE_PARTITION_KEYS,
            f"sample_boundaries.{name}",
        )
        for boundary_name in ("start_boundary_rule", "end_boundary_rule"):
            rule = partition[boundary_name]
            if rule not in {UNRESOLVED, "included", "excluded"}:
                raise MalformedEntry001V2(
                    f"sample_boundaries.{name}.{boundary_name} is unsupported"
                )
        for endpoint in ("start", "end"):
            raw = partition[endpoint]
            if raw != UNRESOLVED:
                try:
                    date.fromisoformat(str(raw))
                except (TypeError, ValueError) as exc:
                    raise MalformedEntry001V2(
                        f"sample_boundaries.{name}.{endpoint} must be an ISO date"
                    ) from exc
    policies = {
        "partition_overlap_policy": {UNRESOLVED, "forbid", "allow"},
        "partition_gap_policy": {UNRESOLVED, "forbid", "allow"},
        "shared_boundary_assignment_rule": {
            UNRESOLVED,
            "earlier_partition",
            "later_partition",
            "both",
            "not_applicable",
        },
    }
    for name, supported in policies.items():
        if value[name] not in supported:
            raise MalformedEntry001V2(f"sample_boundaries.{name} is unsupported")


def _validate_resolved_sample_boundaries(value: Mapping[str, Any]) -> None:
    intervals: list[tuple[str, date, date, bool, bool]] = []
    for name in ("development", "holdout_a", "holdout_b"):
        partition = value[name]
        start = date.fromisoformat(partition["start"])
        end = date.fromisoformat(partition["end"])
        if end < start:
            raise MalformedEntry001V2(f"sample_boundaries.{name} ends before start")
        intervals.append((
            name,
            start,
            end,
            partition["start_boundary_rule"] == "included",
            partition["end_boundary_rule"] == "included",
        ))
    for prior, current in zip(intervals, intervals[1:]):
        _, _prior_start, prior_end, _prior_start_in, prior_end_in = prior
        _, current_start, _current_end, current_start_in, _current_end_in = current
        prior_last = prior_end if prior_end_in else prior_end - timedelta(days=1)
        current_first = (
            current_start if current_start_in else current_start + timedelta(days=1)
        )
        overlaps = current_first <= prior_last
        has_gap = current_first > prior_last + timedelta(days=1)
        if overlaps and value["partition_overlap_policy"] == "forbid":
            raise MalformedEntry001V2("sample partitions overlap under forbidden policy")
        if has_gap and value["partition_gap_policy"] == "forbid":
            raise MalformedEntry001V2("sample partitions contain a forbidden gap")
    shared = value["shared_boundary_assignment_rule"]
    if value["partition_overlap_policy"] == "allow" and shared == "not_applicable":
        raise MalformedEntry001V2(
            "allowed overlap requires a shared-boundary assignment rule"
        )


def _validate_portfolio_construction_structure(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise MalformedEntry001V2("portfolio_construction must be an object")
    _require_exact_keys(
        value,
        _PORTFOLIO_CONSTRUCTION_KEYS,
        "portfolio_construction",
    )
    if value["selection_rule"] not in {UNRESOLVED, "top_n"}:
        raise MalformedEntry001V2("portfolio selection_rule supports only top_n")
    if value["sizing_rule"] not in {UNRESOLVED, "equal_weight"}:
        raise MalformedEntry001V2("portfolio sizing_rule supports only equal_weight")
    count = value["number_of_positions"]
    if count != UNRESOLVED and (
        not isinstance(count, int) or isinstance(count, bool) or count <= 0
    ):
        raise MalformedEntry001V2("number_of_positions must be positive")
    if value["insufficient_eligible_policy"] not in {
        UNRESOLVED,
        "fail",
        "skip_rebalance_date",
        "hold_available_names",
    }:
        raise MalformedEntry001V2("insufficient_eligible_policy is unsupported")
    if value["unfilled_capacity_policy"] not in {
        UNRESOLVED,
        "redistribute_to_available_names",
        "hold_cash",
        "not_applicable",
    }:
        raise MalformedEntry001V2("unfilled_capacity_policy is unsupported")


def _validate_resolved_portfolio_construction(value: Mapping[str, Any]) -> None:
    if value["selection_rule"] != "top_n":
        raise MalformedEntry001V2("governed selection_rule must be top_n")
    if value["sizing_rule"] != "equal_weight":
        raise MalformedEntry001V2("governed sizing_rule must be equal_weight")
    count = value["number_of_positions"]
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise MalformedEntry001V2("number_of_positions must be positive")
    policy = value["insufficient_eligible_policy"]
    unfilled = value["unfilled_capacity_policy"]
    if policy == "hold_available_names":
        if unfilled == "hold_cash":
            raise MalformedEntry001V2(
                "hold_cash is unsupported without governed cash returns"
            )
        if unfilled != "redistribute_to_available_names":
            raise MalformedEntry001V2(
                "hold_available_names requires redistribute_to_available_names"
            )
    elif unfilled != "not_applicable":
        raise MalformedEntry001V2(
            "unfilled_capacity_policy must be not_applicable for this policy"
        )


def _validate_entry_001(
    payload: Mapping[str, Any],
    *,
    validate_against_project_pins: bool,
    validate_source_control_attestation: bool = True,
    allow_artifact_wrapper: bool = True,
) -> None:
    if not isinstance(payload, Mapping):
        raise MalformedEntry001V2("Entry 001 must be an object")
    _validate_entry_001_version(payload)
    payload_keys = set(payload)
    wrapper_keys_present = payload_keys & _ENTRY_001_WRAPPER_KEYS
    expected_keys = ENTRY_001_REQUIRED_KEYS
    if wrapper_keys_present and allow_artifact_wrapper:
        expected_keys = ENTRY_001_REQUIRED_KEYS | _ENTRY_001_WRAPPER_KEYS
    missing = sorted(expected_keys - payload_keys)
    extra = sorted(payload_keys - expected_keys)
    if missing or extra:
        raise MalformedEntry001V2(
            "Entry 001 has invalid top-level keys; "
            f"missing={missing}, extra={extra}"
        )
    if wrapper_keys_present and allow_artifact_wrapper and payload["entry"] != "001":
        raise MalformedEntry001V2("frozen Entry 001 marker must be '001'")
    _validate_proxy_registry_structure(payload["proxy_registry"])
    _validate_portfolio_timing_structure(payload["portfolio_timing"])
    _validate_sample_boundaries_structure(payload["sample_boundaries"])
    _validate_portfolio_construction_structure(payload["portfolio_construction"])
    if payload["terminal_position_policy"] not in {
        UNRESOLVED,
        "fail_on_any_terminal_event",
    }:
        raise MalformedEntry001V2(
            "terminal_position_policy is not executable end to end"
        )
    vintage = payload["data_vintage_identifier"]
    if vintage != UNRESOLVED and (
        not isinstance(vintage, str) or not vintage.strip()
    ):
        raise MalformedEntry001V2(
            "data_vintage_identifier must be a non-empty research bundle ID"
        )
    budget = payload["specification_budget"]
    if budget != UNRESOLVED and (
        not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0
    ):
        raise GovernanceError("specification_budget must be a positive integer")
    required_dimensions = payload["required_dimensions"]
    if (
        not isinstance(required_dimensions, list)
        or not required_dimensions
        or any(not isinstance(item, str) or not item.strip() for item in required_dimensions)
        or len(set(required_dimensions)) != len(required_dimensions)
    ):
        raise MalformedEntry001V2(
            "required_dimensions must be a non-empty unique string list"
        )
    missing_policy = payload["missing_data_policy"]
    if not isinstance(missing_policy, Mapping):
        raise MalformedEntry001V2("missing_data_policy must be an object")
    _require_exact_keys(
        missing_policy,
        frozenset({"policy", "minimum_feature_coverage", "minimum_features_per_dimension"}),
        "missing_data_policy",
    )
    _validate_pit_conventions(payload["pit_conventions"])
    _validate_environment_manifest_structure(payload["environment_manifest"])
    _validate_source_control_section_structure(payload["source_control"])
    _validate_transaction_cost_model_structure(payload["transaction_cost_model"])
    counting = payload["specification_counting_rules"]
    if not isinstance(counting, Mapping) or dict(counting) != SPECIFICATION_COUNTING_RULES:
        raise MalformedEntry001V2(
            "specification_counting_rules must match the Run 2 OPEN reservation invariants"
        )
    unresolved = _find_unresolved(payload)
    if unresolved:
        raise UnresolvedEntry001(
            "Entry 001 contains unresolved placeholders: "
            + ", ".join(unresolved[:20])
        )
    try:
        ResolvedPortfolioTiming.from_mapping(payload["portfolio_timing"])
    except TimingError as exc:
        raise MalformedEntry001V2(str(exc)) from exc
    _validate_resolved_sample_boundaries(payload["sample_boundaries"])
    _validate_resolved_portfolio_construction(payload["portfolio_construction"])
    if payload["terminal_position_policy"] != "fail_on_any_terminal_event":
        raise MalformedEntry001V2("terminal policy is unsupported")
    if (
        not isinstance(payload["data_vintage_identifier"], str)
        or not payload["data_vintage_identifier"].strip()
    ):
        raise MalformedEntry001V2(
            "data_vintage_identifier must be a non-empty research bundle ID"
        )
    empty = sorted(
        key
        for key in ENTRY_001_NON_EMPTY_COLLECTIONS
        if not isinstance(payload.get(key), (Mapping, list, tuple))
        or len(payload[key]) == 0
    )
    if empty:
        raise GovernanceError(
            f"Entry 001 required artifacts cannot be empty: {empty}"
        )
    budget = payload["specification_budget"]
    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
        raise GovernanceError("specification_budget must be a positive integer")
    policy_name = missing_policy["policy"]
    if policy_name not in {"exclude", "median", "worst"}:
        raise MalformedEntry001V2("missing_data_policy.policy is invalid")
    minimum_coverage = missing_policy["minimum_feature_coverage"]
    if (
        not isinstance(minimum_coverage, (int, float))
        or isinstance(minimum_coverage, bool)
        or not 0 <= float(minimum_coverage) <= 1
    ):
        raise MalformedEntry001V2(
            "minimum_feature_coverage must be between 0 and 1"
        )
    minimum_per_dimension = missing_policy["minimum_features_per_dimension"]
    if (
        not isinstance(minimum_per_dimension, int)
        or isinstance(minimum_per_dimension, bool)
        or minimum_per_dimension < 1
    ):
        raise MalformedEntry001V2(
            "minimum_features_per_dimension must be a positive integer"
        )
    try:
        definitions = _parse_proxy_registry(payload["proxy_registry"])
    except (TypeError, ValueError) as exc:
        raise MalformedEntry001V2(f"invalid resolved proxy registry: {exc}") from exc
    constructs = {item.construct for item in definitions}
    unknown_dimensions = set(required_dimensions) - constructs
    if unknown_dimensions:
        raise MalformedEntry001V2(
            f"required_dimensions missing from proxy registry: {sorted(unknown_dimensions)}"
        )
    if any(item.sector_treatment != "none" for item in definitions):
        raise MalformedEntry001V2("Run 1 supports only sector_treatment='none'")
    _validate_environment_manifest(
        payload["environment_manifest"],
        expected_project_pins=(
            project_dependency_pins() if validate_against_project_pins else None
        ),
    )
    if validate_source_control_attestation:
        _validate_source_control(payload["source_control"])
    else:
        _validate_source_control_shape(payload["source_control"])
    _validate_transaction_cost_model(payload["transaction_cost_model"])


def _validate_pit_conventions(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise MalformedEntry001V2("pit_conventions must be an object")
    _require_exact_keys(value, _PIT_CONVENTION_KEYS, "pit_conventions")
    if value["restatement_policy"] != RestatementPolicy.FIRST_REPORTED.value:
        raise MalformedEntry001V2(
            "pit_conventions.restatement_policy supports only first_reported"
        )
    if value["availability_timestamp"] != _AVAILABILITY_TIMESTAMP_CONVENTION:
        raise MalformedEntry001V2(
            "pit_conventions.availability_timestamp does not match the "
            "supported public-timestamp convention"
        )


def _validate_environment_manifest_structure(value: Any) -> bool:
    """Validate manifest shape, returning True only for the shipped placeholder."""

    if not isinstance(value, Mapping):
        raise GovernanceError("environment_manifest must be an object")
    if dict(value) == _ENVIRONMENT_MANIFEST_TEMPLATE:
        return True
    missing = sorted(_ENVIRONMENT_MANIFEST_REQUIRED_FIELDS - set(value))
    if missing:
        raise GovernanceError(
            f"environment_manifest is missing required fields: {missing}"
        )
    extra = sorted(set(value) - _ENVIRONMENT_MANIFEST_REQUIRED_FIELDS)
    if extra:
        raise GovernanceError(
            f"environment_manifest has unknown fields: {extra}"
        )
    packages = value["packages"]
    pinned = value["pinned_dependencies"]
    if not isinstance(packages, Mapping) or not isinstance(pinned, Mapping):
        raise GovernanceError(
            "environment_manifest packages and pinned_dependencies must be objects"
        )
    for field in ("python", "implementation", "platform"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise GovernanceError(
                f"environment_manifest.{field} must be a non-empty string"
            )
    if not isinstance(value["schema_version"], int) or isinstance(
        value["schema_version"], bool
    ):
        raise GovernanceError("environment_manifest.schema_version must be an integer")
    if not isinstance(value["dependency_match"], bool):
        raise GovernanceError("environment_manifest.dependency_match must be boolean")
    if not isinstance(value["mismatches"], Mapping):
        raise GovernanceError("environment_manifest.mismatches must be an object")
    if not pinned:
        raise GovernanceError("environment_manifest pinned_dependencies is empty")
    malformed_pins = sorted(
        str(name)
        for name, version in pinned.items()
        if not isinstance(name, str)
        or not name.strip()
        or not isinstance(version, str)
        or not version.strip()
    )
    if malformed_pins:
        raise GovernanceError(
            "environment_manifest pinned_dependencies has malformed entries: "
            f"{malformed_pins}"
        )
    missing_versions = sorted(
        name for name in pinned
        if not isinstance(packages.get(name), str) or not packages[name].strip()
    )
    if missing_versions:
        raise GovernanceError(
            f"environment_manifest has missing package versions: {missing_versions}"
        )
    return False


def _validate_environment_manifest(
    value: Any,
    *,
    expected_project_pins: Mapping[str, str] | None,
) -> None:
    if _validate_environment_manifest_structure(value):
        raise UnresolvedEntry001("environment_manifest is unresolved")
    packages = value["packages"]
    pinned = value["pinned_dependencies"]
    if (
        expected_project_pins is not None
        and dict(pinned) != dict(expected_project_pins)
    ):
        raise GovernanceError(
            "environment_manifest pinned_dependencies do not match pyproject pins"
        )
    mismatches = {
        name: {"expected": expected, "actual": packages.get(name)}
        for name, expected in pinned.items()
        if packages.get(name) != expected
    }
    if mismatches or value.get("dependency_match") is not True or value.get("mismatches"):
        raise GovernanceError(
            f"environment does not match pinned dependencies: {mismatches or value.get('mismatches')}"
        )


def _validate_source_control_shape(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise GovernanceError("source_control must be an object")
    vcs = value.get("vcs")
    commit = value.get("commit")
    if not isinstance(vcs, str) or not vcs.strip():
        raise GovernanceError("source_control.vcs must be a non-empty string")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", commit) is None:
        raise GovernanceError("source_control.commit must be a full Git commit hash")
    if not isinstance(value.get("dirty"), bool):
        raise GovernanceError("source_control.dirty must be boolean")


def _validate_source_control_section_structure(value: Any) -> bool:
    """Validate source-control shape, returning True for the exact template."""

    if not isinstance(value, Mapping):
        raise GovernanceError("source_control must be an object")
    if dict(value) == _SOURCE_CONTROL_TEMPLATE:
        return True
    missing = sorted(_SOURCE_CONTROL_KEYS - set(value))
    extra = sorted(set(value) - _SOURCE_CONTROL_KEYS)
    if missing or extra:
        raise GovernanceError(
            "source_control has invalid keys; "
            f"missing={missing}, extra={extra}"
        )
    _validate_source_control_shape(value)
    return False


def _validate_source_control(value: Any) -> None:
    _validate_source_control_shape(value)
    if value.get("vcs") != "git":
        raise GovernanceError("source_control.vcs must be 'git'")
    if value["dirty"]:
        raise GovernanceError(
            "Entry 001 requires a clean committed working tree"
        )


def _validate_transaction_cost_model_structure(value: Any) -> bool:
    """Validate cost-model shape, allowing only null as the template value."""

    if not isinstance(value, Mapping):
        raise GovernanceError("transaction_cost_model must be an object")
    missing = sorted(_TRANSACTION_COST_MODEL_KEYS - set(value))
    extra = sorted(set(value) - _TRANSACTION_COST_MODEL_KEYS)
    if missing or extra:
        raise GovernanceError(
            "transaction_cost_model has invalid keys; "
            f"missing={missing}, extra={extra}"
        )
    if value.get("convention") != "traded_notional_times_one_way_bps":
        raise GovernanceError(
            "transaction_cost_model.convention must be "
            "'traded_notional_times_one_way_bps'"
        )
    bps = value["one_way_cost_bps"]
    if bps is None:
        return True
    if (
        not isinstance(bps, (int, float))
        or isinstance(bps, bool)
        or not (float("-inf") < float(bps) < float("inf"))
        or bps < 0
    ):
        raise GovernanceError(
            "transaction_cost_model.one_way_cost_bps must be a finite non-negative number"
        )
    return False


def _validate_transaction_cost_model(value: Any) -> None:
    if _validate_transaction_cost_model_structure(value):
        raise UnresolvedEntry001("transaction_cost_model.one_way_cost_bps is unresolved")


def _find_unresolved(value: Any, path: str = "$") -> list[str]:
    """Locate explicit template placeholders before the no-more-free-decisions boundary."""

    found: list[str] = []
    if value is None:
        return [path]
    if isinstance(value, str) and (
        "UNRESOLVED" in value.upper() or "REPLACE_WITH" in value.upper()
    ):
        return [path]
    if isinstance(value, Mapping):
        for key, item in value.items():
            found.extend(_find_unresolved(item, f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(_find_unresolved(item, f"{path}[{index}]"))
    return found


def require_entry_001(
    path: str | Path,
) -> tuple[Mapping[str, Any], RuntimeValidationResult]:
    verify_artifact(path)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("entry") != "001":
        raise GovernanceError("return research requires a valid Entry 001 artifact")
    _validate_entry_001(payload, validate_against_project_pins=False)
    runtime = _validate_runtime_against_manifest(payload["environment_manifest"])
    return payload, runtime


def load_resolved_entry_001(path: str | Path) -> ResolvedEntry001:
    """Load the only registry container accepted by governed execution."""

    payload, _runtime = require_entry_001(path)
    registry = _parse_proxy_registry(payload["proxy_registry"])
    return ResolvedEntry001(
        proxy_registry=registry,
        proxy_registry_digest_value=proxy_registry_digest(registry),
        entry_001_sha256=sha256_payload(payload),
        missing_data_policy=payload["missing_data_policy"],
        required_dimensions=tuple(payload["required_dimensions"]),
        restatement_policy=payload["pit_conventions"]["restatement_policy"],
        portfolio_timing=ResolvedPortfolioTiming.from_mapping(
            payload["portfolio_timing"]
        ),
        sample_boundaries=payload["sample_boundaries"],
        portfolio_construction=payload["portfolio_construction"],
        terminal_position_policy=payload["terminal_position_policy"],
        data_vintage_identifier=payload["data_vintage_identifier"],
        specification_budget=payload["specification_budget"],
        transaction_cost_model=payload["transaction_cost_model"],
        specification_counting_rules=payload["specification_counting_rules"],
        _token=_RESOLVED_ENTRY_TOKEN,
    )


def _python_major_minor(value: Any) -> tuple[int, int]:
    if not isinstance(value, str):
        raise GovernanceError("manifest Python version must be a string")
    match = re.match(r"^(\d+)\.(\d+)(?:\.|$)", value)
    if match is None:
        raise GovernanceError(f"invalid Python version in manifest: {value!r}")
    return int(match.group(1)), int(match.group(2))


def _validate_runtime_against_manifest(
    value: Mapping[str, Any],
) -> RuntimeValidationResult:
    recorded = value["packages"]
    drift: dict[str, Any] = {}
    runtime_identity = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
    }
    if runtime_identity["implementation"] != value.get("implementation"):
        drift["implementation"] = {
            "recorded": value.get("implementation"),
            "installed": runtime_identity["implementation"],
        }
    if _python_major_minor(runtime_identity["python"]) != _python_major_minor(
        value.get("python")
    ):
        drift["python_major_minor"] = {
            "recorded": value.get("python"),
            "installed": runtime_identity["python"],
        }
    for name, expected in recorded.items():
        try:
            actual: str | None = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        if actual != expected:
            drift[name] = {"recorded": expected, "installed": actual}
    if drift:
        raise GovernanceError(
            f"load-bearing runtime drifted from frozen Entry 001: {drift}"
        )
    runtime_warnings: list[str] = []
    if runtime_identity["python"] != value.get("python"):
        runtime_warnings.append(
            "Python patch version differs from frozen Entry 001: "
            f"recorded={value.get('python')}, installed={runtime_identity['python']}"
        )
    if runtime_identity["platform"] != value.get("platform"):
        runtime_warnings.append(
            "Platform differs from frozen Entry 001: "
            f"recorded={value.get('platform')}, installed={runtime_identity['platform']}"
        )
    return RuntimeValidationResult(
        warnings=tuple(runtime_warnings),
        recorded={
            "python": value.get("python"),
            "implementation": value.get("implementation"),
            "platform": value.get("platform"),
            "packages": dict(recorded),
        },
        installed={
            **runtime_identity,
            "packages": {
                name: importlib.metadata.version(name)
                for name in recorded
            },
        },
    )


def environment_manifest() -> dict[str, Any]:
    pinned_dependencies = project_dependency_pins()
    packages: dict[str, str | None] = {}
    for name in pinned_dependencies:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    mismatches = {
        name: {"expected": expected, "actual": packages.get(name)}
        for name, expected in pinned_dependencies.items()
        if packages.get(name) != expected
    }
    return {
        "schema_version": 1,
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": packages,
        "pinned_dependencies": pinned_dependencies,
        "dependency_match": not mismatches,
        "mismatches": mismatches,
    }


def source_control_manifest(repository: str | Path) -> dict[str, Any]:
    """Capture a committed Git identity and any uncommitted diff hash."""

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GovernanceError(
            f"unable to create source-control manifest for {repository}"
        ) from exc
    result: dict[str, Any] = {
        "vcs": "git",
        "commit": commit,
        "dirty": bool(status),
    }
    # Cleanliness is enforced by each governed consumer at its authority
    # boundary.  Entry 001 validates it at freeze; feature generation validates
    # it immediately before emitting GovernedFeatureBatch.
    if re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", commit) is None:
        raise GovernanceError("source-control manifest did not produce a full commit hash")
    return result
