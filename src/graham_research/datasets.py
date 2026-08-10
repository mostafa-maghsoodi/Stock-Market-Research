"""Governed source datasets with immutable local-ingest manifests.

The MVP verifies an audited local ingest artifact.  It does not claim that the
manifest is vendor-signed: the manifest and its companion SHA-256 are produced
and reviewed outside governed execution, then the loader verifies both the
manifest identity and the bytes it binds.  Execution APIs never accept vintage
strings as overrides.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .domain import FactObservation
from .governance import GovernanceError, verify_artifact
from .timing import ECONOMIC_RETURN_CONVENTION_KEYS


SOURCE_MANIFEST_SCHEMA_VERSION = 2
SOURCE_MANIFEST_PROVENANCE = "audited_local_ingest_manifest"
SOURCE_MANIFEST_KEYS = frozenset({
    "source_manifest_schema_version",
    "source_kind",
    "source_id",
    "research_vintage_bundle_id",
    "source_native_vintage_identifier",
    "content_sha256",
    "audit_artifact_sha256",
    "provenance",
})
HELD_RETURN_SOURCE_MANIFEST_KEYS = SOURCE_MANIFEST_KEYS | frozenset({
    "economic_return_convention",
})


@dataclass(frozen=True)
class SourceManifest:
    source_kind: str
    source_id: str
    research_vintage_bundle_id: str
    source_native_vintage_identifier: str
    content_sha256: str
    audit_artifact_sha256: str
    manifest_sha256: str
    provenance: str
    economic_return_convention: Mapping[str, str] | None


@dataclass(frozen=True, order=True)
class HeldPeriodReturnObservation:
    security_id: str
    period_start: date
    period_end: date
    total_return: float
    terminal_flag: bool

    def __post_init__(self) -> None:
        if not isinstance(self.security_id, str) or not self.security_id.strip():
            raise ValueError("security_id cannot be blank")
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be after period_start")
        if isinstance(self.total_return, bool) or not isinstance(
            self.total_return, (int, float)
        ):
            raise ValueError("total_return must be a finite number")
        numeric = float(self.total_return)
        if not math.isfinite(numeric):
            raise ValueError("total_return must be a finite number")
        if numeric < -1.0:
            raise ValueError("long-only total_return cannot be below -1.0")
        if not isinstance(self.terminal_flag, bool):
            raise ValueError("terminal_flag must be boolean")
        object.__setattr__(self, "total_return", numeric)

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "HeldPeriodReturnObservation":
        raw_terminal = row["terminal_flag"]
        if isinstance(raw_terminal, bool):
            terminal = raw_terminal
        elif isinstance(raw_terminal, str) and raw_terminal.strip().lower() in {
            "true", "false"
        }:
            terminal = raw_terminal.strip().lower() == "true"
        else:
            raise ValueError("terminal_flag must be true or false")
        raw_return = row["total_return"]
        if isinstance(raw_return, bool):
            raise ValueError("total_return must be a finite number")
        try:
            numeric = float(raw_return)
        except (TypeError, ValueError) as exc:
            raise ValueError("total_return must be a finite number") from exc
        return cls(
            security_id=str(row["security_id"]),
            period_start=date.fromisoformat(str(row["period_start"])),
            period_end=date.fromisoformat(str(row["period_end"])),
            total_return=numeric,
            terminal_flag=terminal,
        )


_DATASET_TOKEN = object()


@dataclass(frozen=True, init=False)
class GovernedFactDataset:
    observations: tuple[FactObservation, ...]
    source_manifest: SourceManifest

    def __init__(
        self,
        observations: tuple[FactObservation, ...],
        source_manifest: SourceManifest,
        *,
        _token: object,
    ) -> None:
        if _token is not _DATASET_TOKEN:
            raise TypeError("GovernedFactDataset must be issued by its loader")
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "source_manifest", source_manifest)


@dataclass(frozen=True, init=False)
class GovernedHeldPeriodReturnSource:
    observations: tuple[HeldPeriodReturnObservation, ...]
    source_manifest: SourceManifest

    def __init__(
        self,
        observations: tuple[HeldPeriodReturnObservation, ...],
        source_manifest: SourceManifest,
        *,
        _token: object,
    ) -> None:
        if _token is not _DATASET_TOKEN:
            raise TypeError(
                "GovernedHeldPeriodReturnSource must be issued by its loader"
            )
        keys = [
            (item.security_id, item.period_start, item.period_end)
            for item in observations
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate held-period return source keys")
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "source_manifest", source_manifest)

    def observation(
        self,
        security_id: str,
        period_start: date,
        period_end: date,
    ) -> HeldPeriodReturnObservation | None:
        return next(
            (
                item
                for item in self.observations
                if item.security_id == security_id
                and item.period_start == period_start
                and item.period_end == period_end
            ),
            None,
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_source_manifest(
    content_path: str | Path,
    manifest_path: str | Path,
    *,
    expected_kind: str,
) -> SourceManifest:
    content = Path(content_path)
    manifest_file = Path(manifest_path)
    manifest_sha256 = verify_artifact(manifest_file)
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    expected_keys = (
        HELD_RETURN_SOURCE_MANIFEST_KEYS
        if expected_kind == "held_period_returns"
        else SOURCE_MANIFEST_KEYS
    )
    missing = sorted(expected_keys - set(payload))
    extra = sorted(set(payload) - expected_keys)
    if missing or extra:
        raise GovernanceError(
            f"source manifest has invalid keys; missing={missing}, extra={extra}"
        )
    if payload["source_manifest_schema_version"] != SOURCE_MANIFEST_SCHEMA_VERSION:
        raise GovernanceError("unsupported source manifest schema version")
    if payload["source_kind"] != expected_kind:
        raise GovernanceError(
            f"source manifest kind must be {expected_kind!r}"
        )
    if payload["provenance"] != SOURCE_MANIFEST_PROVENANCE:
        raise GovernanceError(
            "source manifest must identify an audited local ingest artifact"
        )
    for name in (
        "source_id",
        "research_vintage_bundle_id",
        "source_native_vintage_identifier",
        "audit_artifact_sha256",
    ):
        if not isinstance(payload[name], str) or not payload[name].strip():
            raise GovernanceError(f"source manifest {name} must be non-empty")
    for name in ("content_sha256", "audit_artifact_sha256"):
        if (
            not isinstance(payload[name], str)
            or len(payload[name]) != 64
            or any(character not in "0123456789abcdef" for character in payload[name])
        ):
            raise GovernanceError(f"source manifest {name} must be SHA-256")
    economic_convention: Mapping[str, str] | None = None
    if expected_kind == "held_period_returns":
        raw_convention = payload["economic_return_convention"]
        if not isinstance(raw_convention, Mapping):
            raise GovernanceError(
                "held-return economic_return_convention must be an object"
            )
        missing_convention = sorted(
            ECONOMIC_RETURN_CONVENTION_KEYS - set(raw_convention)
        )
        extra_convention = sorted(
            set(raw_convention) - ECONOMIC_RETURN_CONVENTION_KEYS
        )
        if missing_convention or extra_convention:
            raise GovernanceError(
                "held-return economic convention has invalid keys; "
                f"missing={missing_convention}, extra={extra_convention}"
            )
        if any(
            not isinstance(item, str) or not item.strip()
            for item in raw_convention.values()
        ):
            raise GovernanceError(
                "held-return economic convention values must be non-empty strings"
            )
        economic_convention = MappingProxyType(dict(raw_convention))
    actual_content_sha256 = _sha256_file(content)
    if actual_content_sha256 != payload["content_sha256"]:
        raise GovernanceError("source content does not match its audited manifest")
    return SourceManifest(
        source_kind=payload["source_kind"],
        source_id=payload["source_id"],
        research_vintage_bundle_id=payload["research_vintage_bundle_id"],
        source_native_vintage_identifier=payload[
            "source_native_vintage_identifier"
        ],
        content_sha256=payload["content_sha256"],
        audit_artifact_sha256=payload["audit_artifact_sha256"],
        manifest_sha256=manifest_sha256,
        provenance=payload["provenance"],
        economic_return_convention=economic_convention,
    )


def load_governed_fact_dataset(
    data_path: str | Path,
    manifest_path: str | Path,
) -> GovernedFactDataset:
    manifest = _load_source_manifest(
        data_path,
        manifest_path,
        expected_kind="pit_facts",
    )
    with Path(data_path).open(newline="", encoding="utf-8") as handle:
        observations = tuple(
            FactObservation.from_mapping(row) for row in csv.DictReader(handle)
        )
    return GovernedFactDataset(observations, manifest, _token=_DATASET_TOKEN)


def load_governed_held_return_source(
    data_path: str | Path,
    manifest_path: str | Path,
) -> GovernedHeldPeriodReturnSource:
    manifest = _load_source_manifest(
        data_path,
        manifest_path,
        expected_kind="held_period_returns",
    )
    with Path(data_path).open(newline="", encoding="utf-8") as handle:
        observations = tuple(
            HeldPeriodReturnObservation.from_mapping(row)
            for row in csv.DictReader(handle)
        )
    return GovernedHeldPeriodReturnSource(
        observations,
        manifest,
        _token=_DATASET_TOKEN,
    )
