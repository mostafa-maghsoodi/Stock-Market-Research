"""Frozen artifacts, environment manifests, and append-only specification logs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timezone
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


ENTRY_001_REQUIRED_KEYS = frozenset({
    "architecture_version",
    "data_audit",
    "investable_universe",
    "sample_boundaries",
    "proxy_registry",
    "pit_conventions",
    "missing_data_policy",
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
    "rebalance_frequency",
    "holding_period",
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


def freeze_entry_001(path: str | Path, payload: Mapping[str, Any]) -> str:
    _validate_entry_001(payload, validate_against_project_pins=True)
    runtime = _validate_runtime_against_manifest(payload["environment_manifest"])
    for message in runtime.warnings:
        python_warnings.warn(message, RuntimeWarning, stacklevel=2)
    wrapped = {
        **dict(payload),
        "entry": "001",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return freeze_artifact(path, wrapped)


def _validate_entry_001(
    payload: Mapping[str, Any],
    *,
    validate_against_project_pins: bool,
) -> None:
    missing = sorted(ENTRY_001_REQUIRED_KEYS - set(payload))
    if missing:
        raise GovernanceError(f"Entry 001 is incomplete; missing: {missing}")
    unresolved = _find_unresolved(payload)
    if unresolved:
        raise GovernanceError(
            "Entry 001 contains unresolved placeholders: "
            + ", ".join(unresolved[:20])
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
    _validate_environment_manifest(
        payload["environment_manifest"],
        expected_project_pins=(
            project_dependency_pins() if validate_against_project_pins else None
        ),
    )
    _validate_source_control(payload["source_control"])
    _validate_transaction_cost_model(payload["transaction_cost_model"])


def _validate_environment_manifest(
    value: Any,
    *,
    expected_project_pins: Mapping[str, str] | None,
) -> None:
    if not isinstance(value, Mapping):
        raise GovernanceError("environment_manifest must be an object")
    required = {
        "schema_version",
        "python",
        "implementation",
        "platform",
        "packages",
        "pinned_dependencies",
        "dependency_match",
        "mismatches",
    }
    missing = sorted(required - set(value))
    if missing:
        raise GovernanceError(
            f"environment_manifest is missing required fields: {missing}"
        )
    packages = value["packages"]
    pinned = value["pinned_dependencies"]
    if not isinstance(packages, Mapping) or not isinstance(pinned, Mapping):
        raise GovernanceError(
            "environment_manifest packages and pinned_dependencies must be objects"
        )
    if not pinned:
        raise GovernanceError("environment_manifest pinned_dependencies is empty")
    missing_versions = sorted(
        name for name in pinned
        if not isinstance(packages.get(name), str) or not packages[name].strip()
    )
    if missing_versions:
        raise GovernanceError(
            f"environment_manifest has missing package versions: {missing_versions}"
        )
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


def _validate_source_control(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise GovernanceError("source_control must be an object")
    commit = value.get("commit")
    if value.get("vcs") != "git":
        raise GovernanceError("source_control.vcs must be 'git'")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", commit) is None:
        raise GovernanceError("source_control.commit must be a full Git commit hash")
    if not isinstance(value.get("dirty"), bool):
        raise GovernanceError("source_control.dirty must be boolean")
    if value["dirty"]:
        raise GovernanceError(
            "Entry 001 requires a clean committed working tree"
        )


def _validate_transaction_cost_model(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise GovernanceError("transaction_cost_model must be an object")
    if value.get("convention") != "traded_notional_times_one_way_bps":
        raise GovernanceError(
            "transaction_cost_model.convention must be "
            "'traded_notional_times_one_way_bps'"
        )
    bps = value.get("one_way_cost_bps")
    if (
        not isinstance(bps, (int, float))
        or isinstance(bps, bool)
        or not (float("-inf") < float(bps) < float("inf"))
        or bps < 0
    ):
        raise GovernanceError(
            "transaction_cost_model.one_way_cost_bps must be a finite non-negative number"
        )


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
    _validate_source_control(result)
    return result


@dataclass(frozen=True)
class SpecificationLogEntry:
    specification_id: str
    code_hash: str
    data_vintage: str
    rationale: str
    result: str
    disposition: str
    timestamp: str = ""


def append_specification_log(path: str | Path, entry: SpecificationLogEntry) -> None:
    """Append and fsync one JSON line; existing records are never rewritten."""

    payload = asdict(entry)
    if not payload["timestamp"]:
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    line = canonical_json(payload) + b"\n"
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(descriptor, line)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
