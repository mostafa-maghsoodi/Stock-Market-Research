"""Non-governing deterministic closure contracts for the Screen v2 first run.

The constants in this module are proposed policy semantics.  They are code and
test material only: they do not admit provider evidence, populate the production
authority map, or create a CandidateSet.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum
import hashlib
import math
from typing import Mapping, Sequence

from .governance import canonical_json
from .production import EvidenceIdentity, ProductionContractError
from .topology import (
    CrosswalkResolution,
    MassiveSnapshotRecord,
    OfficialSessionRecord,
    SecFilingFact,
    select_first_reported_sec_fact,
)


FIRST_RUN_DECISION_DATE = date(2025, 6, 30)
INITIAL_VALIDATION_RANGE_RULE = (
    "EXACT_126_COMPLETED_PRIMARY_MARKET_SESSIONS_IMMEDIATELY_PRECEDING_"
    "AND_INCLUDING_THE_2025_06_30_DECISION_SESSION"
)


class DecisionState(str, Enum):
    READY_TO_ADOPT = "READY_TO_ADOPT"
    NEEDS_EXACT_PROVIDER_EVIDENCE = "NEEDS_EXACT_PROVIDER_EVIDENCE"
    TECHNICALLY_UNRESOLVED = "TECHNICALLY_UNRESOLVED"
    NO_LONGER_REQUIRED = "NO_LONGER_REQUIRED"


@dataclass(frozen=True)
class SecMappingRule:
    canonical_concept: str
    allowed_xbrl_concepts: tuple[str, ...]
    priority: tuple[str, ...]
    period_type: str
    unit: str
    sign_convention: str
    dimension_requirements: str
    derivation_allowed: bool
    derivation_formula: str | None
    ambiguity_behavior: str
    missing_behavior: str

    def __post_init__(self) -> None:
        if not self.canonical_concept or not self.allowed_xbrl_concepts:
            raise ProductionContractError("SEC mapping rule requires exact concepts")
        if self.priority != self.allowed_xbrl_concepts:
            raise ProductionContractError("SEC mapping priority must be complete and exact")
        if self.period_type not in {"DURATION", "INSTANT"}:
            raise ProductionContractError("SEC mapping period type is closed")
        if self.unit not in {"USD", "SHARES"}:
            raise ProductionContractError("SEC mapping unit is closed")
        if self.derivation_allowed != (self.derivation_formula is not None):
            raise ProductionContractError("SEC mapping derivation flag/formula mismatch")
        if self.ambiguity_behavior != "UNAVAILABLE":
            raise ProductionContractError("SEC mapping ambiguity must fail closed")
        if self.missing_behavior != "UNAVAILABLE":
            raise ProductionContractError("SEC mapping missing behavior must fail closed")


def _sec_rule(
    canonical: str,
    concepts: tuple[str, ...],
    period_type: str,
    unit: str,
    sign: str,
    dimensions: str,
    formula: str | None = None,
) -> SecMappingRule:
    return SecMappingRule(
        canonical, concepts, concepts, period_type, unit, sign, dimensions,
        formula is not None, formula, "UNAVAILABLE", "UNAVAILABLE",
    )


# Closed proposal.  Priority does not assert semantic equivalence: the first
# available exact tag may be used only when no other allowed tag yields a
# conflicting fact for the same governed context.  Conflicts are unavailable.
SEC_FIRST_RUN_MAPPING_CONTRACT: Mapping[str, SecMappingRule] = {
    item.canonical_concept: item
    for item in (
        _sec_rule("revenue", (
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:Revenues", "us-gaap:SalesRevenueNet",
        ), "DURATION", "USD", "REPORTED_SIGN", "CONSOLIDATED_NO_SEGMENT_DIMENSIONS"),
        _sec_rule("gross_profit", ("us-gaap:GrossProfit",), "DURATION", "USD",
                  "REPORTED_SIGN", "CONSOLIDATED_NO_SEGMENT_DIMENSIONS"),
        _sec_rule("operating_income", ("us-gaap:OperatingIncomeLoss",), "DURATION", "USD",
                  "REPORTED_SIGN", "CONSOLIDATED_NO_SEGMENT_DIMENSIONS"),
        _sec_rule("operating_cash_flow", (
            "us-gaap:NetCashProvidedByUsedInOperatingActivities",
        ), "DURATION", "USD", "REPORTED_SIGN", "CONSOLIDATED_NO_SEGMENT_DIMENSIONS"),
        _sec_rule("capital_expenditures", (
            "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
        ), "DURATION", "USD", "POSITIVE_OUTFLOW", "CONSOLIDATED_NO_SEGMENT_DIMENSIONS"),
        _sec_rule("total_assets", ("us-gaap:Assets",), "INSTANT", "USD",
                  "NONNEGATIVE_BALANCE", "CONSOLIDATED_NO_SEGMENT_DIMENSIONS"),
        _sec_rule("income_before_tax", (
            "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ), "DURATION", "USD", "REPORTED_SIGN", "CONSOLIDATED_NO_SEGMENT_DIMENSIONS"),
        _sec_rule("income_tax_expense", ("us-gaap:IncomeTaxExpenseBenefit",),
                  "DURATION", "USD", "REPORTED_SIGN", "CONSOLIDATED_NO_SEGMENT_DIMENSIONS"),
        _sec_rule("short_term_debt", (
            "us-gaap:ShortTermBorrowings", "us-gaap:LongTermDebtCurrent",
        ), "INSTANT", "USD", "NONNEGATIVE_BALANCE", "CONSOLIDATED_NO_SEGMENT_DIMENSIONS",
                  "SUM_EXACT_NONOVERLAPPING_COMPONENTS"),
        _sec_rule("long_term_debt", ("us-gaap:LongTermDebtNoncurrent",),
                  "INSTANT", "USD", "NONNEGATIVE_BALANCE", "CONSOLIDATED_NO_SEGMENT_DIMENSIONS"),
        _sec_rule("preferred_stock", (
            "us-gaap:PreferredStockValue", "us-gaap:PreferredStockValueOutstanding",
        ), "INSTANT", "USD", "NONNEGATIVE_BALANCE", "CONSOLIDATED_NO_CLASS_DIMENSIONS"),
        _sec_rule("noncontrolling_interest", (
            "us-gaap:NoncontrollingInterestInConsolidatedEntity", "us-gaap:MinorityInterest",
        ), "INSTANT", "USD", "NONNEGATIVE_BALANCE", "CONSOLIDATED_NO_SEGMENT_DIMENSIONS"),
        _sec_rule("common_equity", ("us-gaap:StockholdersEquity",), "INSTANT", "USD",
                  "REPORTED_SIGN", "PARENT_STOCKHOLDERS_NO_CLASS_DIMENSIONS"),
        _sec_rule("cash_and_short_term_investments", (
            "us-gaap:CashAndCashEquivalentsAtCarryingValue", "us-gaap:ShortTermInvestments",
        ), "INSTANT", "USD", "NONNEGATIVE_BALANCE", "CONSOLIDATED_NO_SEGMENT_DIMENSIONS",
                  "SUM_EXACT_NONOVERLAPPING_COMPONENTS"),
        _sec_rule("class_shares_outstanding", (
            "dei:EntityCommonStockSharesOutstanding",
        ), "INSTANT", "SHARES", "POSITIVE_COUNT", "EXACT_STOCK_CLASS_DIMENSION_REQUIRED"),
    )
}


def adopt_sec_acceptance_availability(
    fact: SecFilingFact,
    *,
    authority_identity: str,
) -> SecFilingFact:
    """Use EDGAR acceptance as the governed availability time.

    This proves the EDGAR receipt/acceptance time.  It deliberately does not
    claim to be the first timestamp at which the public web page was observable.
    """

    if not authority_identity.strip():
        raise ProductionContractError("SEC availability authority identity is required")
    if fact.public_availability_at not in {None, fact.accepted_at}:
        raise ProductionContractError("SEC availability conflicts with acceptance policy")
    return replace(fact, public_availability_at=fact.accepted_at)


def validate_sec_mapping_fact(
    fact: SecFilingFact,
    *,
    canonical_concept: str,
    dimensions_class: str,
) -> None:
    rule = SEC_FIRST_RUN_MAPPING_CONTRACT.get(canonical_concept)
    if rule is None:
        raise ProductionContractError("SEC_CANONICAL_CONCEPT_UNMAPPED")
    if fact.xbrl_concept not in rule.allowed_xbrl_concepts:
        raise ProductionContractError("SEC_EXTENSION_OR_UNAPPROVED_CONCEPT")
    unit = fact.unit.upper()
    unit = {"ISO4217:USD": "USD", "XBRLI:SHARES": "SHARES"}.get(unit, unit)
    if unit != rule.unit:
        raise ProductionContractError("SEC_CANONICAL_UNIT_MISMATCH")
    actual_period = "DURATION" if fact.period_start is not None else "INSTANT"
    if actual_period != rule.period_type:
        raise ProductionContractError("SEC_PERIOD_TYPE_MISMATCH")
    if dimensions_class != rule.dimension_requirements:
        raise ProductionContractError("SEC_DIMENSION_SCOPE_MISMATCH")


def select_closed_sec_mapping_fact(
    facts: Sequence[SecFilingFact],
    *,
    canonical_concept: str,
    cik: str,
    decision_cutoff: datetime,
    period_start: date | None,
    period_end: date,
    dimensions_digest: str,
    dimensions_class: str,
) -> SecFilingFact:
    rule = SEC_FIRST_RUN_MAPPING_CONTRACT.get(canonical_concept)
    if rule is None or rule.derivation_allowed:
        raise ProductionContractError("SEC_MAPPING_REQUIRES_COMPONENT_RESOLUTION")
    resolved: list[SecFilingFact] = []
    for concept in rule.priority:
        try:
            item = select_first_reported_sec_fact(
                facts, cik=cik, decision_cutoff=decision_cutoff,
                xbrl_concept=concept, unit=rule.unit,
                period_start=period_start, period_end=period_end,
                dimensions_digest=dimensions_digest,
            )
        except ProductionContractError as exc:
            if str(exc) != "SEC_FIRST_REPORTED_FACT_MISSING":
                raise
            continue
        validate_sec_mapping_fact(
            item, canonical_concept=canonical_concept,
            dimensions_class=dimensions_class,
        )
        resolved.append(item)
    if not resolved:
        raise ProductionContractError("SEC_CLOSED_MAPPING_UNAVAILABLE")
    if any(item.value != resolved[0].value for item in resolved[1:]):
        raise ProductionContractError("SEC_CLOSED_MAPPING_AMBIGUOUS")
    return resolved[0]


class ComponentEvidenceState(str, Enum):
    EXPLICIT_VALUE = "EXPLICIT_VALUE"
    EXPLICIT_ZERO = "EXPLICIT_ZERO"
    STRUCTURALLY_NOT_APPLICABLE = "STRUCTURALLY_NOT_APPLICABLE"
    MISSING_UNKNOWN = "MISSING_UNKNOWN"


@dataclass(frozen=True)
class FinancingComponentValue:
    component_id: str
    state: ComponentEvidenceState
    value_usd: float | None
    evidence_identity: EvidenceIdentity | None
    structural_rule_id: str | None = None

    def resolved_value(self) -> float:
        if self.state is ComponentEvidenceState.MISSING_UNKNOWN:
            raise ProductionContractError(f"FINANCING_COMPONENT_UNKNOWN:{self.component_id}")
        if self.state is ComponentEvidenceState.STRUCTURALLY_NOT_APPLICABLE:
            if self.value_usd not in {None, 0, 0.0} or not self.structural_rule_id:
                raise ProductionContractError("structural non-applicability requires exact evidence rule")
            if self.evidence_identity is None:
                raise ProductionContractError("structural non-applicability lacks evidence")
            allowed_structural_rules = {
                "preferred_stock": "NO_PREFERRED_SECURITY_AND_NO_PREFERRED_EQUITY_FACT",
                "noncontrolling_interest": "NO_CONSOLIDATED_NCI_PRESENTATION_OR_FACT",
            }
            if allowed_structural_rules.get(self.component_id) != self.structural_rule_id:
                raise ProductionContractError("structural non-applicability rule is not closed")
            return 0.0
        if self.value_usd is None or self.evidence_identity is None:
            raise ProductionContractError("explicit financing component lacks evidence/value")
        value = float(self.value_usd)
        if not math.isfinite(value):
            raise ProductionContractError("financing component is nonfinite")
        if self.state is ComponentEvidenceState.EXPLICIT_ZERO and value != 0:
            raise ProductionContractError("explicit-zero component is nonzero")
        if self.state is ComponentEvidenceState.EXPLICIT_VALUE and value < 0 and self.component_id != "common_equity":
            raise ProductionContractError("financing component is negative")
        return value


@dataclass(frozen=True)
class ClosedFinancingComponents:
    short_term_debt: FinancingComponentValue
    long_term_debt: FinancingComponentValue
    preferred_stock: FinancingComponentValue
    noncontrolling_interest: FinancingComponentValue
    common_equity: FinancingComponentValue
    cash_and_short_term_investments: FinancingComponentValue

    def values(self) -> Mapping[str, float]:
        return {
            name: getattr(self, name).resolved_value()
            for name in (
                "short_term_debt", "long_term_debt", "preferred_stock",
                "noncontrolling_interest", "common_equity",
                "cash_and_short_term_investments",
            )
        }


def closed_enterprise_value(total_market_capitalization_usd: float, components: ClosedFinancingComponents) -> float:
    values = components.values()
    if not math.isfinite(total_market_capitalization_usd) or total_market_capitalization_usd < 0:
        raise ProductionContractError("TOTAL_MARKET_CAP_INVALID")
    return (
        total_market_capitalization_usd + values["short_term_debt"]
        + values["long_term_debt"] + values["preferred_stock"]
        + values["noncontrolling_interest"] - values["cash_and_short_term_investments"]
    )


def closed_invested_capital(components: ClosedFinancingComponents) -> float:
    values = components.values()
    return (
        values["short_term_debt"] + values["long_term_debt"]
        + values["preferred_stock"] + values["noncontrolling_interest"]
        + values["common_equity"] - values["cash_and_short_term_investments"]
    )


@dataclass(frozen=True)
class ZeroGapSessionPolicy:
    authority_identity: str
    age_metric: str = "COMPLETED_SESSION_COUNT"
    maximum_age: int = 0
    policy: str = "STRICT_ZERO_GAP"

    def __post_init__(self) -> None:
        if not self.authority_identity.strip():
            raise ProductionContractError("session authority identity is required")
        if (self.age_metric, self.maximum_age, self.policy) != (
            "COMPLETED_SESSION_COUNT", 0, "STRICT_ZERO_GAP"
        ):
            raise ProductionContractError("session staleness policy is not strict zero-gap")


def require_prior_completed_session_observation(
    sessions: Sequence[OfficialSessionRecord],
    *,
    decision_date: date,
    observation_session_date: date | None,
    exchange: str,
    policy: ZeroGapSessionPolicy,
) -> OfficialSessionRecord:
    del policy
    prior = sorted(
        (
            item for item in sessions
            if item.exchange == exchange
            and item.status == "COMPLETED"
            and item.session_date < decision_date
        ),
        key=lambda item: item.session_date,
    )
    if not prior:
        raise ProductionContractError("PRIOR_COMPLETED_SESSION_MISSING")
    expected = prior[-1]
    if observation_session_date is None:
        raise ProductionContractError("PRIOR_SESSION_OBSERVATION_MISSING")
    if observation_session_date != expected.session_date:
        raise ProductionContractError("STRICT_ZERO_GAP_STALENESS_VIOLATION")
    return expected


@dataclass(frozen=True)
class CorporateActionTreatment:
    action_type: str
    issuer_continuity: str
    security_continuity: str
    listing_continuity: str
    effective_timestamp_rule: str
    missing_or_ambiguous_behavior: str = "UNAVAILABLE"


RD_014_CORPORATE_ACTION_CONTRACT: Mapping[str, CorporateActionTreatment] = {
    item.action_type: item
    for item in (
        CorporateActionTreatment("TICKER_CHANGE", "PRESERVE_IF_CIK_MATCHES", "PRESERVE_IF_SHARE_CLASS_FIGI_MATCHES", "PRESERVE_IF_MIC_AND_NATIVE_INSTRUMENT_MATCH", "MASSIVE_EVENT_DATE_PLUS_EFFECTIVE_DATABENTO_SYMBOLOGY"),
        CorporateActionTreatment("SPLIT", "PRESERVE", "PRESERVE", "PRESERVE", "MASSIVE_EXECUTION_DATE_SESSION_OPEN"),
        CorporateActionTreatment("REVERSE_SPLIT", "PRESERVE", "PRESERVE", "PRESERVE", "MASSIVE_EXECUTION_DATE_SESSION_OPEN"),
        CorporateActionTreatment("MERGER", "REQUIRE_EXACT_SUCCESSOR_CIK_EVIDENCE", "NEW_UNLESS_EXACT_LEGAL_CONTINUITY", "NEW", "SEC_COMPLETION_ACCESSION_AND_EFFECTIVE_TIME"),
        CorporateActionTreatment("SPINOFF", "NEW_SPUN_ISSUER", "NEW", "NEW", "SEC_COMPLETION_ACCESSION_AND_EFFECTIVE_TIME"),
        CorporateActionTreatment("DELISTING", "PRESERVE", "PRESERVE", "TERMINATE", "MASSIVE_DELISTED_UTC_CORROBORATED_BY_DATABENTO_DEFINITION_END"),
        CorporateActionTreatment("EXCHANGE_TRANSFER", "PRESERVE_IF_CIK_MATCHES", "PRESERVE_IF_SHARE_CLASS_FIGI_MATCHES", "NEW", "NEW_MIC_DEFINITION_EFFECTIVE_START"),
        CorporateActionTreatment("SPAC_BUSINESS_COMBINATION", "REQUIRE_POST_COMBINATION_CIK_EVIDENCE", "NEW_UNLESS_EXACT_LEGAL_CONTINUITY", "NEW", "FIRST_OFFICIAL_SESSION_OPEN_STRICTLY_AFTER_MAX_SEC_ACCEPTANCE_AND_DECLARED_EFFECTIVE_TIME"),
    )
}


@dataclass(frozen=True)
class SpacCombinationEvidence:
    cik: str
    accession: str
    accepted_at: datetime
    declared_effective_at: datetime
    form_type: str
    item_2_01_completion: bool
    predecessor_was_shell_company: bool
    evidence_identity: EvidenceIdentity

    def __post_init__(self) -> None:
        if self.form_type not in {"8-K", "8-K/A"}:
            raise ProductionContractError("SPAC boundary requires Form 8-K")
        if not self.item_2_01_completion or not self.predecessor_was_shell_company:
            raise ProductionContractError("SPAC boundary lacks Item 2.01 shell completion evidence")
        if self.accepted_at.tzinfo is None or self.declared_effective_at.tzinfo is None:
            raise ProductionContractError("SPAC timestamps must be aware")
        if self.evidence_identity.provider != "SEC_EDGAR":
            raise ProductionContractError("SPAC boundary requires SEC evidence")


def resolve_spac_post_combination_boundary(
    evidence: SpacCombinationEvidence,
    sessions: Sequence[OfficialSessionRecord],
    *,
    exchange: str,
) -> datetime:
    threshold = max(evidence.accepted_at, evidence.declared_effective_at)
    candidates = sorted(
        item.session_open for item in sessions
        if item.exchange == exchange and item.status == "COMPLETED" and item.session_open > threshold
    )
    if not candidates:
        raise ProductionContractError("SPAC_POST_COMBINATION_SESSION_MISSING")
    return candidates[0]


@dataclass(frozen=True)
class ClassificationEvidence:
    massive_type_code: str
    massive_type_description: str
    massive_type_evidence_identity: EvidenceIdentity
    common_stock_proven: bool
    registered_investment_company: bool | None
    bdc_election_effective: bool | None
    reit_status_effective: bool | None
    shell_company_effective: bool | None
    exclusion_evidence_identities: tuple[EvidenceIdentity, ...]


def classify_operating_company(evidence: ClassificationEvidence) -> str:
    if not evidence.massive_type_code or not evidence.massive_type_description:
        return "UNKNOWN_CLASSIFICATION"
    if not evidence.common_stock_proven:
        return "INELIGIBLE_NON_COMMON"
    exclusion_values = (
        evidence.registered_investment_company, evidence.bdc_election_effective,
        evidence.reit_status_effective, evidence.shell_company_effective,
    )
    if any(value is None for value in exclusion_values):
        return "UNKNOWN_CLASSIFICATION"
    if any(exclusion_values):
        return "INELIGIBLE_EXCLUDED_CLASS"
    if not evidence.exclusion_evidence_identities:
        return "UNKNOWN_CLASSIFICATION"
    return "ELIGIBLE_COMMON_OPERATING_COMPANY"


@dataclass(frozen=True)
class SecClassSharesEvidence:
    fact: SecFilingFact
    security_id: str
    share_class_figi: str
    exact_class_dimension_digest: str
    class_crosswalk_evidence_identity: EvidenceIdentity


def resolve_pit_class_shares(item: SecClassSharesEvidence, *, decision_cutoff: datetime) -> float:
    fact = item.fact
    if fact.xbrl_concept != "dei:EntityCommonStockSharesOutstanding":
        raise ProductionContractError("PIT_SHARES_WRONG_CONCEPT")
    if fact.unit.upper() != "SHARES" or fact.instant_date is None:
        raise ProductionContractError("PIT_SHARES_REQUIRE_INSTANT_NATIVE_SHARES")
    if fact.dimensions_digest != item.exact_class_dimension_digest:
        raise ProductionContractError("PIT_SHARES_CLASS_DIMENSION_MISMATCH")
    if fact.public_availability_at is None or fact.public_availability_at > decision_cutoff:
        raise ProductionContractError("PIT_SHARES_NOT_AVAILABLE_AT_CUTOFF")
    if not item.security_id or not item.share_class_figi:
        raise ProductionContractError("PIT_SHARES_CLASS_CROSSWALK_MISSING")
    if not math.isfinite(fact.value) or fact.value <= 0:
        raise ProductionContractError("PIT_SHARES_VALUE_INVALID")
    return float(fact.value)


def normalize_sec_value(*, value: float, xbrl_unit: str, canonical_unit: str) -> float:
    # SEC instance facts contain their complete numeric value; decimals describe
    # precision and are not a scale factor.  Only exact native unit matches pass.
    normalized = xbrl_unit.upper()
    expected = canonical_unit.upper()
    aliases = {"ISO4217:USD": "USD", "XBRLI:SHARES": "SHARES"}
    normalized = aliases.get(normalized, normalized)
    if normalized != expected:
        if expected == "USD" and normalized not in {"USD"}:
            raise ProductionContractError("NON_USD_ACCOUNTING_FACT_UNAVAILABLE")
        raise ProductionContractError("SEC_UNIT_MISMATCH")
    if not math.isfinite(float(value)):
        raise ProductionContractError("SEC_VALUE_NONFINITE")
    return float(value)


def normalize_databento_price(price_nanos: int, *, definition_currency: str) -> float:
    if definition_currency.upper() != "USD" or price_nanos <= 0:
        raise ProductionContractError("DATABENTO_USD_PRICE_REQUIRED")
    return price_nanos / 1_000_000_000


def normalize_databento_quantity(quantity: int) -> int:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ProductionContractError("DATABENTO_SHARE_QUANTITY_INVALID")
    return quantity


@dataclass(frozen=True)
class InternalListingIdentity:
    issuer_id: str
    security_id: str
    listing_id: str
    canonicalization: str = "RFC8785_EQUIVALENT_REPOSITORY_CANONICAL_JSON"
    digest_algorithm: str = "SHA-256"


def derive_internal_listing_identity(
    resolution: CrosswalkResolution,
    *,
    sec_cik_evidence_identity: EvidenceIdentity,
) -> InternalListingIdentity:
    intervals = (
        resolution.symbology_effective_start, resolution.symbology_effective_end,
        resolution.definition_effective_start, resolution.definition_effective_end,
    )
    if any(value is None for value in intervals):
        raise ProductionContractError("CROSSWALK_EFFECTIVE_INTERVALS_MISSING")
    symbology_start = resolution.symbology_effective_start
    symbology_end = resolution.symbology_effective_end
    definition_start = resolution.definition_effective_start
    definition_end = resolution.definition_effective_end
    assert symbology_start is not None and symbology_end is not None
    assert definition_start is not None and definition_end is not None
    if sec_cik_evidence_identity.provider != "SEC_EDGAR":
        raise ProductionContractError("issuer identity requires SEC CIK evidence")
    issuer_material = {
        "identity_type": "ISSUER", "cik": resolution.cik,
        "massive_evidence_sha256": resolution.massive_evidence_identity.content_sha256,
        "sec_cik_evidence_sha256": sec_cik_evidence_identity.content_sha256,
    }
    issuer_id = hashlib.sha256(canonical_json(issuer_material)).hexdigest()
    security_material = {
        "identity_type": "SECURITY", "issuer_id": issuer_id,
        "share_class_figi": resolution.share_class_figi,
        "massive_evidence_sha256": resolution.massive_evidence_identity.content_sha256,
    }
    security_id = hashlib.sha256(canonical_json(security_material)).hexdigest()
    listing_material = {
        "identity_type": "LISTING", "security_id": security_id,
        "primary_mic": resolution.primary_exchange,
        "databento_dataset": resolution.databento_dataset,
        "databento_instrument_id": resolution.databento_instrument_id,
        "databento_publisher_id": resolution.databento_publisher_id,
        "decision_at": resolution.decision_at.isoformat(),
        "symbology_effective_start": symbology_start.isoformat(),
        "symbology_effective_end": symbology_end.isoformat(),
        "definition_effective_start": definition_start.isoformat(),
        "definition_effective_end": definition_end.isoformat(),
        "symbology_evidence_sha256": resolution.symbology_evidence_identity.content_sha256,
        "definition_evidence_sha256": resolution.definition_evidence_identity.content_sha256,
    }
    listing_id = hashlib.sha256(canonical_json(listing_material)).hexdigest()
    return InternalListingIdentity(issuer_id, security_id, listing_id)


FINAL_DECISION_STATUS: Mapping[str, DecisionState] = {
    "RD-001": DecisionState.NEEDS_EXACT_PROVIDER_EVIDENCE,
    "RD-002A": DecisionState.READY_TO_ADOPT,
    "RD-002B": DecisionState.READY_TO_ADOPT,
    "RD-004": DecisionState.READY_TO_ADOPT,
    "RD-008": DecisionState.READY_TO_ADOPT,
    "RD-013": DecisionState.READY_TO_ADOPT,
    "RD-014": DecisionState.READY_TO_ADOPT,
    "RD-015": DecisionState.READY_TO_ADOPT,
    "RD-016": DecisionState.READY_TO_ADOPT,
    "RD-017": DecisionState.READY_TO_ADOPT,
    "RD-018": DecisionState.READY_TO_ADOPT,
    "RD-019": DecisionState.READY_TO_ADOPT,
    "RD-020": DecisionState.READY_TO_ADOPT,
    "RD-021": DecisionState.READY_TO_ADOPT,
    "RD-022": DecisionState.READY_TO_ADOPT,
    "RD-CROSSWALK-001": DecisionState.READY_TO_ADOPT,
}
