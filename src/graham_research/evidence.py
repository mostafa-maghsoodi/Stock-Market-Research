"""Safe local evidence collection and non-governing manifest candidates.

Raw provider bytes are written outside Git by default.  The resulting identity
metadata is content-bound but does not admit the evidence for production.
"""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlencode, urlparse

from .governance import canonical_json
from .production import EvidenceIdentity, ProductionContractError


SECRET_PARAMETER_FRAGMENTS = ("api_key", "apikey", "token", "secret", "password", "authorization")
ALLOWED_PROVIDER_PRODUCTS = {
    "SEC_EDGAR": frozenset({"FILING_ARCHIVE"}),
    "MASSIVE": frozenset({"STOCKS_REFERENCE"}),
    "DATABENTO": frozenset({"XNAS.ITCH", "XNYS.PILLAR", "XASE.PILLAR"}),
    "OFFICIAL_EXCHANGE_CALENDAR": frozenset({"NYSE_CALENDAR", "NASDAQ_CALENDAR"}),
}


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductionContractError(f"{label} must be a non-empty string")
    return value.strip()


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None:
        raise ProductionContractError(f"{label} must be timezone-aware")
    return value


def _safe_parameters(parameters: Mapping[str, object]) -> dict[str, object]:
    safe: dict[str, object] = {}
    for key, value in parameters.items():
        lowered = key.lower().replace("-", "_")
        if any(fragment in lowered for fragment in SECRET_PARAMETER_FRAGMENTS):
            raise ProductionContractError(f"secret-like request parameter forbidden: {key}")
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        else:
            raise ProductionContractError(f"request parameter {key} has unsupported type")
    return dict(sorted(safe.items()))


def _validate_endpoint(provider: str, endpoint: str) -> str:
    parsed = urlparse(_nonempty(endpoint, "endpoint"))
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProductionContractError("endpoint must be secret-free HTTPS without query or credentials")
    host = (parsed.hostname or "").lower()
    allowed = {
        "SEC_EDGAR": host == "www.sec.gov" or host == "data.sec.gov" or host.endswith(".sec.gov"),
        "MASSIVE": host == "api.massive.com",
        "DATABENTO": host == "hist.databento.com" or host == "api.databento.com",
        "OFFICIAL_EXCHANGE_CALENDAR": host in {"www.nyse.com", "nyse.com", "www.nasdaqtrader.com", "nasdaqtrader.com"},
    }
    if not allowed.get(provider, False):
        raise ProductionContractError("endpoint host is not allowed for provider")
    return endpoint


@dataclass(frozen=True)
class EvidenceRequest:
    request_id: str
    provider: str
    provider_product: str
    endpoint: str
    request_parameters: Mapping[str, object]
    source_native_vintage_identifier: str
    historical_effective_start: date | None
    historical_effective_end: date | None

    def __post_init__(self) -> None:
        _nonempty(self.request_id, "request_id")
        if self.provider not in ALLOWED_PROVIDER_PRODUCTS:
            raise ProductionContractError("evidence provider is not closed")
        if self.provider_product not in ALLOWED_PROVIDER_PRODUCTS[self.provider]:
            raise ProductionContractError("provider product is not the closed collector product")
        if self.provider == "DATABENTO" and self.request_parameters.get("dataset") != self.provider_product:
            raise ProductionContractError("Databento dataset/product mismatch")
        _validate_endpoint(self.provider, self.endpoint)
        _safe_parameters(self.request_parameters)
        _nonempty(self.source_native_vintage_identifier, "source_native_vintage_identifier")
        if (
            self.historical_effective_start is not None
            and self.historical_effective_end is not None
            and self.historical_effective_end < self.historical_effective_start
        ):
            raise ProductionContractError("historical effective range is inverted")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceRequest":
        expected = {
            "request_id", "provider", "provider_product", "endpoint",
            "request_parameters", "source_native_vintage_identifier",
            "historical_effective_start", "historical_effective_end",
        }
        if set(value) != expected:
            raise ProductionContractError("evidence request keys are not closed")
        return cls(
            request_id=value["request_id"], provider=value["provider"],
            provider_product=value["provider_product"], endpoint=value["endpoint"],
            request_parameters=dict(value["request_parameters"]),
            source_native_vintage_identifier=value["source_native_vintage_identifier"],
            historical_effective_start=(
                date.fromisoformat(value["historical_effective_start"])
                if value["historical_effective_start"] else None
            ),
            historical_effective_end=(
                date.fromisoformat(value["historical_effective_end"])
                if value["historical_effective_end"] else None
            ),
        )


@dataclass(frozen=True)
class SafeHttpResponse:
    status: int
    body: bytes


Transport = Callable[[EvidenceRequest, Mapping[str, str]], SafeHttpResponse]


def _auth_headers(request: EvidenceRequest, *, sec_user_agent: str | None) -> Mapping[str, str]:
    if request.provider == "SEC_EDGAR":
        return {
            "User-Agent": _nonempty(sec_user_agent, "SEC compliant User-Agent"),
            "Accept-Encoding": "gzip, deflate",
        }
    if request.provider == "MASSIVE":
        key = os.environ.get("MASSIVE_API_KEY")
        if not key:
            raise ProductionContractError("MASSIVE_API_KEY is not available")
        return {"Authorization": f"Bearer {key}"}
    if request.provider == "DATABENTO":
        key = os.environ.get("DATABENTO_API_KEY")
        if not key:
            raise ProductionContractError("DATABENTO_API_KEY is not available")
        encoded = base64.b64encode(f"{key}:".encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    return {}


def _https_transport(request: EvidenceRequest, headers: Mapping[str, str]) -> SafeHttpResponse:
    parameters = _safe_parameters(request.request_parameters)
    query = urlencode(parameters)
    parsed = urlparse(request.endpoint)
    host = parsed.hostname
    if host is None:
        raise ProductionContractError("evidence endpoint host is missing")
    path = parsed.path or "/"
    if query:
        path = f"{path}?{query}"
    # Deliberately do not follow redirects: credentials remain scoped to the
    # already validated official host, and redirect/large-download behavior is
    # an explicit failure rather than an implicit authority expansion.
    connection = http.client.HTTPSConnection(host, parsed.port or 443, timeout=60)
    try:
        connection.request("GET", path, headers=dict(headers))
        response = connection.getresponse()
        return SafeHttpResponse(response.status, response.read())
    finally:
        connection.close()


@dataclass(frozen=True)
class CollectedEvidence:
    schema_version: int
    artifact_status: str
    identity: EvidenceIdentity
    request_id: str
    endpoint: str
    request_parameters: Mapping[str, object]
    historical_effective_start: date | None
    historical_effective_end: date | None
    exact_byte_length: int
    raw_file_path: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CollectedEvidence":
        expected = {
            "schema_version", "artifact_status", "identity", "request_id",
            "endpoint", "request_parameters", "historical_effective_start",
            "historical_effective_end", "exact_byte_length", "raw_file_path",
        }
        if set(value) != expected:
            raise ProductionContractError("collected evidence metadata keys are not closed")
        return cls(
            schema_version=value["schema_version"], artifact_status=value["artifact_status"],
            identity=EvidenceIdentity.from_mapping(value["identity"]),
            request_id=value["request_id"], endpoint=value["endpoint"],
            request_parameters=dict(value["request_parameters"]),
            historical_effective_start=(
                date.fromisoformat(value["historical_effective_start"])
                if value["historical_effective_start"] else None
            ),
            historical_effective_end=(
                date.fromisoformat(value["historical_effective_end"])
                if value["historical_effective_end"] else None
            ),
            exact_byte_length=value["exact_byte_length"], raw_file_path=value["raw_file_path"],
        )

    def metadata_mapping(self) -> Mapping[str, object]:
        identity = asdict(self.identity)
        identity["acquired_at_utc"] = self.identity.acquired_at_utc.isoformat()
        return {
            "schema_version": self.schema_version,
            "artifact_status": self.artifact_status,
            "identity": identity,
            "request_id": self.request_id,
            "endpoint": self.endpoint,
            "request_parameters": dict(self.request_parameters),
            "historical_effective_start": (
                self.historical_effective_start.isoformat() if self.historical_effective_start else None
            ),
            "historical_effective_end": (
                self.historical_effective_end.isoformat() if self.historical_effective_end else None
            ),
            "exact_byte_length": self.exact_byte_length,
            "raw_file_path": self.raw_file_path,
        }


def _git_root(path: Path) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=path,
        capture_output=True, text=True,
    )
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else None


def _outside_git_output(output_directory: Path, repository: Path | None) -> Path:
    output = output_directory.expanduser().resolve()
    root = repository.resolve() if repository else _git_root(Path.cwd())
    if root is not None and (output == root or root in output.parents):
        raise ProductionContractError("raw evidence output must be outside Git")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    return output


def collect_evidence(
    request: EvidenceRequest,
    *,
    output_directory: str | Path,
    repository: str | Path | None = None,
    sec_user_agent: str | None = None,
    transport: Transport | None = None,
    acquired_at_utc: datetime | None = None,
) -> CollectedEvidence:
    output = _outside_git_output(
        Path(output_directory), Path(repository) if repository is not None else None
    )
    headers = _auth_headers(request, sec_user_agent=sec_user_agent)
    response = (transport or _https_transport)(request, headers)
    if response.status != 200:
        raise ProductionContractError(f"evidence request failed with HTTP {response.status}")
    body = bytes(response.body)
    if not body:
        raise ProductionContractError("evidence response is empty")
    content_sha256 = hashlib.sha256(body).hexdigest()
    safe_parameters = _safe_parameters(request.request_parameters)
    identity_material = {
        "provider": request.provider,
        "provider_product": request.provider_product,
        "content_sha256": content_sha256,
        "source_native_vintage_identifier": request.source_native_vintage_identifier,
        "endpoint": request.endpoint,
        "request_parameters": safe_parameters,
        "historical_effective_start": (
            request.historical_effective_start.isoformat() if request.historical_effective_start else None
        ),
        "historical_effective_end": (
            request.historical_effective_end.isoformat() if request.historical_effective_end else None
        ),
    }
    evidence_id = hashlib.sha256(canonical_json(identity_material)).hexdigest()
    acquired = _aware(acquired_at_utc or datetime.now(timezone.utc), "acquired_at_utc")
    raw_path = output / f"{evidence_id}.bin"
    metadata_path = output / f"{evidence_id}.identity.json"
    raw_path.write_bytes(body)
    identity = EvidenceIdentity(
        evidence_id=evidence_id, provider=request.provider,
        provider_product=request.provider_product, content_sha256=content_sha256,
        source_native_vintage_identifier=request.source_native_vintage_identifier,
        acquired_at_utc=acquired, repository_relative_path=None,
    )
    collected = CollectedEvidence(
        1, "CANDIDATE_EVIDENCE_NOT_ADMITTED", identity, request.request_id,
        request.endpoint, safe_parameters, request.historical_effective_start,
        request.historical_effective_end, len(body), str(raw_path),
    )
    metadata_path.write_bytes(canonical_json(collected.metadata_mapping()))
    return collected


def revalidate_collected_evidence(collected: CollectedEvidence) -> None:
    raw_path = Path(collected.raw_file_path)
    if not raw_path.is_file():
        raise ProductionContractError("collected evidence bytes are missing")
    content = raw_path.read_bytes()
    if len(content) != collected.exact_byte_length:
        raise ProductionContractError("EVIDENCE_BYTE_LENGTH_MISMATCH")
    if hashlib.sha256(content).hexdigest() != collected.identity.content_sha256:
        raise ProductionContractError("EVIDENCE_SHA256_MISMATCH")
    identity_material = {
        "provider": collected.identity.provider,
        "provider_product": collected.identity.provider_product,
        "content_sha256": collected.identity.content_sha256,
        "source_native_vintage_identifier": collected.identity.source_native_vintage_identifier,
        "endpoint": collected.endpoint,
        "request_parameters": _safe_parameters(collected.request_parameters),
        "historical_effective_start": (
            collected.historical_effective_start.isoformat() if collected.historical_effective_start else None
        ),
        "historical_effective_end": (
            collected.historical_effective_end.isoformat() if collected.historical_effective_end else None
        ),
    }
    expected_id = hashlib.sha256(canonical_json(identity_material)).hexdigest()
    if expected_id != collected.identity.evidence_id:
        raise ProductionContractError("EVIDENCE_IDENTITY_MISMATCH")


@dataclass(frozen=True)
class CandidateProductionEvidenceManifest:
    schema_version: int
    artifact_status: str
    sec_source_evidence: tuple[EvidenceIdentity, ...]
    massive_reference_evidence: tuple[EvidenceIdentity, ...]
    databento_market_evidence: tuple[EvidenceIdentity, ...]
    official_session_evidence: tuple[EvidenceIdentity, ...]
    field_catalog_identity: EvidenceIdentity
    crosswalk_identity: EvidenceIdentity
    configuration_identity: str
    implementation_commit: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CandidateProductionEvidenceManifest":
        expected = {
            "schema_version", "artifact_status", "sec_source_evidence",
            "massive_reference_evidence", "databento_market_evidence",
            "official_session_evidence", "field_catalog_identity",
            "crosswalk_identity", "configuration_identity", "implementation_commit",
        }
        if set(value) != expected:
            raise ProductionContractError("candidate manifest keys are not closed")
        return cls(
            schema_version=value["schema_version"], artifact_status=value["artifact_status"],
            sec_source_evidence=tuple(
                EvidenceIdentity.from_mapping(item) for item in value["sec_source_evidence"]
            ),
            massive_reference_evidence=tuple(
                EvidenceIdentity.from_mapping(item) for item in value["massive_reference_evidence"]
            ),
            databento_market_evidence=tuple(
                EvidenceIdentity.from_mapping(item) for item in value["databento_market_evidence"]
            ),
            official_session_evidence=tuple(
                EvidenceIdentity.from_mapping(item) for item in value["official_session_evidence"]
            ),
            field_catalog_identity=EvidenceIdentity.from_mapping(value["field_catalog_identity"]),
            crosswalk_identity=EvidenceIdentity.from_mapping(value["crosswalk_identity"]),
            configuration_identity=value["configuration_identity"],
            implementation_commit=value["implementation_commit"],
        )

    @classmethod
    def load(cls, path: str | Path) -> "CandidateProductionEvidenceManifest":
        return cls.from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))

    def blockers(self) -> tuple[str, ...]:
        blockers = []
        if self.schema_version != 1:
            blockers.append("CANDIDATE_MANIFEST_SCHEMA_UNSUPPORTED")
        if self.artifact_status != "NOT_PRODUCTION_ADMITTED":
            blockers.append("CANDIDATE_MANIFEST_STATUS_INVALID")
        for label, identities in (
            ("SEC", self.sec_source_evidence),
            ("MASSIVE", self.massive_reference_evidence),
            ("DATABENTO", self.databento_market_evidence),
            ("SESSION", self.official_session_evidence),
        ):
            if not identities:
                blockers.append(f"CANDIDATE_MANIFEST_{label}_EVIDENCE_MISSING")
        expected_providers = (
            ("SEC", self.sec_source_evidence, "SEC_EDGAR"),
            ("MASSIVE", self.massive_reference_evidence, "MASSIVE"),
            ("DATABENTO", self.databento_market_evidence, "DATABENTO"),
            ("SESSION", self.official_session_evidence, "OFFICIAL_EXCHANGE_CALENDAR"),
        )
        for label, identities, expected_provider in expected_providers:
            if any(item.provider != expected_provider for item in identities):
                blockers.append(f"CANDIDATE_MANIFEST_{label}_PROVIDER_MISMATCH")
        if (
            len(self.configuration_identity) != 64
            or any(char not in "0123456789abcdef" for char in self.configuration_identity)
        ):
            blockers.append("CANDIDATE_MANIFEST_CONFIGURATION_IDENTITY_INVALID")
        if (
            len(self.implementation_commit) != 40
            or any(char not in "0123456789abcdef" for char in self.implementation_commit)
        ):
            blockers.append("CANDIDATE_MANIFEST_IMPLEMENTATION_COMMIT_INVALID")
        # A candidate is intentionally never admitted by this type.
        blockers.append("NOT_PRODUCTION_ADMITTED")
        return tuple(sorted(set(blockers)))


def load_evidence_requests(path: str | Path) -> tuple[EvidenceRequest, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(payload) != {"schema_version", "artifact_status", "requests"}:
        raise ProductionContractError("collector request manifest keys are not closed")
    if payload["schema_version"] != 1 or payload["artifact_status"] != "NON_EVIDENCE_REQUEST_TEMPLATE":
        raise ProductionContractError("collector request manifest status/schema is invalid")
    requests = tuple(EvidenceRequest.from_mapping(item) for item in payload["requests"])
    if not requests:
        raise ProductionContractError("collector request manifest is empty")
    return requests
