from __future__ import annotations

from contextlib import contextmanager
from contextlib import redirect_stdout
from datetime import date, datetime, time, timezone
import hashlib
import inspect
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from graham_research.backtest import (
    BacktestInputError,
    BacktestResult,
    OutcomeAccountingError,
    deterministic_portfolio_preflight,
    run_equal_weight_backtest,
    sample_partitions_for_date,
)
from graham_research.cli import main as cli_main
from graham_research.datasets import (
    GovernedFactDataset,
    GovernedHeldPeriodReturnSource,
    HeldPeriodReturnObservation,
)
from graham_research.features import (
    FeatureEngine,
    GovernedFeatureBatch,
    combine_governed_feature_batches,
)
from graham_research.governance import (
    GovernanceError,
    MalformedEntry001V2,
    UnresolvedEntry001,
    canonical_json,
    freeze_artifact,
    freeze_entry_001,
    load_resolved_entry_001,
    source_control_manifest,
)
from graham_research.ranked_artifact import (
    GovernedRankingArtifact,
    RANKED_FRAME_DIGEST_SCOPE,
    RankedArtifactError,
    canonical_ranked_frame_digest,
    create_governed_ranking_artifact,
    inspect_ranking_manifest,
    load_governed_ranking_artifact,
    verify_governed_ranking_artifact,
    write_ranking_manifest,
    ranking_configuration_payload,
)
from graham_research.ranking import CompositeConfig
from graham_research.specification import (
    BudgetExhausted,
    OpenedSpecification,
    RESERVATION_SEMANTICS,
    RunClass,
    RunType,
    SpecificationError,
    SpecificationRegister,
    SpecificationRequest,
)
from graham_research.timing import (
    ECONOMIC_RETURN_CONVENTION_KEYS,
    ResolvedPortfolioTiming,
    TimingError,
)

from run1_fixtures import (
    complete_entry_001,
    fact,
    governed_fact_dataset,
    governed_return_source,
    matching_frozen_runtime,
)


CLEAN = {"vcs": "git", "commit": "c" * 40, "dirty": False}
DIRTY = {"vcs": "git", "commit": "c" * 40, "dirty": True}


def run2_payload(
    *,
    policy: str = "fail",
    unfilled: str = "not_applicable",
    development_end: str = "2025-03-31",
    budget: int = 2,
) -> dict[str, object]:
    payload = complete_entry_001(("gross_profitability",))
    payload["sample_boundaries"] = {
        "development": {
            "start": "2025-01-31",
            "end": development_end,
            "start_boundary_rule": "included",
            "end_boundary_rule": "included",
        },
        "holdout_a": {
            "start": "2026-01-31",
            "end": "2026-03-31",
            "start_boundary_rule": "included",
            "end_boundary_rule": "included",
        },
        "holdout_b": {
            "start": "2027-01-31",
            "end": "2027-03-31",
            "start_boundary_rule": "included",
            "end_boundary_rule": "included",
        },
        "partition_overlap_policy": "forbid",
        "partition_gap_policy": "allow",
        "shared_boundary_assignment_rule": "not_applicable",
    }
    payload["portfolio_construction"].update({
        "number_of_positions": 2,
        "insufficient_eligible_policy": policy,
        "unfilled_capacity_policy": unfilled,
    })
    payload["specification_budget"] = budget
    return payload


@contextmanager
def entry_artifact(payload: dict[str, object]):
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "entry001.json"
        freeze_artifact(
            path,
            {**payload, "entry": "001", "created_at": "synthetic-run2-test"},
        )
        with matching_frozen_runtime():
            yield path, load_resolved_entry_001(path)


def _fact_rows(securities=("AAA", "BBB", "CCC", "DDD")):
    values = {"AAA": 100.0, "BBB": 80.0, "CCC": 60.0, "DDD": 40.0}
    rows = []
    for security in securities:
        rows.extend([
            fact(security, "gross_profit", 2023, values[security]),
            fact(security, "total_assets", 2022, 190, period_type="instant"),
            fact(security, "total_assets", 2023, 210, period_type="instant"),
        ])
    return rows


def _decision_at(value: date) -> datetime:
    return datetime.combine(value, time(21), tzinfo=timezone.utc)


def make_batch(resolved, dates=(date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31))):
    dataset = governed_fact_dataset(_fact_rows())
    engine = FeatureEngine(dataset, resolved)
    with patch("graham_research.features.source_control_manifest", return_value=CLEAN):
        batches = tuple(
            engine.calculate_governed_batch(
                ("AAA", "BBB", "CCC", "DDD"),
                _decision_at(decision_date),
                "/synthetic/repository",
            )
            for decision_date in dates
        )
        return combine_governed_feature_batches(
            batches, "/synthetic/repository"
        )


def make_artifact(resolved, dates=(date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31))):
    batch = make_batch(resolved, dates)
    with patch(
        "graham_research.ranked_artifact.source_control_manifest",
        return_value=CLEAN,
    ):
        return create_governed_ranking_artifact(
            batch, resolved, "/synthetic/repository"
        )


def clone_batch(batch: GovernedFeatureBatch, **changes) -> GovernedFeatureBatch:
    value = object.__new__(GovernedFeatureBatch)
    for name in GovernedFeatureBatch.__annotations__:
        object.__setattr__(value, name, changes.get(name, getattr(batch, name)))
    return value


def clone_artifact(
    artifact: GovernedRankingArtifact,
    frame: pd.DataFrame,
    *,
    bind_content: bool,
    **changes,
) -> GovernedRankingArtifact:
    value = object.__new__(GovernedRankingArtifact)
    for name in GovernedRankingArtifact.__annotations__:
        replacement = changes.get(name, getattr(artifact, name))
        if name == "ranked":
            replacement = frame.copy(deep=True)
        elif name == "ranked_frame_digest" and bind_content:
            replacement = canonical_ranked_frame_digest(frame)
        object.__setattr__(value, name, replacement)
    return value


def decision_frame(mapping: dict[date, tuple[tuple[str, float | None], ...]]):
    return pd.DataFrame([
        {
            "security_id": security,
            "decision_date": decision_date,
            "composite_score": score,
            "unbound_diagnostic": f"unbound-{security}",
        }
        for decision_date, rows in mapping.items()
        for security, score in rows
    ])


def returns_for(
    mapping: dict[
        tuple[date, date],
        tuple[tuple[str, float, bool], ...],
    ],
    *,
    bundle: str = "synthetic-research-vintage-bundle",
    native: str = "independent-return-native-vintage",
):
    return governed_return_source(
        [
            HeldPeriodReturnObservation(security, start, end, value, terminal)
            for (start, end), rows in mapping.items()
            for security, value, terminal in rows
        ],
        research_vintage_bundle_id=bundle,
        source_native_vintage_identifier=native,
    )


def standard_returns(*, identical: bool = False, terminal: bool = False):
    mapping = {}
    intervals = (
        (date(2025, 1, 31), date(2025, 2, 28)),
        (date(2025, 2, 28), date(2025, 3, 31)),
        (date(2025, 3, 31), date(2025, 4, 30)),
    )
    for index, interval in enumerate(intervals):
        mapping[interval] = (
            ("AAA", 0.10, terminal and index == 0),
            ("BBB", 0.10 if identical else 0.00, False),
        )
    return returns_for(mapping)


def request(run_class=RunClass.RESEARCH_SPECIFICATION, rationale="synthetic test"):
    return SpecificationRequest(
        run_class=run_class,
        rationale=rationale,
        run_type=RunType.PORTFOLIO_BACKTEST,
    )


def test_register(path: str | Path) -> SpecificationRegister:
    return SpecificationRegister.for_repository(
        "/synthetic/repository",
        path=path,
    )


def rewrite_register_events(
    register: SpecificationRegister,
    events: list[dict[str, object]],
) -> None:
    register.path.write_bytes(
        b"".join(canonical_json(event) + b"\n" for event in events)
    )


def resign_open_event(event: dict[str, object]) -> None:
    unsigned = {key: value for key, value in event.items() if key != "open_event_digest"}
    event["open_event_digest"] = hashlib.sha256(canonical_json(unsigned)).hexdigest()


class TimingAndSchemaTests(unittest.TestCase):
    def fixed_timing(self, anchor: str, semantics: str):
        return ResolvedPortfolioTiming.from_mapping({
            "calendar_basis": "calendar_days",
            "rebalance_interval_count": 10,
            "rebalance_date_convention": "fixed_n_calendar_days",
            "month_end_convention": "not_applicable",
            "schedule_anchor_date": anchor,
            "anchor_semantics": semantics,
            "holding_period_equals_rebalance_interval": True,
            "holding_period_rule": "rebalance_interval",
            "holding_period_interval_count": "not_applicable",
            "return_interval_start_rule": "decision_date",
            "return_interval_end_rule": "next_scheduled_decision_date",
            "decision_information_cutoff": "synthetic_test_information_cutoff",
            "portfolio_execution_timing": "synthetic_test_execution_timing",
            "return_measurement_start": "synthetic_test_measurement_start",
            "return_measurement_end": "synthetic_test_measurement_end",
            "market_session_basis": "synthetic_test_session_basis",
            "market_timezone": "America/New_York",
            "return_start_endpoint_inclusion": "included",
            "return_end_endpoint_inclusion": "excluded",
            "held_return_source_convention": "synthetic_test_held_return_convention",
        })

    def test_anchor_semantics_distinguish_first_valid_from_epoch(self) -> None:
        first = self.fixed_timing("2025-01-11", "first_valid_date")
        epoch = self.fixed_timing("2025-01-11", "cadence_epoch")
        self.assertFalse(first.is_valid_decision_date(date(2025, 1, 1)))
        self.assertTrue(epoch.is_valid_decision_date(date(2025, 1, 1)))

    def test_different_anchors_define_different_schedules(self) -> None:
        left = self.fixed_timing("2025-01-01", "cadence_epoch")
        right = self.fixed_timing("2025-01-02", "cadence_epoch")
        self.assertNotEqual(
            left.schedule_between(
                date(2025, 1, 1), date(2025, 2, 1),
                start_included=True, end_included=True,
            ),
            right.schedule_between(
                date(2025, 1, 1), date(2025, 2, 1),
                start_included=True, end_included=True,
            ),
        )

    def test_fixed_schedule_requires_anchor_and_anchor_semantics(self) -> None:
        for field in ("schedule_anchor_date", "anchor_semantics"):
            payload = run2_payload()
            payload["portfolio_timing"] = {
                "calendar_basis": "calendar_days",
                "rebalance_interval_count": 10,
                "rebalance_date_convention": "fixed_n_calendar_days",
                "month_end_convention": "not_applicable",
                "schedule_anchor_date": "2025-01-01",
                "anchor_semantics": "cadence_epoch",
                "holding_period_equals_rebalance_interval": True,
                "holding_period_rule": "rebalance_interval",
                "holding_period_interval_count": "not_applicable",
                "return_interval_start_rule": "decision_date",
                "return_interval_end_rule": "next_scheduled_decision_date",
                "decision_information_cutoff": "synthetic_test_information_cutoff",
                "portfolio_execution_timing": "synthetic_test_execution_timing",
                "return_measurement_start": "synthetic_test_measurement_start",
                "return_measurement_end": "synthetic_test_measurement_end",
                "market_session_basis": "synthetic_test_session_basis",
                "market_timezone": "America/New_York",
                "return_start_endpoint_inclusion": "included",
                "return_end_endpoint_inclusion": "excluded",
                "held_return_source_convention": "synthetic_test_held_return_convention",
            }
            payload["portfolio_timing"][field] = "UNRESOLVED"
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(UnresolvedEntry001):
                    freeze_entry_001(
                        Path(temporary) / "entry.json",
                        payload,
                        repository="/not/reached",
                    )

    def test_anchor_is_not_inferred_from_data_or_first_ranked_date(self) -> None:
        mapping = {
            "calendar_basis": "calendar_days",
            "rebalance_interval_count": 10,
            "rebalance_date_convention": "fixed_n_calendar_days",
            "month_end_convention": "not_applicable",
            "schedule_anchor_date": "UNRESOLVED",
            "anchor_semantics": "cadence_epoch",
            "holding_period_equals_rebalance_interval": True,
            "holding_period_rule": "rebalance_interval",
            "holding_period_interval_count": "not_applicable",
            "return_interval_start_rule": "decision_date",
            "return_interval_end_rule": "next_scheduled_decision_date",
            "decision_information_cutoff": "synthetic_test_information_cutoff",
            "portfolio_execution_timing": "synthetic_test_execution_timing",
            "return_measurement_start": "synthetic_test_measurement_start",
            "return_measurement_end": "synthetic_test_measurement_end",
            "market_session_basis": "synthetic_test_session_basis",
            "market_timezone": "America/New_York",
            "return_start_endpoint_inclusion": "included",
            "return_end_endpoint_inclusion": "excluded",
            "held_return_source_convention": "synthetic_test_held_return_convention",
        }
        with self.assertRaises(TimingError):
            ResolvedPortfolioTiming.from_mapping(mapping)

    def test_calendar_schedule_validity_and_exact_interval(self) -> None:
        timing = ResolvedPortfolioTiming.from_mapping(
            run2_payload()["portfolio_timing"]
        )
        self.assertTrue(timing.is_valid_decision_date(date(2025, 1, 31)))
        self.assertFalse(timing.is_valid_decision_date(date(2025, 1, 30)))
        interval = timing.holding_interval(date(2025, 1, 31))
        self.assertEqual(interval.period_end, date(2025, 2, 28))
        with self.assertRaises(TimingError):
            timing.holding_interval(date(2025, 1, 30))

    def test_unequal_holding_interval_is_rejected_without_lot_or_cash_convention(self) -> None:
        value = dict(run2_payload()["portfolio_timing"])
        value.update({
            "holding_period_equals_rebalance_interval": False,
            "holding_period_rule": "fixed_calendar_months",
            "holding_period_interval_count": 2,
            "return_interval_end_rule": "fixed_calendar_months_after_decision",
        })
        with self.assertRaisesRegex(TimingError, "overlapping-lot or cash-gap"):
            ResolvedPortfolioTiming.from_mapping(value)

    def test_unresolved_portfolio_size_and_sample_semantics_block_freeze(self) -> None:
        for mutate in (
            lambda p: p["portfolio_construction"].update(
                number_of_positions="UNRESOLVED"
            ),
            lambda p: p["sample_boundaries"]["development"].update(
                start_boundary_rule="UNRESOLVED"
            ),
        ):
            payload = run2_payload()
            mutate(payload)
            with tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(UnresolvedEntry001):
                    freeze_entry_001(
                        Path(temporary) / "entry.json",
                        payload,
                        repository="/not/reached",
                    )

    def test_economic_return_semantics_are_explicit_and_template_unresolved(self) -> None:
        template = json.loads(
            (Path(__file__).parents[1] / "examples" / "entry001.template.json")
            .read_text(encoding="utf-8")
        )
        for name in ECONOMIC_RETURN_CONVENTION_KEYS:
            self.assertEqual(template["portfolio_timing"][name], "UNRESOLVED")
        payload = run2_payload()
        payload["portfolio_timing"]["market_timezone"] = "UNRESOLVED"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(UnresolvedEntry001):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository="/not/reached",
                )

    def test_unresolved_economic_endpoint_blocks_preflight_before_open(self) -> None:
        payload = run2_payload()
        payload["portfolio_timing"]["return_measurement_end"] = "UNRESOLVED"
        with tempfile.TemporaryDirectory() as temporary:
            entry_path = Path(temporary) / "unresolved-entry.json"
            freeze_artifact(
                entry_path,
                {**payload, "entry": "001", "created_at": "synthetic-test"},
            )
            register = test_register(Path(temporary) / "register.jsonl")
            with self.assertRaises(UnresolvedEntry001):
                run_equal_weight_backtest(
                    None, standard_returns(), entry_path,
                    "/synthetic/repository", register, request(),
                    sample_partition="development",
                )
            self.assertEqual(
                [event["event_type"] for event in register.history()],
                ["blocked"],
            )

    def test_allowed_gap_dates_have_no_partition_and_cannot_enter_schedule(self) -> None:
        with entry_artifact(run2_payload()) as (_path, resolved):
            gap_date = date(2025, 8, 31)
            self.assertEqual(sample_partitions_for_date(resolved, gap_date), ())
            from graham_research.backtest import _partition_schedule

            self.assertTrue(all(
                gap_date not in _partition_schedule(resolved, name)
                for name in ("development", "holdout_a", "holdout_b")
            ))

    def test_hold_cash_is_rejected_not_stubbed(self) -> None:
        payload = run2_payload(
            policy="hold_available_names", unfilled="hold_cash"
        )
        with self.assertRaisesRegex(MalformedEntry001V2, "hold_cash"):
            from graham_research import governance

            governance._validate_entry_001(
                payload, validate_against_project_pins=False
            )

    def test_shared_boundary_assignment_is_explicit(self) -> None:
        from graham_research.backtest import _partition_schedule

        payload = run2_payload()
        payload["sample_boundaries"] = {
            "development": {
                "start": "2025-01-31", "end": "2025-03-31",
                "start_boundary_rule": "included", "end_boundary_rule": "included",
            },
            "holdout_a": {
                "start": "2025-03-31", "end": "2025-05-31",
                "start_boundary_rule": "included", "end_boundary_rule": "included",
            },
            "holdout_b": {
                "start": "2026-01-31", "end": "2026-03-31",
                "start_boundary_rule": "included", "end_boundary_rule": "included",
            },
            "partition_overlap_policy": "allow",
            "partition_gap_policy": "allow",
            "shared_boundary_assignment_rule": "earlier_partition",
        }
        with entry_artifact(payload) as (_path, resolved):
            development = _partition_schedule(resolved, "development")
            holdout = _partition_schedule(resolved, "holdout_a")
        self.assertIn(date(2025, 3, 31), development)
        self.assertNotIn(date(2025, 3, 31), holdout)


class SourceVintageTests(unittest.TestCase):
    def test_source_wrappers_are_loader_issued(self) -> None:
        with self.assertRaises(TypeError):
            GovernedFactDataset((), None)
        with self.assertRaises(TypeError):
            GovernedHeldPeriodReturnSource((), None)

    def test_fact_and_return_native_vintages_may_differ(self) -> None:
        facts = governed_fact_dataset(
            _fact_rows(("AAA",)),
            source_native_vintage_identifier="FACT-NATIVE-2025-01",
        )
        returns = returns_for(
            {
                (date(2025, 1, 31), date(2025, 2, 28)): (
                    ("AAA", 0.1, False),
                )
            },
            native="RETURN-NATIVE-2025-02",
        )
        self.assertNotEqual(
            facts.source_manifest.source_native_vintage_identifier,
            returns.source_manifest.source_native_vintage_identifier,
        )
        self.assertEqual(
            facts.source_manifest.research_vintage_bundle_id,
            returns.source_manifest.research_vintage_bundle_id,
        )

    def test_execution_apis_have_no_vintage_override_parameters(self) -> None:
        for function in (
            FeatureEngine.calculate_governed_batch,
            create_governed_ranking_artifact,
            deterministic_portfolio_preflight,
            run_equal_weight_backtest,
        ):
            parameters = inspect.signature(function).parameters
            for forbidden in (
                "data_vintage_identifier",
                "source_native_vintage_identifier",
                "research_vintage_bundle_id",
            ):
                self.assertNotIn(forbidden, parameters)

    def test_content_tampering_is_rejected_by_source_loader(self) -> None:
        from graham_research.datasets import load_governed_held_return_source

        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "returns.csv"
            data.write_text(
                "security_id,period_start,period_end,total_return,terminal_flag\n"
                "AAA,2025-01-31,2025-02-28,0.1,false\n",
                encoding="utf-8",
            )
            import hashlib

            manifest = Path(temporary) / "manifest.json"
            freeze_artifact(manifest, {
                "source_manifest_schema_version": 2,
                "source_kind": "held_period_returns",
                "source_id": "audited-local-test",
                "research_vintage_bundle_id": "bundle",
                "source_native_vintage_identifier": "native",
                "content_sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
                "audit_artifact_sha256": "e" * 64,
                "provenance": "audited_local_ingest_manifest",
                "economic_return_convention": {
                    name: run2_payload()["portfolio_timing"][name]
                    for name in ECONOMIC_RETURN_CONVENTION_KEYS
                },
            })
            data.write_text(data.read_text() + "BBB,2025-01-31,2025-02-28,0.2,false\n")
            with self.assertRaisesRegex(GovernanceError, "content"):
                load_governed_held_return_source(data, manifest)

    def test_fact_bundle_is_checked_and_native_vintage_is_derived_lineage(self) -> None:
        with entry_artifact(run2_payload()) as (_path, resolved):
            mismatched = governed_fact_dataset(
                _fact_rows(), research_vintage_bundle_id="wrong-bundle"
            )
            with self.assertRaisesRegex(GovernanceError, "vintage bundle"):
                FeatureEngine(mismatched, resolved).calculate_governed_batch(
                    ("AAA",), _decision_at(date(2025, 1, 31)), "/not/reached"
                )
            native = "FACT-NATIVE-INDEPENDENT"
            matched = governed_fact_dataset(
                _fact_rows(), source_native_vintage_identifier=native
            )
            with patch(
                "graham_research.features.source_control_manifest",
                return_value=CLEAN,
            ):
                batch = FeatureEngine(matched, resolved).calculate_governed_batch(
                    ("AAA",), _decision_at(date(2025, 1, 31)), "/synthetic"
                )
        self.assertEqual(batch.fact_source_native_vintage_identifier, native)
        self.assertEqual(
            batch.research_vintage_bundle_id,
            resolved.data_vintage_identifier,
        )


class RankedArtifactTests(unittest.TestCase):
    def test_ranking_configuration_payload_is_the_exact_governed_contract(self) -> None:
        with entry_artifact(run2_payload()) as (_path, resolved):
            payload = ranking_configuration_payload(
                resolved,
                CompositeConfig.from_resolved_entry(resolved),
            )
        self.assertEqual(payload, {
            "ranking_configuration_schema_version": 1,
            "percentile_ranking": {
                "algorithm": "average_rank_rescaled_to_closed_zero_one_interval",
                "tie_method": "average",
                "singleton_percentile": 0.5,
            },
            "missing_data_policy": {
                "policy": "exclude",
                "minimum_feature_coverage": 0.413,
                "minimum_features_per_dimension": 1,
            },
            "required_dimensions": ["business_economics"],
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
        })

    def test_digest_is_row_order_independent_and_score_sensitive(self) -> None:
        frame = decision_frame({
            date(2025, 1, 31): (("AAA", 0.9), ("BBB", 0.8)),
        })
        self.assertEqual(
            canonical_ranked_frame_digest(frame),
            canonical_ranked_frame_digest(frame.iloc[::-1]),
        )
        changed = frame.copy()
        changed.loc[0, "composite_score"] = 0.91
        self.assertNotEqual(
            canonical_ranked_frame_digest(frame),
            canonical_ranked_frame_digest(changed),
        )

    def test_digest_scope_is_exact_and_unbound_changes_are_not_attested(self) -> None:
        with entry_artifact(run2_payload()) as (_path, resolved):
            artifact = make_artifact(resolved)
            changed = artifact.ranked.copy()
            changed["unbound_extra"] = "edited"
            clone = clone_artifact(artifact, changed, bind_content=False)
            inspection = verify_governed_ranking_artifact(clone, resolved)
        self.assertEqual(tuple(inspection["digest_scope"]), RANKED_FRAME_DIGEST_SCOPE)
        self.assertIn("auxiliary", inspection["attestation_limit"])

    def test_modified_bound_content_rejects_even_with_matching_lineage(self) -> None:
        with entry_artifact(run2_payload()) as (_path, resolved):
            artifact = make_artifact(resolved)
            changed = artifact.ranked.copy()
            changed.loc[0, "composite_score"] += 0.01
            clone = clone_artifact(artifact, changed, bind_content=False)
            with self.assertRaisesRegex(RankedArtifactError, "content digest"):
                verify_governed_ranking_artifact(clone, resolved)

    def test_clean_and_dirty_ranking_creation_gate(self) -> None:
        with entry_artifact(run2_payload()) as (_path, resolved):
            batch = make_batch(resolved)
            with patch(
                "graham_research.ranked_artifact.source_control_manifest",
                return_value=DIRTY,
            ), self.assertRaisesRegex(RankedArtifactError, "clean"):
                create_governed_ranking_artifact(
                    batch, resolved, "/synthetic/repository"
                )
            with patch(
                "graham_research.ranked_artifact.source_control_manifest",
                return_value=CLEAN,
            ):
                artifact = create_governed_ranking_artifact(
                    batch, resolved, "/synthetic/repository"
                )
        self.assertEqual(artifact.feature_generation_code_commit, "c" * 40)
        self.assertEqual(artifact.ranking_code_commit, "c" * 40)

    def test_feature_commit_mismatch_rejects_even_with_same_registry(self) -> None:
        with entry_artifact(run2_payload()) as (_path, resolved):
            batch = clone_batch(
                make_batch(resolved), feature_generation_code_commit="d" * 40
            )
            with patch(
                "graham_research.ranked_artifact.source_control_manifest",
                return_value=CLEAN,
            ), self.assertRaisesRegex(RankedArtifactError, "commit differs"):
                create_governed_ranking_artifact(
                    batch, resolved, "/synthetic/repository"
                )

    def test_proxy_and_bundle_lineage_mismatches_reject(self) -> None:
        with entry_artifact(run2_payload()) as (_path, resolved):
            batch = make_batch(resolved)
            variants = (
                clone_batch(batch, proxy_registry_digest="0" * 64),
                clone_batch(batch, research_vintage_bundle_id="other-bundle"),
            )
            for value in variants:
                with self.subTest(value=value), patch(
                    "graham_research.ranked_artifact.source_control_manifest",
                    return_value=CLEAN,
                ), self.assertRaises(RankedArtifactError):
                    create_governed_ranking_artifact(
                        value, resolved, "/synthetic/repository"
                    )

    def test_artifact_constructor_and_result_constructor_are_protected(self) -> None:
        with self.assertRaises(TypeError):
            GovernedRankingArtifact()
        with self.assertRaises(TypeError):
            BacktestResult()
        with self.assertRaises(TypeError):
            OpenedSpecification("id", RunClass.DIAGNOSTIC, RunType.PORTFOLIO_BACKTEST, "event", Path("/tmp/x"))

    def test_selector_authority_is_no_broader_than_digest_scope(self) -> None:
        with entry_artifact(run2_payload()) as (_path, resolved):
            artifact = make_artifact(resolved)
            self.assertEqual(
                artifact.selector_permitted_columns,
                RANKED_FRAME_DIGEST_SCOPE,
            )
            frame = artifact.ranked.copy()
            frame["eligibility_flag"] = False
            altered = clone_artifact(artifact, frame, bind_content=False)
            # The unbound flag is ignored: frozen score/ID/date still determine
            # the two selected names.
            from graham_research.ranked_artifact import select_governed_portfolios

            selected = select_governed_portfolios(altered, resolved)
        self.assertEqual(
            selected.groupby("decision_date")["security_id"].count().tolist(),
            [2, 2, 2],
        )
        broadened = clone_artifact(
            artifact,
            artifact.ranked,
            bind_content=False,
            selector_permitted_columns=(*RANKED_FRAME_DIGEST_SCOPE, "eligibility_flag"),
        )
        with self.assertRaisesRegex(RankedArtifactError, "permission"):
            verify_governed_ranking_artifact(broadened, resolved)

    def test_persisted_package_revalidates_bound_decision_content(self) -> None:
        with entry_artifact(run2_payload()) as (_path, resolved), tempfile.TemporaryDirectory() as temporary:
            artifact = make_artifact(resolved)
            manifest = Path(temporary) / "ranking.manifest.json"
            write_ranking_manifest(artifact, manifest)
            inspection = inspect_ranking_manifest(manifest)
            loaded = load_governed_ranking_artifact(manifest, resolved)
        self.assertTrue(inspection["decision_frame_content_verified"])
        self.assertEqual(loaded.ranked_frame_digest, artifact.ranked_frame_digest)

    def test_manifest_inspection_rejects_bad_commit_and_broadened_selector(self) -> None:
        for field, replacement in (
            ("ranking_code_commit", "not-a-commit"),
            (
                "selector_permitted_columns",
                [*RANKED_FRAME_DIGEST_SCOPE, "unbound_diagnostic"],
            ),
        ):
            with self.subTest(field=field), entry_artifact(run2_payload()) as (_path, resolved), tempfile.TemporaryDirectory() as temporary:
                manifest = Path(temporary) / "ranking.manifest.json"
                write_ranking_manifest(make_artifact(resolved), manifest)
                payload = json.loads(manifest.read_text(encoding="utf-8"))
                payload[field] = replacement
                manifest.write_bytes(canonical_json(payload) + b"\n")
                digest = hashlib.sha256(canonical_json(payload)).hexdigest()
                manifest.with_suffix(manifest.suffix + ".sha256").write_text(
                    f"{digest}  {manifest.name}\n", encoding="ascii"
                )
                with self.assertRaises(RankedArtifactError):
                    inspect_ranking_manifest(manifest)


class PortfolioAndPreflightTests(unittest.TestCase):
    def _preflight(self, artifact, source, path, partition="development"):
        with patch(
            "graham_research.backtest.source_control_manifest", return_value=CLEAN
        ):
            return deterministic_portfolio_preflight(
                artifact,
                source,
                path,
                "/synthetic/repository",
                sample_partition=partition,
            )

    def _run(self, artifact, source, path, register, run_request=None):
        with patch(
            "graham_research.backtest.source_control_manifest", return_value=CLEAN
        ):
            return run_equal_weight_backtest(
                artifact,
                source,
                path,
                "/synthetic/repository",
                register,
                run_request or request(),
                sample_partition="development",
            )

    def _capture_open(self, artifact, source, path, register):
        with patch(
            "graham_research.execution.execute_opened_experiment",
            side_effect=lambda opened, prepared, _register: (opened, prepared),
        ):
            return self._run(artifact, source, path, register)

    def test_governed_api_has_no_top_n_and_requires_independent_source(self) -> None:
        self.assertNotIn(
            "top_n", inspect.signature(run_equal_weight_backtest).parameters
        )
        with entry_artifact(run2_payload()) as (path, resolved):
            artifact = make_artifact(resolved)
            with self.assertRaises(TypeError):
                self._preflight(artifact, artifact.ranked, path)

    def test_selector_receives_only_frozen_portfolio_size(self) -> None:
        import graham_research.backtest as backtest_module

        with entry_artifact(run2_payload()) as (path, resolved):
            artifact = make_artifact(resolved)
            original = backtest_module.select_top_n
            with patch.object(
                backtest_module,
                "select_top_n",
                wraps=original,
            ) as selector:
                self._preflight(artifact, standard_returns(), path)
            self.assertEqual(selector.call_count, 1)
            self.assertEqual(
                selector.call_args.args[1],
                resolved.portfolio_construction["number_of_positions"],
            )

    def test_preflight_maps_exact_intervals_without_spacing_inference(self) -> None:
        with entry_artifact(run2_payload()) as (path, resolved):
            artifact = make_artifact(resolved)
            prepared = self._preflight(artifact, standard_returns(), path)
            self.assertEqual(
                prepared.steps[0].holding_interval.period_end,
                date(2025, 2, 28),
            )
            wrong_spacing = returns_for({
                (date(2025, 1, 31), date(2025, 3, 1)): (
                    ("AAA", 0.1, False), ("BBB", 0.0, False),
                ),
                (date(2025, 2, 28), date(2025, 3, 31)): (
                    ("AAA", 0.1, False), ("BBB", 0.0, False),
                ),
                (date(2025, 3, 31), date(2025, 4, 30)): (
                    ("AAA", 0.1, False), ("BBB", 0.0, False),
                ),
            })
            with self.assertRaisesRegex(BacktestInputError, "coverage"):
                self._preflight(artifact, wrong_spacing, path)

    def test_return_source_economic_convention_must_match_entry_exactly(self) -> None:
        with entry_artifact(run2_payload()) as (path, resolved):
            artifact = make_artifact(resolved)
            convention = dict(resolved.portfolio_timing.economic_return_convention())
            convention["market_timezone"] = "UTC"
            mismatched = governed_return_source(
                list(standard_returns().observations),
                economic_return_convention=convention,
            )
            with self.assertRaisesRegex(BacktestInputError, "measurement convention"):
                self._preflight(artifact, mismatched, path)

    def test_invalid_date_is_rejected_without_nearest_date_snapping(self) -> None:
        with entry_artifact(run2_payload()) as (path, resolved):
            artifact = make_artifact(resolved)
            frame = artifact.ranked.copy()
            frame.loc[frame.index[0], "decision_date"] = date(2025, 1, 30)
            altered = clone_artifact(artifact, frame, bind_content=True)
            with self.assertRaisesRegex(RankedArtifactError, "invalid decision"):
                self._preflight(altered, standard_returns(), path)

    def test_missing_return_and_terminal_event_fail_preopen(self) -> None:
        with entry_artifact(run2_payload()) as (path, resolved):
            artifact = make_artifact(resolved)
            missing = returns_for({
                (date(2025, 1, 31), date(2025, 2, 28)): (
                    ("AAA", 0.1, False),
                )
            })
            with self.assertRaisesRegex(BacktestInputError, "coverage"):
                self._preflight(artifact, missing, path)
            with self.assertRaisesRegex(BacktestInputError, "terminal"):
                self._preflight(
                    artifact, standard_returns(terminal=True), path
                )

    def test_data_bundle_mismatch_fails_while_native_mismatch_passes(self) -> None:
        with entry_artifact(run2_payload()) as (path, resolved):
            artifact = make_artifact(resolved)
            with self.assertRaisesRegex(BacktestInputError, "bundle"):
                self._preflight(
                    artifact,
                    returns_for({}, bundle="different-bundle"),
                    path,
                )
            prepared = self._preflight(
                artifact,
                standard_returns(),
                path,
            )
            self.assertNotEqual(
                prepared.lineage()["fact_source_native_vintage_identifier"],
                prepared.lineage()["return_source_native_vintage_identifier"],
            )

    def test_execution_clean_tree_and_commit_are_preopen_gates(self) -> None:
        with entry_artifact(run2_payload()) as (path, resolved):
            artifact = make_artifact(resolved)
            with patch(
                "graham_research.backtest.source_control_manifest", return_value=DIRTY
            ), self.assertRaisesRegex(BacktestInputError, "clean"):
                deterministic_portfolio_preflight(
                    artifact, standard_returns(), path, "/synthetic/repository",
                    sample_partition="development",
                )
            other_commit = clone_artifact(
                artifact,
                artifact.ranked,
                bind_content=False,
                feature_generation_code_commit="d" * 40,
                ranking_code_commit="d" * 40,
            )
            with self.assertRaisesRegex(BacktestInputError, "execution commit"):
                self._preflight(other_commit, standard_returns(), path)

    def test_initial_deployment_and_drifted_turnover(self) -> None:
        with entry_artifact(run2_payload()) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            artifact = make_artifact(resolved)
            result = self._run(
                artifact,
                standard_returns(),
                path,
                test_register(Path(temporary) / "register.jsonl"),
            )
        turnover = result.periods["traded_notional"].tolist()
        self.assertEqual(turnover[0], 1.0)
        self.assertGreater(turnover[1], 0.0)
        self.assertAlmostEqual(result.periods.iloc[0]["gross_return"], 0.05)
        self.assertAlmostEqual(
            result.periods.iloc[0]["cost"], turnover[0] * 100 / 10_000
        )

    def test_identical_returns_produce_zero_subsequent_turnover(self) -> None:
        with entry_artifact(run2_payload()) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            result = self._run(
                make_artifact(resolved),
                standard_returns(identical=True),
                path,
                test_register(Path(temporary) / "register.jsonl"),
            )
        self.assertAlmostEqual(result.periods.iloc[1]["traded_notional"], 0.0)

    def test_disjoint_switch_reaches_two_notional(self) -> None:
        mapping = {
            date(2025, 1, 31): (("AAA", 1.0), ("BBB", 0.9), ("CCC", 0.1), ("DDD", 0.0)),
            date(2025, 2, 28): (("CCC", 1.0), ("DDD", 0.9), ("AAA", 0.1), ("BBB", 0.0)),
            date(2025, 3, 31): (("CCC", 1.0), ("DDD", 0.9), ("AAA", 0.1), ("BBB", 0.0)),
        }
        source = returns_for({
            (date(2025, 1, 31), date(2025, 2, 28)): (("AAA", 0.0, False), ("BBB", 0.0, False)),
            (date(2025, 2, 28), date(2025, 3, 31)): (("CCC", 0.0, False), ("DDD", 0.0, False)),
            (date(2025, 3, 31), date(2025, 4, 30)): (("CCC", 0.0, False), ("DDD", 0.0, False)),
        })
        with entry_artifact(run2_payload()) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            artifact = clone_artifact(
                make_artifact(resolved), decision_frame(mapping), bind_content=True
            )
            result = self._run(
                artifact, source, path,
                test_register(Path(temporary) / "register.jsonl"),
            )
        self.assertAlmostEqual(result.periods.iloc[1]["traded_notional"], 2.0)

    def test_skip_preserves_absent_holdings_and_continuous_drift(self) -> None:
        mapping = {
            date(2025, 1, 31): (("AAA", 1.0), ("BBB", 0.9)),
            date(2025, 2, 28): (("CCC", 1.0),),
            date(2025, 3, 31): (("AAA", 1.0), ("BBB", 0.9)),
        }
        source = standard_returns()
        with entry_artifact(run2_payload(policy="skip_rebalance_date")) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            artifact = clone_artifact(
                make_artifact(resolved), decision_frame(mapping), bind_content=True
            )
            prepared = self._preflight(artifact, source, path)
            self.assertEqual(prepared.steps[1].held_security_ids, ("AAA", "BBB"))
            result = self._run(
                artifact, source, path,
                test_register(Path(temporary) / "register.jsonl"),
            )
        self.assertFalse(result.periods.iloc[1]["rebalance_executed"])
        self.assertEqual(result.periods.iloc[1]["traded_notional"], 0.0)
        self.assertNotEqual(
            result.positions[
                result.positions["decision_date"] == date(2025, 2, 28)
            ].iloc[0]["start_weight"],
            0.5,
        )

    def test_multiple_skips_compound_drift(self) -> None:
        dates = (
            date(2025, 1, 31), date(2025, 2, 28),
            date(2025, 3, 31), date(2025, 4, 30),
        )
        mapping = {
            dates[0]: (("AAA", 1.0), ("BBB", 0.9)),
            dates[1]: (("CCC", 1.0),),
            dates[2]: (("CCC", 1.0),),
            dates[3]: (("AAA", 1.0), ("BBB", 0.9)),
        }
        source = returns_for({
            (dates[0], dates[1]): (("AAA", 0.1, False), ("BBB", 0.0, False)),
            (dates[1], dates[2]): (("AAA", 0.1, False), ("BBB", 0.0, False)),
            (dates[2], dates[3]): (("AAA", 0.1, False), ("BBB", 0.0, False)),
            (dates[3], date(2025, 5, 31)): (("AAA", 0.1, False), ("BBB", 0.0, False)),
        })
        with entry_artifact(
            run2_payload(policy="skip_rebalance_date", development_end="2025-04-30")
        ) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            artifact = clone_artifact(
                make_artifact(resolved, dates), decision_frame(mapping), bind_content=True
            )
            result = self._run(
                artifact, source, path,
                test_register(Path(temporary) / "register.jsonl"),
            )
        self.assertEqual(
            result.periods["rebalance_executed"].tolist(),
            [True, False, False, True],
        )
        self.assertEqual(result.periods["traded_notional"].tolist()[1:3], [0.0, 0.0])

    def test_hold_available_redistributes_without_cash(self) -> None:
        mapping = {
            date(2025, 1, 31): (("AAA", 1.0), ("BBB", 0.9)),
            date(2025, 2, 28): (("CCC", 1.0),),
            date(2025, 3, 31): (("CCC", 1.0),),
        }
        source = returns_for({
            (date(2025, 1, 31), date(2025, 2, 28)): (("AAA", 0.0, False), ("BBB", 0.0, False)),
            (date(2025, 2, 28), date(2025, 3, 31)): (("CCC", 0.0, False),),
            (date(2025, 3, 31), date(2025, 4, 30)): (("CCC", 0.0, False),),
        })
        with entry_artifact(
            run2_payload(
                policy="hold_available_names",
                unfilled="redistribute_to_available_names",
            )
        ) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            artifact = clone_artifact(
                make_artifact(resolved), decision_frame(mapping), bind_content=True
            )
            result = self._run(
                artifact, source, path,
                test_register(Path(temporary) / "register.jsonl"),
            )
        row = result.positions[
            result.positions["decision_date"] == date(2025, 2, 28)
        ].iloc[0]
        self.assertEqual(row["security_id"], "CCC")
        self.assertEqual(row["start_weight"], 1.0)

    def test_preflight_failure_logs_blocked_but_no_open(self) -> None:
        with entry_artifact(run2_payload()) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")
            with self.assertRaises(BacktestInputError):
                self._run(
                    make_artifact(resolved),
                    returns_for({}),
                    path,
                    register,
                )
            events = register.history()
        self.assertEqual([item["event_type"] for item in events], ["blocked"])
        self.assertEqual(register.budget(2)["used"], 0)

    def test_first_outcome_use_observes_durable_open(self) -> None:
        import graham_research.backtest as backtest_module

        original = backtest_module._produce_portfolio_results_after_open
        with entry_artifact(run2_payload()) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")

            def guarded(authorization, opened, prepared):
                events = register.history()
                self.assertTrue(any(
                    event["event_type"] == "open"
                    and event["specification_id"] == opened.specification_id
                    for event in events
                ))
                self.assertFalse(any(event["event_type"] == "close" for event in events))
                return original(authorization, opened, prepared)

            with patch.object(
                backtest_module,
                "_produce_portfolio_results_after_open",
                side_effect=guarded,
            ) as producer:
                self._run(
                    make_artifact(resolved), standard_returns(), path, register
                )
            self.assertEqual(producer.call_count, 1)

    def test_prepared_digest_is_structural_and_outcome_values_are_not_embedded(self) -> None:
        with entry_artifact(run2_payload()) as (path, resolved):
            prepared = self._preflight(
                make_artifact(resolved), standard_returns(), path
            )
        serialized = canonical_json(prepared.prepared_experiment_payload()).decode()
        self.assertNotIn("gross_return", serialized)
        self.assertIn("return_observation_keys", serialized)
        self.assertTrue(all(
            set(observation) == {"security_id", "period_start", "period_end"}
            for step in prepared.execution_plan()["steps"]
            for observation in step["return_observation_keys"]
        ))
        self.assertEqual(len(prepared.prepared_experiment_digest()), 64)

    def test_open_revalidation_rejects_altered_lineage_parameters_and_digest(self) -> None:
        from graham_research.execution import execute_opened_experiment
        import graham_research.backtest as backtest_module

        mutations = (
            lambda event: event["lineage"].update(fact_source_id="altered-source"),
            lambda event: event["primary_parameters"].update(sample_partition="holdout_a"),
            lambda event: event.update(prepared_experiment_digest="f" * 64),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), entry_artifact(run2_payload()) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
                register = test_register(Path(temporary) / "register.jsonl")
                opened, prepared = self._capture_open(
                    make_artifact(resolved), standard_returns(), path, register
                )
                events = json.loads(json.dumps(register.history()))
                mutate(events[0])
                resign_open_event(events[0])
                rewrite_register_events(register, events)
                with patch.object(
                    backtest_module, "_produce_portfolio_results_after_open"
                ) as producer, self.assertRaises(SpecificationError):
                    execute_opened_experiment(opened, prepared, register)
                self.assertEqual(producer.call_count, 0)

    def test_open_for_prepared_a_cannot_execute_prepared_b(self) -> None:
        from graham_research.execution import execute_opened_experiment
        import graham_research.backtest as backtest_module

        with entry_artifact(run2_payload()) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")
            artifact_a = make_artifact(resolved)
            frame_b = artifact_a.ranked.copy()
            frame_b.loc[0, "composite_score"] = 0.75
            artifact_b = clone_artifact(artifact_a, frame_b, bind_content=True)
            opened_a, prepared_a = self._capture_open(
                artifact_a, standard_returns(), path, register
            )
            _opened_b, prepared_b = self._capture_open(
                artifact_b, standard_returns(), path, register
            )
            self.assertNotEqual(
                prepared_a.prepared_experiment_digest(),
                prepared_b.prepared_experiment_digest(),
            )
            with patch.object(
                backtest_module, "_produce_portfolio_results_after_open"
            ) as producer, self.assertRaisesRegex(
                SpecificationError, "prepared experiment"
            ):
                execute_opened_experiment(opened_a, prepared_b, register)
            self.assertEqual(producer.call_count, 0)

    def test_result_producer_requires_internal_authorization_before_returns(self) -> None:
        import graham_research.backtest as backtest_module

        with entry_artifact(run2_payload()) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")
            opened, prepared = self._capture_open(
                make_artifact(resolved), standard_returns(), path, register
            )
            with self.assertRaisesRegex(TypeError, "authorization"):
                backtest_module._produce_portfolio_results_after_open(
                    None, opened, prepared
                )

    def test_closed_open_cannot_execute_again_and_result_uses_open_lineage(self) -> None:
        from graham_research.execution import execute_opened_experiment
        import graham_research.backtest as backtest_module

        with entry_artifact(run2_payload()) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")
            opened, prepared = self._capture_open(
                make_artifact(resolved), standard_returns(), path, register
            )
            result = execute_opened_experiment(opened, prepared, register)
            self.assertEqual(result.lineage, opened.lineage)
            self.assertEqual(result.open_event_id, opened.open_event_id)
            self.assertEqual(result.open_event_digest, opened.open_event_digest)
            self.assertEqual(
                result.prepared_experiment_digest,
                opened.prepared_experiment_digest,
            )
            with patch.object(
                backtest_module, "_produce_portfolio_results_after_open"
            ) as producer, self.assertRaisesRegex(SpecificationError, "closed"):
                execute_opened_experiment(opened, prepared, register)
            self.assertEqual(producer.call_count, 0)

    def test_exhausted_budget_prevents_outcome_computation_entirely(self) -> None:
        import graham_research.backtest as backtest_module

        with entry_artifact(run2_payload(budget=1)) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")
            artifact = make_artifact(resolved)
            self._run(artifact, standard_returns(), path, register)
            with patch.object(
                backtest_module,
                "_produce_portfolio_results_after_open",
            ) as producer, self.assertRaises(BudgetExhausted):
                self._run(artifact, standard_returns(), path, register)
            self.assertEqual(producer.call_count, 0)
            event_types = [item["event_type"] for item in register.history()]
        self.assertEqual(event_types, ["open", "close", "blocked"])

    def test_terminal_skip_combination_fails_preopen_without_cash_assumption(self) -> None:
        with entry_artifact(
            run2_payload(policy="skip_rebalance_date")
        ) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")
            with self.assertRaisesRegex(BacktestInputError, "terminal"):
                self._run(
                    make_artifact(resolved),
                    standard_returns(terminal=True),
                    path,
                    register,
                )
            self.assertFalse(any(
                item["event_type"] == "open" for item in register.history()
            ))

    def test_post_open_undefined_drift_fails_closed_and_keeps_reservation(self) -> None:
        source = returns_for({
            (date(2025, 1, 31), date(2025, 2, 28)): (("AAA", -1.0, False), ("BBB", -1.0, False)),
            (date(2025, 2, 28), date(2025, 3, 31)): (("AAA", 0.0, False), ("BBB", 0.0, False)),
            (date(2025, 3, 31), date(2025, 4, 30)): (("AAA", 0.0, False), ("BBB", 0.0, False)),
        })
        with entry_artifact(run2_payload(budget=1)) as (path, resolved), tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")
            with self.assertRaises(OutcomeAccountingError):
                self._run(make_artifact(resolved), source, path, register)
            events = register.history()
            budget = register.budget(1)
        self.assertEqual([item["event_type"] for item in events], ["open", "close"])
        self.assertEqual(events[1]["status"], "failed")
        self.assertEqual(
            events[1]["failure_classification"],
            "post_open_outcome_accounting_failure",
        )
        self.assertEqual(budget["used"], 1)
        self.assertEqual(budget["remaining"], 0)
        self.assertIn("no release mechanism", budget["post_open_release_policy"])


class SpecificationRegisterTests(unittest.TestCase):
    def test_run_class_and_rationale_are_required_before_open(self) -> None:
        with self.assertRaises(SpecificationError):
            request(rationale="")
        with self.assertRaises((SpecificationError, TypeError)):
            SpecificationRequest(
                run_class=None,
                rationale="x",
                run_type=RunType.PORTFOLIO_BACKTEST,
            )

    def test_data_correction_requires_invalidated_specification(self) -> None:
        with self.assertRaisesRegex(SpecificationError, "invalidated"):
            SpecificationRequest(
                run_class=RunClass.DATA_CORRECTION,
                rationale="confirmed source correction",
                run_type=RunType.PORTFOLIO_BACKTEST,
            )

    def test_open_close_are_append_only_and_run_class_is_immutable(self) -> None:
        with entry_artifact(run2_payload()) as (entry_path, resolved), tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")
            with patch(
                "graham_research.backtest.source_control_manifest", return_value=CLEAN
            ):
                result = run_equal_weight_backtest(
                    make_artifact(resolved), standard_returns(), entry_path,
                    "/synthetic/repository", register, request(),
                    sample_partition="development",
                )
            open_snapshot = dict(register.history()[0])
            with self.assertRaisesRegex(SpecificationError, "immutable"):
                register.reclassify(result.specification_id, RunClass.DIAGNOSTIC)
            events = register.history()
            budget = register.budget(2)
        self.assertEqual(events[0], open_snapshot)
        self.assertEqual(events[0]["run_class"], "research_specification")
        self.assertEqual(events[1]["specification_id"], result.specification_id)
        self.assertEqual(budget["used"], 1)

    def test_nonresearch_portfolio_classes_are_blocked_before_open(self) -> None:
        with entry_artifact(run2_payload()) as (entry_path, resolved), tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")
            diagnostic = request(RunClass.DIAGNOSTIC)
            correction = SpecificationRequest(
                run_class=RunClass.DATA_CORRECTION,
                rationale="confirmed code correction",
                run_type=RunType.PORTFOLIO_BACKTEST,
                invalidated_specification_id="prior-id",
            )
            for item in (diagnostic, correction):
                with self.subTest(run_class=item.run_class), patch(
                    "graham_research.backtest.source_control_manifest",
                    return_value=CLEAN,
                ), self.assertRaises(SpecificationError):
                    run_equal_weight_backtest(
                        make_artifact(resolved), standard_returns(), entry_path,
                        "/synthetic/repository", register, item,
                        sample_partition="development",
                    )
            budget = register.budget(1)
            events = register.history()
        self.assertEqual(budget["used"], 0)
        self.assertEqual(budget["remaining"], 1)
        self.assertTrue(all(item["event_type"] == "blocked" for item in events))

    def test_register_has_no_public_generic_open_and_unbound_writes_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            register = SpecificationRegister(Path(temporary) / "register.jsonl")
            self.assertFalse(hasattr(register, "open"))
            with self.assertRaisesRegex(SpecificationError, "for_repository"):
                register._record_blocked(
                    request(), stage="test", failure_classification="test",
                    message="must not write",
                )

    def test_malformed_history_fails_instead_of_undercounting_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")
            register.path.write_text(
                '{"schema_version":2,"event_type":"open"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SpecificationError, "invalid keys"):
                register.budget(1)

    def test_full_history_validation_rejects_all_confirmed_corruptions(self) -> None:
        with entry_artifact(run2_payload()) as (entry_path, resolved), tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")
            with patch(
                "graham_research.backtest.source_control_manifest", return_value=CLEAN
            ):
                run_equal_weight_backtest(
                    make_artifact(resolved), standard_returns(), entry_path,
                    "/synthetic/repository", register, request(),
                    sample_partition="development",
                )
            base = json.loads(json.dumps(register.history()))
            mutations = {
                "unknown_schema": lambda events: events[0].update(schema_version=99),
                "unknown_event_type": lambda events: events[0].update(event_type="other"),
                "unknown_event_key": lambda events: events[0].update(extra="x"),
                "missing_event_key": lambda events: events[0].pop("rationale"),
                "invalid_event_id": lambda events: events[0].update(event_id=""),
                "duplicate_event_id": lambda events: events[1].update(
                    event_id=events[0]["event_id"]
                ),
                "duplicate_open_specification": lambda events: (
                    events.append({
                        **events[0],
                        "event_id": "00000000-0000-0000-0000-000000000002",
                    }),
                    resign_open_event(events[-1]),
                ),
                "close_without_prior_open": lambda events: events.pop(0),
                "bad_close_open_mapping": lambda events: events[1].update(
                    open_event_id="00000000-0000-0000-0000-000000000000"
                ),
                "duplicate_close": lambda events: events.append({
                    **events[1],
                    "event_id": "00000000-0000-0000-0000-000000000001",
                }),
                "altered_run_class": lambda events: (
                    events[0].update(run_class="diagnostic"),
                    resign_open_event(events[0]),
                ),
                "incompatible_run_type": lambda events: (
                    events[0].update(run_type="unknown"),
                    resign_open_event(events[0]),
                ),
                "altered_budget_effect": lambda events: (
                    events[0].update(budget_effect="none"),
                    resign_open_event(events[0]),
                ),
                "malformed_lineage": lambda events: (
                    events[0]["lineage"].pop("fact_source_id"),
                    resign_open_event(events[0]),
                ),
                "malformed_primary_parameters": lambda events: (
                    events[0]["primary_parameters"].pop("sample_partition"),
                    resign_open_event(events[0]),
                ),
                "malformed_prepared_digest": lambda events: (
                    events[0].update(prepared_experiment_digest="not-a-digest"),
                    resign_open_event(events[0]),
                ),
                "invalid_open_event_digest": lambda events: events[0].update(
                    open_event_digest="0" * 64
                ),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    events = json.loads(json.dumps(base))
                    mutate(events)
                    rewrite_register_events(register, events)
                    with self.assertRaises(SpecificationError):
                        register.history()

    def test_data_correction_with_real_prior_still_cannot_execute_without_invalidation(self) -> None:
        with entry_artifact(run2_payload()) as (entry_path, resolved), tempfile.TemporaryDirectory() as temporary:
            register = test_register(Path(temporary) / "register.jsonl")
            with patch(
                "graham_research.backtest.source_control_manifest", return_value=CLEAN
            ):
                result = run_equal_weight_backtest(
                    make_artifact(resolved), standard_returns(), entry_path,
                    "/synthetic/repository", register, request(),
                    sample_partition="development",
                )
            correction = SpecificationRequest(
                run_class=RunClass.DATA_CORRECTION,
                rationale="confirmed source correction",
                run_type=RunType.PORTFOLIO_BACKTEST,
                invalidated_specification_id=result.specification_id,
            )
            with patch(
                "graham_research.backtest.source_control_manifest", return_value=CLEAN
            ), self.assertRaisesRegex(SpecificationError, "no governed.*invalidation"):
                run_equal_weight_backtest(
                    make_artifact(resolved), standard_returns(), entry_path,
                    "/synthetic/repository", register, correction,
                    sample_partition="development",
                )
            events = register.history()
        self.assertEqual(
            [event["event_type"] for event in events],
            ["open", "close", "blocked"],
        )

    def test_default_register_does_not_dirty_real_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repo"
            state = root / "state"
            repository.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repository, check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Run2 Test"],
                cwd=repository, check=True,
            )
            tracked = repository / "tracked.txt"
            tracked.write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "clean"], cwd=repository, check=True)
            with patch.dict(
                os.environ,
                {"GRAHAM_RESEARCH_STATE_DIR": str(state)},
                clear=False,
            ):
                register = SpecificationRegister.for_repository(repository)
                register._record_blocked(
                    request(RunClass.DIAGNOSTIC),
                    stage="test",
                    failure_classification="synthetic",
                    message="structural only",
                )
            manifest = source_control_manifest(repository)
        self.assertFalse(manifest["dirty"])
        self.assertFalse(str(register.path).startswith(str(repository)))
        self.assertIn("Every research_specification OPEN", RESERVATION_SEMANTICS)

    def test_explicit_register_paths_are_outside_or_gitignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repo"
            repository.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repository, check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Run2 Test"],
                cwd=repository, check=True,
            )
            (repository / ".gitignore").write_text(".state/\n", encoding="utf-8")
            (repository / "tracked.txt").write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(["git", "commit", "-qm", "clean"], cwd=repository, check=True)

            outside = SpecificationRegister.for_repository(
                repository, path=root / "outside.jsonl"
            )
            outside._record_blocked(
                request(RunClass.DIAGNOSTIC), stage="test",
                failure_classification="synthetic", message="outside",
            )
            inside_ignored = SpecificationRegister.for_repository(
                repository, path=repository / ".state" / "register.jsonl"
            )
            inside_ignored._record_blocked(
                request(RunClass.DIAGNOSTIC), stage="test",
                failure_classification="synthetic", message="ignored",
            )
            invalid = repository / "unignored-register.jsonl"
            with self.assertRaisesRegex(SpecificationError, "gitignored"):
                SpecificationRegister.for_repository(repository, path=invalid)
            with self.assertRaisesRegex(SpecificationError, "for_repository"):
                run_equal_weight_backtest(
                    None, None, "/not-reached", repository,
                    SpecificationRegister(invalid), request(),
                    sample_partition="development",
                )
            status = subprocess.run(
                ["git", "status", "--porcelain"], cwd=repository,
                check=True, capture_output=True, text=True,
            ).stdout
        self.assertEqual(status, "")
        self.assertFalse(invalid.exists())


class Run2CliTests(unittest.TestCase):
    def test_spec_log_budget_and_ranked_inspection_commands(self) -> None:
        with entry_artifact(run2_payload()) as (entry_path, resolved), tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            register_path = root / "register.jsonl"
            register = test_register(register_path)
            register._record_blocked(
                request(RunClass.DIAGNOSTIC),
                stage="test",
                failure_classification="synthetic",
                message="structural only",
            )
            ranking_path = root / "ranking.manifest.json"
            write_ranking_manifest(make_artifact(resolved), ranking_path)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(cli_main([
                    "spec-log", "--repository", "/synthetic",
                    "--register", str(register_path),
                ]), 0)
                self.assertEqual(cli_main([
                    "spec-budget", str(entry_path),
                    "--repository", "/synthetic",
                    "--register", str(register_path),
                ]), 0)
                self.assertEqual(cli_main([
                    "inspect-ranked-artifact", str(ranking_path),
                ]), 0)
            rendered = output.getvalue()
        self.assertIn('"event_type": "blocked"', rendered)
        self.assertIn('"remaining": 2', rendered)
        self.assertIn('"decision_frame_content_verified": true', rendered)


if __name__ == "__main__":
    unittest.main()
