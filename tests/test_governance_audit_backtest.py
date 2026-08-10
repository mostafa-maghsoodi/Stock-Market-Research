from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import date, datetime
from io import StringIO
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import graham_research.governance as governance
from graham_research.audit import audit_facts
from graham_research.backtest import run_equal_weight_backtest
from graham_research.cli import main as cli_main
from graham_research.domain import AuditDecision, FactObservation
from graham_research.features import FeatureEngine
from graham_research.governance import (
    GovernanceError,
    MalformedEntry001V2,
    MissingEntry001SchemaVersion,
    UnresolvedEntry001,
    UnsupportedEntry001SchemaVersion,
    freeze_artifact,
    freeze_entry_001,
    load_resolved_entry_001,
    proxy_registry_digest,
    require_entry_001,
    verify_artifact,
)
from graham_research.ranking import CompositeConfig

from run1_fixtures import (
    FROZEN_PINS,
    SYNTHETIC_MINIMUM_FEATURE_COVERAGE,
    SYNTHETIC_NEAR_ZERO_THRESHOLD,
    complete_entry_001,
    fact,
    matching_frozen_runtime,
    proxy_payload,
)


SYNTHETIC_REPOSITORY = "/synthetic/repository"
SYNTHETIC_SOURCE_CONTROL = {
    "vcs": "git",
    "commit": "a" * 40,
    "dirty": False,
}


def wrapped(payload: dict[str, object]) -> dict[str, object]:
    return {**payload, "entry": "001", "created_at": "synthetic"}


def write_artifact(path: Path, payload: dict[str, object]) -> None:
    freeze_artifact(path, wrapped(payload))


def load_payload(payload: dict[str, object]):
    temporary = tempfile.TemporaryDirectory()
    path = Path(temporary.name) / "entry001.json"
    write_artifact(path, payload)
    with matching_frozen_runtime():
        result = load_resolved_entry_001(path)
    temporary.cleanup()
    return result


class Entry001V2SchemaTests(unittest.TestCase):
    def test_proposed_entry_rejects_unknown_top_level_key(self) -> None:
        payload = complete_entry_001()
        payload["unknown"] = "uninterpreted"
        with self.assertRaisesRegex(MalformedEntry001V2, "top-level keys"):
            governance._validate_entry_001(
                payload,
                validate_against_project_pins=False,
            )

    def test_frozen_entry_rejects_unknown_top_level_key(self) -> None:
        payload = wrapped(complete_entry_001())
        payload["unknown"] = "uninterpreted"
        with self.assertRaisesRegex(MalformedEntry001V2, "top-level keys"):
            governance._validate_entry_001(
                payload,
                validate_against_project_pins=False,
            )

    def test_exact_proposed_and_frozen_top_level_shapes_remain_valid(self) -> None:
        proposed = complete_entry_001()
        self.assertIsNone(
            governance._validate_entry_001(
                proposed,
                validate_against_project_pins=False,
            )
        )
        self.assertIsNone(
            governance._validate_entry_001(
                wrapped(proposed),
                validate_against_project_pins=False,
            )
        )

    def test_frozen_wrapper_must_be_complete_and_mark_entry_001(self) -> None:
        for update in (
            {"entry": "001"},
            {"created_at": "synthetic"},
            {"entry": "002", "created_at": "synthetic"},
        ):
            with self.subTest(update=update):
                payload = {**complete_entry_001(), **update}
                with self.assertRaises(MalformedEntry001V2):
                    governance._validate_entry_001(
                        payload,
                        validate_against_project_pins=False,
                    )

    def test_prefreeze_path_rejects_artifact_wrapper_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(MalformedEntry001V2):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    wrapped(complete_entry_001()),
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_unversioned_entry_is_rejected_as_schema_error(self) -> None:
        payload = complete_entry_001()
        del payload["entry_001_schema_version"]
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(MissingEntry001SchemaVersion):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_only_v2_is_supported(self) -> None:
        payload = complete_entry_001()
        payload["entry_001_schema_version"] = 1
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(UnsupportedEntry001SchemaVersion):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_governed_restatement_policy_is_closed_to_first_reported(self) -> None:
        payload = complete_entry_001()
        payload["pit_conventions"]["restatement_policy"] = "latest_known"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(MalformedEntry001V2):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_pit_conventions_are_strictly_validated(self) -> None:
        for change in (
            {"unknown": "uninterpreted"},
            {"availability_timestamp": "an unsupported timestamp convention"},
        ):
            payload = complete_entry_001()
            payload["pit_conventions"].update(change)
            with self.subTest(change=change), self.assertRaises(MalformedEntry001V2):
                governance._validate_entry_001(
                    payload,
                    validate_against_project_pins=False,
                )

    def test_schema_failure_is_distinct_from_hash_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            schema_path = Path(temporary) / "schema.json"
            payload = complete_entry_001()
            del payload["entry_001_schema_version"]
            freeze_artifact(schema_path, wrapped(payload))
            with self.assertRaises(MissingEntry001SchemaVersion):
                verify_artifact(schema_path)

            corrupt_path = Path(temporary) / "corrupt.json"
            write_artifact(corrupt_path, complete_entry_001())
            content = json.loads(corrupt_path.read_text())
            content["holding_period"] = "changed"
            corrupt_path.write_text(json.dumps(content))
            with self.assertRaisesRegex(GovernanceError, "hash mismatch"):
                verify_artifact(corrupt_path)

    def test_unresolved_required_field_prevents_freeze(self) -> None:
        payload = complete_entry_001()
        payload["holding_period"] = "UNRESOLVED"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(UnresolvedEntry001):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_missing_proxy_structure_prevents_freeze(self) -> None:
        payload = complete_entry_001()
        del payload["proxy_registry"][0]["required_period_structure"]
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(MalformedEntry001V2):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_frequency_partition_overlap_omission_and_undeclared_rejected(self) -> None:
        for governed, exempt in (
            (["gross_profit", "total_assets"], ["total_assets"]),
            (["gross_profit"], []),
            (["gross_profit", "total_assets", "foreign"], []),
        ):
            payload = complete_entry_001(("gross_profitability",))
            proxy = payload["proxy_registry"][0]
            proxy["frequency_governed_source_fields"] = governed
            proxy["frequency_exempt_source_fields"] = exempt
            with self.subTest(governed=governed, exempt=exempt), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(MalformedEntry001V2):
                    freeze_entry_001(
                        Path(temporary) / "entry.json",
                        payload,
                        repository=SYNTHETIC_REPOSITORY,
                    )

    def test_unresolved_does_not_mask_malformed_frequency_partitions(self) -> None:
        malformed_partitions = (
            (["UNRESOLVED", "undeclared"], ["UNRESOLVED"]),
            (["UNRESOLVED", "gross_profit"], ["UNRESOLVED", "gross_profit"]),
            (["UNRESOLVED", "gross_profit", "gross_profit"], ["UNRESOLVED"]),
        )
        for governed, exempt in malformed_partitions:
            payload = complete_entry_001(("gross_profitability",))
            proxy = payload["proxy_registry"][0]
            proxy["frequency_governed_source_fields"] = governed
            proxy["frequency_exempt_source_fields"] = exempt
            with self.subTest(governed=governed, exempt=exempt):
                with self.assertRaises(MalformedEntry001V2):
                    governance._validate_proxy_registry_structure(
                        payload["proxy_registry"]
                    )

    def test_clean_unresolved_frequency_partition_is_structural_not_resolved(self) -> None:
        template = json.loads(
            (Path(__file__).parents[1] / "examples" / "entry001.template.json").read_text()
        )
        governance._validate_proxy_registry_structure(template["proxy_registry"])
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(UnresolvedEntry001):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    template,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_template_lists_all_supported_candidates_and_keeps_each_unresolved(self) -> None:
        template = json.loads(
            (Path(__file__).parents[1] / "examples" / "entry001.template.json").read_text()
        )
        expected_names = [
            "fcf_ev",
            "ebit_ev",
            "gross_profitability",
            "roic",
            "operating_margin_change",
            "fcf_margin_change",
            "revenue_acceleration",
        ]
        self.assertEqual(
            [proxy["name"] for proxy in template["proxy_registry"]],
            expected_names,
        )
        self.assertEqual(set(expected_names), set(governance.SUPPORTED_PROXY_SHAPES))
        for proxy in template["proxy_registry"]:
            with self.subTest(proxy=proxy["name"]):
                self.assertTrue(governance._find_unresolved(proxy))
        for proxy_name in ("fcf_ev", "ebit_ev"):
            proxy = next(
                item for item in template["proxy_registry"]
                if item["name"] == proxy_name
            )
            market_roles = [
                role for role in proxy["required_period_structure"]
                if role["role_kind"] == "market_role"
            ]
            self.assertTrue(market_roles)
            self.assertTrue(
                all(role["alignment_rule"] == "UNRESOLVED" for role in market_roles)
            )

    def test_shipped_governance_placeholders_are_structural_then_unresolved(self) -> None:
        template = json.loads(
            (Path(__file__).parents[1] / "examples" / "entry001.template.json").read_text()
        )
        self.assertTrue(
            governance._validate_environment_manifest_structure(
                template["environment_manifest"]
            )
        )
        self.assertTrue(
            governance._validate_source_control_section_structure(
                template["source_control"]
            )
        )
        self.assertTrue(
            governance._validate_transaction_cost_model_structure(
                template["transaction_cost_model"]
            )
        )
        self.assertIsNone(template["transaction_cost_model"]["one_way_cost_bps"])
        with self.assertRaises(UnresolvedEntry001):
            governance._validate_entry_001(
                template,
                validate_against_project_pins=False,
            )
        self.assertIsNone(template["transaction_cost_model"]["one_way_cost_bps"])

    def test_malformed_source_control_precedes_unrelated_unresolved(self) -> None:
        payload = complete_entry_001()
        payload["holding_period"] = "UNRESOLVED"
        payload["source_control"]["commit"] = "not-a-full-commit"
        with self.assertRaisesRegex(GovernanceError, "source_control.commit") as caught:
            governance._validate_entry_001(
                payload,
                validate_against_project_pins=False,
            )
        self.assertNotIsInstance(caught.exception, UnresolvedEntry001)

    def test_malformed_environment_manifest_precedes_unrelated_unresolved(self) -> None:
        payload = complete_entry_001()
        payload["holding_period"] = "UNRESOLVED"
        payload["environment_manifest"] = {"schema_version": 1}
        with self.assertRaisesRegex(GovernanceError, "missing required fields") as caught:
            governance._validate_entry_001(
                payload,
                validate_against_project_pins=False,
            )
        self.assertNotIsInstance(caught.exception, UnresolvedEntry001)

    def test_resolved_environment_manifest_rejects_unknown_keys(self) -> None:
        payload = complete_entry_001()
        payload["environment_manifest"]["unknown"] = "uninterpreted"
        with self.assertRaisesRegex(GovernanceError, "unknown fields"):
            governance._validate_entry_001(
                payload,
                validate_against_project_pins=False,
            )

    def test_resolved_source_control_rejects_unknown_keys(self) -> None:
        payload = complete_entry_001()
        payload["source_control"]["unknown"] = "uninterpreted"
        with self.assertRaisesRegex(GovernanceError, "invalid keys"):
            governance._validate_entry_001(
                payload,
                validate_against_project_pins=False,
            )

    def test_malformed_transaction_cost_model_precedes_unrelated_unresolved(self) -> None:
        malformed_models = (
            {
                "convention": "traded_notional_times_one_way_bps",
                "one_way_cost_bps": 100.0,
                "undeclared": True,
            },
            {
                "convention": "traded_notional_times_one_way_bps",
                "one_way_cost_bps": "not-a-number",
            },
        )
        for model in malformed_models:
            payload = complete_entry_001()
            payload["holding_period"] = "UNRESOLVED"
            payload["transaction_cost_model"] = model
            with self.subTest(model=model):
                with self.assertRaises(GovernanceError) as caught:
                    governance._validate_entry_001(
                        payload,
                        validate_against_project_pins=False,
                    )
                self.assertNotIsInstance(caught.exception, UnresolvedEntry001)

    def test_arbitrary_status_objects_are_not_governance_placeholders(self) -> None:
        for section in ("environment_manifest", "source_control"):
            payload = complete_entry_001()
            payload["holding_period"] = "UNRESOLVED"
            payload[section] = {"status": "REPLACE_WITH_AN_UNRECOGNIZED_VALUE"}
            with self.subTest(section=section):
                with self.assertRaises(GovernanceError) as caught:
                    governance._validate_entry_001(
                        payload,
                        validate_against_project_pins=False,
                    )
                self.assertNotIsInstance(caught.exception, UnresolvedEntry001)

    def test_null_transaction_cost_remains_unresolved_without_default(self) -> None:
        payload = complete_entry_001()
        payload["transaction_cost_model"]["one_way_cost_bps"] = None
        with self.assertRaises(UnresolvedEntry001):
            governance._validate_entry_001(
                payload,
                validate_against_project_pins=False,
            )
        self.assertIsNone(payload["transaction_cost_model"]["one_way_cost_bps"])

    def test_invalid_required_frequency_rejected(self) -> None:
        payload = complete_entry_001()
        payload["proxy_registry"][0]["required_reporting_frequency"] = "monthly"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(MalformedEntry001V2):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_proxy_execution_fields_are_closed_to_run1_literals(self) -> None:
        invalid = (
            ("transformation", "zscore"),
            ("availability_lag", "30_days"),
            ("missing_data_treatment", "impute_zero"),
        )
        for field_name, value in invalid:
            payload = complete_entry_001()
            payload["proxy_registry"][0][field_name] = value
            with self.subTest(field_name=field_name):
                with self.assertRaises(MalformedEntry001V2):
                    governance._validate_entry_001(
                        payload,
                        validate_against_project_pins=False,
                    )

    def test_exact_run1_proxy_execution_literals_are_valid(self) -> None:
        proxy = complete_entry_001()["proxy_registry"][0]
        self.assertEqual(
            {
                field_name: proxy[field_name]
                for field_name in governance.SUPPORTED_PROXY_EXECUTION_LITERALS
            },
            governance.SUPPORTED_PROXY_EXECUTION_LITERALS,
        )
        governance._validate_proxy_registry_structure([proxy])

    def test_frequency_and_governance_cannot_be_redeclared_on_role(self) -> None:
        for extra in (
            {"required_reporting_frequency": "annual"},
            {"frequency_governed": True},
        ):
            payload = complete_entry_001()
            payload["proxy_registry"][0]["required_period_structure"][0].update(extra)
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(MalformedEntry001V2):
                    freeze_entry_001(
                        Path(temporary) / "entry.json",
                        payload,
                        repository=SYNTHETIC_REPOSITORY,
                    )

    def test_role_kind_is_required_and_closed(self) -> None:
        for change in (None, "hybrid_role"):
            payload = complete_entry_001()
            role = payload["proxy_registry"][0]["required_period_structure"][0]
            if change is None:
                del role["role_kind"]
            else:
                role["role_kind"] = change
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(MalformedEntry001V2):
                    freeze_entry_001(
                        Path(temporary) / "entry.json",
                        payload,
                        repository=SYNTHETIC_REPOSITORY,
                    )

    def test_accounting_role_rejects_alignment_rule(self) -> None:
        payload = complete_entry_001()
        payload["proxy_registry"][0]["required_period_structure"][0]["alignment_rule"] = "UNRESOLVED"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(MalformedEntry001V2):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_market_role_rejects_fiscal_offset_and_resolved_alignment(self) -> None:
        template = json.loads(
            (Path(__file__).parents[1] / "examples" / "entry001.template.json").read_text()
        )
        market = template["proxy_registry"][0]["required_period_structure"][2]
        market["fiscal_year_offset"] = 0
        with self.assertRaises(MalformedEntry001V2):
            governance._validate_proxy_registry_structure(template["proxy_registry"])
        del market["fiscal_year_offset"]
        market["alignment_rule"] = "decision_date"
        with self.assertRaises(MalformedEntry001V2):
            governance._validate_proxy_registry_structure(template["proxy_registry"])

    def test_market_role_is_structurally_representable_but_unfreezable(self) -> None:
        template = json.loads(
            (Path(__file__).parents[1] / "examples" / "entry001.template.json").read_text()
        )
        governance._validate_proxy_registry_structure(template["proxy_registry"])
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(UnresolvedEntry001):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    template,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_duplicate_roles_and_pairs_are_rejected(self) -> None:
        payload = complete_entry_001(("revenue_acceleration",))
        roles = payload["proxy_registry"][0]["required_period_structure"]
        roles[1]["role_name"] = roles[0]["role_name"]
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(MalformedEntry001V2):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_denominator_requires_declared_roles_and_valid_enum(self) -> None:
        for key, value in (
            ("contributing_roles", ["not_a_role"]),
            ("transformation", "harmonic_magic"),
        ):
            payload = complete_entry_001()
            payload["proxy_registry"][0]["denominator_definitions"][0][key] = value
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(MalformedEntry001V2):
                    freeze_entry_001(
                        Path(temporary) / "entry.json",
                        payload,
                        repository=SYNTHETIC_REPOSITORY,
                    )

    def test_unresolved_threshold_prevents_freeze(self) -> None:
        payload = complete_entry_001()
        policy = payload["proxy_registry"][0]["denominator_definitions"][0]["denominator_policy"]
        policy["near_zero_absolute_threshold"] = "UNRESOLVED"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(UnresolvedEntry001):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_invalid_denominator_action_is_rejected(self) -> None:
        payload = complete_entry_001()
        policy = payload["proxy_registry"][0]["denominator_definitions"][0]["denominator_policy"]
        policy["negative"] = "winsorize_silently"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(MalformedEntry001V2):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_missing_and_zero_allow_value_cannot_resolve(self) -> None:
        for action_name in ("missing", "zero"):
            payload = complete_entry_001(("gross_profitability",))
            policy = payload["proxy_registry"][0]["denominator_definitions"][0]["denominator_policy"]
            policy[action_name] = "allow_value"
            with self.subTest(action_name=action_name):
                with self.assertRaises(MalformedEntry001V2):
                    governance._validate_entry_001(
                        payload,
                        validate_against_project_pins=False,
                    )
                with self.assertRaises(ValueError):
                    governance._parse_proxy_registry(payload["proxy_registry"])

    def test_unimplemented_formula_cannot_freeze(self) -> None:
        payload = complete_entry_001()
        payload["proxy_registry"][0]["formula"] = "gross_profit / closing_assets"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(MalformedEntry001V2):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )

    def test_prior_gross_profit_dependency_must_be_resolved(self) -> None:
        payload = complete_entry_001(("gross_profitability",))
        payload["proxy_registry"][0]["prior_gross_profit_dependency"] = "UNRESOLVED"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(UnresolvedEntry001):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )


class RegistryDigestTests(unittest.TestCase):
    def _digest(self, proxy: dict[str, object]) -> str:
        return proxy_registry_digest(governance._parse_proxy_registry([proxy]))

    def test_identical_registry_content_has_identical_digest(self) -> None:
        self.assertEqual(
            self._digest(proxy_payload("gross_profitability")),
            self._digest(proxy_payload("gross_profitability")),
        )

    def test_governed_semantic_changes_change_digest(self) -> None:
        mutations = (
            lambda p: p["denominator_definitions"][0]["denominator_policy"].update({"negative": "allow_value"}),
            lambda p: p.update({"required_reporting_frequency": "quarterly"}),
            lambda p: p.update({
                "frequency_governed_source_fields": ["gross_profit"],
                "frequency_exempt_source_fields": ["total_assets"],
            }),
            lambda p: p["required_period_structure"][2].update({"fiscal_year_offset": -2}),
            lambda p: p.update({"construct": "other_construct"}),
        )
        original = proxy_payload("gross_profitability")
        baseline = self._digest(original)
        for mutation in mutations:
            changed = proxy_payload("gross_profitability")
            mutation(changed)
            with self.subTest(mutation=mutation):
                self.assertNotEqual(baseline, self._digest(changed))


class RuntimeAndFreezeTests(unittest.TestCase):
    def test_valid_v2_freezes_and_loads(self) -> None:
        payload = complete_entry_001()
        with (
            tempfile.TemporaryDirectory() as temporary,
            matching_frozen_runtime(),
            patch(
                "graham_research.governance.project_dependency_pins",
                return_value=FROZEN_PINS,
            ),
            patch(
                "graham_research.governance.source_control_manifest",
                return_value=dict(SYNTHETIC_SOURCE_CONTROL),
            ) as source_control_manifest,
        ):
            path = Path(temporary) / "entry.json"
            freeze_entry_001(
                path,
                payload,
                repository=SYNTHETIC_REPOSITORY,
            )
            loaded, runtime = require_entry_001(path)
        source_control_manifest.assert_called_once_with(SYNTHETIC_REPOSITORY)
        self.assertEqual(loaded["entry_001_schema_version"], 2)
        self.assertFalse(runtime.warnings)

    def test_freeze_rejects_actual_dirty_repository(self) -> None:
        payload = complete_entry_001()
        actual = {**SYNTHETIC_SOURCE_CONTROL, "dirty": True}
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch(
                "graham_research.governance.project_dependency_pins",
                return_value=FROZEN_PINS,
            ),
            patch(
                "graham_research.governance.source_control_manifest",
                return_value=actual,
            ) as source_control_manifest,
        ):
            with self.assertRaisesRegex(GovernanceError, "repository to be clean"):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )
        source_control_manifest.assert_called_once_with(SYNTHETIC_REPOSITORY)

    def test_freeze_rejects_stale_payload_commit(self) -> None:
        payload = complete_entry_001()
        payload["source_control"]["commit"] = "b" * 40
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch(
                "graham_research.governance.project_dependency_pins",
                return_value=FROZEN_PINS,
            ),
            patch(
                "graham_research.governance.source_control_manifest",
                return_value=dict(SYNTHETIC_SOURCE_CONTROL),
            ) as source_control_manifest,
        ):
            with self.assertRaisesRegex(GovernanceError, "does not match"):
                freeze_entry_001(
                    Path(temporary) / "entry.json",
                    payload,
                    repository=SYNTHETIC_REPOSITORY,
                )
        source_control_manifest.assert_called_once_with(SYNTHETIC_REPOSITORY)

    def test_freeze_rejects_payload_vcs_or_dirty_mismatch(self) -> None:
        for key, value in (("vcs", "not-git"), ("dirty", True)):
            payload = complete_entry_001()
            payload["source_control"][key] = value
            with (
                self.subTest(key=key, value=value),
                tempfile.TemporaryDirectory() as temporary,
                patch(
                    "graham_research.governance.project_dependency_pins",
                    return_value=FROZEN_PINS,
                ),
                patch(
                    "graham_research.governance.source_control_manifest",
                    return_value=dict(SYNTHETIC_SOURCE_CONTROL),
                ) as source_control_manifest,
            ):
                with self.assertRaisesRegex(GovernanceError, "does not match"):
                    freeze_entry_001(
                        Path(temporary) / "entry.json",
                        payload,
                        repository=SYNTHETIC_REPOSITORY,
                    )
                source_control_manifest.assert_called_once_with(
                    SYNTHETIC_REPOSITORY
                )

    def test_cli_freeze_requires_and_forwards_explicit_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "entry.config.json"
            output = Path(temporary) / "entry.json"
            config.write_text(json.dumps(complete_entry_001()), encoding="utf-8")
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
                cli_main([
                    "freeze-entry-001",
                    str(config),
                    str(output),
                ])
            self.assertEqual(raised.exception.code, 2)
            stdout = StringIO()
            with (
                matching_frozen_runtime(),
                patch(
                    "graham_research.governance.project_dependency_pins",
                    return_value=FROZEN_PINS,
                ),
                patch(
                    "graham_research.governance.source_control_manifest",
                    return_value=dict(SYNTHETIC_SOURCE_CONTROL),
                ) as source_control_manifest,
                redirect_stdout(stdout),
            ):
                self.assertEqual(
                    cli_main([
                        "freeze-entry-001",
                        str(config),
                        str(output),
                        "--repository",
                        SYNTHETIC_REPOSITORY,
                    ]),
                    0,
                )
            source_control_manifest.assert_called_once_with(SYNTHETIC_REPOSITORY)
            self.assertTrue(output.is_file())
            self.assertTrue(stdout.getvalue().strip())

    def test_runtime_dependency_drift_blocks_load(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry.json"
            write_artifact(path, complete_entry_001())
            versions = {**FROZEN_PINS, "numpy": "999.0.0"}
            with (
                patch("graham_research.governance.importlib.metadata.version", side_effect=lambda name: versions[name]),
                patch("graham_research.governance.platform.python_version", return_value="3.12.0"),
                patch("graham_research.governance.platform.python_implementation", return_value="CPython"),
                patch("graham_research.governance.platform.platform", return_value="synthetic-test-platform"),
            ):
                with self.assertRaises(GovernanceError):
                    require_entry_001(path)

    def test_cli_surfaces_incidental_runtime_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry.json"
            write_artifact(path, complete_entry_001())
            stdout, stderr = StringIO(), StringIO()
            versions = dict(FROZEN_PINS)
            with (
                patch("graham_research.governance.importlib.metadata.version", side_effect=lambda name: versions[name]),
                patch("graham_research.governance.platform.python_version", return_value="3.12.9"),
                patch("graham_research.governance.platform.python_implementation", return_value="CPython"),
                patch("graham_research.governance.platform.platform", return_value="patched-platform"),
                redirect_stdout(stdout), redirect_stderr(stderr),
            ):
                self.assertEqual(cli_main(["check-entry-001", str(path)]), 0)
            self.assertEqual(json.loads(stdout.getvalue())["runtime_validation"]["status"], "matched_with_warnings")
            self.assertEqual(stderr.getvalue().count("WARNING:"), 2)


class AuditFixtureAndBacktestTests(unittest.TestCase):
    @staticmethod
    def _finding(report, text: str):
        return next(item for item in report.findings if text in item.finding)

    def test_exact_repeated_source_identity_is_duplicate_and_restricted(self) -> None:
        row = fact("AAA", "revenue", 2024, 1, accession="stable")
        report = audit_facts([row, row])
        finding = self._finding(report, "Duplicate source observations")
        self.assertIs(
            finding.eligibility_decision,
            AuditDecision.ADMISSIBLE_RESTRICTED,
        )
        self.assertNotIn(
            "internally contradictory",
            {item.finding for item in report.findings},
        )

    def test_conflicting_value_is_excluded_and_not_called_duplicate(self) -> None:
        row = fact("AAA", "revenue", 2024, 1, accession="stable")
        report = audit_facts([row, replace(row, value=2)])
        finding = self._finding(report, "internally contradictory")
        self.assertIs(finding.eligibility_decision, AuditDecision.EXCLUDED)
        self.assertFalse(
            any("Duplicate source observations" in item.finding for item in report.findings)
        )

    def test_conflicting_unit_is_excluded_and_not_called_duplicate(self) -> None:
        row = fact("AAA", "revenue", 2024, 1, accession="stable")
        report = audit_facts([row, replace(row, unit="EUR")])
        finding = self._finding(report, "internally contradictory")
        self.assertIs(finding.eligibility_decision, AuditDecision.EXCLUDED)
        self.assertFalse(
            any("Duplicate source observations" in item.finding for item in report.findings)
        )

    def test_revision_groups_distinguish_frequency_and_fiscal_quarter(self) -> None:
        annual = replace(
            fact("AAA", "revenue", 2024, 1),
            accession=None,
        )
        quarterly = replace(
            annual,
            reporting_frequency="quarterly",
            form_type="10-Q",
            fiscal_quarter=4,
        )
        distinct_quarter = replace(quarterly, fiscal_quarter=3)
        for rows in ((annual, quarterly), (quarterly, distinct_quarter)):
            with self.subTest(rows=rows):
                report = audit_facts(rows)
                self.assertFalse(
                    any(
                        "Revision histories" in item.finding
                        for item in report.findings
                    )
                )

    def test_genuine_same_slot_versions_without_accession_are_excluded(self) -> None:
        first = replace(
            fact("AAA", "revenue", 2024, 1),
            accession=None,
        )
        revised = replace(
            first,
            available_at=datetime.fromisoformat("2025-03-15T21:00:00+00:00"),
            value=2,
            form_type="10-K/A",
        )
        report = audit_facts([first, revised])
        finding = self._finding(report, "Revision histories")
        self.assertIs(finding.eligibility_decision, AuditDecision.EXCLUDED)

    def test_audit_reports_complete_period_metadata_coverage(self) -> None:
        rows = [
            fact("AAA", "revenue", 2024, 1),
            FactObservation(
                "AAA", "revenue", date(2023, 12, 31),
                datetime.fromisoformat("2024-02-01T00:00:00+00:00"), 1, "x",
            ),
        ]
        coverage = audit_facts(rows).period_metadata_coverage
        self.assertEqual(coverage["reporting_frequency"]["annual"], 1)
        self.assertEqual(coverage["reporting_frequency"]["unknown"], 1)
        self.assertEqual(coverage["period_type"]["duration"], 1)
        self.assertEqual(coverage["fiscal_year"]["annual_with_fiscal_year"], 1)
        self.assertEqual(coverage["fiscal_year"]["missing_fiscal_year"], 1)

    def test_unknown_metadata_alone_does_not_exclude_audit(self) -> None:
        row = FactObservation(
            "AAA", "revenue", date(2024, 12, 31),
            datetime.fromisoformat("2025-02-01T00:00:00+00:00"), 1, "x",
        )
        self.assertFalse(audit_facts([row]).has_exclusions)

    def test_impossible_timestamp_is_excluded(self) -> None:
        row = FactObservation(
            "AAA", "revenue", date(2025, 12, 31),
            datetime.fromisoformat("2025-01-01T00:00:00+00:00"), 1, "x",
        )
        report = audit_facts([row])
        self.assertTrue(report.has_exclusions)
        self.assertIs(report.findings[0].eligibility_decision, AuditDecision.EXCLUDED)

    def test_shipped_facts_have_explicit_metadata(self) -> None:
        import csv

        path = Path(__file__).parents[1] / "examples" / "facts.example.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        accounting = [row for row in rows if row["source"] == "SEC"]
        self.assertTrue(all(row["period_type"] != "unknown" for row in accounting))
        self.assertTrue(all(row["reporting_frequency"] == "annual" for row in accounting))
        self.assertTrue(all(row["fiscal_year"] for row in accounting))

    def test_fixture_values_are_not_production_defaults_or_template_values(self) -> None:
        template = (Path(__file__).parents[1] / "examples" / "entry001.template.json").read_text()
        self.assertNotIn(str(SYNTHETIC_NEAR_ZERO_THRESHOLD), template)
        self.assertNotIn(str(SYNTHETIC_MINIMUM_FEATURE_COVERAGE), template)
        feature_signature = inspect.signature(FeatureEngine)
        self.assertIs(feature_signature.parameters["resolved_entry_001"].default, inspect.Parameter.empty)
        config_signature = inspect.signature(CompositeConfig)
        for name in (
            "minimum_features_per_dimension", "minimum_feature_coverage",
            "required_dimensions", "missing_policy",
        ):
            self.assertIs(config_signature.parameters[name].default, inspect.Parameter.empty)

    def test_backtest_still_requires_verified_v2_entry(self) -> None:
        frame = pd.DataFrame([
            {"decision_date": "2025-01-31", "security_id": "AAA", "composite_score": 0.9, "forward_total_return": 0.10},
            {"decision_date": "2025-01-31", "security_id": "BBB", "composite_score": 0.8, "forward_total_return": 0.05},
            {"decision_date": "2025-02-28", "security_id": "CCC", "composite_score": 0.9, "forward_total_return": 0.08},
            {"decision_date": "2025-02-28", "security_id": "DDD", "composite_score": 0.8, "forward_total_return": 0.06},
        ])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry.json"
            with self.assertRaises(GovernanceError):
                run_equal_weight_backtest(frame, path, 2)
            write_artifact(path, complete_entry_001())
            with matching_frozen_runtime():
                result = run_equal_weight_backtest(frame, path, 2)
        self.assertEqual(result.periods["traded_notional"].tolist(), [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
