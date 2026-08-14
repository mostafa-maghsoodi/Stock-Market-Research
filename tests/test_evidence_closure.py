from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path

import pytest

from graham_research.closure import (
    ClassificationEvidence,
    ClosedFinancingComponents,
    ComponentEvidenceState,
    FINAL_DECISION_STATUS,
    FinancingComponentValue,
    SecClassSharesEvidence,
    SpacCombinationEvidence,
    ZeroGapSessionPolicy,
    adopt_sec_acceptance_availability,
    classify_operating_company,
    closed_enterprise_value,
    closed_invested_capital,
    derive_internal_listing_identity,
    normalize_databento_price,
    normalize_sec_value,
    require_prior_completed_session_observation,
    resolve_pit_class_shares,
    select_closed_sec_mapping_fact,
    resolve_spac_post_combination_boundary,
    validate_sec_mapping_fact,
)
from graham_research.evidence import (
    CandidateProductionEvidenceManifest,
    EvidenceRequest,
    SafeHttpResponse,
    collect_evidence,
    revalidate_collected_evidence,
)
from graham_research.production import EvidenceIdentity, ProductionContractError
from graham_research.topology import (
    CrosswalkResolution,
    OfficialSessionRecord,
    SecFilingFact,
)


UTC = timezone.utc
ACCEPTED = datetime(2025, 2, 3, 21, 1, 2, tzinfo=UTC)
DECISION = datetime(2025, 6, 30, 20, 0, tzinfo=UTC)


def identity(provider: str = "SEC_EDGAR", product: str = "FILING_ARCHIVE", char: str = "1") -> EvidenceIdentity:
    return EvidenceIdentity(
        f"{provider}-{product}-{char}", provider, product, char * 64, "vintage",
        ACCEPTED, None,
    )


def sec_fact(**changes: object) -> SecFilingFact:
    values = {
        "cik": "0000000001", "accession": "0000000001-25-000001",
        "form_type": "10-K", "accepted_at": ACCEPTED,
        "public_availability_at": None,
        "xbrl_concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "unit": "USD", "period_start": date(2024, 1, 1),
        "period_end": date(2024, 12, 31), "instant_date": None,
        "value": 100.0, "context_id": "ctx", "native_fact_id": "fact",
        "fiscal_year": 2024, "evidence_identity": identity(),
        "dimensions_digest": "dims",
    }
    values.update(changes)
    return SecFilingFact(**values)


def session(day: date, *, status: str = "COMPLETED") -> OfficialSessionRecord:
    return OfficialSessionRecord(
        "XNAS", day, "America/New_York",
        datetime(day.year, day.month, day.day, 13, 30, tzinfo=UTC),
        datetime(day.year, day.month, day.day, 20, 0, tzinfo=UTC),
        status, False,
        identity("OFFICIAL_EXCHANGE_CALENDAR", "NASDAQ_CALENDAR"),
    )


def crosswalk() -> CrosswalkResolution:
    massive = identity("MASSIVE", "STOCKS_REFERENCE")
    symbology = identity("DATABENTO", "XNAS.ITCH", "2")
    definition = identity("DATABENTO", "XNAS.ITCH", "3")
    return CrosswalkResolution(
        DECISION, "0000000001", "BBG-CLASS", "ABC", "XNAS", "XNAS.ITCH",
        "ABC", 101, 7, massive, symbology, definition,
        "RD-CROSSWALK-001_REQUIRED",
        datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC),
    )


def component(name: str, state: ComponentEvidenceState, value: float | None, *, evidence: bool = True) -> FinancingComponentValue:
    structural_rules = {
        "preferred_stock": "NO_PREFERRED_SECURITY_AND_NO_PREFERRED_EQUITY_FACT",
        "noncontrolling_interest": "NO_CONSOLIDATED_NCI_PRESENTATION_OR_FACT",
    }
    return FinancingComponentValue(
        name, state, value, identity() if evidence else None,
        structural_rules.get(name) if state is ComponentEvidenceState.STRUCTURALLY_NOT_APPLICABLE else None,
    )


def complete_components() -> ClosedFinancingComponents:
    return ClosedFinancingComponents(
        component("short_term_debt", ComponentEvidenceState.EXPLICIT_VALUE, 1),
        component("long_term_debt", ComponentEvidenceState.EXPLICIT_VALUE, 2),
        component("preferred_stock", ComponentEvidenceState.STRUCTURALLY_NOT_APPLICABLE, None),
        component("noncontrolling_interest", ComponentEvidenceState.EXPLICIT_ZERO, 0),
        component("common_equity", ComponentEvidenceState.EXPLICIT_VALUE, 5),
        component("cash_and_short_term_investments", ComponentEvidenceState.EXPLICIT_VALUE, 3),
    )


def test_sec_acceptance_is_exact_governed_cutoff_without_public_web_claim() -> None:
    adopted = adopt_sec_acceptance_availability(sec_fact(), authority_identity="RD-004A")
    assert adopted.public_availability_at == adopted.accepted_at
    conflicting = sec_fact(public_availability_at=ACCEPTED.replace(second=3))
    with pytest.raises(ProductionContractError, match="conflicts"):
        adopt_sec_acceptance_availability(conflicting, authority_identity="RD-004A")


def test_sec_closed_mapping_requires_exact_concept_period_unit_and_dimensions() -> None:
    fact = sec_fact()
    validate_sec_mapping_fact(
        fact, canonical_concept="revenue",
        dimensions_class="CONSOLIDATED_NO_SEGMENT_DIMENSIONS",
    )
    with pytest.raises(ProductionContractError, match="EXTENSION_OR_UNAPPROVED"):
        validate_sec_mapping_fact(
            replace(fact, xbrl_concept="issuer:Revenue"), canonical_concept="revenue",
            dimensions_class="CONSOLIDATED_NO_SEGMENT_DIMENSIONS",
        )


def test_sec_closed_priority_rejects_conflicting_allowed_concepts() -> None:
    first = adopt_sec_acceptance_availability(sec_fact(), authority_identity="RD-004A")
    second = replace(
        first, xbrl_concept="us-gaap:Revenues", value=101,
        native_fact_id="fact-2", accession="0000000001-25-000002",
    )
    with pytest.raises(ProductionContractError, match="AMBIGUOUS"):
        select_closed_sec_mapping_fact(
            [first, second], canonical_concept="revenue", cik="0000000001",
            decision_cutoff=DECISION, period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31), dimensions_digest="dims",
            dimensions_class="CONSOLIDATED_NO_SEGMENT_DIMENSIONS",
        )


def test_explicit_zero_structural_na_and_missing_are_distinct() -> None:
    components = complete_components()
    assert closed_enterprise_value(100, components) == 100
    assert closed_invested_capital(components) == 5
    missing = replace(
        components,
        preferred_stock=component(
            "preferred_stock", ComponentEvidenceState.MISSING_UNKNOWN, None, evidence=False
        ),
    )
    with pytest.raises(ProductionContractError, match="UNKNOWN"):
        closed_enterprise_value(100, missing)
    unsupported = replace(
        components,
        preferred_stock=component(
            "preferred_stock", ComponentEvidenceState.STRUCTURALLY_NOT_APPLICABLE,
            None, evidence=False,
        ),
    )
    with pytest.raises(ProductionContractError, match="lacks evidence"):
        closed_enterprise_value(100, unsupported)


def test_class_dimensional_cover_shares_are_required() -> None:
    fact = adopt_sec_acceptance_availability(
        sec_fact(
            xbrl_concept="dei:EntityCommonStockSharesOutstanding", unit="SHARES",
            period_start=None, instant_date=date(2025, 1, 31),
            period_end=date(2025, 1, 31), dimensions_digest="class-a", value=42,
        ),
        authority_identity="RD-004A",
    )
    item = SecClassSharesEvidence(fact, "SECURITY-A", "FIGI-A", "class-a", identity())
    assert resolve_pit_class_shares(item, decision_cutoff=DECISION) == 42
    with pytest.raises(ProductionContractError, match="DIMENSION_MISMATCH"):
        resolve_pit_class_shares(replace(item, exact_class_dimension_digest="class-b"), decision_cutoff=DECISION)


def test_zero_gap_session_requires_exact_prior_completed_session() -> None:
    policy = ZeroGapSessionPolicy("RD-013")
    sessions = [session(date(2025, 6, 27)), session(date(2025, 6, 30))]
    result = require_prior_completed_session_observation(
        sessions, decision_date=date(2025, 6, 30),
        observation_session_date=date(2025, 6, 27), exchange="XNAS", policy=policy,
    )
    assert result.session_date == date(2025, 6, 27)
    with pytest.raises(ProductionContractError, match="ZERO_GAP"):
        require_prior_completed_session_observation(
            sessions, decision_date=date(2025, 6, 30),
            observation_session_date=date(2025, 6, 26), exchange="XNAS", policy=policy,
        )


def test_unknown_classification_is_ineligible_and_positive_evidence_is_required() -> None:
    base = ClassificationEvidence(
        "CS", "Common Stock", identity("MASSIVE", "STOCKS_REFERENCE"), True,
        False, False, False, None, (identity(),),
    )
    assert classify_operating_company(base) == "UNKNOWN_CLASSIFICATION"
    assert classify_operating_company(replace(base, shell_company_effective=False)) == "ELIGIBLE_COMMON_OPERATING_COMPANY"
    assert classify_operating_company(replace(base, shell_company_effective=True)) == "INELIGIBLE_EXCLUDED_CLASS"


def test_spac_boundary_requires_sec_completion_then_next_session() -> None:
    evidence = SpacCombinationEvidence(
        "0000000001", "0000000001-25-000001", ACCEPTED,
        datetime(2025, 2, 3, 12, tzinfo=UTC), "8-K", True, True, identity(),
    )
    assert resolve_spac_post_combination_boundary(
        evidence, [session(date(2025, 2, 3)), session(date(2025, 2, 4))], exchange="XNAS"
    ).date() == date(2025, 2, 4)
    with pytest.raises(ProductionContractError, match="SESSION_MISSING"):
        resolve_spac_post_combination_boundary(evidence, [], exchange="XNAS")


def test_crosswalk_identity_is_reproducible_and_ticker_is_not_sole_material() -> None:
    sec_cik = identity()
    first = derive_internal_listing_identity(crosswalk(), sec_cik_evidence_identity=sec_cik)
    second = derive_internal_listing_identity(crosswalk(), sec_cik_evidence_identity=sec_cik)
    assert first == second
    assert len(first.issuer_id) == len(first.security_id) == len(first.listing_id) == 64
    changed = replace(crosswalk(), databento_instrument_id=102)
    assert derive_internal_listing_identity(
        changed, sec_cik_evidence_identity=sec_cik
    ).listing_id != first.listing_id
    assert derive_internal_listing_identity(
        changed, sec_cik_evidence_identity=sec_cik
    ).security_id == first.security_id


def test_first_run_rejects_non_usd_accounting_and_normalizes_native_price() -> None:
    assert normalize_sec_value(value=10, xbrl_unit="iso4217:USD", canonical_unit="USD") == 10
    with pytest.raises(ProductionContractError, match="NON_USD"):
        normalize_sec_value(value=10, xbrl_unit="iso4217:EUR", canonical_unit="USD")
    assert normalize_databento_price(12_500_000_000, definition_currency="USD") == 12.5


def test_all_policy_decisions_are_closed_except_exact_evidence() -> None:
    assert FINAL_DECISION_STATUS["RD-001"].value == "NEEDS_EXACT_PROVIDER_EVIDENCE"
    assert all(
        state.value == "READY_TO_ADOPT"
        for decision, state in FINAL_DECISION_STATUS.items()
        if decision != "RD-001"
    )


def test_evidence_collector_hides_secrets_and_is_content_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASSIVE_API_KEY", "test-credential")
    request = EvidenceRequest(
        "massive-snapshot", "MASSIVE", "STOCKS_REFERENCE",
        "https://api.massive.com/v3/reference/tickers",
        {"date": "2025-06-30", "market": "stocks"}, "request-id-1",
        date(2025, 6, 30), date(2025, 6, 30),
    )

    def transport(_: EvidenceRequest, headers: dict[str, str]) -> SafeHttpResponse:
        assert headers["Authorization"] == "Bearer test-credential"
        return SafeHttpResponse(200, b'{"results":[]}')

    output = tmp_path / "raw"
    collected = collect_evidence(
        request, output_directory=output, repository=Path(__file__).parents[1],
        transport=transport, acquired_at_utc=ACCEPTED,
    )
    revalidate_collected_evidence(collected)
    metadata = json.dumps(collected.metadata_mapping())
    assert "test-credential" not in metadata
    assert collected.artifact_status == "CANDIDATE_EVIDENCE_NOT_ADMITTED"
    assert len(collected.identity.evidence_id) == 64


def test_evidence_collector_rejects_secret_parameters_and_sha_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASSIVE_API_KEY", "secret")
    with pytest.raises(ProductionContractError, match="secret-like"):
        EvidenceRequest(
            "bad", "MASSIVE", "STOCKS_REFERENCE",
            "https://api.massive.com/v3/reference/tickers", {"apiKey": "secret"},
            "v", None, None,
        )
    request = EvidenceRequest(
        "ok", "MASSIVE", "STOCKS_REFERENCE",
        "https://api.massive.com/v3/reference/tickers", {}, "v", None, None,
    )
    repository = Path(__file__).parents[1]
    with pytest.raises(ProductionContractError, match="outside Git"):
        collect_evidence(
            request, output_directory=repository / "raw-evidence", repository=repository,
            transport=lambda *_: SafeHttpResponse(200, b"not-written"),
            acquired_at_utc=ACCEPTED,
        )
    collected = collect_evidence(
        request, output_directory=tmp_path / "raw", repository=repository,
        transport=lambda *_: SafeHttpResponse(200, b"original"), acquired_at_utc=ACCEPTED,
    )
    Path(collected.raw_file_path).write_bytes(b"changed")
    with pytest.raises(ProductionContractError, match="SHA256|BYTE_LENGTH"):
        revalidate_collected_evidence(collected)


def test_candidate_manifest_can_never_self_admit() -> None:
    sec = identity()
    massive = identity("MASSIVE", "STOCKS_REFERENCE")
    db = identity("DATABENTO", "XNAS.ITCH")
    calendar = identity("OFFICIAL_EXCHANGE_CALENDAR", "NASDAQ_CALENDAR")
    manifest = CandidateProductionEvidenceManifest(
        1, "NOT_PRODUCTION_ADMITTED", (sec,), (massive,), (db,), (calendar,),
        sec, massive, "a" * 64, "b" * 40,
    )
    assert manifest.blockers() == ("NOT_PRODUCTION_ADMITTED",)
    assert "CANDIDATE_MANIFEST_STATUS_INVALID" in replace(
        manifest, artifact_status="PRODUCTION_ADMITTED"
    ).blockers()
