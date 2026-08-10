"""Append-only, preflight-bound specification registration and budgeting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import MappingProxyType
from typing import Any, Iterable, Mapping
from uuid import UUID, uuid4

from .governance import GovernanceError, canonical_json


REGISTER_SCHEMA_VERSION = 2
RESERVATION_SEMANTICS = (
    "Every research_specification OPEN counts as used. No slot-release event "
    "exists while post-OPEN release policy remains unresolved; this conservative "
    "interim accounting cannot create additional research budget."
)

PREPARED_LINEAGE_KEYS = frozenset({
    "entry_001_sha256",
    "research_vintage_bundle_id",
    "fact_source_kind",
    "fact_source_id",
    "fact_source_native_vintage_identifier",
    "fact_source_content_sha256",
    "fact_source_audit_artifact_sha256",
    "fact_source_manifest_sha256",
    "return_source_kind",
    "return_source_id",
    "return_source_native_vintage_identifier",
    "return_source_content_sha256",
    "return_source_audit_artifact_sha256",
    "return_source_manifest_sha256",
    "ranked_frame_digest",
    "ranked_frame_digest_scope",
    "proxy_registry_digest",
    "ranking_configuration_digest",
    "feature_generation_code_commit",
    "ranking_code_commit",
    "execution_code_commit",
})
PRIMARY_PARAMETER_KEYS = frozenset({
    "sample_partition",
    "sample_partition_boundaries",
    "portfolio_construction",
    "terminal_position_policy",
    "portfolio_timing",
    "transaction_cost_model",
    "specification_budget",
    "specification_counting_rules",
})
_BLOCKED_KEYS = frozenset({
    "schema_version", "event_id", "event_type", "timestamp", "stage",
    "run_class", "run_type", "rationale", "invalidated_specification_id",
    "failure_classification", "message", "budget_effect",
})
_OPEN_KEYS = frozenset({
    "schema_version", "event_id", "event_type", "timestamp",
    "specification_id", "run_class", "run_type", "rationale",
    "invalidated_specification_id", "lineage", "primary_parameters",
    "prepared_experiment_digest", "budget_effect", "reservation_semantics",
    "open_event_digest",
})
_CLOSE_KEYS = frozenset({
    "schema_version", "event_id", "event_type", "timestamp",
    "specification_id", "open_event_id", "status", "output_artifacts",
    "failure_classification", "failure_message", "budget_effect",
})


class SpecificationError(GovernanceError):
    pass


class BudgetExhausted(SpecificationError):
    pass


class RunClass(str, Enum):
    RESEARCH_SPECIFICATION = "research_specification"
    DATA_CORRECTION = "data_correction"
    DIAGNOSTIC = "diagnostic"


class RunType(str, Enum):
    PORTFOLIO_BACKTEST = "portfolio_backtest"


@dataclass(frozen=True)
class SpecificationRequest:
    run_class: RunClass
    rationale: str
    run_type: RunType
    invalidated_specification_id: str | None = None

    def __post_init__(self) -> None:
        try:
            run_class = RunClass(self.run_class)
            run_type = RunType(self.run_type)
        except (TypeError, ValueError) as exc:
            raise SpecificationError("run_class and run_type use closed enums") from exc
        object.__setattr__(self, "run_class", run_class)
        object.__setattr__(self, "run_type", run_type)
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise SpecificationError("a contemporaneous rationale is required")
        prior = self.invalidated_specification_id
        if run_class is RunClass.DATA_CORRECTION:
            if not isinstance(prior, str) or not prior.strip():
                raise SpecificationError(
                    "data_correction requires an invalidated specification ID"
                )
        elif prior is not None:
            raise SpecificationError(
                "invalidated specification linkage is only valid for data_correction"
            )


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_json(item) for item in value)
    return value


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _sha256_payload(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _canonical_value(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _open_event_digest(event_without_digest: Mapping[str, Any]) -> str:
    return _sha256_payload(event_without_digest)


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


def _require_uuid(value: object, description: str) -> None:
    if not isinstance(value, str):
        raise SpecificationError(f"{description} must be a canonical UUID string")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError) as exc:
        raise SpecificationError(f"{description} must be a UUID") from exc
    if str(parsed) != value:
        raise SpecificationError(f"{description} must be a canonical UUID string")


_OPEN_TOKEN = object()


@dataclass(frozen=True, init=False)
class OpenedSpecification:
    specification_id: str
    run_class: RunClass
    run_type: RunType
    open_event_id: str
    open_event_digest: str
    prepared_experiment_digest: str
    lineage: Mapping[str, Any]
    primary_parameters: Mapping[str, Any]
    register_path: Path

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _OPEN_TOKEN:
            raise TypeError(
                "OpenedSpecification is issued only by the integrated post-preflight OPEN"
            )
        for name in self.__annotations__:
            value = values[name]
            if name in {"lineage", "primary_parameters"}:
                value = _freeze_json(value)
            object.__setattr__(self, name, value)


_EXECUTION_TOKEN = object()


@dataclass(frozen=True, init=False)
class _ExecutionAuthorization:
    specification_id: str
    open_event_id: str
    open_event_digest: str
    prepared_experiment_digest: str
    run_class: str
    run_type: str
    lineage: Mapping[str, Any]

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _EXECUTION_TOKEN:
            raise TypeError("execution authorization is internal")
        for name in self.__annotations__:
            value = values[name]
            if name == "lineage":
                value = _freeze_json(value)
            object.__setattr__(self, name, value)


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def default_register_path(repository: str | Path) -> Path:
    root_text = os.environ.get("GRAHAM_RESEARCH_STATE_DIR")
    if root_text:
        root = Path(root_text).expanduser()
    else:
        xdg = os.environ.get("XDG_STATE_HOME")
        root = (
            Path(xdg).expanduser() / "graham_research"
            if xdg
            else Path.home() / ".local" / "state" / "graham_research"
        )
    return root / "specification-register.jsonl"


def _validate_register_path(repository: Path, target: Path) -> None:
    if not _inside(target, repository):
        return
    relative = target.relative_to(repository)
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", str(relative)],
        cwd=repository,
        check=False,
        capture_output=True,
    ).returncode == 0
    if not ignored:
        raise SpecificationError(
            "a register inside the repository must be explicitly gitignored"
        )


class SpecificationRegister:
    """Strictly validated JSONL history; writes require repository path governance."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self._repository: Path | None = None

    @classmethod
    def for_repository(
        cls,
        repository: str | Path,
        *,
        path: str | Path | None = None,
    ) -> "SpecificationRegister":
        repository_path = Path(repository).expanduser().resolve()
        target = (
            Path(path).expanduser().resolve()
            if path is not None
            else default_register_path(repository_path).expanduser().resolve()
        )
        _validate_register_path(repository_path, target)
        register = cls(target)
        register._repository = repository_path
        return register

    def _assert_write_authority(self) -> None:
        if self._repository is None:
            raise SpecificationError(
                "register writes require SpecificationRegister.for_repository(...)"
            )
        _validate_register_path(self._repository, self.path)

    def assert_governed_for_repository(self, repository: str | Path) -> None:
        self._assert_write_authority()
        if self._repository != Path(repository).expanduser().resolve():
            raise SpecificationError("register is governed for another repository")

    def _open_locked(self):
        self._assert_write_authority()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    @classmethod
    def _read_locked(cls, handle) -> list[dict[str, Any]]:
        handle.seek(0)
        events: list[dict[str, Any]] = []
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SpecificationError(
                    f"malformed register event at line {line_number}"
                ) from exc
            if not isinstance(event, dict):
                raise SpecificationError(
                    f"register event at line {line_number} is not an object"
                )
            events.append(event)
        cls._validate_history(events)
        return events

    @staticmethod
    def _append_locked(handle, event: Mapping[str, Any]) -> None:
        handle.seek(0, os.SEEK_END)
        handle.write(canonical_json(event) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())

    @classmethod
    def _validate_history(cls, events: Iterable[Mapping[str, Any]]) -> None:
        event_ids: set[str] = set()
        opens_by_specification: dict[str, Mapping[str, Any]] = {}
        opens_by_event: dict[str, Mapping[str, Any]] = {}
        closed_specifications: set[str] = set()
        for position, event in enumerate(events, start=1):
            event_type = event.get("event_type")
            expected = {
                "blocked": _BLOCKED_KEYS,
                "open": _OPEN_KEYS,
                "close": _CLOSE_KEYS,
            }.get(event_type)
            if expected is None:
                raise SpecificationError(
                    f"register event {position} has unsupported event_type"
                )
            missing = sorted(expected - set(event))
            extra = sorted(set(event) - expected)
            if missing or extra:
                raise SpecificationError(
                    f"register event {position} has invalid keys; "
                    f"missing={missing}, extra={extra}"
                )
            if event["schema_version"] != REGISTER_SCHEMA_VERSION:
                raise SpecificationError("register schema version is unsupported")
            _require_uuid(event["event_id"], "register event_id")
            if event["event_id"] in event_ids:
                raise SpecificationError("duplicate register event_id")
            event_ids.add(event["event_id"])
            try:
                timestamp = datetime.fromisoformat(str(event["timestamp"]))
            except (TypeError, ValueError) as exc:
                raise SpecificationError("register timestamp is invalid") from exc
            if timestamp.tzinfo is None:
                raise SpecificationError("register timestamp must be timezone-aware")

            if event_type == "blocked":
                cls._validate_blocked_event(event)
                continue
            if event_type == "open":
                cls._validate_open_event(event)
                specification_id = str(event["specification_id"])
                if specification_id in opens_by_specification:
                    raise SpecificationError("duplicate OPEN specification_id")
                opens_by_specification[specification_id] = event
                opens_by_event[str(event["event_id"])] = event
                continue
            cls._validate_close_event(event)
            specification_id = str(event["specification_id"])
            opened = opens_by_specification.get(specification_id)
            if opened is None:
                raise SpecificationError("CLOSE does not reference a prior OPEN")
            if event["open_event_id"] != opened["event_id"]:
                raise SpecificationError("CLOSE open_event_id does not match OPEN")
            if event["open_event_id"] not in opens_by_event:
                raise SpecificationError("CLOSE references an unknown OPEN event")
            if specification_id in closed_specifications:
                raise SpecificationError("specification has more than one CLOSE")
            closed_specifications.add(specification_id)

    @staticmethod
    def _validate_request_fields(event: Mapping[str, Any]) -> tuple[RunClass, RunType]:
        try:
            run_class = RunClass(event["run_class"])
            run_type = RunType(event["run_type"])
        except (TypeError, ValueError) as exc:
            raise SpecificationError("register run class/type is invalid") from exc
        if not isinstance(event["rationale"], str) or not event["rationale"].strip():
            raise SpecificationError("register rationale is invalid")
        invalidated = event["invalidated_specification_id"]
        if run_class is RunClass.DATA_CORRECTION:
            if not isinstance(invalidated, str) or not invalidated.strip():
                raise SpecificationError("data-correction linkage is missing")
        elif invalidated is not None:
            raise SpecificationError("unexpected invalidated-specification linkage")
        return run_class, run_type

    @classmethod
    def _validate_blocked_event(cls, event: Mapping[str, Any]) -> None:
        cls._validate_request_fields(event)
        for name in ("stage", "failure_classification", "message"):
            if not isinstance(event[name], str) or not event[name].strip():
                raise SpecificationError(f"blocked event {name} is invalid")
        if event["budget_effect"] != "none_no_open":
            raise SpecificationError("blocked event budget effect is invalid")

    @classmethod
    def _validate_open_event(cls, event: Mapping[str, Any]) -> None:
        run_class, run_type = cls._validate_request_fields(event)
        if run_class is not RunClass.RESEARCH_SPECIFICATION:
            raise SpecificationError(
                "portfolio outcome OPEN is limited to research_specification"
            )
        if run_type is not RunType.PORTFOLIO_BACKTEST:
            raise SpecificationError("OPEN run type is unsupported")
        _require_uuid(event["specification_id"], "OPEN specification_id")
        if event["budget_effect"] != "reserve_one_research_slot":
            raise SpecificationError("OPEN budget effect is invalid")
        if event["reservation_semantics"] != RESERVATION_SEMANTICS:
            raise SpecificationError("OPEN reservation semantics were altered")
        if not isinstance(event["lineage"], Mapping) or set(event["lineage"]) != PREPARED_LINEAGE_KEYS:
            raise SpecificationError("OPEN lineage schema is invalid")
        if not isinstance(event["primary_parameters"], Mapping) or set(event["primary_parameters"]) != PRIMARY_PARAMETER_KEYS:
            raise SpecificationError("OPEN primary-parameter schema is invalid")
        for name in (
            "entry_001_sha256", "fact_source_content_sha256",
            "fact_source_audit_artifact_sha256", "fact_source_manifest_sha256",
            "return_source_content_sha256", "return_source_audit_artifact_sha256",
            "return_source_manifest_sha256", "ranked_frame_digest",
            "proxy_registry_digest", "ranking_configuration_digest",
        ):
            if not _is_sha256(event["lineage"].get(name)):
                raise SpecificationError(f"OPEN lineage {name} must be SHA-256")
        for name in (
            "feature_generation_code_commit", "ranking_code_commit",
            "execution_code_commit",
        ):
            if not _is_git_commit(event["lineage"].get(name)):
                raise SpecificationError(f"OPEN lineage {name} must be a Git commit")
        for name in (
            "research_vintage_bundle_id", "fact_source_kind", "fact_source_id",
            "fact_source_native_vintage_identifier", "return_source_kind",
            "return_source_id", "return_source_native_vintage_identifier",
        ):
            value = event["lineage"].get(name)
            if not isinstance(value, str) or not value.strip():
                raise SpecificationError(f"OPEN lineage {name} must be non-empty")
        if event["lineage"].get("ranked_frame_digest_scope") != [
            "security_id", "decision_date", "composite_score"
        ]:
            raise SpecificationError("OPEN ranked-frame digest scope is invalid")
        for name in ("prepared_experiment_digest", "open_event_digest"):
            if not _is_sha256(event[name]):
                raise SpecificationError(f"OPEN {name} must be SHA-256")
        unsigned = {key: value for key, value in event.items() if key != "open_event_digest"}
        if _open_event_digest(unsigned) != event["open_event_digest"]:
            raise SpecificationError("OPEN event digest does not match its content")

    @staticmethod
    def _validate_close_event(event: Mapping[str, Any]) -> None:
        _require_uuid(event["specification_id"], "CLOSE specification_id")
        _require_uuid(event["open_event_id"], "CLOSE open_event_id")
        if event["status"] not in {"completed", "failed", "abandoned"}:
            raise SpecificationError("CLOSE status is unsupported")
        if event["budget_effect"] != "none_open_reservation_unchanged":
            raise SpecificationError("CLOSE budget effect is invalid")
        artifacts = event["output_artifacts"]
        if not isinstance(artifacts, list) or any(
            not isinstance(item, str) for item in artifacts
        ):
            raise SpecificationError("CLOSE output_artifacts is invalid")
        for name in ("failure_classification", "failure_message"):
            if event[name] is not None and not isinstance(event[name], str):
                raise SpecificationError(f"CLOSE {name} is invalid")

    def history(self) -> tuple[Mapping[str, Any], ...]:
        if not self.path.exists():
            return ()
        with self.path.open("rb") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            try:
                return tuple(self._read_locked(handle))
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _used(events: Iterable[Mapping[str, Any]]) -> int:
        return sum(event["event_type"] == "open" for event in events)

    def budget(self, total: int) -> Mapping[str, Any]:
        if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
            raise SpecificationError("specification budget must be positive")
        used = self._used(self.history())
        return {
            "used": used,
            "total": total,
            "remaining": max(total - used, 0),
            "reservation_semantics": RESERVATION_SEMANTICS,
            "post_open_release_policy": "UNRESOLVED; no release mechanism implemented",
        }

    def validate_portfolio_request(self, request: SpecificationRequest) -> None:
        events = self.history()
        if request.run_class is RunClass.RESEARCH_SPECIFICATION:
            return
        if request.run_class is RunClass.DIAGNOSTIC:
            raise SpecificationError(
                "diagnostic runs cannot execute governed portfolio outcomes"
            )
        prior = [
            event for event in events
            if event["event_type"] == "open"
            and event["specification_id"] == request.invalidated_specification_id
        ]
        if len(prior) != 1:
            raise SpecificationError(
                "data_correction must link to one existing specification OPEN"
            )
        raise SpecificationError(
            "data-correction portfolio outcomes are disabled because no governed "
            "specification-invalidation mechanism has been approved"
        )

    def _record_blocked(
        self,
        request: SpecificationRequest,
        *,
        stage: str,
        failure_classification: str,
        message: str,
    ) -> str:
        event = {
            "schema_version": REGISTER_SCHEMA_VERSION,
            "event_id": str(uuid4()),
            "event_type": "blocked",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "run_class": request.run_class.value,
            "run_type": request.run_type.value,
            "rationale": request.rationale,
            "invalidated_specification_id": request.invalidated_specification_id,
            "failure_classification": failure_classification,
            "message": message,
            "budget_effect": "none_no_open",
        }
        handle = self._open_locked()
        try:
            self._read_locked(handle)
            self._validate_history([event])
            self._append_locked(handle, event)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        return str(event["event_id"])

    def _open_prepared(
        self,
        request: SpecificationRequest,
        prepared: Any,
    ) -> OpenedSpecification:
        """Internal persistence used only by the integrated post-preflight gateway."""

        from .backtest import PreparedPortfolioExperiment

        if not isinstance(prepared, PreparedPortfolioExperiment):
            raise TypeError("OPEN requires a deterministic-preflight capability")
        self.validate_portfolio_request(request)
        lineage = _canonical_value(prepared.lineage())
        primary_parameters = _canonical_value(prepared.primary_parameters())
        prepared_digest = prepared.prepared_experiment_digest()
        specification_budget = prepared.resolved_entry.specification_budget
        specification_id = str(uuid4())
        event_id = str(uuid4())
        handle = self._open_locked()
        try:
            events = self._read_locked(handle)
            if self._used(events) >= specification_budget:
                blocked = {
                    "schema_version": REGISTER_SCHEMA_VERSION,
                    "event_id": str(uuid4()),
                    "event_type": "blocked",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "stage": "budget_check",
                    "run_class": request.run_class.value,
                    "run_type": request.run_type.value,
                    "rationale": request.rationale,
                    "invalidated_specification_id": request.invalidated_specification_id,
                    "failure_classification": "budget_exhausted",
                    "message": "research specification budget is exhausted",
                    "budget_effect": "none_no_open",
                }
                self._validate_history([*events, blocked])
                self._append_locked(handle, blocked)
                raise BudgetExhausted("research specification budget is exhausted")
            unsigned = {
                "schema_version": REGISTER_SCHEMA_VERSION,
                "event_id": event_id,
                "event_type": "open",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "specification_id": specification_id,
                "run_class": request.run_class.value,
                "run_type": request.run_type.value,
                "rationale": request.rationale,
                "invalidated_specification_id": request.invalidated_specification_id,
                "lineage": lineage,
                "primary_parameters": primary_parameters,
                "prepared_experiment_digest": prepared_digest,
                "budget_effect": "reserve_one_research_slot",
                "reservation_semantics": RESERVATION_SEMANTICS,
            }
            event = {**unsigned, "open_event_digest": _open_event_digest(unsigned)}
            self._validate_history([*events, event])
            self._append_locked(handle, event)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        return OpenedSpecification(
            specification_id=specification_id,
            run_class=request.run_class,
            run_type=request.run_type,
            open_event_id=event_id,
            open_event_digest=str(event["open_event_digest"]),
            prepared_experiment_digest=prepared_digest,
            lineage=lineage,
            primary_parameters=primary_parameters,
            register_path=self.path,
            _token=_OPEN_TOKEN,
        )

    def assert_opened(self, opened: OpenedSpecification) -> Mapping[str, Any]:
        if not isinstance(opened, OpenedSpecification):
            raise TypeError("opened-specification capability is required")
        if opened.register_path != self.path:
            raise SpecificationError("OPEN capability belongs to another register")
        events = self.history()
        matches = [
            event for event in events
            if event["event_type"] == "open"
            and event["event_id"] == opened.open_event_id
            and event["specification_id"] == opened.specification_id
        ]
        if len(matches) != 1:
            raise SpecificationError("durable OPEN event is missing or ambiguous")
        event = matches[0]
        expected = {
            "run_class": opened.run_class.value,
            "run_type": opened.run_type.value,
            "open_event_digest": opened.open_event_digest,
            "prepared_experiment_digest": opened.prepared_experiment_digest,
            "lineage": _plain_json(opened.lineage),
            "primary_parameters": _plain_json(opened.primary_parameters),
        }
        if any(event[name] != value for name, value in expected.items()):
            raise SpecificationError("OPEN capability does not match durable OPEN")
        if any(
            item["event_type"] == "close"
            and item["specification_id"] == opened.specification_id
            for item in events
        ):
            raise SpecificationError("closed specification cannot execute")
        return event

    def _authorize_execution(
        self,
        opened: OpenedSpecification,
        prepared: Any,
    ) -> _ExecutionAuthorization:
        from .backtest import PreparedPortfolioExperiment

        if not isinstance(prepared, PreparedPortfolioExperiment):
            raise TypeError("execution requires a deterministic-preflight capability")
        event = self.assert_opened(opened)
        if opened.run_class is not RunClass.RESEARCH_SPECIFICATION:
            raise SpecificationError("portfolio outcomes require research_specification")
        if prepared.prepared_experiment_digest() != event["prepared_experiment_digest"]:
            raise SpecificationError("prepared experiment does not match OPEN")
        if _canonical_value(prepared.lineage()) != event["lineage"]:
            raise SpecificationError("prepared lineage does not match OPEN")
        if _canonical_value(prepared.primary_parameters()) != event["primary_parameters"]:
            raise SpecificationError("prepared parameters do not match OPEN")
        return _ExecutionAuthorization(
            specification_id=opened.specification_id,
            open_event_id=opened.open_event_id,
            open_event_digest=opened.open_event_digest,
            prepared_experiment_digest=opened.prepared_experiment_digest,
            run_class=str(event["run_class"]),
            run_type=str(event["run_type"]),
            lineage=event["lineage"],
            _token=_EXECUTION_TOKEN,
        )

    def _close(
        self,
        opened: OpenedSpecification,
        *,
        status: str,
        output_artifacts: Iterable[str] = (),
        failure_classification: str | None = None,
        failure_message: str | None = None,
    ) -> str:
        if status not in {"completed", "failed", "abandoned"}:
            raise SpecificationError("CLOSE status is unsupported")
        self.assert_opened(opened)
        event = {
            "schema_version": REGISTER_SCHEMA_VERSION,
            "event_id": str(uuid4()),
            "event_type": "close",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "specification_id": opened.specification_id,
            "open_event_id": opened.open_event_id,
            "status": status,
            "output_artifacts": list(output_artifacts),
            "failure_classification": failure_classification,
            "failure_message": failure_message,
            "budget_effect": "none_open_reservation_unchanged",
        }
        handle = self._open_locked()
        try:
            events = self._read_locked(handle)
            self._validate_history([*events, event])
            self._append_locked(handle, event)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        return str(event["event_id"])

    def reclassify(self, specification_id: str, run_class: RunClass) -> None:
        del specification_id, run_class
        raise SpecificationError("run_class is immutable after OPEN")


def _verify_execution_authorization(
    authorization: object,
    opened: OpenedSpecification,
    prepared_experiment_digest: str,
) -> _ExecutionAuthorization:
    if not isinstance(authorization, _ExecutionAuthorization):
        raise TypeError("internal execution authorization is required")
    if authorization.prepared_experiment_digest != prepared_experiment_digest:
        raise SpecificationError("execution authorization is bound to another experiment")
    if (
        authorization.specification_id != opened.specification_id
        or authorization.open_event_id != opened.open_event_id
        or authorization.open_event_digest != opened.open_event_digest
        or authorization.run_class != opened.run_class.value
        or authorization.run_type != opened.run_type.value
    ):
        raise SpecificationError("execution authorization is bound to another OPEN")
    return authorization
