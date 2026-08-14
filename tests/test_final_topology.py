from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from graham_research.domain import FactObservation, PeriodType, ReportingFrequency
from graham_research.production import (
    EvidenceIdentity,
    ExchangeSessionEvidence,
    ProductionContractError,
    production_readiness_preflight,
    validate_production_fact,
)
from graham_research.topology import (
    ClassMarketValue,
    ClassSharesObservation,
    CrosswalkResolution,
    DatabentoCloseStatistic,
    DatabentoDefinitionRecord,
    DatabentoSessionMarker,
    DatabentoSymbologyInterval,
    DatabentoTradeRecord,
    FinancingComponents,
    MassiveSnapshotRecord,
    OfficialSessionRecord,
    RawVolumePolicy,
    SecFilingFact,
    enterprise_value,
    invested_capital,
    require_spac_boundary,
    resolve_massive_databento_crosswalk,
    resolve_raw_primary_close,
    resolve_raw_primary_volume,
    select_first_reported_sec_fact,
    total_market_capitalization,
    validate_session_markers,
)


UTC = timezone.utc
DECISION = datetime(2025, 6, 30, 20, 0, tzinfo=UTC)


def evidence(provider: str, product: str) -> EvidenceIdentity:
    return EvidenceIdentity(
        evidence_id=f"{provider}-{product}", provider=provider,
        provider_product=product, content_sha256="1" * 64,
        source_native_vintage_identifier="vintage",
        acquired_at_utc=DECISION, repository_relative_path=None,
    )


def massive(**changes: object) -> MassiveSnapshotRecord:
    values = dict(
        historical_date=date(2025, 6, 30), ticker="ABC", active=True,
        primary_exchange="XNAS", type_code="CS", currency="USD",
        cik="0000000001", composite_figi="BBG-COMPOSITE",
        share_class_figi="BBG-CLASS", last_updated_utc=DECISION,
        evidence_identity=evidence("MASSIVE", "STOCKS_REFERENCE"),
    )
    values.update(changes)
    return MassiveSnapshotRecord(**values)


def mapping(**changes: object) -> DatabentoSymbologyInterval:
    values = dict(
        dataset="XNAS.ITCH", input_symbol="ABC", raw_symbol="ABC",
        instrument_id=101, start_at=datetime(2025, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 1, 1, tzinfo=UTC),
        evidence_identity=evidence("DATABENTO", "XNAS.ITCH"),
    )
    values.update(changes)
    return DatabentoSymbologyInterval(**values)


def definition(**changes: object) -> DatabentoDefinitionRecord:
    values = dict(
        dataset="XNAS.ITCH", publisher_id=7, instrument_id=101,
        raw_symbol="ABC", exchange="XNAS", security_type="COMMON_STOCK",
        currency="USD", effective_start=datetime(2025, 1, 1, tzinfo=UTC),
        effective_end=datetime(2026, 1, 1, tzinfo=UTC),
        evidence_identity=evidence("DATABENTO", "XNAS.ITCH"),
    )
    values.update(changes)
    return DatabentoDefinitionRecord(**values)


def crosswalk() -> CrosswalkResolution:
    return resolve_massive_databento_crosswalk(
        massive(), [mapping()], [definition()], decision_at=DECISION
    )


def session(**changes: object) -> OfficialSessionRecord:
    values = dict(
        exchange="XNAS", session_date=date(2025, 6, 30),
        timezone_name="America/New_York",
        session_open=datetime(2025, 6, 30, 13, 30, tzinfo=UTC),
        session_close=datetime(2025, 6, 30, 20, 0, tzinfo=UTC),
        status="COMPLETED", early_close=False,
        evidence_identity=evidence("OFFICIAL_EXCHANGE_CALENDAR", "NASDAQ_CALENDAR"),
    )
    values.update(changes)
    return OfficialSessionRecord(**values)


def sec_fact(**changes: object) -> SecFilingFact:
    values = dict(
        cik="0000000001", accession="0000000001-25-000001", form_type="10-K",
        accepted_at=datetime(2025, 2, 1, 12, 0, tzinfo=UTC),
        public_availability_at=datetime(2025, 2, 1, 12, 0, 1, tzinfo=UTC),
        xbrl_concept="us-gaap:Revenues", unit="USD",
        period_start=date(2024, 1, 1), period_end=date(2024, 12, 31),
        instant_date=None, value=10.0, context_id="ctx", native_fact_id="fact-1",
        fiscal_year=2024, evidence_identity=evidence("SEC_EDGAR", "FILING_ARCHIVE"),
        dimensions_digest="dimensions",
    )
    values.update(changes)
    return SecFilingFact(**values)


def test_sec_timestamp_cutoff_and_explicit_period_range() -> None:
    before = sec_fact()
    after = sec_fact(
        accession="0000000001-25-000002", native_fact_id="fact-2",
        accepted_at=datetime(2025, 7, 1, tzinfo=UTC),
        public_availability_at=datetime(2025, 7, 1, tzinfo=UTC),
    )
    selected = select_first_reported_sec_fact(
        [after, before], decision_cutoff=DECISION,
        cik="0000000001",
        xbrl_concept="us-gaap:Revenues", unit="USD",
        period_start=date(2024, 1, 1), period_end=date(2024, 12, 31),
        dimensions_digest="dimensions",
    )
    assert selected.accession == before.accession
    assert selected.period_start == date(2024, 1, 1)


def test_first_reported_accession_rejects_later_restatement() -> None:
    first = sec_fact()
    amended = sec_fact(
        accession="0000000001-25-000002", form_type="10-K/A",
        native_fact_id="fact-2", accepted_at=datetime(2025, 3, 1, tzinfo=UTC),
        public_availability_at=datetime(2025, 3, 1, tzinfo=UTC), value=99,
    )
    assert select_first_reported_sec_fact(
        [amended, first], decision_cutoff=DECISION,
        cik="0000000001",
        xbrl_concept="us-gaap:Revenues", unit="USD",
        period_start=date(2024, 1, 1), period_end=date(2024, 12, 31),
        dimensions_digest="dimensions",
    ).value == 10


def test_sec_fact_requires_independent_public_availability_evidence() -> None:
    item = sec_fact(public_availability_at=None)
    with pytest.raises(ProductionContractError, match="PUBLIC_AVAILABILITY"):
        item.to_fact_observation(
            security_id="S", canonical_field="revenue",
            availability_authority_identity="authority",
            source_native_vintage_identifier="vintage",
        )


def test_sec_duration_requires_native_start_and_end() -> None:
    with pytest.raises(ProductionContractError, match="explicit duration or instant"):
        sec_fact(period_start=None, instant_date=None)


def test_crosswalk_requires_one_unique_date_venue_symbology_definition_match() -> None:
    result = crosswalk()
    assert result.databento_instrument_id == 101
    assert result.identity_authority_status == "RD-CROSSWALK-001_REQUIRED"


def test_crosswalk_missing_and_ambiguous_fail_closed() -> None:
    with pytest.raises(ProductionContractError, match="CROSSWALK_MISSING"):
        resolve_massive_databento_crosswalk(massive(), [], [definition()], decision_at=DECISION)
    with pytest.raises(ProductionContractError, match="CROSSWALK_AMBIGUOUS"):
        resolve_massive_databento_crosswalk(
            massive(), [mapping(), mapping(instrument_id=102)],
            [definition(), definition(instrument_id=102, publisher_id=8)],
            decision_at=DECISION,
        )


def test_wrong_primary_venue_fails() -> None:
    wrong = massive(primary_exchange="XNYS")
    with pytest.raises(ProductionContractError, match="CROSSWALK_MISSING"):
        resolve_massive_databento_crosswalk(
            wrong, [mapping()], [definition()], decision_at=DECISION
        )


def test_massive_unknown_and_common_stock_remain_ineligible_without_taxonomy() -> None:
    assert massive(type_code="UNKNOWN").classification == "UNKNOWN_CLASSIFICATION"
    assert massive(type_code="CS").screen_eligible_classification is False
    assert massive(type_code="ADRC").classification == "UNKNOWN_CLASSIFICATION"


def test_delisted_massive_record_is_structurally_valid() -> None:
    assert massive(active=False).active is False


def test_raw_close_requires_exact_primary_venue_statistic() -> None:
    item = DatabentoCloseStatistic(
        "XNAS.ITCH", 7, 101, DECISION, DECISION, DECISION,
        12_500_000_000, 11, 1, 42, evidence("DATABENTO", "XNAS.ITCH"),
    )
    resolved = resolve_raw_primary_close(crosswalk(), session(), [item])
    assert resolved.price == 12.5
    assert resolved.evidence_identity.evidence_id == "DATABENTO-XNAS.ITCH"
    without_reference_timestamp = DatabentoCloseStatistic(
        "XNAS.ITCH", 7, 101, DECISION, DECISION, None,
        12_500_000_000, 11, 1, 43, evidence("DATABENTO", "XNAS.ITCH"),
    )
    assert resolve_raw_primary_close(
        crosswalk(), session(), [without_reference_timestamp]
    ).price == 12.5
    with pytest.raises(ProductionContractError, match="WRONG_PRIMARY_VENUE"):
        resolve_raw_primary_close(crosswalk(), session(exchange="XNYS"), [item])


def test_databento_session_markers_must_match_official_session() -> None:
    markers = [
        DatabentoSessionMarker(
            "XNAS.ITCH", "XNAS", "OPEN", session().session_open, 7,
            evidence("DATABENTO", "XNAS.ITCH"),
        ),
        DatabentoSessionMarker(
            "XNAS.ITCH", "XNAS", "CLOSE", session().session_close, 7,
            evidence("DATABENTO", "XNAS.ITCH"),
        ),
    ]
    validate_session_markers(session(), markers)
    with pytest.raises(ProductionContractError, match="CLOSE_MISMATCH"):
        validate_session_markers(session(), markers[:1])


def test_raw_volume_uses_direct_feed_semantics_without_invented_conditions() -> None:
    trade = DatabentoTradeRecord(
        "XNAS.ITCH", 7, 101, datetime(2025, 6, 30, 15, tzinfo=UTC),
        datetime(2025, 6, 30, 15, tzinfo=UTC), 1, 100, "T", (), False,
        "ORIGINAL", evidence("DATABENTO", "XNAS.ITCH"),
    )
    policy = RawVolumePolicy("authority", frozenset(), frozenset(), True,
                             "FAIL_ON_CANCEL_OR_CORRECTION")
    assert resolve_raw_primary_volume(
        crosswalk(), session(), [trade], policy=policy
    ).volume == 100
    invented = DatabentoTradeRecord(
        "XNAS.ITCH", 7, 101, datetime(2025, 6, 30, 15, tzinfo=UTC),
        datetime(2025, 6, 30, 15, tzinfo=UTC), 2, 100, "T", ("UNKNOWN",), False,
        "ORIGINAL", evidence("DATABENTO", "XNAS.ITCH"),
    )
    with pytest.raises(ProductionContractError, match="UNDOCUMENTED_TRADE_CONDITION"):
        resolve_raw_primary_volume(crosswalk(), session(), [invented], policy=policy)


def test_multiclass_market_cap_and_missing_shares() -> None:
    shares_a = ClassSharesObservation(
        "I", "A", "FIGI-A", date(2025, 4, 1), datetime(2025, 4, 2, tzinfo=UTC),
        100, "0000000001-25-000001", evidence("SEC_EDGAR", "FILING_ARCHIVE"),
    )
    shares_b = ClassSharesObservation(
        "I", "B", "FIGI-B", date(2025, 4, 1), datetime(2025, 4, 2, tzinfo=UTC),
        50, "0000000001-25-000001", evidence("SEC_EDGAR", "FILING_ARCHIVE"),
    )
    classes = [
        ClassMarketValue("I", "A", DECISION, 10, shares_a),
        ClassMarketValue("I", "B", DECISION, 20, shares_b),
    ]
    assert total_market_capitalization(classes) == 2_000
    with pytest.raises(ProductionContractError, match="SHARES_MISSING"):
        total_market_capitalization([ClassMarketValue("I", "A", DECISION, 10, None)])


def test_ev_and_invested_capital_require_every_component() -> None:
    complete = FinancingComponents(1, 2, 3, 4, 5, 6)
    assert enterprise_value(100, complete) == 104
    assert invested_capital(complete) == 9
    with pytest.raises(ProductionContractError, match="COMPONENT_MISSING"):
        enterprise_value(100, FinancingComponents(1, 2, None, 4, 5, 6))


def test_spac_boundary_absence_fails_closed() -> None:
    with pytest.raises(ProductionContractError, match="BOUNDARY_MISSING"):
        require_spac_boundary(None)


def test_production_readiness_stays_false_until_crosswalk_authority_exists() -> None:
    result = production_readiness_preflight(".")
    assert result["production_execution_ready"] is False
    assert result["candidate_set_created"] is False
    assert (
        "RESEARCHER_DECISION_AUTHORITY_UNRESOLVED:RD-CROSSWALK-001"
        in result["blockers"]
    )


def test_sec_and_market_providers_may_differ_when_timestamp_is_admissible() -> None:
    market_identity = evidence("DATABENTO", "XNAS.ITCH")
    market_session = ExchangeSessionEvidence(
        exchange="NASDAQ", timezone_name="America/New_York",
        session_date=date(2025, 6, 30),
        session_open=datetime(2025, 6, 30, 13, 30, tzinfo=UTC),
        session_close=DECISION, session_status="COMPLETED",
        provider="DATABENTO", provider_product="XNAS.ITCH",
        evidence_identity=market_identity,
    )
    fact = FactObservation(
        "S", "revenue", date(2024, 12, 31), datetime(2025, 2, 1, tzinfo=UTC),
        10, "SEC", accession="0000000001-25-000001", unit="USD",
        period_type=PeriodType.DURATION, reporting_frequency=ReportingFrequency.ANNUAL,
        period_start=date(2024, 1, 1), provider="SEC_EDGAR",
        provider_product="FILING_ARCHIVE", native_observation_id="fact",
        source_native_vintage_identifier="vintage",
    )
    validate_production_fact(fact, session=market_session)
