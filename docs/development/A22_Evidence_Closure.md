# A22 technical/evidence closure

Status: **non-governing proposal material**. This document does not admit a
provider, approve a decision, create a ProductionEvidenceManifest, create a
CandidateSet, or authorize outcome access or transactions.

## Official-source boundary

Only official sources were used:

- SEC EDGAR timestamp guidance and APIs:
  https://www.sec.gov/about/webmaster-frequently-asked-questions and
  https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC XBRL Guide and cover-page shares guidance:
  https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide-2026-01-16.pdf and
  https://www.sec.gov/newsroom/whats-new/osd-announcement-2210-dqreminder-entitycommonstocksharesoutstanding
- SEC forms N-CEN and N-54A:
  https://www.sec.gov/submit-filings/forms-index/formn-cen and
  https://www.sec.gov/files/formn-54a.pdf
- Massive historical tickers, ticker types, ticker events, and splits:
  https://massive.com/docs/rest/stocks/tickers/all-tickers,
  https://massive.com/docs/rest/stocks/tickers/ticker-types,
  https://massive.com/docs/rest/stocks/corporate-actions/ticker-events, and
  https://massive.com/docs/rest/stocks/corporate-actions/splits
- Databento statistics, trades, symbology, and venue datasets:
  https://databento.com/docs/schemas-and-data-formats/statistics,
  https://databento.com/docs/schemas-and-data-formats/trades,
  https://databento.com/docs/standards-and-conventions/symbology, and
  https://databento.com/docs/knowledge-base/datasets
- NYSE and Nasdaq official calendars/hours:
  https://www.nyse.com/trade/hours-calendars and
  https://nasdaqtrader.com/Trader.aspx?id=Calendar

No additional provider was selected or investigated.

## Original RD semantic audit

Repository history and the pre-closure `RESEARCHER_DECISIONS` registry establish
the meanings below. “Same” permits a narrower technical implementation without
changing the decision's subject.

| ID | Original meaning | A22 closure meaning | Result | Repair |
|---|---|---|---|---|
| RD-001 | production provider/product topology | exact first-run topology | same | none |
| RD-002A | initial production-validation range | 126-session seasoning window | drifted | restored validation-range meaning |
| RD-002B | first governed decision date | 2025-06-30 candidate | same | none |
| RD-002C | full intended historical range | deferred for first single-date run | same | explicit `NO_LONGER_REQUIRED` for first run |
| RD-004 | native/canonical mappings and field catalog | SEC availability plus exact mapping contract | same/narrowed | none |
| RD-008 | production historical market-data product | Databento close/volume contract | same/narrowed | none |
| RD-013 | missing-session/stale-price bound | strict zero-gap completed-session rule | same/narrowed | none |
| RD-014 | corporate-action continuity/effective events | exact action/SPAC contract | same/narrowed | none |
| RD-015 | PIT shares construction | SEC filing-level class shares | same/narrowed | none |
| RD-016 | total market-cap construction | complete class-summed construction | same/narrowed | none |
| RD-017 | enterprise-value construction | exact component EV | same/narrowed | none |
| RD-018 | historical operating-company taxonomy | positive-evidence classification | same/narrowed | none |
| RD-019 | invested-capital construction | exact component construction | same/narrowed | none |
| RD-020 | denominator-specific near-zero materiality | exact per-denominator thresholds | same/narrowed | none |
| RD-021 | unit/currency normalization | USD/shares/USD-per-share contract | same/narrowed | none |
| RD-022 | CandidateSet evidence identity contract | existing contract preserved | same | none |
| RD-CROSSWALK-001 | unique Massive/Databento crosswalk with stable internal IDs | run/evidence bytes embedded in IDs | drifted from stable-ID architecture | stable IDs separated from provenance |

## RD-004A — SEC availability

Proposed value: `READY_TO_ADOPT`.

```text
SEC_AVAILABLE_AT = exact EDGAR ACCEPTANCE-DATETIME for the accession
ADMISSIBLE = SEC_AVAILABLE_AT <= governed decision cutoff
```

The timestamp proves EDGAR receipt/acceptance. It does not prove the literal
first time the filing was observable on the public website; SEC says no such
timestamp is exposed. The rule is a named, deterministic research cutoff, not a
claim about public-web latency. No additional latency is invented.

## RD-004B — closed SEC mapping contract

Global rules:

- exact QName only; extensions are unavailable without separately admitted
  equivalence evidence;
- annual duration facts require native start and end; instant facts require the
  native instant;
- currency facts require exact `iso4217:USD`; share facts require exact shares;
- consolidated/parent/class dimension scope must equal the rule below;
- priority is evaluated in listed order, but conflicting simultaneous allowed
  facts are `UNAVAILABLE`, not pooled;
- missing is `UNAVAILABLE`;
- no fact-name similarity, value-magnitude unit inference, or retroactive
  restatement substitution.

| Canonical concept | Exact priority | Period/unit/sign | Dimensions | Derivation |
|---|---|---|---|---|
| revenue | `RevenueFromContractWithCustomerExcludingAssessedTax`; `Revenues`; `SalesRevenueNet` | duration/USD/reported | consolidated, no segment | none |
| gross_profit | `GrossProfit` | duration/USD/reported | consolidated, no segment | none |
| operating_income | `OperatingIncomeLoss` | duration/USD/reported | consolidated, no segment | none |
| operating_cash_flow | `NetCashProvidedByUsedInOperatingActivities` | duration/USD/reported | consolidated, no segment | none |
| capital_expenditures | `PaymentsToAcquirePropertyPlantAndEquipment` | duration/USD/positive outflow | consolidated, no segment | none |
| total_assets | `Assets` | instant/USD/nonnegative | consolidated, no segment | none |
| income_before_tax | `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`; then `IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments` | duration/USD/reported | consolidated, no segment | none |
| income_tax_expense | `IncomeTaxExpenseBenefit` | duration/USD/reported | consolidated, no segment | none |
| short_term_debt | `ShortTermBorrowings`; `LongTermDebtCurrent` | instant/USD/nonnegative | consolidated, no segment | sum only exact non-overlapping components |
| long_term_debt | `LongTermDebtNoncurrent` | instant/USD/nonnegative | consolidated, no segment | none |
| preferred_stock | `PreferredStockValue`; `PreferredStockValueOutstanding` | instant/USD/nonnegative | consolidated, no class | none |
| noncontrolling_interest | `NoncontrollingInterestInConsolidatedEntity`; `MinorityInterest` | instant/USD/nonnegative | consolidated, no segment | none |
| common_equity | `StockholdersEquity` | instant/USD/reported | parent stockholders, no class | none |
| cash_and_short_term_investments | `CashAndCashEquivalentsAtCarryingValue`; `ShortTermInvestments` | instant/USD/nonnegative | consolidated, no segment | sum exact non-overlapping components |
| class_shares_outstanding | `dei:EntityCommonStockSharesOutstanding` | instant/shares/positive | exact stock-class dimension | none |

All names in the table are `us-gaap:` except the explicit `dei:` concept.

## RD-008 — Databento primary close and raw volume

Proposed value: `READY_TO_ADOPT`.

### Primary close

- dataset is fixed by primary MIC: `XNAS.ITCH`, `XNYS.PILLAR`, or
  `XASE.PILLAR`;
- require exact publisher/instrument from the governed crosswalk;
- require `statistics.stat_type = 11` and positive finite normalized price;
- require event time in the official core session and at the venue closing
  auction; use `ts_ref` when populated, otherwise `ts_event`;
- `ts_recv` is capture provenance, not the economic event time;
- any delete/correction, multiple active closes, undefined price, wrong venue,
  or missing close makes the observation unavailable;
- no midpoint, consolidated close, or OHLCV fallback.

Databento lists type 11 for all three datasets and documents the Nasdaq and
NYSE-family closing-cross/auction normalization.

### Raw primary-listing volume

Databento direct equity feeds do not supply SIP-style trade-condition codes.
No condition code is invented. The proposed construction is:

```text
SUM(size) over unique final Databento trades-schema records
where dataset/publisher/instrument equal the governed primary listing
and official_core_open <= ts_event <= official_core_close
```

- include regular-session opening and closing auction executions;
- include odd lots because the direct prop feeds include them;
- exclude pre-market and post-market by the official core window;
- late receipt and out-of-sequence arrival are retained based on `ts_event`,
  then deterministically ordered by native sequence/time;
- duplicate native sequence identity fails;
- cancel, correction, break, invalid/incomplete stream, or unresolved native
  replay semantics make the observation unavailable;
- require final archive/completeness evidence;
- do not use `ohlcv-1d`, which is UTC-day based and can embody vendor-specific
  break, timestamp, and block-trade choices.

## RD-013 — session and staleness

Proposed value: `READY_TO_ADOPT`.

```text
age_metric = COMPLETED_SESSION_COUNT
maximum_age = 0
policy = STRICT_ZERO_GAP
```

The observation must be from the immediately prior completed primary-market
session. No carry-forward is allowed. Missing security observation means the
security is unavailable; missing or ambiguous official session evidence fails
the run.

Authority hierarchy:

1. official NYSE calendar/hours for XNYS and XASE;
2. official Nasdaq Trader calendar/hours for XNAS;
3. exchange notices for exceptional cancellation/closure;
4. Databento status/statistics only as corroboration.

Timezone is `America/New_York`. Core hours are 09:30–16:00 ET, or the exact
official early close. Absence of trades never defines a holiday.

## RD-014 — corporate actions and SPAC boundary

Proposed value: `READY_TO_ADOPT`.

| Action | Issuer | Security | Listing | Effective rule | Failure |
|---|---|---|---|---|---|
| ticker change | preserve only exact CIK | preserve only exact share-class FIGI | preserve only exact MIC/native instrument | Massive event plus effective Databento symbology | unavailable |
| split/reverse split | preserve | preserve | preserve | Massive execution-date session open; raw market data is not back-adjusted | unavailable |
| merger | exact successor-CIK evidence | new unless exact legal continuity | new | SEC completion accession/effective time | unavailable |
| spinoff | new spun issuer | new | new | SEC completion accession/effective time | unavailable |
| delisting | preserve | preserve | terminate | Massive delisted time corroborated by Databento definition end | unavailable |
| exchange transfer | preserve only exact CIK | preserve only exact share-class FIGI | new | new-MIC definition effective start | unavailable |
| SPAC combination | require post-combination CIK | new unless exact legal continuity | new | first official session open strictly after the later of exact SEC acceptance and declared effective time | unavailable/ineligible |

Ticker is never identity. Massive's experimental ticker-event endpoint supports
ticker change only and cannot prove mergers or SPAC completion. SPAC completion
requires an exact SEC 8-K/8-K-A accession with Item 2.01 completion and evidence
that the predecessor was a shell company. Missing exact completion/effective
evidence means ineligible.

## RD-015 — PIT class shares

Proposed value: `READY_TO_ADOPT`.

Use only `dei:EntityCommonStockSharesOutstanding` from the exact filing/accession
with CIK, EDGAR acceptance, instant date, native shares unit, reported value,
context/native fact identity, and exact stock-class dimension. Observation
instant and availability time remain separate. Weighted-average shares and
Massive shares are not substitutes. Every eligible class must map uniquely to a
share-class FIGI/security; otherwise that class and issuer market cap are
unavailable.

## RD-017 and RD-019 — EV and invested capital

Proposed values: `READY_TO_ADOPT`.

```text
EV = total market capitalization
   + short-term debt + long-term debt + preferred stock + NCI
   - cash and short-term investments

invested capital = short-term debt + long-term debt + preferred stock + NCI
                 + common equity - cash and short-term investments
```

Current and prior invested capital use the already-governed arithmetic average.
No vendor aggregate field is allowed.

Each component has exactly one state:

- `EXPLICIT_VALUE`: exact mapped fact and evidence;
- `EXPLICIT_ZERO`: exact mapped zero fact and evidence;
- `STRUCTURALLY_NOT_APPLICABLE`: zero only when an approved structural rule and
  exact filing/taxonomy evidence prove absence;
- `MISSING_UNKNOWN`: EV/invested capital unavailable.

Missing is never silently zero. Structural non-applicability must bind the
specific rule and evidence identity.

## RD-018 — operating-company taxonomy

Proposed value: `READY_TO_ADOPT` using positive evidence.

Inclusion requires all of:

1. historically effective Massive type metadata proves common stock;
2. exact PIT CIK/share-class/listing crosswalk;
3. SEC evidence proves no effective registered-investment-company status;
4. no effective N-54A BDC election;
5. no effective REIT status in the admitted filing evidence;
6. no effective shell/pre-combination-SPAC status; and
7. none of ADR, preferred, ETF, mutual fund, closed-end fund, BDC, REIT,
   rights, warrants, units, when-issued, or other non-common state is proven.

Massive codes are interpreted only through exact admitted ticker-type metadata.
Unknown/unproven state is `UNKNOWN_CLASSIFICATION => INELIGIBLE`, consistent
with Screen v2 fail-closed eligibility. No company-name or current-status
heuristic is permitted.

## RD-021 — units and currency

Proposed value: `READY_TO_ADOPT`.

- canonical units: `USD`, `SHARES`, `USD_PER_SHARE`;
- SEC fact units come from native XBRL unit metadata; decimals express precision
  and do not scale the numeric fact;
- first run accepts accounting currency only as exact USD;
- `NON_USD_ACCOUNTING_FACT => UNAVAILABLE`; no FX source is introduced;
- Massive reference fields are not used as accounting amounts;
- Databento price integer units convert at `1e-9` to USD/share only when the
  effective definition currency is USD;
- Databento trade size is shares with no inferred scale.

## RD-CROSSWALK-001

Proposed value: `READY_TO_ADOPT`.

The existing one-and-only-one match remains mandatory. Stable internal identity
and run-specific evidence provenance are separate. Stable identifiers use
repository canonical JSON and lowercase SHA-256:

```text
issuer_id = SHA256({identity_schema=STABLE_ISSUER_ID_V1,
                    issuer_namespace=SEC_CIK, normalized CIK})
security_id = SHA256({identity_schema=STABLE_SECURITY_ID_V1, issuer_id,
                      share_class_namespace=OPENFIGI_SHARE_CLASS,
                      share-class FIGI})
listing_id = SHA256({identity_schema=STABLE_LISTING_ID_V1, security_id,
                     primary MIC, actual governed listing lifecycle start})
```

Decision/acquisition timestamps, raw evidence hashes, manifest/run identity,
observed ticker, provider-native instrument/publisher, and row-level effective
intervals are forbidden stable-ID inputs. They are bound instead by a separate
`CrosswalkEvidenceIdentity`, which also binds the stable IDs, decision time,
exact SEC/Massive/Databento evidence identities, match count, and
canonicalization version. It may legitimately change between runs.

`actual_governed_lifecycle_start` requires exact admitted boundary evidence
under the crosswalk/corporate-action rules. It is explicitly distinct from
`earliest_observed_provider_record`. The latter can be a left-censored provider
coverage boundary and is provenance only. If the actual boundary is unknown:

```text
LISTING_LIFECYCLE_START_UNKNOWN
=> stable listing_id unavailable
```

Adding earlier provider observations inside an already proved lifecycle cannot
change the listing ID. A proved transfer or new lifecycle boundary does.

Ticker is match evidence for a dated interval but is not sole identity material.
Missing CIK/FIGI/lifecycle boundary/interval/evidence, zero matches, or multiple
matches fails. A true CIK successor, share-class FIGI successor, exchange
transfer, or separately proved new listing lifecycle creates the corresponding
new stable identity.

## RD-016, RD-020, and RD-022

- RD-016 remains the sum of class raw primary close times PIT class shares over
  every effective common-equity class; a missing class fails.
- RD-020 remains `exclude_feature`, with USD thresholds: EV 1,000,000; average
  assets 1,000,000; pretax income 100,000; average invested capital 1,000,000;
  and each of current/prior/prior-growth/two-year-prior revenue 1,000,000.
- RD-022 remains byte-for-byte the existing CandidateSet identity contract; the
  protected ranking digest remains exactly security ID, decision date, and
  composite score.

## First governed date

`2025-06-30` remains technically qualified as a proposal: an ordinary official
session, Databento dataset history beginning in 2018 covers 126/60-session
lookbacks, SEC has the required annual filing depth, and researcher-supplied
observations report historical Massive/Databento access. Exact evidence bytes
and per-security completeness are still required.

RD-002A retains its original meaning: the inclusive initial production-validation
range recorded by `ProviderSampleAdmissionPack.validation_start` and
`validation_end` through the existing non-production freeze mechanism. It is
not the seasoning window.

The 126 completed-session first-run evidence window is a non-authority
`CompletedSessionLookback` derived from the governed decision cutoff, official
session evidence, the latest fully completed admissible primary-market session,
and the already-governed Screen v2 seasoning requirement. The decision-date
session is included only when its exact normal or early close is at or before
the cutoff; otherwise the prior completed session anchors the window. Holidays
cannot anchor it. It does not receive or reuse an RD identifier.

## Local evidence collection

The `collect-first-run-evidence` CLI reads a closed request manifest, authenticates
from `MASSIVE_API_KEY` or `DATABENTO_API_KEY` headers, uses a configurable SEC
User-Agent, and writes raw bytes plus identity metadata outside Git. It never
prints headers or secrets, forbids secret-like request parameters and query-bearing
endpoints, records acquisition time/range/endpoint/safe parameters/byte length,
and derives a content-bound evidence ID.

```text
graham-research collect-first-run-evidence REQUESTS.json \
  --output-directory /outside/git/a22-evidence \
  --repository "$PWD" \
  --sec-user-agent "Researcher Name contact@example.com"

graham-research revalidate-collected-evidence \
  /outside/git/a22-evidence/<evidence-id>.identity.json
```

The checked-in request template is `NON_EVIDENCE_REQUEST_TEMPLATE` only.

## Candidate ProductionEvidenceManifest

`CandidateProductionEvidenceManifest` binds SEC, Massive, Databento, official
session, field-catalog, crosswalk, configuration, and implementation identities.
Its only accepted status is `NOT_PRODUCTION_ADMITTED`, and it always emits that
blocker. Its crosswalk field binds the separately materialized
`CrosswalkEvidenceIdentity`; the manifest does not mint or redefine stable
issuer/security/listing IDs. No candidate instance with fake evidence is checked
in.

## Final decision status

| Decision | State |
|---|---|
| RD-001 | `NEEDS_EXACT_PROVIDER_EVIDENCE` |
| RD-002A | `READY_TO_ADOPT` |
| RD-002B | `READY_TO_ADOPT` |
| RD-002C | `NO_LONGER_REQUIRED` for the first single-date run |
| RD-004 | `READY_TO_ADOPT` |
| RD-008 | `READY_TO_ADOPT` |
| RD-013 | `READY_TO_ADOPT` |
| RD-014 | `READY_TO_ADOPT` |
| RD-015 | `READY_TO_ADOPT` |
| RD-016 | `READY_TO_ADOPT` |
| RD-017 | `READY_TO_ADOPT` |
| RD-018 | `READY_TO_ADOPT` |
| RD-019 | `READY_TO_ADOPT` |
| RD-020 | `READY_TO_ADOPT` |
| RD-021 | `READY_TO_ADOPT` |
| RD-022 | `READY_TO_ADOPT` |
| RD-CROSSWALK-001 | `READY_TO_ADOPT` |

RD-002C remains `NO_LONGER_REQUIRED` for the first single-date run and is still
required before later multi-date historical research.

## FINAL PRODUCTION DECISION DECLARATION — PROPOSED, NOT YET ADOPTED

The eventual one-shot declaration must adopt exactly the policies above and
bind these identities without guessing:

```text
SCREEN_V2_APPROVAL_RECORD_IDENTITY = {
  repository_id: mostafa-maghsoodi/Stock-Market-Research,
  approval_record_path: docs/approvals/v1/screen-specification-v2-approval-001.json,
  approval_record_commit: 2363b96b490e805ed5d50392fa476100ffdbbcf3,
  approval_record_git_blob: 67f6db0005179a88152df7817065c8b2c4251595,
  approval_record_exact_byte_sha256: b9bc27f57a386ae635ba67dac210f33f1db67258589bfc6e88005de0babe3570
}
SEC_EDGAR_PRODUCT_AND_EVIDENCE_IDENTITIES = <TO_BE_BOUND_FROM_ADMITTED_EVIDENCE>
MASSIVE_PRODUCT_ENTITLEMENT_AND_EVIDENCE_IDENTITIES = <TO_BE_BOUND_FROM_ADMITTED_EVIDENCE>
DATABENTO_DATASET_ENTITLEMENT_AND_EVIDENCE_IDENTITIES = <TO_BE_BOUND_FROM_ADMITTED_EVIDENCE>
OFFICIAL_SESSION_EVIDENCE_IDENTITIES = <TO_BE_BOUND_FROM_ADMITTED_EVIDENCE>
FIELD_CATALOG_IDENTITY = <TO_BE_BOUND_FROM_ADMITTED_EVIDENCE>
CROSSWALK_EVIDENCE_IDENTITY = <TO_BE_BOUND_FROM_ADMITTED_EVIDENCE>
PRODUCTION_EVIDENCE_MANIFEST_IDENTITY = <TO_BE_BOUND_FROM_ADMITTED_EVIDENCE>
POST_MERGE_IMPLEMENTATION_COMMIT = <TO_BE_BOUND_AFTER_NORMAL_PR19_MERGE>
POST_MERGE_IMPLEMENTATION_TREE = <TO_BE_BOUND_AFTER_NORMAL_PR19_MERGE>

RD-001 = SEC EDGAR filing archive + Massive Stocks Reference + Databento
         XNAS.ITCH/XNYS.PILLAR/XASE.PILLAR + official NYSE/Nasdaq calendars;
         Sharadar is optional diagnostics only
RD-002A = initial production-validation range: inclusive UTC validation_start
          and validation_end recorded by the existing non-production freeze;
          exact dates remain researcher-supplied and are not adopted here
RD-002B = 2025-06-30
FIRST_RUN_EVIDENCE_WINDOW = non-authority CompletedSessionLookback of exactly
                            126 sessions resolved from the governed cutoff,
                            official session evidence, latest fully completed
                            admissible primary-market session, and governed
                            Screen v2 seasoning; decision_date alone never anchors
                            the window
RD-004A = EDGAR acceptance datetime is the governed availability timestamp
RD-004B = closed exact SEC mapping contract in this document
RD-008 = exact type-11 primary close and session-bounded native trade sum
RD-013 = COMPLETED_SESSION_COUNT / 0 / STRICT_ZERO_GAP
RD-014 = corporate-action and SPAC contract in this document
RD-015 = filing-level class-dimensional cover-page shares
RD-016 = complete class-summed total market capitalization
RD-017 = component EV with explicit-zero/structural-NA/missing states
RD-018 = positive-evidence operating-company classification
RD-019 = component invested capital and governed two-period average
RD-020 = exact denominator thresholds in this document; exclude_feature
RD-021 = USD/SHARES/USD_PER_SHARE; non-USD accounting unavailable
RD-022 = existing CandidateSet identity contract unchanged
RD-CROSSWALK-001 = stable CIK/FIGI/MIC/actual-governed-lifecycle identities
                   separated from the date/evidence-bound
                   CrosswalkEvidenceIdentity; earliest provider observation is
                   provenance only and an unknown actual boundary fails closed

I attest that no realized strategy outcome was examined in making these decisions.
```

This declaration is not yet adopted and does not itself create governing bytes.
