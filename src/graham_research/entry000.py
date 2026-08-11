"""Entry000 Package v2 construction, publication, and verification.

The v2 package is an immutable six-component authority envelope.  This module
does not infer human approval: callers must supply the exact committed Approval
Record identities that the researcher approved.  Verification proves bytes,
Git provenance, and closure consistency only.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Mapping
from uuid import uuid4

from .governance import GovernanceError, canonical_json


REPOSITORY_ID = "mostafa-maghsoodi/Stock-Market-Research"
RUN1_COMMIT = "587051d1aa77d2634a364c76061016bfca7dccc0"
RUN2_COMMIT = "be1f9973e0aeeaaca80ab8f100a3de9a7a7c72db"
CANONICALIZATION = "CanonicalJSON-v1"

ENTRY000_TOP_LEVEL_KEYS = frozenset({
    "entry_000_package_schema_version",
    "entry",
    "package_label",
    "package_id",
    "created_at_utc",
    "canonicalization_version",
    "repository_id",
    "run_lineage",
    "components",
    "approval_evidence",
    "attestations",
})
RUN_LINEAGE_KEYS = frozenset({"run1_commit", "run2_commit"})
COMPONENT_KEYS = frozenset({
    "ordinal",
    "component_role",
    "authority_class",
    "repository_relative_path",
    "media_type",
    "document_or_schema_version",
    "source_commit",
    "git_blob",
    "exact_byte_sha256",
    "byte_length",
    "exact_bytes_base64",
    "approval_record_identity",
})
APPROVAL_IDENTITY_KEYS = frozenset({
    "repository_id",
    "approval_record_path",
    "approval_record_commit",
    "approval_record_git_blob",
    "approval_record_exact_byte_sha256",
})
APPROVAL_EVIDENCE_KEYS = frozenset({
    "approval_record_identity",
    "approval_record_byte_length",
    "approval_record_exact_bytes_base64",
})
APPROVAL_RECORD_KEYS = frozenset({
    "approval_record_schema_version",
    "approval_id",
    "approval_type",
    "status",
    "researcher_id",
    "decided_at_utc",
    "subject",
    "no_realized_outcome_attestation",
    "predecessor_approval_record_identity",
})
SUBJECT_KEYS = frozenset({
    "subject_type",
    "repository_id",
    "repository_relative_path",
    "source_commit",
    "git_blob",
    "exact_byte_sha256",
    "subject_schema_or_document_version",
})
NO_OUTCOME_ATTESTATION_KEYS = frozenset({
    "statement_version",
    "statement",
    "attested_by_researcher_id",
    "attested_at_utc",
})
PACKAGE_ATTESTATION_KEYS = frozenset({
    "no_realized_outcome_statement_version",
    "no_realized_outcome_statement",
    "prior_publication_statement_version",
    "prior_publication_statement",
    "legacy_preservation_statement",
    "unresolved_values_remain_unresolved",
})

PACKAGE_ATTESTATIONS = {
    "no_realized_outcome_statement_version": 1,
    "no_realized_outcome_statement": (
        "No realized strategy outcome was examined in freezing this package."
    ),
    "prior_publication_statement_version": 1,
    "prior_publication_statement": (
        "No Entry000 Package v2 with this semantic package identity or "
        "publication path was previously frozen."
    ),
    "legacy_preservation_statement": (
        "This freeze does not overwrite, mutate, relabel, upgrade, or "
        "reinterpret any legacy Entry000 or Entry001 artifact."
    ),
    "unresolved_values_remain_unresolved": True,
}

COMPONENT_SPECS = (
    (
        1,
        "HISTORICAL_ARCHITECTURE_V3_1_MARKDOWN",
        "historical_source",
        "docs/architecture/Architecture_v3.1_Final.md",
        "text/markdown",
        "3.1",
        None,
    ),
    (
        2,
        "HISTORICAL_ARCHITECTURE_V3_1_PDF",
        "historical_source",
        "docs/architecture/Architecture_v3.1_Final.pdf",
        "application/pdf",
        "3.1",
        None,
    ),
    (
        3,
        "SUCCESSOR_ARCHITECTURE_V3_2",
        "current_authority",
        "docs/architecture/Architecture_v3.2_Final.md",
        "text/markdown",
        "3.2",
        "docs/approvals/v1/architecture-v3-2-approval-001.json",
    ),
    (
        4,
        "SCREEN_SPECIFICATION_CONTRACT_V1",
        "current_authority",
        "docs/architecture/Screen_Specification_v1_Final.md",
        "text/markdown",
        "1",
        "docs/approvals/v1/screen-specification-v1-approval-001.json",
    ),
    (
        5,
        "BATCH1_RESEARCH_INTENT",
        "current_authority",
        "docs/research/Batch1_Research_Intent_Final.md",
        "text/markdown",
        "1",
        "docs/approvals/v1/batch1-research-intent-approval-001.json",
    ),
    (
        6,
        "AMENDMENT_LEDGER",
        "current_authority",
        "docs/architecture/amendments/Amendment_Ledger_v1.0.0.json",
        "application/json",
        "1.0.0",
        "docs/approvals/v1/amendment-ledger-v1-0-0-approval-001.json",
    ),
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_GIT_SHA1 = re.compile(r"[0-9a-f]{40}")
_APPROVAL_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_LEGACY_CREATED_AT = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{6})?\+00:00"
)


class Entry000Error(GovernanceError):
    """Fail-closed Entry000 schema, identity, or publication error."""


def _require_exact_keys(value: object, expected: frozenset[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Entry000Error(f"{path} must be an object")
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        raise Entry000Error(
            f"{path} has invalid keys; missing={missing}, extra={extra}"
        )
    return value


def _require_sha256(value: object, path: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise Entry000Error(f"{path} must be 64 lowercase hexadecimal characters")
    return value


def _require_commit(value: object, path: str) -> str:
    if not isinstance(value, str) or _GIT_SHA1.fullmatch(value) is None:
        raise Entry000Error(f"{path} must be a full lowercase Git SHA-1")
    return value


def _require_path(value: object, path: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise Entry000Error(f"{path} must be a normalized repository-relative path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts or str(parsed) != value:
        raise Entry000Error(f"{path} must be a normalized repository-relative path")
    return value


def _require_utc_timestamp(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise Entry000Error(f"{path} must be an RFC3339 UTC timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise Entry000Error(f"{path} must be an RFC3339 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise Entry000Error(f"{path} must be UTC")
    return value


def _decode_canonical_base64(value: object, path: str) -> bytes:
    if not isinstance(value, str):
        raise Entry000Error(f"{path} must be canonical base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise Entry000Error(f"{path} must be canonical base64") from exc
    if base64.b64encode(decoded).decode("ascii") != value:
        raise Entry000Error(f"{path} must be canonical base64")
    return decoded


def _git_blob_id(content: bytes) -> str:
    header = b"blob " + str(len(content)).encode("ascii") + b"\0"
    return hashlib.sha1(header + content).hexdigest()


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _git(repository: Path, *arguments: str, binary: bool = False) -> bytes | str:
    try:
        output = subprocess.check_output(["git", *arguments], cwd=repository)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise Entry000Error(
            f"unable to resolve Git object: {' '.join(arguments)}"
        ) from exc
    return output if binary else output.decode("utf-8").strip()


def _git_object_bytes(repository: Path, commit: str, path: str) -> tuple[str, bytes]:
    _require_commit(commit, "commit")
    _require_path(path, "path")
    blob = str(_git(repository, "rev-parse", f"{commit}:{path}"))
    content = bytes(_git(repository, "show", f"{commit}:{path}", binary=True))
    if blob != _git_blob_id(content):
        raise Entry000Error(f"Git blob mismatch for {commit}:{path}")
    return blob, content


def _identity_key(identity: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(identity["repository_id"]),
        str(identity["approval_record_path"]),
        str(identity["approval_record_commit"]),
        str(identity["approval_record_git_blob"]),
        str(identity["approval_record_exact_byte_sha256"]),
    )


def _validate_approval_identity(value: object, path: str) -> Mapping[str, Any]:
    identity = _require_exact_keys(value, APPROVAL_IDENTITY_KEYS, path)
    if identity["repository_id"] != REPOSITORY_ID:
        raise Entry000Error(f"{path}.repository_id is invalid")
    _require_path(identity["approval_record_path"], f"{path}.approval_record_path")
    _require_commit(identity["approval_record_commit"], f"{path}.approval_record_commit")
    _require_commit(identity["approval_record_git_blob"], f"{path}.approval_record_git_blob")
    _require_sha256(
        identity["approval_record_exact_byte_sha256"],
        f"{path}.approval_record_exact_byte_sha256",
    )
    return identity


def _validate_approval_record(content: bytes, path: str) -> Mapping[str, Any]:
    try:
        text = content.decode("utf-8")
        record = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Entry000Error(f"{path} is not valid UTF-8 JSON") from exc
    if canonical_json(record) + b"\n" != content:
        raise Entry000Error(f"{path} is not CanonicalJSON-v1 plus one LF")
    record = _require_exact_keys(record, APPROVAL_RECORD_KEYS, path)
    subject = _require_exact_keys(record["subject"], SUBJECT_KEYS, f"{path}.subject")
    attestation = _require_exact_keys(
        record["no_realized_outcome_attestation"],
        NO_OUTCOME_ATTESTATION_KEYS,
        f"{path}.no_realized_outcome_attestation",
    )
    if record["approval_record_schema_version"] != 1:
        raise Entry000Error(f"{path} has an unsupported schema version")
    approval_id = record["approval_id"]
    if not isinstance(approval_id, str) or _APPROVAL_ID.fullmatch(approval_id) is None:
        raise Entry000Error(f"{path}.approval_id is invalid")
    if PurePosixPath(path).stem != approval_id:
        raise Entry000Error(f"{path}.approval_id does not match its filename")
    if record["approval_type"] != "APPROVE" or record["status"] != "APPROVED":
        raise Entry000Error(f"{path} is not an APPROVE/APPROVED record")
    if record["predecessor_approval_record_identity"] is not None:
        raise Entry000Error(f"{path} has an unexpected predecessor")
    if record["researcher_id"] != "mostafa-maghsoodi":
        raise Entry000Error(f"{path}.researcher_id is invalid")
    _require_utc_timestamp(record["decided_at_utc"], f"{path}.decided_at_utc")
    if subject["repository_id"] != REPOSITORY_ID:
        raise Entry000Error(f"{path}.subject.repository_id is invalid")
    _require_path(subject["repository_relative_path"], f"{path}.subject.path")
    _require_commit(subject["source_commit"], f"{path}.subject.source_commit")
    _require_commit(subject["git_blob"], f"{path}.subject.git_blob")
    _require_sha256(subject["exact_byte_sha256"], f"{path}.subject.sha256")
    if not isinstance(subject["subject_schema_or_document_version"], str):
        raise Entry000Error(f"{path}.subject version is invalid")
    if attestation != {
        "statement_version": 1,
        "statement": "No realized strategy outcome was examined in making this approval.",
        "attested_by_researcher_id": "mostafa-maghsoodi",
        "attested_at_utc": record["decided_at_utc"],
    }:
        raise Entry000Error(f"{path} has an invalid no-outcome attestation")
    return record


def _approval_identity(
    repository: Path,
    approval_record_path: str,
    approval_record_commit: str,
) -> tuple[dict[str, str], bytes, Mapping[str, Any]]:
    blob, content = _git_object_bytes(
        repository, approval_record_commit, approval_record_path
    )
    record = _validate_approval_record(content, approval_record_path)
    identity = {
        "repository_id": REPOSITORY_ID,
        "approval_record_path": approval_record_path,
        "approval_record_commit": approval_record_commit,
        "approval_record_git_blob": blob,
        "approval_record_exact_byte_sha256": _sha256_bytes(content),
    }
    return identity, content, record


def _component_from_subject(
    repository: Path,
    spec: tuple[int, str, str, str, str, str, str | None],
    approval_identity: Mapping[str, Any],
    approval_record: Mapping[str, Any],
) -> dict[str, Any]:
    ordinal, role, authority_class, expected_path, media_type, version, _ = spec
    subject = approval_record["subject"]
    expected_subject_type = {
        "SUCCESSOR_ARCHITECTURE_V3_2": "ARCHITECTURE",
        "SCREEN_SPECIFICATION_CONTRACT_V1": "CONTRACT",
        "BATCH1_RESEARCH_INTENT": "RESEARCH_INTENT",
        "AMENDMENT_LEDGER": "AMENDMENT_LEDGER",
    }[role]
    if (
        subject["subject_type"] != expected_subject_type
        or subject["repository_relative_path"] != expected_path
        or subject["subject_schema_or_document_version"] != version
    ):
        raise Entry000Error(f"Approval Record subject does not match component {role}")
    blob, content = _git_object_bytes(
        repository, subject["source_commit"], subject["repository_relative_path"]
    )
    if (
        blob != subject["git_blob"]
        or _sha256_bytes(content) != subject["exact_byte_sha256"]
    ):
        raise Entry000Error(f"Approval Record subject bytes do not match component {role}")
    return {
        "ordinal": ordinal,
        "component_role": role,
        "authority_class": authority_class,
        "repository_relative_path": expected_path,
        "media_type": media_type,
        "document_or_schema_version": version,
        "source_commit": subject["source_commit"],
        "git_blob": blob,
        "exact_byte_sha256": _sha256_bytes(content),
        "byte_length": len(content),
        "exact_bytes_base64": base64.b64encode(content).decode("ascii"),
        "approval_record_identity": dict(approval_identity),
    }


def build_entry000_v2(
    repository: str | Path,
    *,
    authority_commit: str,
    approval_record_commits: Mapping[str, str],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the exact first Entry000 v2 payload without publishing it.

    ``approval_record_commits`` is deliberately explicit.  The builder cannot
    infer which containing commit identity the researcher externally approved.
    """

    root = Path(repository).resolve()
    _require_commit(authority_commit, "authority_commit")
    expected_record_paths = {
        spec[6] for spec in COMPONENT_SPECS if spec[6] is not None
    }
    if set(approval_record_commits) != expected_record_paths:
        raise Entry000Error(
            "approval_record_commits must contain exactly the four current-authority records"
        )
    components: list[dict[str, Any]] = []
    evidence_by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    records_by_path: dict[str, Mapping[str, Any]] = {}

    for spec in COMPONENT_SPECS:
        ordinal, role, authority_class, path, media_type, version, record_path = spec
        if record_path is None:
            blob, content = _git_object_bytes(root, authority_commit, path)
            components.append({
                "ordinal": ordinal,
                "component_role": role,
                "authority_class": authority_class,
                "repository_relative_path": path,
                "media_type": media_type,
                "document_or_schema_version": version,
                "source_commit": authority_commit,
                "git_blob": blob,
                "exact_byte_sha256": _sha256_bytes(content),
                "byte_length": len(content),
                "exact_bytes_base64": base64.b64encode(content).decode("ascii"),
                "approval_record_identity": None,
            })
            continue
        identity, record_bytes, record = _approval_identity(
            root, record_path, approval_record_commits[record_path]
        )
        component = _component_from_subject(root, spec, identity, record)
        components.append(component)
        records_by_path[record_path] = record
        evidence_by_key[_identity_key(identity)] = {
            "approval_record_identity": identity,
            "approval_record_byte_length": len(record_bytes),
            "approval_record_exact_bytes_base64": base64.b64encode(
                record_bytes
            ).decode("ascii"),
        }

    ledger_component = components[5]
    ledger = json.loads(
        base64.b64decode(ledger_component["exact_bytes_base64"], validate=True)
    )
    for entry in ledger.get("entries", ()):
        identity = _validate_approval_identity(
            entry.get("decision_approval_record_identity"),
            f"ledger.{entry.get('amendment_id')}.approval_identity",
        )
        record_path = str(identity["approval_record_path"])
        blob, record_bytes = _git_object_bytes(
            root,
            str(identity["approval_record_commit"]),
            record_path,
        )
        if (
            blob != identity["approval_record_git_blob"]
            or _sha256_bytes(record_bytes)
            != identity["approval_record_exact_byte_sha256"]
        ):
            raise Entry000Error(f"ledger Approval Record identity mismatch: {record_path}")
        _validate_approval_record(record_bytes, record_path)
        evidence_by_key[_identity_key(identity)] = {
            "approval_record_identity": dict(identity),
            "approval_record_byte_length": len(record_bytes),
            "approval_record_exact_bytes_base64": base64.b64encode(
                record_bytes
            ).decode("ascii"),
        }

    created = created_at_utc or datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    _require_utc_timestamp(created, "created_at_utc")
    evidence = sorted(
        evidence_by_key.values(),
        key=lambda item: item["approval_record_identity"]["approval_record_path"],
    )
    unsigned = {
        "entry_000_package_schema_version": 2,
        "entry": "000",
        "canonicalization_version": CANONICALIZATION,
        "repository_id": REPOSITORY_ID,
        "run_lineage": {"run1_commit": RUN1_COMMIT, "run2_commit": RUN2_COMMIT},
        "components": components,
        "approval_evidence": evidence,
        "attestations": dict(PACKAGE_ATTESTATIONS),
    }
    package_id = _sha256_bytes(canonical_json(unsigned))
    payload = {
        **unsigned,
        "package_label": f"entry000-v2-{package_id[:12]}",
        "package_id": package_id,
        "created_at_utc": created,
    }
    verify_entry000_payload(payload)
    return payload


def _subject_matches_component(
    subject: Mapping[str, Any], component: Mapping[str, Any]
) -> bool:
    return subject == {
        "subject_type": {
            "SUCCESSOR_ARCHITECTURE_V3_2": "ARCHITECTURE",
            "SCREEN_SPECIFICATION_CONTRACT_V1": "CONTRACT",
            "BATCH1_RESEARCH_INTENT": "RESEARCH_INTENT",
            "AMENDMENT_LEDGER": "AMENDMENT_LEDGER",
        }[str(component["component_role"])],
        "repository_id": REPOSITORY_ID,
        "repository_relative_path": component["repository_relative_path"],
        "source_commit": component["source_commit"],
        "git_blob": component["git_blob"],
        "exact_byte_sha256": component["exact_byte_sha256"],
        "subject_schema_or_document_version": component[
            "document_or_schema_version"
        ],
    }


def verify_entry000_payload(payload: object) -> Mapping[str, Any]:
    package = _require_exact_keys(payload, ENTRY000_TOP_LEVEL_KEYS, "Entry000PackageV2")
    if package["entry_000_package_schema_version"] != 2 or package["entry"] != "000":
        raise Entry000Error("unsupported Entry000 Package version or entry")
    if package["canonicalization_version"] != CANONICALIZATION:
        raise Entry000Error("Entry000 canonicalization version is invalid")
    if package["repository_id"] != REPOSITORY_ID:
        raise Entry000Error("Entry000 repository identity is invalid")
    if not isinstance(package["package_label"], str) or not package["package_label"]:
        raise Entry000Error("Entry000 package_label must be non-empty")
    _require_sha256(package["package_id"], "package_id")
    _require_utc_timestamp(package["created_at_utc"], "created_at_utc")
    lineage = _require_exact_keys(package["run_lineage"], RUN_LINEAGE_KEYS, "run_lineage")
    if lineage != {"run1_commit": RUN1_COMMIT, "run2_commit": RUN2_COMMIT}:
        raise Entry000Error("Entry000 run lineage is invalid")
    attestations = _require_exact_keys(
        package["attestations"], PACKAGE_ATTESTATION_KEYS, "attestations"
    )
    if dict(attestations) != PACKAGE_ATTESTATIONS:
        raise Entry000Error("Entry000 attestations are invalid")

    components = package["components"]
    if not isinstance(components, list) or len(components) != 6:
        raise Entry000Error("Entry000 must contain exactly six components")
    decoded_components: list[bytes] = []
    for index, (raw, spec) in enumerate(zip(components, COMPONENT_SPECS), start=1):
        component = _require_exact_keys(raw, COMPONENT_KEYS, f"components[{index - 1}]")
        ordinal, role, authority_class, expected_path, media, version, _ = spec
        expected_values = {
            "ordinal": ordinal,
            "component_role": role,
            "authority_class": authority_class,
            "repository_relative_path": expected_path,
            "media_type": media,
            "document_or_schema_version": version,
        }
        if any(component[name] != value for name, value in expected_values.items()):
            raise Entry000Error(f"component {index} identity/order is invalid")
        _require_commit(component["source_commit"], f"components[{index - 1}].source_commit")
        _require_commit(component["git_blob"], f"components[{index - 1}].git_blob")
        _require_sha256(component["exact_byte_sha256"], f"components[{index - 1}].sha256")
        if not isinstance(component["byte_length"], int) or isinstance(
            component["byte_length"], bool
        ) or component["byte_length"] < 0:
            raise Entry000Error(f"components[{index - 1}].byte_length is invalid")
        content = _decode_canonical_base64(
            component["exact_bytes_base64"], f"components[{index - 1}].exact_bytes_base64"
        )
        if (
            len(content) != component["byte_length"]
            or _sha256_bytes(content) != component["exact_byte_sha256"]
            or _git_blob_id(content) != component["git_blob"]
        ):
            raise Entry000Error(f"component {index} byte identity mismatch")
        if authority_class == "historical_source":
            if component["approval_record_identity"] is not None:
                raise Entry000Error("historical components require null approval identity")
        else:
            _validate_approval_identity(
                component["approval_record_identity"],
                f"components[{index - 1}].approval_record_identity",
            )
        decoded_components.append(content)

    evidence = package["approval_evidence"]
    if not isinstance(evidence, list):
        raise Entry000Error("approval_evidence must be an array")
    evidence_by_key: dict[tuple[str, str, str, str, str], tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    paths: list[str] = []
    for index, raw in enumerate(evidence):
        item = _require_exact_keys(raw, APPROVAL_EVIDENCE_KEYS, f"approval_evidence[{index}]")
        identity = _validate_approval_identity(
            item["approval_record_identity"],
            f"approval_evidence[{index}].approval_record_identity",
        )
        content = _decode_canonical_base64(
            item["approval_record_exact_bytes_base64"],
            f"approval_evidence[{index}].approval_record_exact_bytes_base64",
        )
        if not isinstance(item["approval_record_byte_length"], int) or isinstance(
            item["approval_record_byte_length"], bool
        ) or item["approval_record_byte_length"] < 0:
            raise Entry000Error("approval evidence byte length is invalid")
        if (
            len(content) != item["approval_record_byte_length"]
            or _sha256_bytes(content) != identity["approval_record_exact_byte_sha256"]
            or _git_blob_id(content) != identity["approval_record_git_blob"]
        ):
            raise Entry000Error("approval evidence byte identity mismatch")
        record_path = str(identity["approval_record_path"])
        record = _validate_approval_record(content, record_path)
        key = _identity_key(identity)
        if key in evidence_by_key:
            raise Entry000Error("duplicate approval evidence identity")
        evidence_by_key[key] = (identity, record)
        paths.append(record_path)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise Entry000Error("approval evidence must be uniquely path-sorted")

    required_keys: set[tuple[str, str, str, str, str]] = set()
    for component in components[2:]:
        identity = _validate_approval_identity(
            component["approval_record_identity"], "component approval identity"
        )
        key = _identity_key(identity)
        required_keys.add(key)
        record = evidence_by_key.get(key)
        if record is None or not _subject_matches_component(record[1]["subject"], component):
            raise Entry000Error("component approval evidence does not bind its component")

    try:
        ledger = json.loads(decoded_components[5].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Entry000Error("embedded Amendment Ledger is invalid JSON") from exc
    entries = ledger.get("entries")
    if not isinstance(entries, list) or [item.get("amendment_id") for item in entries] != [
        "ADR-001", "ADR-002", "ADR-003", "ADR-004"
    ]:
        raise Entry000Error("embedded Amendment Ledger entry set is invalid")
    for entry in entries:
        identity = _validate_approval_identity(
            entry.get("decision_approval_record_identity"),
            f"ledger.{entry.get('amendment_id')}.approval_identity",
        )
        key = _identity_key(identity)
        required_keys.add(key)
        evidence_record = evidence_by_key.get(key)
        if evidence_record is None:
            raise Entry000Error("ledger ADR approval evidence is missing")
        decision_identity = entry.get("decision_record_identity")
        subject = evidence_record[1]["subject"]
        if not isinstance(decision_identity, Mapping) or subject != {
            "subject_type": "ADR_RECORD",
            "repository_id": REPOSITORY_ID,
            "repository_relative_path": decision_identity.get("repository_relative_path"),
            "source_commit": decision_identity.get("source_commit"),
            "git_blob": decision_identity.get("git_blob"),
            "exact_byte_sha256": decision_identity.get("exact_byte_sha256"),
            "subject_schema_or_document_version": evidence_record[1]["subject"][
                "subject_schema_or_document_version"
            ],
        }:
            raise Entry000Error("ledger ADR approval subject mismatch")
    if set(evidence_by_key) != required_keys:
        raise Entry000Error("approval evidence closure is incomplete or contains extras")

    semantic = {
        key: value
        for key, value in package.items()
        if key not in {"package_label", "package_id", "created_at_utc"}
    }
    expected_package_id = _sha256_bytes(canonical_json(semantic))
    if package["package_id"] != expected_package_id:
        raise Entry000Error("Entry000 package_id does not match semantic content")
    return {
        "verification": "INTRINSIC_VERIFIED",
        "package_id": package["package_id"],
        "component_count": len(components),
        "approval_evidence_count": len(evidence),
    }


def verify_entry000_repository(
    payload: object, repository: str | Path
) -> Mapping[str, Any]:
    intrinsic = verify_entry000_payload(payload)
    package = payload
    assert isinstance(package, Mapping)
    root = Path(repository).resolve()
    for component in package["components"]:
        blob, content = _git_object_bytes(
            root,
            str(component["source_commit"]),
            str(component["repository_relative_path"]),
        )
        embedded = base64.b64decode(component["exact_bytes_base64"], validate=True)
        if blob != component["git_blob"] or content != embedded:
            raise Entry000Error("repository component provenance mismatch")
    for evidence in package["approval_evidence"]:
        identity = evidence["approval_record_identity"]
        blob, content = _git_object_bytes(
            root,
            str(identity["approval_record_commit"]),
            str(identity["approval_record_path"]),
        )
        embedded = base64.b64decode(
            evidence["approval_record_exact_bytes_base64"], validate=True
        )
        if blob != identity["approval_record_git_blob"] or content != embedded:
            raise Entry000Error("repository approval provenance mismatch")
    return {**intrinsic, "verification": "REPOSITORY_VERIFIED"}


def _publication_bytes(payload: Mapping[str, Any]) -> tuple[bytes, str, bytes]:
    content = canonical_json(payload) + b"\n"
    digest = _sha256_bytes(content)
    sidecar = f"{digest}  entry000.package.json\n".encode("ascii")
    return content, digest, sidecar


def verify_entry000_publication(
    artifact_path: str | Path,
    *,
    repository: str | Path | None = None,
) -> Mapping[str, Any]:
    target = Path(artifact_path)
    sidecar_path = target.with_suffix(".sha256")
    if target.is_symlink() or sidecar_path.is_symlink():
        raise Entry000Error("Entry000 publication paths must not be symlinks")
    try:
        content = target.read_bytes()
        sidecar = sidecar_path.read_bytes()
        payload = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Entry000Error("Entry000 publication is missing or invalid") from exc
    expected_content, digest, expected_sidecar = _publication_bytes(payload)
    if content != expected_content:
        raise Entry000Error("Entry000 artifact is not canonical JSON plus one LF")
    if sidecar != expected_sidecar:
        raise Entry000Error("Entry000 sidecar does not match exact artifact bytes")
    result = (
        verify_entry000_repository(payload, repository)
        if repository is not None
        else verify_entry000_payload(payload)
    )
    expected_parent = Path("artifacts/entry000/v2") / str(payload["package_id"])
    normalized = PurePosixPath(target.as_posix())
    if tuple(normalized.parts[-5:-1]) != tuple(expected_parent.parts):
        raise Entry000Error("Entry000 publication path does not match package_id")
    if target.name != "entry000.package.json":
        raise Entry000Error("Entry000 artifact filename is invalid")
    return {**result, "full_artifact_sha256": digest}


def _write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_entry000_v2(
    repository: str | Path,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Publish one immutable Entry000 v2 directory using the contract state machine."""

    root = Path(repository).resolve()
    verified = verify_entry000_repository(payload, root)
    package_id = str(verified["package_id"])
    parent = root / "artifacts" / "entry000" / "v2"
    final_directory = parent / package_id
    artifact_path = final_directory / "entry000.package.json"
    content, digest, sidecar = _publication_bytes(payload)
    parent.mkdir(parents=True, exist_ok=True)
    git_dir_text = str(_git(root, "rev-parse", "--git-dir"))
    git_dir = Path(git_dir_text)
    if not git_dir.is_absolute():
        git_dir = root / git_dir
    lock_dir = git_dir / "graham-research-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_key = canonical_json([
        REPOSITORY_ID,
        "ENTRY000_PACKAGE_V2",
        package_id,
        str(artifact_path.relative_to(root)),
    ])
    lock_path = lock_dir / f"{_sha256_bytes(lock_key)}.lock"
    lock_handle = lock_path.open("a+b")
    try:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Entry000Error("LIVE_PUBLICATION_ATTEMPT_EXISTS") from exc
        if final_directory.exists() or final_directory.is_symlink():
            try:
                existing = verify_entry000_publication(
                    artifact_path, repository=root
                )
            except Entry000Error as exc:
                raise Entry000Error("CORRUPT_EXISTING_PUBLICATION") from exc
            if existing["package_id"] == package_id:
                return {
                    **existing,
                    "publication_result": "ALREADY_EXISTS_VERIFIED",
                    "publication_path": str(artifact_path.relative_to(root)),
                }
            raise Entry000Error("PUBLICATION_IDENTITY_CONFLICT")
        attempt = parent / f".entry000-{package_id}-{uuid4()}.private"
        attempt.mkdir(mode=0o700)
        attempt_artifact = attempt / "entry000.package.json"
        attempt_sidecar = attempt / "entry000.package.sha256"
        try:
            _write_exclusive(attempt_artifact, content)
            _write_exclusive(attempt_sidecar, sidecar)
            _fsync_directory(attempt)
            verify_entry000_payload(json.loads(attempt_artifact.read_text("utf-8")))
            if attempt_artifact.read_bytes() != content or attempt_sidecar.read_bytes() != sidecar:
                raise Entry000Error("private publication verification failed")
            if final_directory.exists() or final_directory.is_symlink():
                raise Entry000Error("PUBLICATION_IDENTITY_CONFLICT")
            os.rename(attempt, final_directory)
            _fsync_directory(parent)
        except Exception as exc:
            raise Entry000Error(f"FAILED_PRIVATE: {attempt.name}: {exc}") from exc
        result = verify_entry000_publication(artifact_path, repository=root)
        return {
            **result,
            "publication_result": "SUCCESS",
            "publication_path": str(artifact_path.relative_to(root)),
            "full_artifact_sha256": digest,
        }
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


LEGACY_ENTRY000_KEYS = frozenset({
    "entry",
    "architecture_version",
    "created_at",
    "architecture_sha256",
    "architecture_text",
    "statement",
    "unresolved_operational_items",
})
LEGACY_UNRESOLVED_ITEMS = [
    "data-audit findings",
    "exact investable-universe values",
    "proxy-registry formulas selected for the cycle",
    "estimate-data admissibility",
    "sample boundaries",
    "numeric specification budget",
    "transaction costs",
    "rebalance frequency and holding period",
    "audit-dependent statistical implementation details",
]


def verify_legacy_entry000_v1(artifact_path: str | Path) -> str:
    target = Path(artifact_path)
    try:
        content = target.read_bytes()
        payload = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Entry000Error("legacy Entry000 is missing or invalid") from exc
    payload = _require_exact_keys(payload, LEGACY_ENTRY000_KEYS, "LegacyEntry000V1")
    if content != canonical_json(payload) + b"\n":
        raise Entry000Error("legacy Entry000 bytes are not canonical")
    if payload["entry"] != "000" or payload["architecture_version"] != "3.1":
        raise Entry000Error("legacy Entry000 identity is invalid")
    if not isinstance(payload["architecture_text"], str):
        raise Entry000Error("legacy architecture_text must be a JSON string")
    architecture_digest = _sha256_bytes(payload["architecture_text"].encode("utf-8"))
    if payload["architecture_sha256"] != architecture_digest:
        raise Entry000Error("legacy architecture digest mismatch")
    created = payload["created_at"]
    if not isinstance(created, str) or _LEGACY_CREATED_AT.fullmatch(created) is None:
        raise Entry000Error("legacy created_at spelling is invalid")
    try:
        parsed = datetime.fromisoformat(created)
    except ValueError as exc:
        raise Entry000Error("legacy created_at is invalid") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed) or parsed.isoformat() != created:
        raise Entry000Error("legacy created_at must round-trip as UTC isoformat")
    if payload["statement"] != (
        "No strategy-return results were examined in designing Architecture v3.1."
    ):
        raise Entry000Error("legacy no-outcome statement is invalid")
    if payload["unresolved_operational_items"] != LEGACY_UNRESOLVED_ITEMS:
        raise Entry000Error("legacy unresolved-item list is invalid")
    digest = _sha256_bytes(canonical_json(payload))
    sidecar = target.with_suffix(target.suffix + ".sha256")
    try:
        actual_sidecar = sidecar.read_bytes()
    except OSError as exc:
        raise Entry000Error("legacy Entry000 sidecar is missing") from exc
    expected_sidecar = f"{digest}  {target.name}\n".encode("ascii")
    if actual_sidecar != expected_sidecar:
        raise Entry000Error("legacy Entry000 sidecar is invalid")
    return digest


def verify_entry000_dispatch(
    artifact_path: str | Path,
    *,
    repository: str | Path | None = None,
) -> str:
    target = Path(artifact_path)
    try:
        payload = json.loads(target.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Entry000Error("Entry000 artifact is missing or invalid") from exc
    if "entry_000_package_schema_version" in payload:
        if payload["entry_000_package_schema_version"] != 2:
            raise Entry000Error("unsupported Entry000 package schema version")
        return str(
            verify_entry000_publication(target, repository=repository)[
                "full_artifact_sha256"
            ]
        )
    return verify_legacy_entry000_v1(target)
