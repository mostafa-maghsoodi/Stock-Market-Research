from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
from pathlib import Path

import pandas as pd
import pytest

from graham_research.domain import FactObservation, PeriodType, ReportingFrequency
from graham_research.production import (
    AUDIT_ITEM_NAMES,
    CandidateSet,
    EvidenceIdentity,
    ExchangeSessionEvidence,
    FieldCatalog,
    FieldCatalogEntry,
    MarketObservation,
    PREREQUISITE_KEYS,
    ProductionContractError,
    SCREEN_V2_CONFIG_DIGEST,
    ScreenV2ReadinessState,
    SecurityMasterRecord,
    UniverseObservation,
    build_point_in_time_universe,
    consolidated_external_blockers,
    create_candidate_set,
    evaluate_production_readiness,
    implementation_gap_audit,
    prior_completed_primary_market_session,
    production_readiness_preflight,
    run_governed_screen_v2,
    validate_production_fact,
    verify_repository_authority,
)
from graham_research.ranked_artifact import RANKED_FRAME_DIGEST_SCOPE


UTC = timezone.utc
NOW = datetime(2024, 6, 3, 22, tzinfo=UTC)
REPOSITORY = Path(__file__).resolve().parents[1]


def evidence(**changes: object) -> EvidenceIdentity:
    values = {
        "evidence_id": "evidence-001",
        "provider": "TEST_PROVIDER",
        "provider_product": "TEST_PRODUCT",
        "content_sha256": "1" * 64,
        "source_native_vintage_identifier": "vintage-001",
        "acquired_at_utc": NOW,
        "repository_relative_path": None,
    }
    values.update(changes)
    return EvidenceIdentity(**values)


def master(**changes: object) -> SecurityMasterRecord:
    values = {
        "issuer_id": "issuer-1", "security_id": "security-1", "listing_id": "listing-1",
        "provider_native_issuer_id": "native-issuer-1",
        "provider_native_security_id": "native-security-1",
        "provider_native_listing_id": "native-listing-1",
        "exchange": "NYSE", "currency": "USD",
        "security_type": "COMMON_OPERATING_COMPANY_EQUITY",
        "is_common_equity": True, "is_operating_company": True,
        "is_primary_listing": True, "effective_start": date(2000, 1, 1),
        "effective_end": None, "is_inactive_or_delisted": False,
        "corporate_action_predecessor_security_id": None,
        "is_pre_combination_spac": False, "post_combination_boundary": None,
        "share_class_id": "A", "issuer_crosswalk_id": "crosswalk-1",
        "evidence_identity": evidence(),
    }
    values.update(changes)
    return SecurityMasterRecord(**values)


def universe_observation(**changes: object) -> UniverseObservation:
    security = changes.get("security_master", master())
    values = {
        "issuer_id": security.issuer_id, "security_id": security.security_id,
        "decision_date": date(2024, 6, 3),
        "total_market_capitalization_usd": 1_000_000_000,
        "raw_primary_close_usd": 10.0,
        "completed_session_dollar_volumes_usd": (3_000_000.0,) * 60,
        "completed_sessions_since_seasoning_boundary": 200,
        "security_master": security, "market_evidence_identity": evidence(),
    }
    values.update(changes)
    return UniverseObservation(**values)


def session(session_date: date = date(2024, 6, 3)) -> ExchangeSessionEvidence:
    return ExchangeSessionEvidence(
        exchange="NYSE", timezone_name="America/New_York", session_date=session_date,
        session_open=datetime.combine(session_date, datetime.min.time(), tzinfo=UTC).replace(hour=13, minute=30),
        session_close=datetime.combine(session_date, datetime.min.time(), tzinfo=UTC).replace(hour=20),
        session_status="COMPLETED", provider="TEST_PROVIDER", provider_product="TEST_PRODUCT",
        evidence_identity=evidence(),
    )


def ready_state() -> ScreenV2ReadinessState:
    return ScreenV2ReadinessState(
        "RESOLVED_RESEARCH_POLICY", "RESOLVED_PROVIDER_AND_DATA_EVIDENCE",
        "VERIFIED_REPOSITORY_IDENTITIES", "PRODUCTION_EXECUTION_READY",
        {name: True for name in PREREQUISITE_KEYS},
    )


def test_governing_repository_authority_is_exact() -> None:
    result = verify_repository_authority(REPOSITORY)
    assert result
    assert all(result.values())


def test_fact_observation_accepts_explicit_production_identity() -> None:
    fact = FactObservation.from_mapping({
        "security_id": "s", "field": "revenue", "period_start": "2023-01-01",
        "period_end": "2023-12-31", "available_at": "2024-02-01T12:00:00+00:00",
        "value": "10", "source": "archive", "period_type": "duration",
        "reporting_frequency": "annual", "provider": "TEST_PROVIDER",
        "provider_product": "TEST_PRODUCT", "native_observation_id": "obs-1",
        "source_native_vintage_identifier": "vintage-1",
    })
    assert fact.period_start == date(2023, 1, 1)
    assert fact.native_observation_id == "obs-1"


def test_fact_period_range_and_blank_native_identity_rejected() -> None:
    with pytest.raises(ValueError, match="period_start"):
        FactObservation("s", "f", date(2023, 1, 1), NOW, 1, "x", period_start=date(2024, 1, 1))
    with pytest.raises(ValueError, match="native_observation_id"):
        FactObservation("s", "f", date(2023, 1, 1), NOW, 1, "x", native_observation_id=" ")


def test_production_fact_requires_period_start_and_native_provenance() -> None:
    fact = FactObservation(
        "s", "revenue", date(2023, 12, 31), datetime(2024, 2, 1, tzinfo=UTC), 1, "x",
        period_type=PeriodType.DURATION, reporting_frequency=ReportingFrequency.ANNUAL,
    )
    with pytest.raises(ProductionContractError, match="MISSING_PERIOD_START"):
        validate_production_fact(fact, session=session())


def test_after_close_accounting_information_rejected() -> None:
    fact = FactObservation(
        "s", "revenue", date(2023, 12, 31), datetime(2024, 6, 3, 21, tzinfo=UTC), 1, "x",
        period_start=date(2023, 1, 1), period_type=PeriodType.DURATION,
        reporting_frequency=ReportingFrequency.ANNUAL, provider="TEST_PROVIDER",
        provider_product="TEST_PRODUCT", native_observation_id="obs",
        source_native_vintage_identifier="vintage",
    )
    with pytest.raises(ProductionContractError, match="AFTER_CLOSE"):
        validate_production_fact(fact, session=session())


def test_live_or_current_fact_without_historical_identity_is_rejected() -> None:
    fact = FactObservation(
        "s", "revenue", date(2023, 12, 31), datetime(2024, 2, 1, tzinfo=UTC), 1, "live",
        period_start=date(2023, 1, 1), period_type=PeriodType.DURATION,
        reporting_frequency=ReportingFrequency.ANNUAL,
    )
    with pytest.raises(ProductionContractError, match="PROVIDER_MISSING"):
        validate_production_fact(fact, session=session())


def test_prior_completed_session_and_staleness_are_explicit() -> None:
    selected = prior_completed_primary_market_session(
        [session(date(2024, 5, 31)), session()], exchange="NYSE",
        decision_cutoff=datetime(2024, 6, 3, 22, tzinfo=UTC), expected_session_date=date(2024, 6, 3),
    )
    assert selected.session_date == date(2024, 6, 3)
    with pytest.raises(ProductionContractError, match="STALE"):
        prior_completed_primary_market_session(
            [session(date(2024, 5, 31))], exchange="NYSE",
            decision_cutoff=datetime(2024, 6, 3, 22, tzinfo=UTC), expected_session_date=date(2024, 6, 3),
        )
    with pytest.raises(ProductionContractError, match="NO_PRIOR"):
        prior_completed_primary_market_session([], exchange="NYSE", decision_cutoff=NOW)


def test_market_observation_must_match_explicit_session_close() -> None:
    market = MarketObservation(
        "s", "l", date(2024, 6, 3), datetime(2024, 6, 3, 19, 59, tzinfo=UTC),
        10, 100, "USD", "TEST_PROVIDER", "TEST_PRODUCT", "obs", evidence(),
    )
    with pytest.raises(ProductionContractError, match="NOT_AT_SESSION_CLOSE"):
        market.validate_against_session(session())


@pytest.mark.parametrize(("change", "reason"), [
    ({"total_market_capitalization_usd": 499_999_999}, "MARKET_CAPITALIZATION"),
    ({"raw_primary_close_usd": 4.99}, "RAW_CLOSE"),
    ({"completed_session_dollar_volumes_usd": (1_999_999.0,) * 60}, "MEDIAN_DOLLAR_VOLUME"),
    ({"completed_sessions_since_seasoning_boundary": 125}, "INSUFFICIENT_SEASONING"),
])
def test_universe_numeric_gates_fail_closed(change: dict[str, object], reason: str) -> None:
    assert any(reason in item for item in universe_observation(**change).exclusion_reasons())


@pytest.mark.parametrize("security_type", [
    "ADR", "PREFERRED_EQUITY", "ETF", "MUTUAL_FUND", "CLOSED_END_FUND",
    "BDC", "REIT", "PRE_COMBINATION_SPAC", "RIGHT", "WARRANT", "UNIT", "WHEN_ISSUED",
])
def test_excluded_historical_security_types(security_type: str) -> None:
    item = universe_observation(security_master=master(security_type=security_type))
    assert "INELIGIBLE_HISTORICAL_SECURITY_CLASSIFICATION" in item.exclusion_reasons()


def test_current_classification_cannot_fallback_to_historical_date() -> None:
    item = universe_observation(security_master=master(effective_start=date(2025, 1, 1)))
    assert "INELIGIBLE_HISTORICAL_SECURITY_CLASSIFICATION" in item.exclusion_reasons()


def test_post_combination_spac_requires_126_sessions() -> None:
    record = master(post_combination_boundary=date(2024, 1, 2))
    item = universe_observation(security_master=record, completed_sessions_since_seasoning_boundary=125)
    assert "POST_COMBINATION_SPAC_NOT_SEASONED" in item.exclusion_reasons()


def test_multiclass_resolution_primary_then_volume_then_security_id() -> None:
    nonprimary = universe_observation(
        security_master=master(security_id="A", listing_id="A", share_class_id="A", is_primary_listing=False),
        completed_session_dollar_volumes_usd=(9_000_000.0,) * 60,
    )
    primary = universe_observation(
        security_master=master(security_id="B", listing_id="B", share_class_id="B", is_primary_listing=True),
        completed_session_dollar_volumes_usd=(3_000_000.0,) * 60,
    )
    assert [item.security_id for item in build_point_in_time_universe([nonprimary, primary])] == ["B"]
    tied_a = universe_observation(security_master=master(security_id="A", listing_id="A", share_class_id="A", is_primary_listing=False))
    tied_b = universe_observation(security_master=master(security_id="B", listing_id="B", share_class_id="B", is_primary_listing=False))
    assert [item.security_id for item in build_point_in_time_universe([tied_b, tied_a])] == ["A"]


def test_liquidity_requires_exactly_sixty_explicit_sessions() -> None:
    with pytest.raises(ProductionContractError, match="EXACTLY_60"):
        _ = universe_observation(completed_session_dollar_volumes_usd=(3_000_000.0,) * 59).median_dollar_volume_usd


def test_field_catalog_is_closed_and_missing_mappings_fail() -> None:
    with pytest.raises(ProductionContractError, match="invalid keys"):
        FieldCatalog.from_mapping({"schema_version": 1, "identity": {}, "entries": [], "extra": 1})
    catalog = FieldCatalog(1, evidence(), ())
    blockers = catalog.validate(REPOSITORY)
    assert "FIELD_MAPPING_MISSING:revenue" in blockers
    assert "FIELD_CATALOG_IDENTITY_UNVERIFIED" in blockers


def test_field_entry_rejects_provider_evidence_mismatch() -> None:
    with pytest.raises(ProductionContractError, match="provider evidence mismatch"):
        FieldCatalogEntry(
            "revenue", "reported revenue", "DURATION", "ANNUAL",
            "USD_MILLIONS", "USD", 1_000_000, "REPORTED_USD",
            "P", "PRODUCT", "native-revenue", evidence(provider="OTHER"),
            date(2000, 1, 1), None, "filing timestamp", "FIRST_REPORTED", ("revenue",),
            evidence(provider="P", provider_product="PRODUCT"),
        )


def test_readiness_state_equivalence_is_fail_closed_for_every_gate() -> None:
    for gate in PREREQUISITE_KEYS:
        values = {name: True for name in PREREQUISITE_KEYS}
        values[gate] = False
        with pytest.raises(ProductionContractError, match="equivalence"):
            ScreenV2ReadinessState(
                "RESOLVED_RESEARCH_POLICY", "RESOLVED_PROVIDER_AND_DATA_EVIDENCE",
                "VERIFIED_REPOSITORY_IDENTITIES", "PRODUCTION_EXECUTION_READY", values,
            )


def test_absent_evidence_blocks_readiness_and_candidate_set() -> None:
    state, blockers, _ = evaluate_production_readiness(REPOSITORY)
    assert state.repository_identity_state == "VERIFIED_REPOSITORY_IDENTITIES"
    assert not state.production_execution_ready
    assert "PRODUCTION_EVIDENCE_MANIFEST_ABSENT" in blockers
    with pytest.raises(ProductionContractError, match="PUBLICATION_BLOCKED"):
        create_candidate_set(pd.DataFrame(), readiness=state, governed_batch_lineage_sha256="1" * 64)


def ranked_frame(count: int = 100) -> pd.DataFrame:
    frame = pd.DataFrame({
        "security_id": [f"S{number:03d}" for number in range(count)],
        "decision_date": [pd.Timestamp("2024-06-03", tz="UTC")] * count,
        "VALUATION": [1.0] * count, "BUSINESS_ECONOMICS": [1.0] * count,
        "FUNDAMENTAL_CHANGE": [1.0] * count,
    })
    frame["composite_score"] = 1.0
    for proxy in (
        "fcf_ev", "ebit_ev", "gross_profitability", "roic",
        "operating_margin_change", "fcf_margin_change", "revenue_acceleration",
    ):
        frame[proxy] = 0.1
    return frame


def test_candidateset_top100_tie_break_and_digest_scope_unchanged() -> None:
    assert RANKED_FRAME_DIGEST_SCOPE == ("security_id", "decision_date", "composite_score")
    frame = ranked_frame(101).sample(frac=1, random_state=7).reset_index(drop=True)
    candidate = create_candidate_set(frame, readiness=ready_state(), governed_batch_lineage_sha256="2" * 64)
    assert isinstance(candidate, CandidateSet)
    assert len(candidate.members) == 100
    assert [row["security_id"] for row in candidate.members[:3]] == ["S000", "S001", "S002"]
    assert candidate.members[-1]["security_id"] == "S099"
    assert candidate.to_dict()["transaction_authority"] is False


def test_candidateset_requires_both_valuation_proxies_and_population() -> None:
    frame = ranked_frame().drop(columns=["fcf_ev"])
    with pytest.raises(ProductionContractError, match="VALUATION_COVERAGE"):
        create_candidate_set(frame, readiness=ready_state(), governed_batch_lineage_sha256="2" * 64)
    with pytest.raises(ProductionContractError, match="INSUFFICIENT_ELIGIBLE_POPULATION"):
        create_candidate_set(ranked_frame(99), readiness=ready_state(), governed_batch_lineage_sha256="2" * 64)
    frame = ranked_frame()
    frame.loc[0, "ebit_ev"] = None
    with pytest.raises(ProductionContractError, match="INSUFFICIENT_ELIGIBLE_POPULATION"):
        create_candidate_set(frame, readiness=ready_state(), governed_batch_lineage_sha256="2" * 64)


def test_candidateset_rejects_skipna_dimension_reweighting() -> None:
    frame = ranked_frame()
    frame.loc[0, "BUSINESS_ECONOMICS"] = None
    with pytest.raises(ProductionContractError, match="DIMENSION_COVERAGE"):
        create_candidate_set(frame, readiness=ready_state(), governed_batch_lineage_sha256="2" * 64)
    frame = ranked_frame()
    frame.loc[0, "composite_score"] = 0.5
    with pytest.raises(ProductionContractError, match="EQUAL_WEIGHTED"):
        create_candidate_set(frame, readiness=ready_state(), governed_batch_lineage_sha256="2" * 64)


def test_preflight_is_outcome_free_and_blocks_real_run() -> None:
    result = production_readiness_preflight(REPOSITORY)
    assert result["research_policy_resolved"] is True
    assert result["repository_identities_verified"] is True
    assert result["provider_data_evidence_resolved"] is False
    assert result["production_execution_ready"] is False
    assert result["first_real_governed_run"] == "FIRST_REAL_RUN_BLOCKED"
    assert result["candidate_set_created"] is False
    assert result["realized_outcomes_inspected"] is False
    assert result["transaction_authority"] is False
    orchestrated = run_governed_screen_v2(REPOSITORY, evidence_manifest_path=None)
    assert orchestrated["first_real_governed_run"] == "FIRST_REAL_RUN_BLOCKED"
    assert orchestrated["candidate_set_created"] is False


def test_full_audit_and_external_blocker_contracts_are_complete() -> None:
    audit = implementation_gap_audit()
    blockers = consolidated_external_blockers()
    assert len(AUDIT_ITEM_NAMES) == len(audit) == 65
    assert [item["item"] for item in audit] == list(range(1, 66))
    assert {item["classification"] for item in audit} <= {
        "IMPLEMENTED_AND_VERIFIED", "IMPLEMENTED_BUT_INCOMPLETE",
        "MISSING_IMPLEMENTATION", "BLOCKED_BY_EXTERNAL_EVIDENCE", "NOT_APPLICABLE",
    }
    assert len(blockers) == 23
    assert [item["blocker_id"] for item in blockers] == [f"EXT-{number:03d}" for number in range(1, 24)]
    assert all(item["minimum_evidence_needed"] for item in blockers)


def test_evidence_identity_verifies_exact_repository_bytes(tmp_path: Path) -> None:
    payload = b"immutable evidence\n"
    path = tmp_path / "evidence.bin"
    path.write_bytes(payload)
    identity = evidence(
        content_sha256=hashlib.sha256(payload).hexdigest(),
        repository_relative_path="evidence.bin",
    )
    assert identity.verify_content(tmp_path)
    path.write_bytes(b"changed")
    assert not identity.verify_content(tmp_path)


def test_screen_v2_configuration_is_content_bound() -> None:
    assert len(SCREEN_V2_CONFIG_DIGEST) == 64
    assert SCREEN_V2_CONFIG_DIGEST == hashlib.sha256(
        __import__("graham_research.production", fromlist=["canonical_json"]).canonical_json(
            __import__("graham_research.production", fromlist=["SCREEN_V2_CONFIG"]).SCREEN_V2_CONFIG
        )
    ).hexdigest()
