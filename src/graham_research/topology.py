"""Deterministic, provider-neutral contracts for the proposed Screen v2 topology.

These contracts validate candidate SEC, Massive, Databento, and official-session
evidence.  They do not select providers, approve mappings, derive governing
identities, or create production evidence.  Every economically meaningful or
provider-semantic choice remains an explicit authority input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
import re
from typing import Mapping, Sequence

from .domain import FactObservation, PeriodType, ReportingFrequency
from .production import EvidenceIdentity, ProductionContractError


MIC_TO_DATABENTO_DATASET = {
    "XNAS": "XNAS.ITCH",
    "XNYS": "XNYS.PILLAR",
    "XASE": "XASE.PILLAR",
}

# The public official ticker-types sample establishes CS as Common Stock. Exact
# descriptions for the remaining observed codes require authenticated metadata
# evidence and therefore are not embedded as production semantics here.
MASSIVE_DIRECT_EXCLUSIONS: Mapping[str, str] = {}

SEC_ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
SEC_CIK_RE = re.compile(r"^\d{10}$")
DBN_UNDEF_PRICE = 2**63 - 1


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductionContractError(f"{label} must be a non-empty string")
    return value.strip()


def _aware(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ProductionContractError(f"{label} must be timezone-aware")
    return value


def _provider_matches(identity: EvidenceIdentity, provider: str, product: str) -> None:
    if identity.provider != provider or identity.provider_product != product:
        raise ProductionContractError("provider/evidence identity mismatch")


@dataclass(frozen=True)
class SecConceptCandidate:
    canonical_concept: str
    xbrl_concepts: tuple[str, ...]
    economic_definition: str
    period_type: str
    canonical_unit: str
    sign_convention: str
    derivation_allowed: bool
    derivation_formula: str | None
    ambiguity_behavior: str = "REQUIRE_GOVERNED_MAPPING"

    def __post_init__(self) -> None:
        _text(self.canonical_concept, "canonical_concept")
        if not self.xbrl_concepts or len(set(self.xbrl_concepts)) != len(self.xbrl_concepts):
            raise ProductionContractError("XBRL candidates must be non-empty and unique")
        if self.period_type not in {"DURATION", "INSTANT"}:
            raise ProductionContractError("SEC concept period type is closed")
        if self.canonical_unit not in {"USD", "SHARES"}:
            raise ProductionContractError("SEC canonical unit is closed")
        if self.ambiguity_behavior != "REQUIRE_GOVERNED_MAPPING":
            raise ProductionContractError("SEC ambiguity behavior must fail closed")
        if self.derivation_allowed != (self.derivation_formula is not None):
            raise ProductionContractError("derivation flag/formula mismatch")


# Candidate catalogue only.  Multiple tags are never pooled or prioritized by
# this constant; RD-004 must bind the exact accepted concepts and derivations.
SEC_CANONICAL_FIELD_CANDIDATES = (
    SecConceptCandidate(
        "revenue",
        (
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:Revenues",
            "us-gaap:SalesRevenueNet",
        ),
        "Annual revenue from the registrant's ordinary activities.",
        "DURATION", "USD", "REPORTED_SIGN", False, None,
    ),
    SecConceptCandidate(
        "gross_profit", ("us-gaap:GrossProfit",),
        "Reported revenue less reported cost of revenue.",
        "DURATION", "USD", "REPORTED_SIGN", False, None,
    ),
    SecConceptCandidate(
        "operating_income", ("us-gaap:OperatingIncomeLoss",),
        "Reported operating income or loss.",
        "DURATION", "USD", "REPORTED_SIGN", False, None,
    ),
    SecConceptCandidate(
        "operating_cash_flow", ("us-gaap:NetCashProvidedByUsedInOperatingActivities",),
        "Net cash provided by or used in operating activities.",
        "DURATION", "USD", "REPORTED_SIGN", False, None,
    ),
    SecConceptCandidate(
        "capital_expenditures", ("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",),
        "Cash payments to acquire property, plant, and equipment.",
        "DURATION", "USD", "POSITIVE_OUTFLOW", False, None,
    ),
    SecConceptCandidate(
        "total_assets", ("us-gaap:Assets",), "Total assets.",
        "INSTANT", "USD", "REPORTED_SIGN", False, None,
    ),
    SecConceptCandidate(
        "income_before_tax",
        (
            "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ),
        "Income or loss before income taxes under an exactly governed scope.",
        "DURATION", "USD", "REPORTED_SIGN", False, None,
    ),
    SecConceptCandidate(
        "income_tax_expense", ("us-gaap:IncomeTaxExpenseBenefit",),
        "Income-tax expense or benefit.",
        "DURATION", "USD", "REPORTED_SIGN", False, None,
    ),
    SecConceptCandidate(
        "short_term_debt",
        ("us-gaap:ShortTermBorrowings", "us-gaap:LongTermDebtCurrent"),
        "Current financing obligations under governed component coverage.",
        "INSTANT", "USD", "REPORTED_SIGN", True,
        "SUM(governed non-overlapping current-debt components)",
    ),
    SecConceptCandidate(
        "long_term_debt", ("us-gaap:LongTermDebtNoncurrent",),
        "Non-current debt.", "INSTANT", "USD", "REPORTED_SIGN", False, None,
    ),
    SecConceptCandidate(
        "preferred_stock",
        ("us-gaap:PreferredStockValue", "us-gaap:PreferredStockValueOutstanding"),
        "Preferred-stock carrying amount under a governed scope.",
        "INSTANT", "USD", "REPORTED_SIGN", False, None,
    ),
    SecConceptCandidate(
        "noncontrolling_interest",
        ("us-gaap:MinorityInterest", "us-gaap:NoncontrollingInterestInConsolidatedEntity"),
        "Noncontrolling interest included in the financing construction.",
        "INSTANT", "USD", "REPORTED_SIGN", False, None,
    ),
    SecConceptCandidate(
        "common_equity", ("us-gaap:StockholdersEquity",),
        "Equity attributable to the parent stockholders.",
        "INSTANT", "USD", "REPORTED_SIGN", False, None,
    ),
    SecConceptCandidate(
        "cash_and_short_term_investments",
        (
            "us-gaap:CashAndCashEquivalentsAtCarryingValue",
            "us-gaap:ShortTermInvestments",
        ),
        "Cash, cash equivalents, and governed short-term investments.",
        "INSTANT", "USD", "REPORTED_SIGN", True,
        "SUM(governed non-overlapping cash and short-term-investment components)",
    ),
    SecConceptCandidate(
        "shares_outstanding", ("dei:EntityCommonStockSharesOutstanding",),
        "Cover-page common shares outstanding for an explicit stock-class context.",
        "INSTANT", "SHARES", "POSITIVE_COUNT", False, None,
    ),
)


@dataclass(frozen=True)
class SecFilingFact:
    cik: str
    accession: str
    form_type: str
    accepted_at: datetime
    public_availability_at: datetime | None
    xbrl_concept: str
    unit: str
    period_start: date | None
    period_end: date
    instant_date: date | None
    value: float
    context_id: str
    native_fact_id: str
    fiscal_year: int
    evidence_identity: EvidenceIdentity
    dimensions_digest: str

    def __post_init__(self) -> None:
        if not SEC_CIK_RE.fullmatch(self.cik):
            raise ProductionContractError("SEC CIK must be zero-padded to ten digits")
        if not SEC_ACCESSION_RE.fullmatch(self.accession):
            raise ProductionContractError("SEC accession format is invalid")
        if self.form_type not in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}:
            raise ProductionContractError("SEC annual form type is unsupported")
        _aware(self.accepted_at, "accepted_at")
        if self.public_availability_at is not None:
            _aware(self.public_availability_at, "public_availability_at")
            if self.public_availability_at < self.accepted_at:
                raise ProductionContractError("public availability precedes SEC acceptance")
        for value, label in (
            (self.xbrl_concept, "xbrl_concept"), (self.unit, "unit"),
            (self.context_id, "context_id"), (self.native_fact_id, "native_fact_id"),
            (self.dimensions_digest, "dimensions_digest"),
        ):
            _text(value, label)
        if self.period_start is not None and self.instant_date is not None:
            raise ProductionContractError("SEC fact cannot be duration and instant")
        if self.period_start is None and self.instant_date is None:
            raise ProductionContractError("SEC fact requires explicit duration or instant context")
        if self.period_start is not None and self.period_start > self.period_end:
            raise ProductionContractError("SEC duration range is inverted")
        if self.instant_date is not None and self.instant_date != self.period_end:
            raise ProductionContractError("SEC instant date must equal period_end")
        if isinstance(self.value, bool) or not math.isfinite(float(self.value)):
            raise ProductionContractError("SEC fact value must be finite")
        _provider_matches(self.evidence_identity, "SEC_EDGAR", "FILING_ARCHIVE")

    @property
    def period_type(self) -> PeriodType:
        return PeriodType.DURATION if self.period_start is not None else PeriodType.INSTANT

    def to_fact_observation(
        self,
        *,
        security_id: str,
        canonical_field: str,
        availability_authority_identity: str,
        source_native_vintage_identifier: str,
    ) -> FactObservation:
        _text(availability_authority_identity, "availability_authority_identity")
        if self.public_availability_at is None:
            raise ProductionContractError("SEC_PUBLIC_AVAILABILITY_TIMESTAMP_UNRESOLVED")
        return FactObservation(
            security_id=_text(security_id, "security_id"),
            field=_text(canonical_field, "canonical_field"),
            period_start=self.period_start,
            period_end=self.period_end,
            available_at=self.public_availability_at,
            value=float(self.value),
            source=f"SEC:{self.accession}",
            accession=self.accession,
            unit=self.unit,
            period_type=self.period_type,
            reporting_frequency=ReportingFrequency.ANNUAL,
            form_type=self.form_type,
            fiscal_year=self.fiscal_year,
            provider="SEC_EDGAR",
            provider_product="FILING_ARCHIVE",
            native_observation_id=self.native_fact_id,
            source_native_vintage_identifier=_text(
                source_native_vintage_identifier, "source_native_vintage_identifier"
            ),
            metadata={
                "cik": self.cik,
                "context_id": self.context_id,
                "xbrl_concept": self.xbrl_concept,
                "dimensions_digest": self.dimensions_digest,
                "accepted_at": self.accepted_at.isoformat(),
                "availability_authority_identity": availability_authority_identity,
            },
        )


def select_first_reported_sec_fact(
    facts: Sequence[SecFilingFact],
    *,
    cik: str,
    decision_cutoff: datetime,
    xbrl_concept: str,
    unit: str,
    period_start: date | None,
    period_end: date,
    dimensions_digest: str,
) -> SecFilingFact:
    """Select the earliest admissible accession; never replace it with a restatement."""

    _aware(decision_cutoff, "decision_cutoff")
    candidates = [
        item for item in facts
        if item.cik == cik
        and item.xbrl_concept == xbrl_concept
        and item.unit == unit
        and item.period_start == period_start
        and item.period_end == period_end
        and item.dimensions_digest == dimensions_digest
        and item.public_availability_at is not None
        and item.public_availability_at <= decision_cutoff
    ]
    if not candidates:
        raise ProductionContractError("SEC_FIRST_REPORTED_FACT_MISSING")
    ordered = sorted(candidates, key=lambda item: (item.accepted_at, item.accession, item.native_fact_id))
    first = ordered[0]
    if len(ordered) > 1 and (
        ordered[1].accepted_at,
        ordered[1].accession,
        ordered[1].native_fact_id,
    ) == (first.accepted_at, first.accession, first.native_fact_id):
        raise ProductionContractError("SEC_FIRST_REPORTED_FACT_AMBIGUOUS")
    return first


@dataclass(frozen=True)
class MassiveSnapshotRecord:
    historical_date: date
    ticker: str
    active: bool
    primary_exchange: str
    type_code: str
    currency: str
    cik: str | None
    composite_figi: str | None
    share_class_figi: str | None
    last_updated_utc: datetime
    evidence_identity: EvidenceIdentity

    def __post_init__(self) -> None:
        _text(self.ticker, "Massive ticker")
        if not isinstance(self.active, bool):
            raise ProductionContractError("Massive active state must be boolean")
        if self.primary_exchange not in MIC_TO_DATABENTO_DATASET:
            raise ProductionContractError("Massive primary exchange is outside Screen v2")
        _text(self.type_code, "Massive type code")
        if self.currency.upper() != "USD":
            raise ProductionContractError("Massive record is not USD")
        if self.cik is not None and not SEC_CIK_RE.fullmatch(self.cik):
            raise ProductionContractError("Massive CIK must be zero-padded")
        _aware(self.last_updated_utc, "Massive last_updated_utc")
        _provider_matches(self.evidence_identity, "MASSIVE", "STOCKS_REFERENCE")

    @property
    def classification(self) -> str:
        if self.type_code in MASSIVE_DIRECT_EXCLUSIONS:
            return MASSIVE_DIRECT_EXCLUSIONS[self.type_code]
        if self.type_code == "CS":
            return "COMMON_STOCK_OPERATING_STATUS_UNRESOLVED"
        return "UNKNOWN_CLASSIFICATION"

    @property
    def screen_eligible_classification(self) -> bool:
        # Screen v2 admits only proven common operating-company equity.  CS alone
        # cannot prove the operating-company, REIT, BDC, or SPAC state.
        return False


@dataclass(frozen=True)
class DatabentoSymbologyInterval:
    dataset: str
    input_symbol: str
    raw_symbol: str
    instrument_id: int
    start_at: datetime
    end_at: datetime
    evidence_identity: EvidenceIdentity

    def __post_init__(self) -> None:
        if self.dataset not in MIC_TO_DATABENTO_DATASET.values():
            raise ProductionContractError("Databento dataset is outside Screen v2")
        _text(self.input_symbol, "symbology input_symbol")
        _text(self.raw_symbol, "symbology raw_symbol")
        if isinstance(self.instrument_id, bool) or self.instrument_id <= 0:
            raise ProductionContractError("instrument_id must be positive")
        _aware(self.start_at, "symbology start_at")
        _aware(self.end_at, "symbology end_at")
        if self.end_at <= self.start_at:
            raise ProductionContractError("symbology interval is inverted")
        _provider_matches(self.evidence_identity, "DATABENTO", self.dataset)

    def effective_at(self, value: datetime) -> bool:
        return self.start_at <= value < self.end_at


@dataclass(frozen=True)
class DatabentoDefinitionRecord:
    dataset: str
    publisher_id: int
    instrument_id: int
    raw_symbol: str
    exchange: str
    security_type: str
    currency: str
    effective_start: datetime
    effective_end: datetime
    evidence_identity: EvidenceIdentity

    def __post_init__(self) -> None:
        if self.dataset != MIC_TO_DATABENTO_DATASET.get(self.exchange):
            raise ProductionContractError("definition dataset/exchange mismatch")
        if self.publisher_id <= 0 or self.instrument_id <= 0:
            raise ProductionContractError("definition native identifiers must be positive")
        for value, label in (
            (self.raw_symbol, "definition raw_symbol"),
            (self.security_type, "definition security_type"),
            (self.currency, "definition currency"),
        ):
            _text(value, label)
        _aware(self.effective_start, "definition effective_start")
        _aware(self.effective_end, "definition effective_end")
        if self.effective_end <= self.effective_start:
            raise ProductionContractError("definition effective interval is inverted")
        _provider_matches(self.evidence_identity, "DATABENTO", self.dataset)

    def effective_at(self, value: datetime) -> bool:
        return self.effective_start <= value < self.effective_end


@dataclass(frozen=True)
class CrosswalkResolution:
    decision_at: datetime
    cik: str
    share_class_figi: str
    massive_ticker: str
    primary_exchange: str
    databento_dataset: str
    databento_raw_symbol: str
    databento_instrument_id: int
    databento_publisher_id: int
    massive_evidence_identity: EvidenceIdentity
    symbology_evidence_identity: EvidenceIdentity
    definition_evidence_identity: EvidenceIdentity
    identity_authority_status: str = "RD-CROSSWALK-001_REQUIRED"
    symbology_effective_start: datetime | None = None
    symbology_effective_end: datetime | None = None
    definition_effective_start: datetime | None = None
    definition_effective_end: datetime | None = None
    # The start of the continuous economic listing lifecycle, not merely the
    # start of the particular definition row observed for this run.  It is
    # stable identity material; the row-level effective intervals above are
    # provenance material.
    listing_lifecycle_start: datetime | None = None


def _continuous_listing_lifecycle_start(
    matched: DatabentoDefinitionRecord,
    definitions: Sequence[DatabentoDefinitionRecord],
) -> datetime:
    """Return the start of the contiguous definition chain containing *matched*.

    A metadata refresh inside one continuous listing must not mint a new
    listing identity.  A true gap, venue transfer, publisher change, dataset
    change, or native-instrument change starts a separate lifecycle.
    """

    same_listing = sorted(
        (
            item for item in definitions
            if item.dataset == matched.dataset
            and item.publisher_id == matched.publisher_id
            and item.instrument_id == matched.instrument_id
            and item.exchange == matched.exchange
        ),
        key=lambda item: (item.effective_start, item.effective_end),
    )
    start = matched.effective_start
    changed = True
    while changed:
        changed = False
        for item in same_listing:
            if item.effective_start < start <= item.effective_end:
                start = item.effective_start
                changed = True
    return start


def resolve_massive_databento_crosswalk(
    massive: MassiveSnapshotRecord,
    mappings: Sequence[DatabentoSymbologyInterval],
    definitions: Sequence[DatabentoDefinitionRecord],
    *,
    decision_at: datetime,
) -> CrosswalkResolution:
    """Resolve a unique date+venue+symbology+definition match, never ticker alone."""

    _aware(decision_at, "decision_at")
    if massive.historical_date != decision_at.date():
        raise ProductionContractError("MASSIVE_SNAPSHOT_DATE_MISMATCH")
    if massive.cik is None:
        raise ProductionContractError("MASSIVE_CIK_MISSING")
    if massive.share_class_figi is None:
        raise ProductionContractError("MASSIVE_SHARE_CLASS_FIGI_MISSING")
    dataset = MIC_TO_DATABENTO_DATASET[massive.primary_exchange]
    effective_mappings = [
        item for item in mappings
        if item.dataset == dataset
        and item.input_symbol == massive.ticker
        and item.effective_at(decision_at)
    ]
    matches: list[tuple[DatabentoSymbologyInterval, DatabentoDefinitionRecord]] = []
    for mapping in effective_mappings:
        for definition in definitions:
            if (
                definition.dataset == dataset
                and definition.exchange == massive.primary_exchange
                and definition.instrument_id == mapping.instrument_id
                and definition.raw_symbol == mapping.raw_symbol
                and definition.effective_at(decision_at)
            ):
                matches.append((mapping, definition))
    if not matches:
        raise ProductionContractError("CROSSWALK_MISSING")
    if len(matches) != 1:
        raise ProductionContractError("CROSSWALK_AMBIGUOUS")
    matched_mapping, definition = matches[0]
    listing_lifecycle_start = _continuous_listing_lifecycle_start(
        definition, definitions
    )
    return CrosswalkResolution(
        decision_at=decision_at,
        cik=massive.cik,
        share_class_figi=massive.share_class_figi,
        massive_ticker=massive.ticker,
        primary_exchange=massive.primary_exchange,
        databento_dataset=dataset,
        databento_raw_symbol=definition.raw_symbol,
        databento_instrument_id=definition.instrument_id,
        databento_publisher_id=definition.publisher_id,
        massive_evidence_identity=massive.evidence_identity,
        symbology_evidence_identity=matched_mapping.evidence_identity,
        definition_evidence_identity=definition.evidence_identity,
        symbology_effective_start=matched_mapping.start_at,
        symbology_effective_end=matched_mapping.end_at,
        definition_effective_start=definition.effective_start,
        definition_effective_end=definition.effective_end,
        listing_lifecycle_start=listing_lifecycle_start,
    )


@dataclass(frozen=True)
class OfficialSessionRecord:
    exchange: str
    session_date: date
    timezone_name: str
    session_open: datetime
    session_close: datetime
    status: str
    early_close: bool
    evidence_identity: EvidenceIdentity

    def __post_init__(self) -> None:
        if self.exchange not in MIC_TO_DATABENTO_DATASET:
            raise ProductionContractError("official session exchange is outside Screen v2")
        _text(self.timezone_name, "session timezone")
        _aware(self.session_open, "session_open")
        _aware(self.session_close, "session_close")
        if self.session_close <= self.session_open:
            raise ProductionContractError("session close must follow open")
        if self.status not in {"COMPLETED", "HOLIDAY", "CANCELLED"}:
            raise ProductionContractError("official session status is closed")
        if self.status != "COMPLETED" and self.early_close:
            raise ProductionContractError("non-completed session cannot be early close")
        if self.evidence_identity.provider != "OFFICIAL_EXCHANGE_CALENDAR":
            raise ProductionContractError("session requires official exchange evidence")


@dataclass(frozen=True)
class DatabentoSessionMarker:
    dataset: str
    exchange: str
    marker_type: str
    ts_event: datetime
    publisher_id: int
    evidence_identity: EvidenceIdentity

    def __post_init__(self) -> None:
        if self.dataset != MIC_TO_DATABENTO_DATASET.get(self.exchange):
            raise ProductionContractError("session marker dataset/exchange mismatch")
        if self.marker_type not in {"OPEN", "CLOSE"}:
            raise ProductionContractError("session marker type is closed")
        _aware(self.ts_event, "session marker ts_event")
        if self.publisher_id <= 0:
            raise ProductionContractError("session marker publisher is invalid")
        _provider_matches(self.evidence_identity, "DATABENTO", self.dataset)


def validate_session_markers(
    session: OfficialSessionRecord,
    markers: Sequence[DatabentoSessionMarker],
) -> None:
    if session.status != "COMPLETED":
        raise ProductionContractError("DATABENTO_MARKERS_REQUIRE_COMPLETED_SESSION")
    expected = {"OPEN": session.session_open, "CLOSE": session.session_close}
    for marker_type, timestamp in expected.items():
        matches = [
            item for item in markers
            if item.exchange == session.exchange
            and item.marker_type == marker_type
            and item.ts_event == timestamp
        ]
        if len(matches) != 1:
            raise ProductionContractError(f"DATABENTO_SESSION_{marker_type}_MISMATCH")


@dataclass(frozen=True)
class DatabentoCloseStatistic:
    dataset: str
    publisher_id: int
    instrument_id: int
    ts_event: datetime
    ts_recv: datetime
    ts_ref: datetime | None
    price_nanos: int
    stat_type: int
    update_action: int
    sequence: int
    evidence_identity: EvidenceIdentity

    def __post_init__(self) -> None:
        if self.dataset not in MIC_TO_DATABENTO_DATASET.values():
            raise ProductionContractError("close statistic dataset is outside Screen v2")
        for value, label in (
            (self.ts_event, "statistics ts_event"),
            (self.ts_recv, "statistics ts_recv"),
        ):
            _aware(value, label)
        if self.ts_ref is not None:
            _aware(self.ts_ref, "statistics ts_ref")
        if self.publisher_id <= 0 or self.instrument_id <= 0 or self.sequence < 0:
            raise ProductionContractError("statistics native identity is invalid")
        if self.stat_type != 11:
            raise ProductionContractError("RAW_CLOSE_REQUIRES_CLOSE_STAT_TYPE_11")
        if self.update_action not in {1, 2}:
            raise ProductionContractError("statistics update_action is unsupported")
        if self.price_nanos in {DBN_UNDEF_PRICE, -DBN_UNDEF_PRICE} or self.price_nanos <= 0:
            raise ProductionContractError("statistics close price is undefined")
        _provider_matches(self.evidence_identity, "DATABENTO", self.dataset)

    @property
    def closing_event_at(self) -> datetime:
        # Databento does not require ts_ref for close statistic type 11.  When
        # the venue supplies no reference timestamp, ts_event is authoritative.
        return self.ts_ref if self.ts_ref is not None else self.ts_event


@dataclass(frozen=True)
class ResolvedPrimaryClose:
    listing_instrument_id: int
    session_date: date
    price: float
    currency: str
    source_sequence: int
    evidence_identity: EvidenceIdentity


def resolve_raw_primary_close(
    crosswalk: CrosswalkResolution,
    session: OfficialSessionRecord,
    statistics: Sequence[DatabentoCloseStatistic],
) -> ResolvedPrimaryClose:
    if session.exchange != crosswalk.primary_exchange:
        raise ProductionContractError("RAW_CLOSE_WRONG_PRIMARY_VENUE")
    if session.status != "COMPLETED":
        raise ProductionContractError("RAW_CLOSE_REQUIRES_COMPLETED_SESSION")
    relevant = [
        item for item in statistics
        if item.dataset == crosswalk.databento_dataset
        and item.publisher_id == crosswalk.databento_publisher_id
        and item.instrument_id == crosswalk.databento_instrument_id
        and session.session_open <= item.closing_event_at <= session.session_close
    ]
    if any(item.update_action == 2 for item in relevant):
        raise ProductionContractError("RAW_PRIMARY_CLOSE_DELETION_PRESENT")
    active = [
        item for item in relevant if item.update_action == 1
    ]
    if not active:
        raise ProductionContractError("RAW_PRIMARY_CLOSE_MISSING")
    if len(active) != 1:
        raise ProductionContractError("RAW_PRIMARY_CLOSE_AMBIGUOUS")
    item = active[0]
    return ResolvedPrimaryClose(
        listing_instrument_id=item.instrument_id,
        session_date=session.session_date,
        price=item.price_nanos / 1_000_000_000,
        currency="USD",
        source_sequence=item.sequence,
        evidence_identity=item.evidence_identity,
    )


@dataclass(frozen=True)
class DatabentoTradeRecord:
    dataset: str
    publisher_id: int
    instrument_id: int
    ts_event: datetime
    ts_recv: datetime
    sequence: int
    size: int
    action: str
    condition_codes: tuple[str, ...]
    is_auction: bool
    correction_state: str
    evidence_identity: EvidenceIdentity

    def __post_init__(self) -> None:
        if self.dataset not in MIC_TO_DATABENTO_DATASET.values():
            raise ProductionContractError("trade dataset is outside Screen v2")
        _aware(self.ts_event, "trade ts_event")
        _aware(self.ts_recv, "trade ts_recv")
        if self.publisher_id <= 0 or self.instrument_id <= 0 or self.sequence < 0:
            raise ProductionContractError("trade native identity is invalid")
        if self.size <= 0 or self.action != "T":
            raise ProductionContractError("raw-volume input must be a positive trade")
        if not isinstance(self.is_auction, bool):
            raise ProductionContractError("trade auction marker must be boolean")
        if self.correction_state not in {"ORIGINAL", "CANCEL", "CORRECT"}:
            raise ProductionContractError("trade correction state is unsupported")
        _provider_matches(self.evidence_identity, "DATABENTO", self.dataset)


@dataclass(frozen=True)
class RawVolumePolicy:
    authority_identity: str
    included_condition_codes: frozenset[str]
    excluded_condition_codes: frozenset[str]
    include_auction_prints: bool
    correction_behavior: str
    source_semantics: str = "DATABENTO_PROP_FEED_NO_TRADE_CONDITIONS"

    def __post_init__(self) -> None:
        _text(self.authority_identity, "raw-volume authority identity")
        if self.included_condition_codes & self.excluded_condition_codes:
            raise ProductionContractError("trade-condition policy overlaps")
        if self.source_semantics != "DATABENTO_PROP_FEED_NO_TRADE_CONDITIONS":
            raise ProductionContractError("raw-volume source semantics are unresolved")
        if self.included_condition_codes or self.excluded_condition_codes:
            raise ProductionContractError(
                "Databento direct equity feeds do not supply trade-condition codes"
            )
        if self.include_auction_prints is not True:
            raise ProductionContractError("raw primary-session volume includes auction prints")
        if self.correction_behavior != "FAIL_ON_CANCEL_OR_CORRECTION":
            raise ProductionContractError("raw-volume correction behavior is unresolved")


@dataclass(frozen=True)
class ResolvedPrimaryVolume:
    listing_instrument_id: int
    session_date: date
    volume: int
    source_sequences: tuple[int, ...]
    source_evidence_ids: tuple[str, ...]
    policy_authority_identity: str


def resolve_raw_primary_volume(
    crosswalk: CrosswalkResolution,
    session: OfficialSessionRecord,
    trades: Sequence[DatabentoTradeRecord],
    *,
    policy: RawVolumePolicy,
) -> ResolvedPrimaryVolume:
    if session.exchange != crosswalk.primary_exchange:
        raise ProductionContractError("RAW_VOLUME_WRONG_PRIMARY_VENUE")
    if session.status != "COMPLETED":
        raise ProductionContractError("RAW_VOLUME_REQUIRES_COMPLETED_SESSION")
    selected = [
        item for item in trades
        if item.dataset == crosswalk.databento_dataset
        and item.publisher_id == crosswalk.databento_publisher_id
        and item.instrument_id == crosswalk.databento_instrument_id
        and session.session_open <= item.ts_event <= session.session_close
    ]
    if not selected:
        raise ProductionContractError("RAW_PRIMARY_VOLUME_MISSING")
    sequences = [item.sequence for item in selected]
    if len(sequences) != len(set(sequences)):
        raise ProductionContractError("RAW_VOLUME_DUPLICATE_SEQUENCE")
    total = 0
    for item in selected:
        if item.correction_state != "ORIGINAL":
            raise ProductionContractError("RAW_VOLUME_CORRECTION_REQUIRES_PROVIDER_RULE")
        if item.condition_codes:
            raise ProductionContractError("RAW_VOLUME_UNDOCUMENTED_TRADE_CONDITION")
        total += item.size
    if total <= 0:
        raise ProductionContractError("RAW_PRIMARY_VOLUME_EMPTY_AFTER_POLICY")
    included = [
        item for item in selected
        if not item.condition_codes
    ]
    return ResolvedPrimaryVolume(
        listing_instrument_id=crosswalk.databento_instrument_id,
        session_date=session.session_date,
        volume=total,
        source_sequences=tuple(sorted(item.sequence for item in included)),
        source_evidence_ids=tuple(sorted({item.evidence_identity.evidence_id for item in included})),
        policy_authority_identity=policy.authority_identity,
    )


@dataclass(frozen=True)
class ClassSharesObservation:
    issuer_id: str
    security_id: str
    share_class_figi: str
    observation_date: date
    public_availability_at: datetime
    shares: float
    accession: str
    evidence_identity: EvidenceIdentity

    def __post_init__(self) -> None:
        for value, label in (
            (self.issuer_id, "issuer_id"), (self.security_id, "security_id"),
            (self.share_class_figi, "share_class_figi"), (self.accession, "accession"),
        ):
            _text(value, label)
        _aware(self.public_availability_at, "shares public_availability_at")
        if not SEC_ACCESSION_RE.fullmatch(self.accession):
            raise ProductionContractError("shares accession format is invalid")
        if isinstance(self.shares, bool) or not math.isfinite(float(self.shares)) or self.shares <= 0:
            raise ProductionContractError("shares must be finite and positive")
        _provider_matches(self.evidence_identity, "SEC_EDGAR", "FILING_ARCHIVE")


@dataclass(frozen=True)
class ClassMarketValue:
    issuer_id: str
    security_id: str
    decision_cutoff: datetime
    raw_primary_close_usd: float
    shares: ClassSharesObservation | None


def total_market_capitalization(classes: Sequence[ClassMarketValue]) -> float:
    if not classes:
        raise ProductionContractError("MARKET_CAP_CLASSES_MISSING")
    issuer_ids = {item.issuer_id for item in classes}
    decision_cutoffs = {item.decision_cutoff for item in classes}
    security_ids = [item.security_id for item in classes]
    if (
        len(issuer_ids) != 1
        or len(decision_cutoffs) != 1
        or len(security_ids) != len(set(security_ids))
    ):
        raise ProductionContractError("MARKET_CAP_CLASS_SET_INVALID")
    total = 0.0
    for item in classes:
        if item.shares is None:
            raise ProductionContractError("MARKET_CAP_CLASS_SHARES_MISSING")
        if item.shares.issuer_id != item.issuer_id or item.shares.security_id != item.security_id:
            raise ProductionContractError("MARKET_CAP_CLASS_CROSSWALK_MISMATCH")
        _aware(item.decision_cutoff, "market-cap decision_cutoff")
        if item.shares.observation_date > item.decision_cutoff.date():
            raise ProductionContractError("MARKET_CAP_SHARES_FROM_FUTURE")
        if item.shares.public_availability_at > item.decision_cutoff:
            raise ProductionContractError("MARKET_CAP_SHARES_UNAVAILABLE")
        if not math.isfinite(item.raw_primary_close_usd) or item.raw_primary_close_usd <= 0:
            raise ProductionContractError("MARKET_CAP_CLASS_CLOSE_INVALID")
        total += item.raw_primary_close_usd * item.shares.shares
    return total


@dataclass(frozen=True)
class FinancingComponents:
    short_term_debt: float | None
    long_term_debt: float | None
    preferred_stock: float | None
    noncontrolling_interest: float | None
    common_equity: float | None
    cash_and_short_term_investments: float | None

    def _required(self, *, include_common_equity: bool) -> tuple[float, ...]:
        values = (
            self.short_term_debt, self.long_term_debt, self.preferred_stock,
            self.noncontrolling_interest,
            *((self.common_equity,) if include_common_equity else ()),
            self.cash_and_short_term_investments,
        )
        if any(value is None for value in values):
            raise ProductionContractError("FINANCING_COMPONENT_MISSING")
        parsed = tuple(float(value) for value in values if value is not None)
        if any(not math.isfinite(value) for value in parsed):
            raise ProductionContractError("FINANCING_COMPONENT_NONFINITE")
        nonnegative = (
            self.short_term_debt, self.long_term_debt, self.preferred_stock,
            self.noncontrolling_interest, self.cash_and_short_term_investments,
        )
        if any(value is not None and value < 0 for value in nonnegative):
            raise ProductionContractError("FINANCING_COMPONENT_NEGATIVE")
        return parsed


def enterprise_value(total_market_capitalization_usd: float, components: FinancingComponents) -> float:
    if not math.isfinite(total_market_capitalization_usd):
        raise ProductionContractError("TOTAL_MARKET_CAP_NONFINITE")
    short, long, preferred, nci, cash = components._required(include_common_equity=False)
    return total_market_capitalization_usd + short + long + preferred + nci - cash


def invested_capital(components: FinancingComponents) -> float:
    short, long, preferred, nci, common, cash = components._required(include_common_equity=True)
    return short + long + preferred + nci + common - cash


def require_spac_boundary(boundary: date | None) -> date:
    if boundary is None:
        raise ProductionContractError("SPAC_POST_COMBINATION_BOUNDARY_MISSING")
    return boundary
