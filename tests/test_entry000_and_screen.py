from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest

import graham_research.screen as screen_module
from graham_research.entry000 import (
    COMPONENT_SPECS,
    Entry000Error,
    build_entry000_v2,
    verify_entry000_payload,
    verify_entry000_publication,
    verify_entry000_repository,
)
from graham_research.governance import freeze_entry_000, verify_artifact
from graham_research.ranked_artifact import RANKED_FRAME_DIGEST_SCOPE
from graham_research.screen import (
    CANDIDATE_ARTIFACT_KIND,
    CANDIDATE_SCHEMA_STATUS,
    ProviderCapabilities,
    REQUIRED_DIMENSIONS,
    REQUIRED_PROXY_ORDER,
    ScreenGovernanceError,
    UniversePolicy,
    run_outcome_free_screen_preflight,
    screen_regeneration_identity,
    validate_screen_regeneration_record,
)
from graham_research.specification import SpecificationRegister


REPOSITORY = Path(__file__).resolve().parents[1]
AUTHORITY_COMMIT = "fbf7b9b7d2381081a63f17203b32dd6e7c916380"
APPROVAL_COMMITS = {
    "docs/approvals/v1/architecture-v3-2-approval-001.json": (
        "1bea5245ef5e0fa4d20da8796cb3e63fea96cb67"
    ),
    "docs/approvals/v1/screen-specification-v1-approval-001.json": (
        "1bea5245ef5e0fa4d20da8796cb3e63fea96cb67"
    ),
    "docs/approvals/v1/batch1-research-intent-approval-001.json": (
        "1bea5245ef5e0fa4d20da8796cb3e63fea96cb67"
    ),
    "docs/approvals/v1/amendment-ledger-v1-0-0-approval-001.json": (
        AUTHORITY_COMMIT
    ),
}


def unavailable_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        fundamental_data_mode="UNAVAILABLE",
        fundamental_availability_timestamps=False,
        fundamental_revision_history=False,
        fundamental_fiscal_metadata=False,
        immutable_fundamental_history=False,
        security_master_mode="UNAVAILABLE",
        historical_market_data_mode="UNAVAILABLE",
        historical_price=False,
        historical_volume=False,
        historical_market_cap_or_components=False,
        historical_shares=False,
        historical_enterprise_value_inputs=False,
        corporate_actions=False,
        market_sessions=False,
        market_timezones=False,
        market_timing_policy_approved=False,
    )


def fully_asserted_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        fundamental_data_mode="PIT_ARCHIVE",
        fundamental_availability_timestamps=True,
        fundamental_revision_history=True,
        fundamental_fiscal_metadata=True,
        immutable_fundamental_history=True,
        security_master_mode="FULL_DATE_EFFECTIVE",
        historical_market_data_mode="HISTORICAL_ARCHIVE",
        historical_price=True,
        historical_volume=True,
        historical_market_cap_or_components=True,
        historical_shares=True,
        historical_enterprise_value_inputs=True,
        corporate_actions=True,
        market_sessions=True,
        market_timezones=True,
        market_timing_policy_approved=True,
    )


class Entry000PackageV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = build_entry000_v2(
            REPOSITORY,
            authority_commit=AUTHORITY_COMMIT,
            approval_record_commits=APPROVAL_COMMITS,
            created_at_utc="2026-08-11T05:00:00.000000Z",
        )

    def test_exact_six_component_order_and_no_seventh_component(self) -> None:
        components = self.payload["components"]
        self.assertEqual(len(components), 6)
        self.assertEqual(
            [item["component_role"] for item in components],
            [spec[1] for spec in COMPONENT_SPECS],
        )
        self.assertNotIn(
            "APPROVAL_RECORD_V1", [item["component_role"] for item in components]
        )

    def test_repository_backed_component_and_evidence_identity(self) -> None:
        result = verify_entry000_repository(self.payload, REPOSITORY)
        self.assertEqual(result["verification"], "REPOSITORY_VERIFIED")
        self.assertEqual(result["component_count"], 6)
        self.assertEqual(result["approval_evidence_count"], 8)

    def test_published_package_and_full_byte_sidecar_verify(self) -> None:
        target = (
            REPOSITORY
            / "artifacts"
            / "entry000"
            / "v2"
            / self.payload["package_id"]
            / "entry000.package.json"
        )
        result = verify_entry000_publication(target, repository=REPOSITORY)
        self.assertEqual(result["verification"], "REPOSITORY_VERIFIED")
        self.assertEqual(verify_artifact(target), result["full_artifact_sha256"])

    def test_changed_embedded_byte_is_rejected(self) -> None:
        changed = copy.deepcopy(self.payload)
        encoded = changed["components"][0]["exact_bytes_base64"]
        changed["components"][0]["exact_bytes_base64"] = (
            ("A" if encoded[0] != "A" else "B") + encoded[1:]
        )
        with self.assertRaisesRegex(Entry000Error, "byte identity mismatch"):
            verify_entry000_payload(changed)

    def test_changed_component_path_is_rejected(self) -> None:
        changed = copy.deepcopy(self.payload)
        changed["components"][0]["repository_relative_path"] = "docs/changed.md"
        with self.assertRaisesRegex(Entry000Error, "identity/order"):
            verify_entry000_payload(changed)

    def test_changed_approval_identity_is_rejected(self) -> None:
        changed = copy.deepcopy(self.payload)
        changed["components"][2]["approval_record_identity"][
            "approval_record_commit"
        ] = "0" * 40
        with self.assertRaisesRegex(Entry000Error, "does not bind"):
            verify_entry000_payload(changed)

    def test_unreferenced_approval_evidence_is_rejected(self) -> None:
        changed = copy.deepcopy(self.payload)
        changed["approval_evidence"].append(
            copy.deepcopy(changed["approval_evidence"][0])
        )
        with self.assertRaises(Entry000Error):
            verify_entry000_payload(changed)

    def test_package_id_excludes_only_publication_label_and_time(self) -> None:
        changed = copy.deepcopy(self.payload)
        changed["package_label"] = "another-non-authority-label"
        changed["created_at_utc"] = "2026-08-11T05:00:01.000000Z"
        result = verify_entry000_payload(changed)
        self.assertEqual(result["package_id"], self.payload["package_id"])

    def test_legacy_entry000_dispatch_remains_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "entry000.json"
            expected = freeze_entry_000(target, "historical architecture")
            self.assertEqual(verify_artifact(target), expected)
            payload = json.loads(target.read_text("utf-8"))
            payload["statement"] = "changed"
            target.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(Entry000Error):
                verify_artifact(target)


class GovernedScreenPreflightTests(unittest.TestCase):
    def test_proxy_order_and_required_dimensions_are_preserved(self) -> None:
        self.assertEqual(
            REQUIRED_PROXY_ORDER,
            (
                "fcf_ev",
                "ebit_ev",
                "gross_profitability",
                "roic",
                "operating_margin_change",
                "fcf_margin_change",
                "revenue_acceleration",
            ),
        )
        self.assertEqual(
            REQUIRED_DIMENSIONS,
            ("VALUATION", "BUSINESS_ECONOMICS", "FUNDAMENTAL_CHANGE"),
        )

    def test_historical_market_timing_blocks_essential_valuation(self) -> None:
        report = run_outcome_free_screen_preflight(
            provider_capabilities=unavailable_capabilities(),
            universe_policy=UniversePolicy(),
            accounting_fixture_prepared=True,
        )
        self.assertIn("HISTORICAL_MARKET_TIMING_UNRESOLVED", report.diagnostic_codes)
        self.assertIn("VALUATION_ESSENTIAL_UNAVAILABLE", report.diagnostic_codes)
        self.assertEqual(report.stage_status["valuation"], "BLOCKED_BY_HISTORICAL_TIMING")

    def test_current_live_data_is_historically_inadmissible(self) -> None:
        capabilities = ProviderCapabilities(
            **{
                **unavailable_capabilities().__dict__,
                "fundamental_data_mode": "CURRENT_OR_LIVE",
                "historical_market_data_mode": "CURRENT_OR_LIVE",
                "security_master_mode": "CURRENT_SURVIVORS_ONLY",
            }
        )
        report = run_outcome_free_screen_preflight(
            provider_capabilities=capabilities,
            universe_policy=UniversePolicy(),
            accounting_fixture_prepared=False,
        )
        self.assertIn(
            "CURRENT_LIVE_MARKET_DATA_HISTORICALLY_INADMISSIBLE",
            report.diagnostic_codes,
        )
        self.assertIn(
            "CURRENT_LIVE_FUNDAMENTALS_HISTORICALLY_INADMISSIBLE",
            report.diagnostic_codes,
        )
        self.assertIn(
            "CURRENT_SURVIVOR_ONLY_UNIVERSE_INADMISSIBLE",
            report.diagnostic_codes,
        )

    def test_unresolved_thresholds_never_receive_defaults(self) -> None:
        policy = UniversePolicy()
        self.assertEqual(policy.operational_values_state, "UNRESOLVED_RESEARCHER_DECISION")
        self.assertFalse(any("floor_value" in name for name in policy.__dataclass_fields__))
        report = run_outcome_free_screen_preflight(
            provider_capabilities=fully_asserted_capabilities(),
            universe_policy=policy,
            accounting_fixture_prepared=True,
        )
        for code in (
            "UNIVERSE_SIZE_FLOOR_UNRESOLVED",
            "UNIVERSE_PRICE_FLOOR_UNRESOLVED",
            "UNIVERSE_LIQUIDITY_FLOOR_UNRESOLVED",
            "LISTING_SEASONING_UNRESOLVED",
        ):
            self.assertIn(code, report.diagnostic_codes)

    def test_current_survivor_policy_cannot_be_constructed(self) -> None:
        with self.assertRaisesRegex(ValueError, "current-survivor-only"):
            UniversePolicy(survivorship_policy="CURRENT_SURVIVORS_ONLY")

    def test_candidate_set_remains_separate_and_unproduced(self) -> None:
        self.assertEqual(CANDIDATE_ARTIFACT_KIND, "GovernedCandidateSetArtifact")
        self.assertEqual(
            CANDIDATE_SCHEMA_STATUS, "FUTURE_SEPARATE_GOVERNED_ARTIFACT"
        )
        self.assertFalse(hasattr(screen_module, "GovernedCandidateSetArtifact"))
        report = run_outcome_free_screen_preflight(
            provider_capabilities=fully_asserted_capabilities(),
            universe_policy=UniversePolicy(),
            accounting_fixture_prepared=True,
        )
        self.assertEqual(report.candidate_set_state, "not_produced")
        self.assertIn(
            "CANDIDATE_MEMBERSHIP_RULE_UNRESOLVED", report.diagnostic_codes
        )

    def test_ranking_digest_scope_is_unchanged(self) -> None:
        self.assertEqual(
            RANKED_FRAME_DIGEST_SCOPE,
            ("security_id", "decision_date", "composite_score"),
        )

    def test_screen_preflight_has_no_outcome_or_register_input(self) -> None:
        parameters = inspect.signature(run_outcome_free_screen_preflight).parameters
        forbidden = {
            "returns",
            "held_returns",
            "forward_returns",
            "outcomes",
            "specification_register",
            "register",
        }
        self.assertTrue(forbidden.isdisjoint(parameters))
        with tempfile.TemporaryDirectory() as temporary:
            register = SpecificationRegister.for_repository(
                "/synthetic/repository",
                path=Path(temporary) / "register.jsonl",
            )
            before = register.history()
            report = run_outcome_free_screen_preflight(
                provider_capabilities=unavailable_capabilities(),
                universe_policy=UniversePolicy(),
                accounting_fixture_prepared=True,
            )
            self.assertEqual(register.history(), before)
            self.assertEqual(report.outcome_budget_effect, "none_no_slot_no_open_close")
            self.assertEqual(report.outcome_register_events, 0)
            self.assertFalse(report.realized_outcomes_read)

    def test_diagnostics_are_deterministic(self) -> None:
        arguments = {
            "provider_capabilities": unavailable_capabilities(),
            "universe_policy": UniversePolicy(),
            "accounting_fixture_prepared": True,
        }
        first = run_outcome_free_screen_preflight(**arguments)
        second = run_outcome_free_screen_preflight(**arguments)
        self.assertEqual(first.to_dict(), second.to_dict())


class ScreenRegenerationIdentityTests(unittest.TestCase):
    def record(self) -> dict[str, object]:
        values = iter(f"{index:064x}" for index in range(1, 20))
        return {
            "screen_regeneration_schema_version": 1,
            "screen_specification_id": next(values),
            "screen_specification_sha256": next(values),
            "universe_artifact_sha256": next(values),
            "security_master_artifact_sha256": next(values),
            "source_snapshot_references": [
                {
                    "source_kind": "PIT_ACCOUNTING_FACTS",
                    "source_id": "pit-fixture",
                    "snapshot_id": "pit-snapshot",
                    "snapshot_sha256": next(values),
                    "archive_manifest_sha256": next(values),
                }
            ],
            "accounting_semantics_sha256": next(values),
            "proxy_registry_sha256": next(values),
            "ranking_configuration_sha256": next(values),
            "required_dimensions": [
                "Valuation",
                "Business Economics",
                "Fundamental Change",
            ],
            "decision_date_set_digest": next(values),
            "code_identities": {
                "ordered_identities": [],
                "digest": next(values),
            },
            "environment_manifest_sha256": next(values),
            "canonicalization_identity": "CanonicalJSON-v1",
            "ranked_artifact_sha256": next(values),
            "ranked_content_digest": next(values),
            "candidate_set_state": "not_produced",
            "candidate_set_artifact_sha256": None,
        }

    def test_unproduced_candidate_state_has_deterministic_identity(self) -> None:
        record = self.record()
        validate_screen_regeneration_record(record)
        first = screen_regeneration_identity(record)
        second = screen_regeneration_identity(copy.deepcopy(record))
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("screen-regeneration-v1:"))
        self.assertNotEqual(first.split(":", 1)[1], record["ranked_content_digest"])

    def test_candidate_state_and_digest_must_agree(self) -> None:
        record = self.record()
        record["candidate_set_artifact_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            ScreenGovernanceError, "CANDIDATE_STATE_DIGEST_MISMATCH"
        ):
            validate_screen_regeneration_record(record)


if __name__ == "__main__":
    unittest.main()
