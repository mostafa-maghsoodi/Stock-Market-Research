from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from graham_research.admission import (
    BLOCKER_RECLASSIFICATION,
    CAPABILITY_IDS,
    PROVIDER_CAPABILITY_SPECIFICATION,
    CorporateActionRecord,
    ProviderSampleAdmissionPack,
    blocker_reclassification,
    researcher_decision_packet,
    validate_provider_sample_pack,
)
from graham_research.production import (
    CANONICAL_FIELD_UNITS,
    PREREQUISITE_KEYS,
    CandidateSetDerivedIdentity,
    EvidenceIdentity,
    FieldCatalogEntry,
    ProductionContractError,
    REQUIRED_FIRST_RUN_RESEARCHER_DECISION_IDS,
    SecurityMasterRecord,
    ScreenV2ReadinessState,
    canonical_eligible_population_digest,
    create_candidate_set,
    derive_candidate_set_identity,
    production_decision_authority_blockers,
)


UTC = timezone.utc
NOW = datetime(2026, 8, 14, tzinfo=UTC)
REPOSITORY = Path(__file__).resolve().parents[1]


def identity_for(path: Path, root: Path, *, evidence_id: str = "evidence") -> EvidenceIdentity:
    return EvidenceIdentity(
        evidence_id=evidence_id,
        provider="TEST_PROVIDER",
        provider_product="TEST_PRODUCT",
        content_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_native_vintage_identifier="test-vintage",
        acquired_at_utc=NOW,
        repository_relative_path=str(path.relative_to(root)),
    )


def ready_state() -> ScreenV2ReadinessState:
    return ScreenV2ReadinessState(
        "RESOLVED_RESEARCH_POLICY", "RESOLVED_PROVIDER_AND_DATA_EVIDENCE",
        "VERIFIED_REPOSITORY_IDENTITIES", "PRODUCTION_EXECUTION_READY",
        {key: True for key in PREREQUISITE_KEYS},
    )


def ranked_frame() -> pd.DataFrame:
    frame = pd.DataFrame({
        "security_id": [f"S{number:03d}" for number in range(100)],
        "decision_date": [pd.Timestamp("2026-06-30", tz="UTC")] * 100,
        "VALUATION": [0.5] * 100,
        "BUSINESS_ECONOMICS": [0.5] * 100,
        "FUNDAMENTAL_CHANGE": [0.5] * 100,
        "composite_score": [0.5] * 100,
    })
    for proxy in (
        "fcf_ev", "ebit_ev", "gross_profitability", "roic",
        "operating_margin_change", "fcf_margin_change", "revenue_acceleration",
    ):
        frame[proxy] = 0.1
    return frame


def test_all_23_blockers_have_only_closed_dependency_classes() -> None:
    result = blocker_reclassification()
    assert len(result) == 23
    assert set(BLOCKER_RECLASSIFICATION) == {f"EXT-{number:03d}" for number in range(1, 24)}
    assert "INTERNAL_DETERMINISTIC" in BLOCKER_RECLASSIFICATION["EXT-022"]
    assert "DERIVED_AFTER_PROVIDER_ADMISSION" in BLOCKER_RECLASSIFICATION["EXT-022"]


def test_provider_capability_specification_is_closed_and_complete() -> None:
    assert CAPABILITY_IDS == tuple(f"CAP-{number:03d}" for number in range(1, 26))
    assert len(PROVIDER_CAPABILITY_SPECIFICATION) == 25
    required_keys = {
        "capability_id", "capability_name", "required", "evidence_type",
        "minimum_documentation", "minimum_sample",
        "machine_verifiable_acceptance_test", "failure_behavior",
    }
    assert all(set(item) == required_keys for item in PROVIDER_CAPABILITY_SPECIFICATION)
    assert all(item["required"] is True for item in PROVIDER_CAPABILITY_SPECIFICATION)


def test_researcher_packet_separates_three_sample_boundaries_and_authority() -> None:
    decisions = {item["decision_id"]: item for item in researcher_decision_packet()}
    assert len(decisions) == 17
    assert decisions["RD-002A"]["decision_name"] == "initial production-validation range"
    assert decisions["RD-002B"]["required_before_first_run"] is True
    assert decisions["RD-002C"]["required_before_first_run"] is False
    for decision_id in (
        "RD-001", "RD-002B", "RD-002C", "RD-004", "RD-008", "RD-013",
        "RD-014", "RD-015", "RD-016", "RD-017", "RD-018", "RD-019",
        "RD-020", "RD-021", "RD-022", "RD-CROSSWALK-001",
    ):
        assert decisions[decision_id]["authority_path"] == "NEW_AUTHORITY_REQUIRED"


def test_readiness_cannot_discover_or_self_assert_human_approval() -> None:
    assert len(REQUIRED_FIRST_RUN_RESEARCHER_DECISION_IDS) == 15
    blockers = production_decision_authority_blockers(REPOSITORY)
    assert len(blockers) == 15
    assert all(item.startswith("RESEARCHER_DECISION_AUTHORITY_UNRESOLVED:") for item in blockers)


def test_candidateset_derived_identity_is_reproducible_and_separate() -> None:
    frame = ranked_frame()
    candidate = create_candidate_set(
        frame, readiness=ready_state(), governed_batch_lineage_sha256="a" * 64
    )
    population = canonical_eligible_population_digest(frame)
    first = derive_candidate_set_identity(
        candidate,
        eligible_population_digest=population,
        production_evidence_manifest_sha256="b" * 64,
    )
    second = derive_candidate_set_identity(
        candidate,
        eligible_population_digest=population,
        production_evidence_manifest_sha256="b" * 64,
    )
    assert first == second
    assert isinstance(first, CandidateSetDerivedIdentity)
    assert first.authority_status == "NON_GOVERNING_DERIVED_IDENTITY"
    assert first.candidate_set_exact_byte_sha256 == hashlib.sha256(candidate.canonical_bytes()).hexdigest()
    assert first.ranked_frame_digest == candidate.ranked_frame_digest
    assert set(frame.columns) > {"security_id", "decision_date", "composite_score"}


def test_candidateset_identity_fails_closed_on_any_mismatch() -> None:
    frame = ranked_frame()
    candidate = create_candidate_set(
        frame, readiness=ready_state(), governed_batch_lineage_sha256="a" * 64
    )
    population = canonical_eligible_population_digest(frame)
    identity = derive_candidate_set_identity(
        candidate,
        eligible_population_digest=population,
        production_evidence_manifest_sha256="b" * 64,
    )
    with pytest.raises(ProductionContractError, match="MISMATCH"):
        identity.verify(
            candidate,
            eligible_population_digest="c" * 64,
            production_evidence_manifest_sha256="b" * 64,
        )
    with pytest.raises(ProductionContractError, match="selection-rule"):
        replace(identity, selection_rule_digest="d" * 64)
    with pytest.raises(ProductionContractError, match="derived identity digest"):
        replace(identity, derived_identity_sha256="e" * 64)


def test_field_catalog_requires_native_scale_currency_and_exact_canonical_unit() -> None:
    evidence = EvidenceIdentity(
        "e", "P", "PRODUCT", "1" * 64, "v", NOW, None
    )
    with pytest.raises(ProductionContractError, match="canonical unit mismatch"):
        FieldCatalogEntry(
            "raw_close", "raw closing price", "MARKET_SESSION", "DAILY",
            "NATIVE_PRICE", "USD", 1.0, "REPORTED_USD", "P", "PRODUCT",
            "native-close", evidence, date(2000, 1, 1), None,
            "available at close", "raw corrections by native vintage",
            ("raw_close",), evidence,
        )
    with pytest.raises(ProductionContractError, match="finite and positive"):
        FieldCatalogEntry(
            "revenue", "revenue", "DURATION", "ANNUAL", "USD_MILLIONS",
            "USD", 0.0, "REPORTED_USD", "P", "PRODUCT", "native-revenue",
            evidence, date(2000, 1, 1), None, "filing time", "FIRST_REPORTED",
            ("revenue",), evidence,
        )
    assert CANONICAL_FIELD_UNITS["shares_outstanding"] == "SHARES"
    assert CANONICAL_FIELD_UNITS["raw_close"] == "USD_PER_SHARE"


def test_field_catalog_rejects_effective_range_and_mapping_evidence_mismatch() -> None:
    good = EvidenceIdentity("e", "P", "PRODUCT", "1" * 64, "v", NOW, None)
    wrong = EvidenceIdentity("w", "OTHER", "PRODUCT", "2" * 64, "v", NOW, None)
    with pytest.raises(ProductionContractError, match="effective range"):
        FieldCatalogEntry(
            "revenue", "revenue", "DURATION", "ANNUAL", "USD", "USD", 1,
            "REPORTED_USD", "P", "PRODUCT", "native", good,
            date(2025, 1, 1), date(2024, 1, 1), "filing", "FIRST_REPORTED",
            ("revenue",), good,
        )
    with pytest.raises(ProductionContractError, match="provider evidence mismatch"):
        FieldCatalogEntry(
            "revenue", "revenue", "DURATION", "ANNUAL", "USD", "USD", 1,
            "REPORTED_USD", "P", "PRODUCT", "native", wrong,
            date(2020, 1, 1), None, "filing", "FIRST_REPORTED", ("revenue",), good,
        )


def test_non_evidence_template_is_structural_and_rejected() -> None:
    path = REPOSITORY / "examples/non_evidence/provider_sample_admission.template.json"
    result = validate_provider_sample_pack(path, repository=REPOSITORY)
    assert result["admitted"] is False
    assert result["production_evidence"] is False
    blockers = set(result["blockers"])
    assert "ENTITLEMENT_IDENTITY_UNVERIFIED" in blockers
    assert "ARCHIVE_RIGHTS_IDENTITY_UNVERIFIED" in blockers
    assert "CAP-009_UNSUPPORTED" in blockers
    assert "CAP-019_UNSUPPORTED" in blockers


def _minimal_pack(tmp_path: Path, *, fundamentals: list[dict] | None = None, inactive: bool = False) -> ProviderSampleAdmissionPack:
    evidence_payload = b"documented evidence"
    evidence_path = tmp_path / "evidence.txt"
    evidence_path.write_bytes(evidence_payload)
    common_identity = identity_for(evidence_path, tmp_path)

    security_record = {
        "issuer_id": "I", "security_id": "S", "listing_id": "L",
        "provider_native_issuer_id": "NI", "provider_native_security_id": "NS",
        "provider_native_listing_id": "NL", "exchange": "NYSE", "currency": "USD",
        "security_type": "COMMON_OPERATING_COMPANY_EQUITY", "is_common_equity": True,
        "is_operating_company": True, "is_primary_listing": True,
        "effective_start": "2020-01-01", "effective_end": None,
        "is_inactive_or_delisted": inactive,
        "corporate_action_predecessor_security_id": None,
        "is_pre_combination_spac": False, "post_combination_boundary": None,
        "share_class_id": "A", "issuer_crosswalk_id": "X",
        "evidence_identity": {
            "evidence_id": "e", "provider": "TEST_PROVIDER",
            "provider_product": "TEST_PRODUCT", "content_sha256": "1" * 64,
            "source_native_vintage_identifier": "v", "acquired_at_utc": NOW.isoformat(),
            "repository_relative_path": None,
        },
    }
    payloads: dict[str, dict] = {
        "security_master": {"schema_version": 1, "records": [security_record]},
        "fundamentals": {"schema_version": 1, "records": fundamentals or [{"bad": True}]},
    }
    for name in (
        "market_data", "exchange_sessions", "corporate_actions",
        "field_definitions", "identifiers_crosswalks",
    ):
        payloads[name] = {"schema_version": 1, "records": [{"bad": True}]}
    identities = {}
    for name, payload in payloads.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        identities[name] = identity_for(path, tmp_path, evidence_id=name)
    return ProviderSampleAdmissionPack(
        1, "PROVIDER_SAMPLE_CANDIDATE_NOT_ADMITTED", "Test Legal", "TEST_PROVIDER",
        "TEST_PRODUCT", "v1", date(2020, 1, 1), date(2020, 12, 31), NOW,
        common_identity, common_identity, common_identity, identities, (),
    )


def test_sample_pack_requires_inactive_delisted_history_and_native_ids(tmp_path: Path) -> None:
    blockers = _minimal_pack(tmp_path).validate(tmp_path)
    assert "SAMPLE_MISSING_INACTIVE_OR_DELISTED_SECURITY" in blockers
    payload = json.loads((tmp_path / "security_master.json").read_text())
    payload["records"][0]["provider_native_security_id"] = ""
    (tmp_path / "security_master.json").write_text(json.dumps(payload))
    pack = _minimal_pack(tmp_path, inactive=True)
    # Replacing after pack construction preserves a matching content identity.
    payload = json.loads((tmp_path / "security_master.json").read_text())
    payload["records"][0]["provider_native_security_id"] = ""
    (tmp_path / "security_master.json").write_text(json.dumps(payload))
    assert "DATASET_SECURITY_MASTER_IDENTITY_UNVERIFIED" in pack.validate(tmp_path)
    with pytest.raises(ProductionContractError, match="provider_native_security_id"):
        SecurityMasterRecord.from_mapping(payload["records"][0])


def test_sample_pack_requires_first_reported_pair_and_timestamp(tmp_path: Path) -> None:
    one_fact = {
        "security_id": "S", "field": "revenue", "period_start": "2020-01-01",
        "period_end": "2020-12-31", "available_at": "2021-02-01T00:00:00+00:00",
        "value": 1, "source": "archive", "accession": "A", "unit": "USD",
        "period_type": "duration", "reporting_frequency": "annual", "form_type": "10-K",
        "fiscal_year": 2020, "fiscal_quarter": None, "provider": "TEST_PROVIDER",
        "provider_product": "TEST_PRODUCT", "native_observation_id": "N1",
        "source_native_vintage_identifier": "V1",
    }
    blockers = _minimal_pack(tmp_path, fundamentals=[one_fact], inactive=True).validate(tmp_path)
    assert "SAMPLE_MISSING_FIRST_REPORTED_AND_RESTATEMENT_PAIR" in blockers
    bad = dict(one_fact, available_at="2021-02-01T00:00:00")
    blockers = _minimal_pack(tmp_path, fundamentals=[bad], inactive=True).validate(tmp_path)
    assert "SAMPLE_FUNDAMENTALS_CONTENT_INVALID" in blockers


def test_corporate_action_contract_is_closed_and_timestamped() -> None:
    evidence = {
        "evidence_id": "e", "provider": "P", "provider_product": "PRODUCT",
        "content_sha256": "1" * 64, "source_native_vintage_identifier": "v",
        "acquired_at_utc": NOW.isoformat(), "repository_relative_path": None,
    }
    action = CorporateActionRecord.from_mapping({
        "native_action_id": "A", "issuer_id": "I", "security_id": "S",
        "listing_id": "L", "action_type": "SPLIT", "announced_at": NOW.isoformat(),
        "effective_at": NOW.isoformat(), "predecessor_security_id": None,
        "successor_security_id": None, "split_ratio": 2, "evidence_identity": evidence,
    })
    assert action.split_ratio == 2
    with pytest.raises(ProductionContractError, match="unsupported"):
        CorporateActionRecord.from_mapping({
            "native_action_id": "A", "issuer_id": "I", "security_id": "S",
            "listing_id": "L", "action_type": "UNKNOWN", "announced_at": NOW.isoformat(),
            "effective_at": NOW.isoformat(), "predecessor_security_id": None,
            "successor_security_id": None, "split_ratio": None, "evidence_identity": evidence,
        })
