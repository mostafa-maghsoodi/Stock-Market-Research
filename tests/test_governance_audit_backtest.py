from __future__ import annotations

from contextlib import contextmanager
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings

import pandas as pd

import graham_research.governance as governance
from graham_research.audit import audit_facts
from graham_research.backtest import run_equal_weight_backtest
from graham_research.domain import AuditDecision, FactObservation
from graham_research.governance import (
    ENTRY_001_REQUIRED_KEYS,
    GovernanceError,
    environment_manifest,
    freeze_entry_001,
    project_dependency_pins,
    require_entry_001,
    verify_artifact,
)
from graham_research.legacy import assess_graham_snapshot
from graham_research.cli import main as cli_main


FROZEN_PINS = {
    "numpy": "2.3.5",
    "pandas": "2.2.3",
}

FROZEN_RUNTIME = {
    "python": "3.12.0",
    "implementation": "CPython",
    "platform": "test-platform",
}


@contextmanager
def matching_frozen_runtime(
    numpy_version: str = "2.3.5",
    python_version: str = FROZEN_RUNTIME["python"],
    implementation: str = FROZEN_RUNTIME["implementation"],
    platform_value: str = FROZEN_RUNTIME["platform"],
):
    versions = {**FROZEN_PINS, "numpy": numpy_version}
    with (
        patch(
            "graham_research.governance.importlib.metadata.version",
            side_effect=lambda name: versions[name],
        ),
        patch(
            "graham_research.governance.platform.python_version",
            return_value=python_version,
        ),
        patch(
            "graham_research.governance.platform.python_implementation",
            return_value=implementation,
        ),
        patch(
            "graham_research.governance.platform.platform",
            return_value=platform_value,
        ),
    ):
        yield


def freeze_for_test(path: Path, payload: dict[str, object]) -> str:
    with matching_frozen_runtime():
        return freeze_entry_001(path, payload)


def frozen_environment_fixture() -> dict[str, object]:
    """Deterministic fixture; deliberately independent of the test runtime."""

    return {
        "schema_version": 1,
        **FROZEN_RUNTIME,
        "packages": dict(FROZEN_PINS),
        "pinned_dependencies": dict(FROZEN_PINS),
        "dependency_match": True,
        "mismatches": {},
    }


def complete_entry_001() -> dict[str, object]:
    payload: dict[str, object] = {
        key: ({"frozen": True} if key not in {"architecture_version", "specification_budget"} else ("3.1" if key == "architecture_version" else 10))
        for key in ENTRY_001_REQUIRED_KEYS
    }
    payload.update({
        "proxy_registry": [{"name": "fcf_ev", "formula": "fcf / ev"}],
        "research_provenance": [{"artifact": "architecture-v3.1"}],
        "environment_manifest": frozen_environment_fixture(),
        "source_control": {
            "vcs": "git",
            "commit": "a" * 40,
            "dirty": False,
        },
        "transaction_cost_model": {
            "convention": "traded_notional_times_one_way_bps",
            "one_way_cost_bps": 100.0,
        },
    })
    return payload


class GovernanceTests(unittest.TestCase):
    def test_literal_fixture_matches_project_pins(self) -> None:
        self.assertEqual(FROZEN_PINS, project_dependency_pins())

    def test_foreign_pyproject_is_not_a_pin_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pyproject.toml"
            path.write_text(
                "[project]\nname='foreign-project'\n"
                "dependencies=['numpy==1.0.0','pandas==1.0.0']\n",
                encoding="utf-8",
            )
            self.assertIsNone(governance._pins_from_pyproject_candidate(path))

    def test_matching_metadata_and_source_pins_are_accepted(self) -> None:
        with patch(
            "graham_research.governance.importlib.metadata.requires",
            return_value=["numpy==2.3.5", "pandas==2.2.3"],
        ):
            self.assertEqual(
                governance._load_project_dependency_pins(),
                FROZEN_PINS,
            )

    def test_stale_metadata_disagreeing_with_source_is_rejected(self) -> None:
        with patch(
            "graham_research.governance.importlib.metadata.requires",
            return_value=["numpy==7.0.0", "pandas==8.0.0"],
        ):
            with self.assertRaises(RuntimeError):
                governance._load_project_dependency_pins()

    def test_stale_project_metadata_does_not_block_frozen_entry_load(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry001.json"
            freeze_for_test(path, complete_entry_001())
            with (
                patch(
                    "graham_research.governance.importlib.metadata.requires",
                    return_value=["numpy==7.0.0", "pandas==8.0.0"],
                ),
                matching_frozen_runtime(),
            ):
                payload, runtime = require_entry_001(path)
                self.assertEqual(payload["entry"], "001")
                self.assertFalse(runtime.warnings)
                with self.assertRaises(RuntimeError):
                    project_dependency_pins()

    def test_unresolved_entry_is_rejected(self) -> None:
        payload = complete_entry_001()
        payload["holding_period"] = "UNRESOLVED"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(GovernanceError):
                freeze_for_test(Path(temporary) / "entry001.json", payload)

    def test_each_required_artifact_rejects_empty_collection(self) -> None:
        for key, empty_value in (
            ("proxy_registry", []),
            ("research_provenance", []),
            ("environment_manifest", {}),
            ("source_control", {}),
        ):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                payload = complete_entry_001()
                payload[key] = empty_value
                with self.assertRaises(GovernanceError):
                    freeze_for_test(Path(temporary) / "entry001.json", payload)

    def test_environment_version_mismatch_is_rejected(self) -> None:
        payload = complete_entry_001()
        manifest = dict(payload["environment_manifest"])
        manifest["packages"] = dict(manifest["packages"])
        manifest["packages"]["numpy"] = "999.0.0"
        manifest["dependency_match"] = False
        manifest["mismatches"] = {
            "numpy": {"expected": "2.3.5", "actual": "999.0.0"}
        }
        payload["environment_manifest"] = manifest
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(GovernanceError):
                freeze_for_test(Path(temporary) / "entry001.json", payload)

    def test_environment_manifest_reports_the_actual_runtime(self) -> None:
        manifest = environment_manifest()
        actual_match = all(
            manifest["packages"].get(name) == version
            for name, version in manifest["pinned_dependencies"].items()
        )
        self.assertEqual(manifest["dependency_match"], actual_match)
        self.assertEqual(bool(manifest["mismatches"]), not actual_match)

    def test_entry_001_load_rejects_runtime_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry001.json"
            freeze_for_test(path, complete_entry_001())
            with matching_frozen_runtime():
                require_entry_001(path)
            with matching_frozen_runtime(numpy_version="999.0.0"):
                with self.assertRaises(GovernanceError):
                    require_entry_001(path)

    def test_incidental_runtime_drift_is_reported_not_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry001.json"
            freeze_for_test(path, complete_entry_001())
            with matching_frozen_runtime(
                python_version="3.12.9",
                platform_value="patched-kernel-platform",
            ):
                payload, runtime = require_entry_001(path)
            self.assertNotIn("_runtime_validation", payload)
            self.assertEqual(runtime.to_dict()["status"], "matched_with_warnings")
            self.assertEqual(len(runtime.warnings), 2)

    def test_cli_prints_runtime_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry001.json"
            freeze_for_test(path, complete_entry_001())
            stdout = StringIO()
            stderr = StringIO()
            with (
                matching_frozen_runtime(
                    python_version="3.12.9",
                    platform_value="patched-kernel-platform",
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                self.assertEqual(cli_main(["check-entry-001", str(path)]), 0)
            output = json.loads(stdout.getvalue())
            self.assertEqual(
                output["runtime_validation"]["status"],
                "matched_with_warnings",
            )
            self.assertEqual(stderr.getvalue().count("WARNING:"), 2)

    def test_python_minor_or_implementation_drift_is_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry001.json"
            freeze_for_test(path, complete_entry_001())
            for changes in (
                {"python_version": "3.13.0"},
                {"implementation": "PyPy"},
            ):
                with self.subTest(changes=changes), matching_frozen_runtime(**changes):
                    with self.assertRaises(GovernanceError):
                        require_entry_001(path)

    def test_entry_001_freeze_rejects_fabricated_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry001.json"
            with matching_frozen_runtime(numpy_version="999.0.0"):
                with self.assertRaises(GovernanceError):
                    freeze_entry_001(path, complete_entry_001())

    def test_entry_001_freeze_warns_on_incidental_runtime_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry001.json"
            with (
                matching_frozen_runtime(
                    python_version="3.12.9",
                    platform_value="patched-kernel-platform",
                ),
                warnings.catch_warnings(record=True) as caught,
            ):
                warnings.simplefilter("always")
                freeze_entry_001(path, complete_entry_001())
            self.assertEqual(len(caught), 2)
            self.assertTrue(path.exists())

    def test_zero_specification_budget_is_rejected(self) -> None:
        payload = complete_entry_001()
        payload["specification_budget"] = 0
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(GovernanceError):
                freeze_for_test(Path(temporary) / "entry001.json", payload)

    def test_hash_detects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry001.json"
            freeze_for_test(path, complete_entry_001())
            verify_artifact(path)
            payload = json.loads(path.read_text())
            payload["holding_period"] = "changed"
            path.write_text(json.dumps(payload))
            with self.assertRaises(GovernanceError):
                verify_artifact(path)

    def test_backtest_charges_every_dollar_bought_and_sold(self) -> None:
        frame = pd.DataFrame([
            {"decision_date": "2025-01-31", "security_id": "AAA", "composite_score": 0.9, "forward_total_return": 0.10},
            {"decision_date": "2025-01-31", "security_id": "BBB", "composite_score": 0.8, "forward_total_return": 0.05},
            {"decision_date": "2025-01-31", "security_id": "CCC", "composite_score": 0.2, "forward_total_return": 0.01},
            {"decision_date": "2025-01-31", "security_id": "DDD", "composite_score": 0.1, "forward_total_return": 0.01},
            {"decision_date": "2025-02-28", "security_id": "AAA", "composite_score": 0.2, "forward_total_return": 0.02},
            {"decision_date": "2025-02-28", "security_id": "BBB", "composite_score": 0.1, "forward_total_return": 0.02},
            {"decision_date": "2025-02-28", "security_id": "CCC", "composite_score": 0.9, "forward_total_return": 0.08},
            {"decision_date": "2025-02-28", "security_id": "DDD", "composite_score": 0.8, "forward_total_return": 0.06},
        ])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry001.json"
            with self.assertRaises(GovernanceError):
                run_equal_weight_backtest(frame, path, top_n=2)
            freeze_for_test(path, complete_entry_001())
            with matching_frozen_runtime(
                python_version="3.12.9",
                platform_value="patched-kernel-platform",
            ):
                result = run_equal_weight_backtest(frame, path, top_n=2)
            self.assertEqual(len(result.periods), 2)
            self.assertEqual(result.periods["traded_notional"].tolist(), [1.0, 2.0])
            self.assertEqual(result.periods["cost"].tolist(), [0.01, 0.02])
            self.assertAlmostEqual(result.periods.iloc[0]["net_return"], 0.065)
            self.assertEqual(len(result.runtime_warnings), 2)


class AuditAndLegacyTests(unittest.TestCase):
    def test_impossible_timestamp_is_excluded(self) -> None:
        row = FactObservation(
            security_id="AAA",
            field="revenue",
            period_end=date(2025, 12, 31),
            available_at=datetime.fromisoformat("2025-01-01T00:00:00+00:00"),
            value=1.0,
            source="bad",
            accession="1",
            unit="USD",
        )
        report = audit_facts([row])
        self.assertTrue(report.has_exclusions)
        self.assertEqual(report.findings[0].eligibility_decision, AuditDecision.EXCLUDED)

    def test_derived_tax_rate_is_excluded_from_fact_layer(self) -> None:
        row = FactObservation(
            security_id="AAA",
            field="effective_tax_rate",
            period_end=date(2025, 12, 31),
            available_at=datetime.fromisoformat("2026-02-01T00:00:00+00:00"),
            value=0.25,
            source="vendor-derived",
            accession="1",
            unit="pure",
        )
        report = audit_facts([row])
        self.assertTrue(report.has_exclusions)
        self.assertIn("derived ratio", report.findings[0].finding.lower())

    def test_legacy_snapshot_is_live_only(self) -> None:
        result = assess_graham_snapshot({
            "company": {"ticker": "AAA"},
            "metrics": {"normalized_eps": 2.0, "normalization": {}},
        })
        self.assertTrue(result.reusable_for_live_research)
        self.assertFalse(result.eligible_for_historical_backtest)


if __name__ == "__main__":
    unittest.main()
