"""Content-bound governed ranking artifacts.

The ranked-frame digest binds only the three decision-bearing columns declared
in :data:`RANKED_FRAME_DIGEST_SCOPE`.  Auxiliary diagnostics may travel with an
artifact, but neither the digest nor the governed selector attests to or reads
them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import hashlib
import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .features import GovernedFeatureBatch
from .governance import (
    GovernanceError,
    ResolvedEntry001,
    canonical_json,
    freeze_artifact,
    proxy_registry_digest,
    source_control_manifest,
    verify_artifact,
)
from .ranking import CompositeConfig, rank_features, select_top_n


RANKED_FRAME_DIGEST_SCOPE = (
    "security_id",
    "decision_date",
    "composite_score",
)
RANKED_FRAME_DIGEST_SCHEMA_VERSION = 1
RANKING_CONFIGURATION_SCHEMA_VERSION = 1
MISSING_TOKEN = "<NA>"
ATTESTATION_LIMIT = (
    "Only digest_scope columns are content-bound; auxiliary columns "
    "are not attested and cannot influence governed selection."
)
RANKING_MANIFEST_KEYS = frozenset({
    "artifact",
    "entry_001_sha256",
    "research_vintage_bundle_id",
    "fact_source_kind",
    "fact_source_id",
    "fact_source_native_vintage_identifier",
    "fact_source_content_sha256",
    "fact_source_audit_artifact_sha256",
    "fact_source_manifest_sha256",
    "proxy_registry_digest",
    "ranking_configuration_digest",
    "feature_generation_code_commit",
    "ranking_code_commit",
    "creation_timestamp",
    "ranked_frame_digest",
    "digest_scope",
    "selector_permitted_columns",
    "attestation_limit",
    "decision_frame_artifact",
    "decision_frame_artifact_sha256",
})


class RankedArtifactError(GovernanceError):
    pass


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_git_commit(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_ranking_inspection(payload: Mapping[str, Any]) -> None:
    """Validate the self-contained ranking attestation without loading Entry 001."""

    for name in (
        "entry_001_sha256",
        "fact_source_content_sha256",
        "fact_source_audit_artifact_sha256",
        "fact_source_manifest_sha256",
        "proxy_registry_digest",
        "ranking_configuration_digest",
        "ranked_frame_digest",
        "decision_frame_artifact_sha256",
    ):
        if not _is_sha256(payload.get(name)):
            raise RankedArtifactError(f"ranking manifest {name} must be SHA-256")
    for name in (
        "research_vintage_bundle_id",
        "fact_source_kind",
        "fact_source_id",
        "fact_source_native_vintage_identifier",
        "creation_timestamp",
        "attestation_limit",
    ):
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            raise RankedArtifactError(f"ranking manifest {name} must be non-empty")
    for name in ("feature_generation_code_commit", "ranking_code_commit"):
        if not _is_git_commit(payload.get(name)):
            raise RankedArtifactError(f"ranking manifest {name} must be a Git SHA-1")
    try:
        created = datetime.fromisoformat(str(payload["creation_timestamp"]))
    except (TypeError, ValueError) as exc:
        raise RankedArtifactError("ranking manifest creation_timestamp is invalid") from exc
    if created.tzinfo is None:
        raise RankedArtifactError("ranking manifest creation_timestamp must be aware")
    if payload.get("fact_source_kind") != "pit_facts":
        raise RankedArtifactError("ranking manifest fact source kind is invalid")
    if payload.get("attestation_limit") != ATTESTATION_LIMIT:
        raise RankedArtifactError("ranking manifest attestation limit was altered")
    if payload.get("feature_generation_code_commit") != payload.get("ranking_code_commit"):
        raise RankedArtifactError("ranking manifest feature/ranking commits differ")
    if tuple(payload.get("digest_scope", ())) != RANKED_FRAME_DIGEST_SCOPE:
        raise RankedArtifactError("ranking manifest digest scope is unsupported")
    if tuple(payload.get("selector_permitted_columns", ())) != RANKED_FRAME_DIGEST_SCOPE:
        raise RankedArtifactError("ranking selector permission exceeds digest scope")


def _normalized_utc(value: object) -> str:
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, time.min, tzinfo=timezone.utc).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
    if isinstance(value, str):
        try:
            parsed_date = date.fromisoformat(value)
        except ValueError:
            pass
        else:
            return datetime.combine(
                parsed_date, time.min, tzinfo=timezone.utc
            ).isoformat(timespec="microseconds").replace("+00:00", "Z")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise RankedArtifactError(f"invalid decision_date: {value!r}") from exc
    if timestamp.tzinfo is None:
        raise RankedArtifactError("ranked decision_date must be timezone-aware")
    utc = timestamp.tz_convert("UTC").to_pydatetime()
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _score_token(value: object) -> str:
    if pd.isna(value):
        return MISSING_TOKEN
    if isinstance(value, bool):
        raise RankedArtifactError("composite_score cannot be boolean")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise RankedArtifactError("composite_score must be numeric or missing") from exc
    if not math.isfinite(numeric):
        raise RankedArtifactError("composite_score must be finite or missing")
    return numeric.hex()


def _calendar_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise RankedArtifactError("ranked decision_date must be timezone-aware")
    return timestamp.tz_convert("UTC").date()


def canonical_ranked_frame_rows(frame: pd.DataFrame) -> tuple[tuple[str, str, str], ...]:
    """Return the exact canonical decision-bearing representation."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("ranked frame must be a pandas DataFrame")
    missing = sorted(set(RANKED_FRAME_DIGEST_SCOPE) - set(frame.columns))
    if missing:
        raise RankedArtifactError(f"ranked frame is missing digest columns: {missing}")
    rows: list[tuple[str, str, str]] = []
    identities: set[tuple[str, str]] = set()
    for row in frame.loc[:, list(RANKED_FRAME_DIGEST_SCOPE)].itertuples(index=False):
        security_id = row.security_id
        if not isinstance(security_id, str) or not security_id.strip():
            raise RankedArtifactError("security_id must be a non-empty string")
        normalized_date = _normalized_utc(row.decision_date)
        identity = (security_id, _calendar_date(row.decision_date).isoformat())
        if identity in identities:
            raise RankedArtifactError(
                "duplicate security_id/governed-calendar-date rows"
            )
        identities.add(identity)
        rows.append((security_id, normalized_date, _score_token(row.composite_score)))
    return tuple(sorted(rows, key=lambda item: (item[1], item[0], item[2])))


def canonical_ranked_frame_digest(frame: pd.DataFrame) -> str:
    payload = {
        "schema_version": RANKED_FRAME_DIGEST_SCHEMA_VERSION,
        "scope": list(RANKED_FRAME_DIGEST_SCOPE),
        "missing_token": MISSING_TOKEN,
        "float_serialization": "float.hex",
        "datetime_serialization": "UTC ISO-8601 microseconds with Z suffix",
        "rows": canonical_ranked_frame_rows(frame),
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def ranking_configuration_payload(
    resolved_entry: ResolvedEntry001,
    config: CompositeConfig,
) -> Mapping[str, Any]:
    """Describe ranking behavior not already defined by the proxy registry.

    The Entry 001 hash binds the whole specification and the proxy-registry
    digest separately binds proxy semantics.  This digest intentionally repeats
    Entry ranking fields so a ranking artifact can expose its exact ranking
    behavior without interpreting the full Entry; code-only invariants are
    included here and are additionally bound by the clean Git commit.
    """

    expected = CompositeConfig.from_resolved_entry(resolved_entry)
    if config != expected:
        raise RankedArtifactError("ranking configuration differs from Entry 001")
    return {
        "ranking_configuration_schema_version": (
            RANKING_CONFIGURATION_SCHEMA_VERSION
        ),
        "percentile_ranking": {
            "algorithm": "average_rank_rescaled_to_closed_zero_one_interval",
            "tie_method": "average",
            "singleton_percentile": 0.5,
        },
        "missing_data_policy": {
            "policy": config.missing_policy,
            "minimum_feature_coverage": config.minimum_feature_coverage,
            "minimum_features_per_dimension": config.minimum_features_per_dimension,
        },
        "required_dimensions": list(config.required_dimensions),
        "dimension_aggregation": {
            "method": "equal_weight_arithmetic_mean",
        },
        "composite_aggregation": {
            "required_dimension_behavior": "skipna_false",
        },
        "selector_ordering": {
            "primary_key": "composite_score",
            "primary_direction": "descending",
            "tie_break_key": "security_id",
            "tie_break_direction": "ascending",
            "missing_composite_policy": "exclude",
        },
    }


def ranking_configuration_digest(
    resolved_entry: ResolvedEntry001,
    config: CompositeConfig,
) -> str:
    return hashlib.sha256(
        canonical_json(ranking_configuration_payload(resolved_entry, config))
    ).hexdigest()


_ARTIFACT_TOKEN = object()


@dataclass(frozen=True, init=False)
class GovernedRankingArtifact:
    ranked: pd.DataFrame
    entry_001_sha256: str
    research_vintage_bundle_id: str
    fact_source_kind: str
    fact_source_id: str
    fact_source_native_vintage_identifier: str
    fact_source_content_sha256: str
    fact_source_audit_artifact_sha256: str
    fact_source_manifest_sha256: str
    proxy_registry_digest: str
    ranking_configuration_digest: str
    feature_generation_code_commit: str
    ranking_code_commit: str
    creation_timestamp: str
    ranked_frame_digest: str
    digest_scope: tuple[str, ...]
    selector_permitted_columns: tuple[str, ...]

    def __init__(self, *, _token: object, **values: object) -> None:
        if _token is not _ARTIFACT_TOKEN:
            raise TypeError(
                "GovernedRankingArtifact is emitted only by governed ranking creation"
            )
        for name in self.__annotations__:
            object.__setattr__(self, name, values[name])

    def inspection(self) -> Mapping[str, Any]:
        return {
            "entry_001_sha256": self.entry_001_sha256,
            "research_vintage_bundle_id": self.research_vintage_bundle_id,
            "fact_source_kind": self.fact_source_kind,
            "fact_source_id": self.fact_source_id,
            "fact_source_native_vintage_identifier": (
                self.fact_source_native_vintage_identifier
            ),
            "fact_source_content_sha256": self.fact_source_content_sha256,
            "fact_source_audit_artifact_sha256": (
                self.fact_source_audit_artifact_sha256
            ),
            "fact_source_manifest_sha256": self.fact_source_manifest_sha256,
            "proxy_registry_digest": self.proxy_registry_digest,
            "ranking_configuration_digest": self.ranking_configuration_digest,
            "feature_generation_code_commit": self.feature_generation_code_commit,
            "ranking_code_commit": self.ranking_code_commit,
            "creation_timestamp": self.creation_timestamp,
            "ranked_frame_digest": self.ranked_frame_digest,
            "digest_scope": list(self.digest_scope),
            "selector_permitted_columns": list(self.selector_permitted_columns),
            "attestation_limit": ATTESTATION_LIMIT,
        }


def create_governed_ranking_artifact(
    batch: GovernedFeatureBatch,
    resolved_entry: ResolvedEntry001,
    repository: str | Path,
) -> GovernedRankingArtifact:
    if not isinstance(batch, GovernedFeatureBatch):
        raise TypeError("governed ranking requires GovernedFeatureBatch")
    if not isinstance(resolved_entry, ResolvedEntry001):
        raise TypeError("governed ranking requires ResolvedEntry001")
    if batch.entry_001_sha256 != resolved_entry.entry_001_sha256:
        raise RankedArtifactError("feature batch Entry 001 hash mismatch")
    if (
        batch.research_vintage_bundle_id
        != resolved_entry.data_vintage_identifier
    ):
        raise RankedArtifactError("feature batch research-vintage bundle mismatch")
    if batch.proxy_registry_digest != proxy_registry_digest(
        resolved_entry.proxy_registry
    ):
        raise RankedArtifactError("feature batch proxy-registry digest mismatch")
    manifest = source_control_manifest(repository)
    if manifest["dirty"]:
        raise RankedArtifactError("governed ranking requires a clean source tree")
    if manifest["commit"] != batch.feature_generation_code_commit:
        raise RankedArtifactError(
            "ranking commit differs from feature-generation commit"
        )
    config = CompositeConfig.from_resolved_entry(resolved_entry)
    result = rank_features(batch, resolved_entry, config)
    ranked = result.ranked.copy(deep=True)
    invalid_dates = sorted({
        _calendar_date(value)
        for value in ranked["decision_date"]
        if not resolved_entry.portfolio_timing.is_valid_decision_date(
            _calendar_date(value)
        )
    })
    if invalid_dates:
        raise RankedArtifactError(
            f"ranked decision dates violate frozen schedule: {invalid_dates}"
        )
    return GovernedRankingArtifact(
        ranked=ranked,
        entry_001_sha256=resolved_entry.entry_001_sha256,
        research_vintage_bundle_id=resolved_entry.data_vintage_identifier,
        fact_source_kind=batch.fact_source_kind,
        fact_source_id=batch.fact_source_id,
        fact_source_native_vintage_identifier=(
            batch.fact_source_native_vintage_identifier
        ),
        fact_source_content_sha256=batch.fact_source_content_sha256,
        fact_source_audit_artifact_sha256=(
            batch.fact_source_audit_artifact_sha256
        ),
        fact_source_manifest_sha256=batch.fact_source_manifest_sha256,
        proxy_registry_digest=batch.proxy_registry_digest,
        ranking_configuration_digest=ranking_configuration_digest(
            resolved_entry, config
        ),
        feature_generation_code_commit=batch.feature_generation_code_commit,
        ranking_code_commit=str(manifest["commit"]),
        creation_timestamp=datetime.now(timezone.utc).isoformat(),
        ranked_frame_digest=canonical_ranked_frame_digest(ranked),
        digest_scope=RANKED_FRAME_DIGEST_SCOPE,
        selector_permitted_columns=RANKED_FRAME_DIGEST_SCOPE,
        _token=_ARTIFACT_TOKEN,
    )


def verify_governed_ranking_artifact(
    artifact: GovernedRankingArtifact,
    resolved_entry: ResolvedEntry001,
) -> Mapping[str, Any]:
    if not isinstance(artifact, GovernedRankingArtifact):
        raise TypeError("expected GovernedRankingArtifact")
    for name in (
        "entry_001_sha256",
        "fact_source_content_sha256",
        "fact_source_audit_artifact_sha256",
        "fact_source_manifest_sha256",
        "proxy_registry_digest",
        "ranking_configuration_digest",
        "ranked_frame_digest",
    ):
        value = getattr(artifact, name)
        if not _is_sha256(value):
            raise RankedArtifactError(f"ranked artifact {name} must be SHA-256")
    for name in (
        "research_vintage_bundle_id",
        "fact_source_kind",
        "fact_source_id",
        "fact_source_native_vintage_identifier",
        "creation_timestamp",
    ):
        value = getattr(artifact, name)
        if not isinstance(value, str) or not value.strip():
            raise RankedArtifactError(f"ranked artifact {name} must be non-empty")
    for name in ("feature_generation_code_commit", "ranking_code_commit"):
        if not _is_git_commit(getattr(artifact, name)):
            raise RankedArtifactError(f"ranked artifact {name} must be a Git SHA-1")
    if artifact.fact_source_kind != "pit_facts":
        raise RankedArtifactError("ranked artifact fact source kind is invalid")
    try:
        created = datetime.fromisoformat(artifact.creation_timestamp)
    except (TypeError, ValueError) as exc:
        raise RankedArtifactError("ranked artifact creation timestamp is invalid") from exc
    if created.tzinfo is None:
        raise RankedArtifactError("ranked artifact creation timestamp must be aware")
    if artifact.digest_scope != RANKED_FRAME_DIGEST_SCOPE:
        raise RankedArtifactError("ranked artifact digest scope is unsupported")
    if artifact.selector_permitted_columns != RANKED_FRAME_DIGEST_SCOPE:
        raise RankedArtifactError("selector permission exceeds digest scope")
    if artifact.entry_001_sha256 != resolved_entry.entry_001_sha256:
        raise RankedArtifactError("ranked artifact Entry 001 mismatch")
    if artifact.research_vintage_bundle_id != resolved_entry.data_vintage_identifier:
        raise RankedArtifactError("ranked artifact research-vintage bundle mismatch")
    if artifact.proxy_registry_digest != proxy_registry_digest(
        resolved_entry.proxy_registry
    ):
        raise RankedArtifactError("ranked artifact proxy-registry mismatch")
    expected_config = ranking_configuration_digest(
        resolved_entry, CompositeConfig.from_resolved_entry(resolved_entry)
    )
    if artifact.ranking_configuration_digest != expected_config:
        raise RankedArtifactError("ranked artifact ranking-configuration mismatch")
    if artifact.feature_generation_code_commit != artifact.ranking_code_commit:
        raise RankedArtifactError("feature/ranking code commits differ")
    recomputed = canonical_ranked_frame_digest(artifact.ranked)
    if artifact.ranked_frame_digest != recomputed:
        raise RankedArtifactError("ranked-frame content digest mismatch")
    if any(
        not resolved_entry.portfolio_timing.is_valid_decision_date(
            _calendar_date(value)
        )
        for value in artifact.ranked["decision_date"]
    ):
        raise RankedArtifactError("ranked artifact contains an invalid decision date")
    return artifact.inspection()


def select_governed_portfolios(
    artifact: GovernedRankingArtifact,
    resolved_entry: ResolvedEntry001,
) -> pd.DataFrame:
    """Select using only bound columns and the frozen portfolio size."""

    verify_governed_ranking_artifact(artifact, resolved_entry)
    decision_frame = artifact.ranked.loc[:, list(RANKED_FRAME_DIGEST_SCOPE)].copy()
    count = int(resolved_entry.portfolio_construction["number_of_positions"])
    return select_top_n(decision_frame, count)


def write_ranking_manifest(
    artifact: GovernedRankingArtifact,
    path: str | Path,
) -> str:
    """Freeze a manifest plus the canonical decision-bearing content it binds."""

    if artifact.digest_scope != RANKED_FRAME_DIGEST_SCOPE:
        raise RankedArtifactError("cannot persist an unsupported digest scope")
    if canonical_ranked_frame_digest(artifact.ranked) != artifact.ranked_frame_digest:
        raise RankedArtifactError("cannot persist modified decision-bearing content")
    manifest_path = Path(path)
    decision_path = manifest_path.with_name(
        f"{manifest_path.stem}.decision-frame.json"
    )
    decision_digest = freeze_artifact(decision_path, {
        "artifact": "governed_ranking_decision_frame",
        "schema_version": RANKED_FRAME_DIGEST_SCHEMA_VERSION,
        "scope": list(RANKED_FRAME_DIGEST_SCOPE),
        "rows": canonical_ranked_frame_rows(artifact.ranked),
    })
    return freeze_artifact(manifest_path, {
        "artifact": "governed_ranking",
        **artifact.inspection(),
        "decision_frame_artifact": decision_path.name,
        "decision_frame_artifact_sha256": decision_digest,
    })


def inspect_ranking_manifest(path: str | Path) -> Mapping[str, Any]:
    manifest_path = Path(path)
    verify_artifact(manifest_path)
    import json

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = sorted(RANKING_MANIFEST_KEYS - set(payload))
    extra = sorted(set(payload) - RANKING_MANIFEST_KEYS)
    if missing or extra:
        raise RankedArtifactError(
            f"ranking manifest has invalid keys; missing={missing}, extra={extra}"
        )
    if payload.get("artifact") != "governed_ranking":
        raise RankedArtifactError("not a governed ranking manifest")
    _validate_ranking_inspection(payload)
    decision_name = payload.get("decision_frame_artifact")
    if not isinstance(decision_name, str) or Path(decision_name).name != decision_name:
        raise RankedArtifactError("ranking decision-frame artifact name is invalid")
    decision_path = manifest_path.parent / decision_name
    decision_sha = verify_artifact(decision_path)
    if decision_sha != payload.get("decision_frame_artifact_sha256"):
        raise RankedArtifactError("ranking decision-frame artifact identity mismatch")
    decision_payload = json.loads(decision_path.read_text(encoding="utf-8"))
    if set(decision_payload) != {"artifact", "schema_version", "scope", "rows"}:
        raise RankedArtifactError("ranking decision-frame keys are invalid")
    if decision_payload.get("artifact") != "governed_ranking_decision_frame":
        raise RankedArtifactError("ranking decision-frame artifact type is invalid")
    if decision_payload.get("schema_version") != RANKED_FRAME_DIGEST_SCHEMA_VERSION:
        raise RankedArtifactError("ranking decision-frame schema version is invalid")
    if tuple(decision_payload.get("scope", ())) != RANKED_FRAME_DIGEST_SCOPE:
        raise RankedArtifactError("ranking decision-frame scope is invalid")
    rows = decision_payload.get("rows")
    if not isinstance(rows, list):
        raise RankedArtifactError("ranking decision-frame rows are invalid")
    parsed_rows: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 3:
            raise RankedArtifactError("canonical decision-frame row is invalid")
        try:
            score = None if row[2] == MISSING_TOKEN else float.fromhex(row[2])
        except (TypeError, ValueError) as exc:
            raise RankedArtifactError(
                "canonical decision-frame score is invalid"
            ) from exc
        parsed_rows.append({
            "security_id": row[0],
            "decision_date": row[1],
            "composite_score": score,
        })
    frame = pd.DataFrame(parsed_rows, columns=RANKED_FRAME_DIGEST_SCOPE)
    if canonical_ranked_frame_digest(frame) != payload.get("ranked_frame_digest"):
        raise RankedArtifactError("persisted ranked-frame content digest mismatch")
    return {**payload, "decision_frame_content_verified": True}


def load_governed_ranking_artifact(
    path: str | Path,
    resolved_entry: ResolvedEntry001,
) -> GovernedRankingArtifact:
    """Load the frozen canonical decision frame and revalidate Entry lineage."""

    payload = inspect_ranking_manifest(path)
    manifest_path = Path(path)
    import json

    decision_payload = json.loads(
        (manifest_path.parent / payload["decision_frame_artifact"]).read_text(
            encoding="utf-8"
        )
    )
    frame = pd.DataFrame([
        {
            "security_id": row[0],
            "decision_date": row[1],
            "composite_score": (
                None if row[2] == MISSING_TOKEN else float.fromhex(row[2])
            ),
        }
        for row in decision_payload["rows"]
    ], columns=RANKED_FRAME_DIGEST_SCOPE)
    artifact = GovernedRankingArtifact(
        ranked=frame,
        entry_001_sha256=payload["entry_001_sha256"],
        research_vintage_bundle_id=payload["research_vintage_bundle_id"],
        fact_source_kind=payload["fact_source_kind"],
        fact_source_id=payload["fact_source_id"],
        fact_source_native_vintage_identifier=payload[
            "fact_source_native_vintage_identifier"
        ],
        fact_source_content_sha256=payload["fact_source_content_sha256"],
        fact_source_audit_artifact_sha256=payload[
            "fact_source_audit_artifact_sha256"
        ],
        fact_source_manifest_sha256=payload["fact_source_manifest_sha256"],
        proxy_registry_digest=payload["proxy_registry_digest"],
        ranking_configuration_digest=payload["ranking_configuration_digest"],
        feature_generation_code_commit=payload[
            "feature_generation_code_commit"
        ],
        ranking_code_commit=payload["ranking_code_commit"],
        creation_timestamp=payload["creation_timestamp"],
        ranked_frame_digest=payload["ranked_frame_digest"],
        digest_scope=tuple(payload["digest_scope"]),
        selector_permitted_columns=tuple(payload["selector_permitted_columns"]),
        _token=_ARTIFACT_TOKEN,
    )
    verify_governed_ranking_artifact(artifact, resolved_entry)
    return artifact
