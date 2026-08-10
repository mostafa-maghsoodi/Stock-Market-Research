"""Governed equal-weight portfolio preparation and post-OPEN accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import pandas as pd

from .datasets import (
    GovernedHeldPeriodReturnSource,
    HeldPeriodReturnObservation,
)
from .governance import (
    GovernanceError,
    ResolvedEntry001,
    RuntimeValidationResult,
    canonical_json,
    load_resolved_entry_001,
    require_entry_001,
    source_control_manifest,
)
from .ranked_artifact import (
    GovernedRankingArtifact,
    RANKED_FRAME_DIGEST_SCOPE,
    verify_governed_ranking_artifact,
)
from .ranking import select_top_n
from .specification import (
    OpenedSpecification,
    RunType,
    SpecificationRegister,
    SpecificationRequest,
    _verify_execution_authorization,
)
from .timing import HoldingInterval, TimingError


class BacktestInputError(GovernanceError):
    pass


class OutcomeAccountingError(RuntimeError):
    """A realized post-OPEN state has no mathematically defined continuation."""


@dataclass(frozen=True)
class PreparedPortfolioStep:
    decision_date: date
    holding_interval: HoldingInterval
    selected_security_ids: tuple[str, ...] | None
    held_security_ids: tuple[str, ...]
    return_observations: tuple[HeldPeriodReturnObservation, ...]


_PREPARED_TOKEN = object()


@dataclass(frozen=True, init=False)
class PreparedPortfolioExperiment:
    resolved_entry: ResolvedEntry001
    runtime_validation: RuntimeValidationResult
    ranking_artifact: GovernedRankingArtifact
    return_source: GovernedHeldPeriodReturnSource
    sample_partition: str
    steps: tuple[PreparedPortfolioStep, ...]
    current_code_commit: str

    def __init__(self, *, _token: object, **values: object) -> None:
        if _token is not _PREPARED_TOKEN:
            raise TypeError(
                "PreparedPortfolioExperiment is issued only by deterministic preflight"
            )
        for name in self.__annotations__:
            object.__setattr__(self, name, values[name])

    def lineage(self) -> Mapping[str, Any]:
        source = self.return_source.source_manifest
        artifact = self.ranking_artifact
        return {
            "entry_001_sha256": self.resolved_entry.entry_001_sha256,
            "research_vintage_bundle_id": (
                self.resolved_entry.data_vintage_identifier
            ),
            "fact_source_kind": artifact.fact_source_kind,
            "fact_source_id": artifact.fact_source_id,
            "fact_source_native_vintage_identifier": (
                artifact.fact_source_native_vintage_identifier
            ),
            "fact_source_content_sha256": artifact.fact_source_content_sha256,
            "fact_source_audit_artifact_sha256": (
                artifact.fact_source_audit_artifact_sha256
            ),
            "fact_source_manifest_sha256": artifact.fact_source_manifest_sha256,
            "return_source_native_vintage_identifier": (
                source.source_native_vintage_identifier
            ),
            "return_source_kind": source.source_kind,
            "return_source_id": source.source_id,
            "return_source_content_sha256": source.content_sha256,
            "return_source_audit_artifact_sha256": (
                source.audit_artifact_sha256
            ),
            "return_source_manifest_sha256": source.manifest_sha256,
            "ranked_frame_digest": artifact.ranked_frame_digest,
            "ranked_frame_digest_scope": list(artifact.digest_scope),
            "proxy_registry_digest": artifact.proxy_registry_digest,
            "ranking_configuration_digest": (
                artifact.ranking_configuration_digest
            ),
            "feature_generation_code_commit": (
                artifact.feature_generation_code_commit
            ),
            "ranking_code_commit": artifact.ranking_code_commit,
            "execution_code_commit": self.current_code_commit,
        }

    def primary_parameters(self) -> Mapping[str, Any]:
        construction = self.resolved_entry.portfolio_construction
        timing = self.resolved_entry.portfolio_timing
        return {
            "sample_partition": self.sample_partition,
            "sample_partition_boundaries": dict(
                self.resolved_entry.sample_boundaries[self.sample_partition]
            ),
            "portfolio_construction": dict(construction),
            "terminal_position_policy": (
                self.resolved_entry.terminal_position_policy
            ),
            "portfolio_timing": asdict(timing),
            "transaction_cost_model": dict(
                self.resolved_entry.transaction_cost_model
            ),
            "specification_budget": self.resolved_entry.specification_budget,
            "specification_counting_rules": dict(
                self.resolved_entry.specification_counting_rules
            ),
        }

    def execution_plan(self) -> Mapping[str, Any]:
        """Canonical structural plan; deliberately excludes all return values."""

        return {
            "schedule_dates": [step.decision_date.isoformat() for step in self.steps],
            "steps": [
                {
                    "decision_date": step.decision_date.isoformat(),
                    "holding_interval_key": {
                        "period_start": step.holding_interval.period_start.isoformat(),
                        "period_end": step.holding_interval.period_end.isoformat(),
                    },
                    "selected_security_ids": (
                        None
                        if step.selected_security_ids is None
                        else list(step.selected_security_ids)
                    ),
                    "held_security_ids": list(step.held_security_ids),
                    "return_observation_keys": [
                        {
                            "security_id": row.security_id,
                            "period_start": row.period_start.isoformat(),
                            "period_end": row.period_end.isoformat(),
                        }
                        for row in step.return_observations
                    ],
                }
                for step in self.steps
            ],
        }

    def prepared_experiment_payload(self) -> Mapping[str, Any]:
        return {
            "prepared_experiment_schema_version": 1,
            "lineage": dict(self.lineage()),
            "primary_parameters": dict(self.primary_parameters()),
            "execution_plan": self.execution_plan(),
        }

    def prepared_experiment_digest(self) -> str:
        return hashlib.sha256(
            canonical_json(self.prepared_experiment_payload())
        ).hexdigest()


_RESULT_TOKEN = object()


@dataclass(frozen=True, init=False)
class BacktestResult:
    periods: pd.DataFrame
    positions: pd.DataFrame
    mean_gross_return: float
    mean_net_return: float
    cumulative_net_return: float
    mean_traded_notional: float
    runtime_warnings: tuple[str, ...]
    specification_id: str
    open_event_id: str
    open_event_digest: str
    run_class: str
    run_type: str
    prepared_experiment_digest: str
    lineage: Mapping[str, Any]

    def __init__(self, *, _token: object, **values: object) -> None:
        if _token is not _RESULT_TOKEN:
            raise TypeError(
                "BacktestResult is emitted only after a durable specification OPEN"
            )
        for name in self.__annotations__:
            value = values[name]
            if name == "lineage":
                value = MappingProxyType(dict(value))
            object.__setattr__(self, name, value)


def _partition_schedule(
    resolved: ResolvedEntry001,
    partition_name: str,
) -> tuple[date, ...]:
    if partition_name not in {"development", "holdout_a", "holdout_b"}:
        raise BacktestInputError("sample_partition is unsupported")
    partition = resolved.sample_boundaries[partition_name]
    start = date.fromisoformat(str(partition["start"]))
    end = date.fromisoformat(str(partition["end"]))
    start_included = partition["start_boundary_rule"] == "included"
    end_included = partition["end_boundary_rule"] == "included"
    names = ("development", "holdout_a", "holdout_b")
    index = names.index(partition_name)
    shared = resolved.sample_boundaries["shared_boundary_assignment_rule"]
    if index > 0:
        prior = resolved.sample_boundaries[names[index - 1]]
        if (
            date.fromisoformat(str(prior["end"])) == start
            and prior["end_boundary_rule"] == "included"
            and start_included
            and shared == "earlier_partition"
        ):
            start_included = False
    if index < len(names) - 1:
        following = resolved.sample_boundaries[names[index + 1]]
        if (
            date.fromisoformat(str(following["start"])) == end
            and following["start_boundary_rule"] == "included"
            and end_included
            and shared == "later_partition"
        ):
            end_included = False
    return resolved.portfolio_timing.schedule_between(
        start,
        end,
        start_included=start_included,
        end_included=end_included,
    )


def sample_partitions_for_date(
    resolved: ResolvedEntry001,
    value: date,
) -> tuple[str, ...]:
    """Return explicit memberships; allowed gaps have no partition membership."""

    names = ("development", "holdout_a", "holdout_b")
    memberships: list[str] = []
    for index, name in enumerate(names):
        partition = resolved.sample_boundaries[name]
        start = date.fromisoformat(str(partition["start"]))
        end = date.fromisoformat(str(partition["end"]))
        after_start = value > start or (
            value == start and partition["start_boundary_rule"] == "included"
        )
        before_end = value < end or (
            value == end and partition["end_boundary_rule"] == "included"
        )
        if not (after_start and before_end):
            continue
        shared = resolved.sample_boundaries["shared_boundary_assignment_rule"]
        if index > 0 and value == start and shared == "earlier_partition":
            continue
        if index < len(names) - 1 and value == end and shared == "later_partition":
            continue
        memberships.append(name)
    return tuple(memberships)


def _decision_date_value(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise BacktestInputError(f"invalid ranked decision_date: {value!r}") from exc
    if timestamp.tzinfo is None:
        raise BacktestInputError("ranked decision_date must be timezone-aware")
    return timestamp.tz_convert("UTC").date()


def _eligible_by_date(
    artifact: GovernedRankingArtifact,
    number_of_positions: int,
) -> tuple[
    Mapping[date, tuple[str, ...]],
    Mapping[date, tuple[str, ...]],
]:
    # This projection is the selector's entire input authority. No auxiliary
    # artifact column can influence membership.
    frame = artifact.ranked.loc[:, list(RANKED_FRAME_DIGEST_SCOPE)].copy()
    frame["_governed_date"] = frame["decision_date"].map(_decision_date_value)
    eligible = frame.dropna(subset=["composite_score"]).sort_values(
        ["_governed_date", "composite_score", "security_id"],
        ascending=[True, False, True],
    )
    selected = select_top_n(frame, number_of_positions).copy()
    selected["_governed_date"] = selected["decision_date"].map(
        _decision_date_value
    )
    eligible_by_date = {
        decision_date: tuple(group["security_id"].astype(str).tolist())
        for decision_date, group in eligible.groupby("_governed_date", sort=True)
    }
    selected_by_date = {
        decision_date: tuple(group["security_id"].astype(str).tolist())
        for decision_date, group in selected.groupby("_governed_date", sort=True)
    }
    return eligible_by_date, selected_by_date


def _structurally_resolve_returns(
    source: GovernedHeldPeriodReturnSource,
    held: tuple[str, ...],
    interval: HoldingInterval,
) -> tuple[HeldPeriodReturnObservation, ...]:
    """Read values only to validate row shape, coverage, and finiteness.

    This preflight function returns the exact input observations. It never
    aggregates, transforms, summarizes, logs, or reports their values.
    """

    rows: list[HeldPeriodReturnObservation] = []
    for security_id in held:
        row = source.observation(
            security_id,
            interval.period_start,
            interval.period_end,
        )
        if row is None:
            raise BacktestInputError(
                "held-period return coverage is incomplete for a required "
                "security/interval"
            )
        if not math.isfinite(row.total_return):
            raise BacktestInputError("required held-period return is non-finite")
        rows.append(row)
    return tuple(rows)


def deterministic_portfolio_preflight(
    ranking_artifact: GovernedRankingArtifact,
    return_source: GovernedHeldPeriodReturnSource,
    entry_001_path: str | Path,
    repository: str | Path,
    *,
    sample_partition: str,
) -> PreparedPortfolioExperiment:
    """Complete every deterministic outcome-free gate before OPEN."""

    if not isinstance(return_source, GovernedHeldPeriodReturnSource):
        raise TypeError("an independently loaded governed return source is required")
    payload, runtime = require_entry_001(entry_001_path)
    resolved = load_resolved_entry_001(entry_001_path)
    if resolved.entry_001_sha256 != ranking_artifact.entry_001_sha256:
        raise BacktestInputError("ranking artifact was built under another Entry 001")
    verify_governed_ranking_artifact(ranking_artifact, resolved)
    return_manifest = return_source.source_manifest
    approved_bundle = str(payload["data_vintage_identifier"])
    if return_manifest.research_vintage_bundle_id != approved_bundle:
        raise BacktestInputError("return-source research-vintage bundle mismatch")
    if ranking_artifact.research_vintage_bundle_id != approved_bundle:
        raise BacktestInputError("fact/ranking research-vintage bundle mismatch")
    # Source-native vintage identifiers are independent observations and are
    # deliberately not compared with one another.
    current_manifest = source_control_manifest(repository)
    if current_manifest["dirty"]:
        raise BacktestInputError("governed execution requires a clean source tree")
    if current_manifest["commit"] != ranking_artifact.ranking_code_commit:
        raise BacktestInputError("execution commit differs from ranking commit")

    timing = resolved.portfolio_timing
    expected_return_convention = dict(timing.economic_return_convention())
    actual_return_convention = return_manifest.economic_return_convention
    if actual_return_convention is None or dict(actual_return_convention) != expected_return_convention:
        raise BacktestInputError(
            "held-return source economic measurement convention does not match "
            "the frozen portfolio timing contract"
        )
    for value in ranking_artifact.ranked["decision_date"]:
        decision_date = _decision_date_value(value)
        if not timing.is_valid_decision_date(decision_date):
            raise BacktestInputError(
                f"ranked decision date is invalid under frozen schedule: {decision_date}"
            )
    schedule = _partition_schedule(resolved, sample_partition)
    if not schedule:
        raise BacktestInputError("selected sample partition has no scheduled dates")
    construction = resolved.portfolio_construction
    number_of_positions = int(construction["number_of_positions"])
    eligible, selected_by_date = _eligible_by_date(
        ranking_artifact, number_of_positions
    )
    policy = str(construction["insufficient_eligible_policy"])
    active: tuple[str, ...] = ()
    steps: list[PreparedPortfolioStep] = []
    for decision_date in schedule:
        candidates = eligible.get(decision_date, ())
        selected: tuple[str, ...] | None
        if len(candidates) >= number_of_positions:
            selected = selected_by_date[decision_date]
            active = selected
        elif policy == "fail":
            raise BacktestInputError(
                "insufficient eligible securities under frozen fail policy"
            )
        elif policy == "hold_available_names":
            if not candidates:
                raise BacktestInputError(
                    "hold_available_names has no securities and would require cash"
                )
            selected = candidates
            active = selected
        elif policy == "skip_rebalance_date":
            if not active:
                raise BacktestInputError(
                    "initial skipped deployment is unsupported without cash governance"
                )
            selected = None
        else:
            raise BacktestInputError("unsupported insufficient-eligible policy")
        try:
            interval = timing.holding_interval(decision_date)
        except TimingError as exc:
            raise BacktestInputError(str(exc)) from exc
        returns = _structurally_resolve_returns(return_source, active, interval)
        if any(row.terminal_flag for row in returns):
            # No terminal convention is executable end-to-end until disposition
            # state, turnover/cost timing, and continuation are frozen.
            raise BacktestInputError(
                "terminal event is unsupported by fail_on_any_terminal_event"
            )
        steps.append(
            PreparedPortfolioStep(
                decision_date=decision_date,
                holding_interval=interval,
                selected_security_ids=selected,
                held_security_ids=active,
                return_observations=returns,
            )
        )
    return PreparedPortfolioExperiment(
        resolved_entry=resolved,
        runtime_validation=runtime,
        ranking_artifact=ranking_artifact,
        return_source=return_source,
        sample_partition=sample_partition,
        steps=tuple(steps),
        current_code_commit=str(current_manifest["commit"]),
        _token=_PREPARED_TOKEN,
    )


def _produce_portfolio_results_after_open(
    authorization: object,
    opened: OpenedSpecification,
    prepared: PreparedPortfolioExperiment,
) -> BacktestResult:
    """First result-producing use of any forward-return value in the MVP."""

    verified_authorization = _verify_execution_authorization(
        authorization,
        opened,
        prepared.prepared_experiment_digest(),
    )
    if verified_authorization.run_type != RunType.PORTFOLIO_BACKTEST.value:
        raise BacktestInputError("OPEN run_type does not match portfolio execution")
    cost_bps = float(
        prepared.resolved_entry.transaction_cost_model["one_way_cost_bps"]
    )
    pre_rebalance_weights: dict[str, float] = {}
    period_rows: list[dict[str, object]] = []
    position_rows: list[dict[str, object]] = []
    for step in prepared.steps:
        if step.selected_security_ids is None:
            if not pre_rebalance_weights:
                raise OutcomeAccountingError(
                    "skipped rebalance has no continuing portfolio state"
                )
            start_weights = dict(pre_rebalance_weights)
            traded_notional = 0.0
            executed = False
        else:
            count = len(step.selected_security_ids)
            start_weights = {
                security_id: 1.0 / count
                for security_id in step.selected_security_ids
            }
            names = set(pre_rebalance_weights) | set(start_weights)
            traded_notional = sum(
                abs(
                    start_weights.get(name, 0.0)
                    - pre_rebalance_weights.get(name, 0.0)
                )
                for name in names
            )
            executed = True
        return_by_security = {
            row.security_id: row for row in step.return_observations
        }
        # This is the first outcome-bearing operation: the same exact resolved
        # observations feed gross return and the drift numerators below.
        gross_return = sum(
            start_weights[name] * return_by_security[name].total_return
            for name in start_weights
        )
        end_values = {
            name: weight * (1.0 + return_by_security[name].total_return)
            for name, weight in start_weights.items()
        }
        normalization = sum(end_values.values())
        if not math.isfinite(normalization) or normalization <= 0:
            raise OutcomeAccountingError(
                "realized drift normalization is non-positive or non-finite"
            )
        pre_rebalance_weights = {
            name: value / normalization for name, value in end_values.items()
        }
        transaction_cost = traded_notional * cost_bps / 10_000.0
        net_return = gross_return - transaction_cost
        period_rows.append({
            "decision_date": step.decision_date,
            "period_start": step.holding_interval.period_start,
            "period_end": step.holding_interval.period_end,
            "rebalance_executed": executed,
            "gross_return": gross_return,
            "traded_notional": traded_notional,
            "cost": transaction_cost,
            "net_return": net_return,
            "holdings": len(start_weights),
        })
        for name in sorted(start_weights):
            position_rows.append({
                "decision_date": step.decision_date,
                "period_start": step.holding_interval.period_start,
                "period_end": step.holding_interval.period_end,
                "security_id": name,
                "start_weight": start_weights[name],
                "total_return": return_by_security[name].total_return,
                "pre_rebalance_weight_next": pre_rebalance_weights[name],
            })
    periods = pd.DataFrame(period_rows)
    if periods.empty:
        raise OutcomeAccountingError("no portfolio periods were produced")
    cumulative = float((1.0 + periods["net_return"]).prod() - 1.0)
    return BacktestResult(
        periods=periods,
        positions=pd.DataFrame(position_rows),
        mean_gross_return=float(periods["gross_return"].mean()),
        mean_net_return=float(periods["net_return"].mean()),
        cumulative_net_return=cumulative,
        mean_traded_notional=float(periods["traded_notional"].mean()),
        runtime_warnings=prepared.runtime_validation.warnings,
        specification_id=verified_authorization.specification_id,
        open_event_id=verified_authorization.open_event_id,
        open_event_digest=verified_authorization.open_event_digest,
        run_class=verified_authorization.run_class,
        run_type=verified_authorization.run_type,
        prepared_experiment_digest=(
            verified_authorization.prepared_experiment_digest
        ),
        lineage=verified_authorization.lineage,
        _token=_RESULT_TOKEN,
    )


def run_equal_weight_backtest(
    ranking_artifact: GovernedRankingArtifact,
    return_source: GovernedHeldPeriodReturnSource,
    entry_001_path: str | Path,
    repository: str | Path,
    register: SpecificationRegister,
    request: SpecificationRequest,
    *,
    sample_partition: str,
) -> BacktestResult:
    """Governed API with no caller-controlled portfolio-size parameter."""

    if request.run_type is not RunType.PORTFOLIO_BACKTEST:
        raise BacktestInputError("request run_type must be portfolio_backtest")
    register.assert_governed_for_repository(repository)
    try:
        register.validate_portfolio_request(request)
    except Exception as exc:
        register._record_blocked(
            request,
            stage="run_class_gate",
            failure_classification="portfolio_outcome_run_class_not_permitted",
            message=str(exc),
        )
        raise
    try:
        prepared = deterministic_portfolio_preflight(
            ranking_artifact,
            return_source,
            entry_001_path,
            repository,
            sample_partition=sample_partition,
        )
    except Exception as exc:
        register._record_blocked(
            request,
            stage="deterministic_preflight",
            failure_classification="deterministic_preflight_failure",
            message=str(exc),
        )
        raise
    opened = register._open_prepared(request, prepared)
    # Local import prevents a second execution route and makes the universal
    # opened-experiment gateway the sole caller of result production.
    from .execution import execute_opened_experiment

    return execute_opened_experiment(opened, prepared, register)
