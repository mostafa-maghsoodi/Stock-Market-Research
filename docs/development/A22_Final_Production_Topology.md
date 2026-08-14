# A22 final production-topology design

Status: provider-neutral implementation material. These bytes are not governing
authority, provider evidence, production admission, a provider selection, or a
CandidateSet.

## Proposed first-run topology

The minimum candidate topology is SEC EDGAR plus Massive Stocks Reference plus
Databento Historical `XNAS.ITCH`, `XNYS.PILLAR`, and `XASE.PILLAR`, plus exact
official exchange calendar/session evidence. Sharadar is optional diagnostics
only and is not an authoritative dependency.

| Requirement | Candidate source | State |
|---|---|---|
| Filing/accession and XBRL contexts | SEC filing archive | `SUFFICIENT_WITH_GOVERNED_CROSSWALK` |
| SEC acceptance timestamp | Complete submission header | `SUFFICIENT` as acceptance evidence |
| Exact public availability | SEC plus approved availability semantics | `REQUIRES_RESEARCHER_DECISION` |
| Historical universe snapshot | Massive historical ticker endpoint | `SUFFICIENT_WITH_GOVERNED_CROSSWALK` |
| Active/inactive, primary MIC, ticker type | Massive historical snapshot | `SUFFICIENT_WITH_GOVERNED_CROSSWALK` |
| Stable listing market observations | Databento historical symbology and definition | `SUFFICIENT_WITH_GOVERNED_CROSSWALK` |
| Official primary close | Databento venue `statistics`, close `stat_type=11` | `SUFFICIENT_WITH_GOVERNED_CROSSWALK` |
| Raw primary-venue volume | Databento venue trades | `REQUIRES_RESEARCHER_DECISION` |
| Historical sessions | Official exchange calendar plus Databento status/statistics | `REQUIRES_EXTERNAL_DOCUMENTATION` |
| Exact eligibility taxonomy | Massive type plus SEC/definition evidence | `TECHNICALLY_MISSING` for unresolved classes |
| SPAC combination boundary | SEC event filing plus admitted event rule | `TECHNICALLY_MISSING` as a universal rule |
| PIT class shares | SEC cover-page XBRL plus class crosswalk | `SUFFICIENT_WITH_GOVERNED_CROSSWALK` for fully tagged classes |
| Multi-class issuer market cap | Deterministic class sum | `REQUIRES_RESEARCHER_DECISION` |
| EV and invested capital | SEC component facts | `REQUIRES_RESEARCHER_DECISION` |

The topology is not yet sufficient for a real run. No additional paid-provider
search is justified: the remaining deficiencies are authority, documentation,
classification/event evidence, and exact mapping problems rather than proof
that a fourth paid provider is technically necessary.

## SEC filing-level PIT contract

`SecFilingFact` requires CIK, accession, annual form, timezone-aware acceptance,
separate public-availability timestamp, XBRL concept, unit, explicit duration
start/end or instant date, value, context ID, native fact ID, fiscal year,
dimension digest, and detached evidence identity. `select_first_reported_sec_fact`
selects the earliest admissible accession for the exact concept/unit/context/
period and never replaces it with a later amendment.

The SEC complete-submission header exposes `ACCEPTANCE-DATETIME`, and XBRL
contexts natively expose duration start/end and instant dates. SEC guidance also
states that it does not expose a timestamp identifying when filing content first
became available on sec.gov. Consequently, acceptance is a strong timing
candidate but cannot silently be equated to public availability. RD-004 must bind
the exact conservative availability semantics before production.

Official references:

- https://www.sec.gov/about/webmaster-frequently-asked-questions
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- https://www.sec.gov/file/xbrl-guide

## Candidate SEC field catalogue

`SEC_CANONICAL_FIELD_CANDIDATES` is closed and exact but non-governing. It never
uses fuzzy names or pools candidates. Every entry has
`ambiguity_behavior=REQUIRE_GOVERNED_MAPPING`.

| Canonical concept | Candidate tag(s) | Remaining issue |
|---|---|---|
| revenue | `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`, `SalesRevenueNet` | exact priority/equivalence |
| gross profit | `GrossProfit` | reported-only availability |
| operating income | `OperatingIncomeLoss` | scope evidence |
| operating cash flow | `NetCashProvidedByUsedInOperatingActivities` | scope evidence |
| capital expenditures | `PaymentsToAcquirePropertyPlantAndEquipment` | exact economic scope/sign |
| total assets | `Assets` | dimensions/consolidated scope |
| income before tax | two enumerated continuing-operations candidates | exact scope/equivalence |
| income-tax expense | `IncomeTaxExpenseBenefit` | sign convention |
| short-term debt | `ShortTermBorrowings`, `LongTermDebtCurrent` | non-overlap/summation |
| long-term debt | `LongTermDebtNoncurrent` | scope |
| preferred stock | `PreferredStockValue`, `PreferredStockValueOutstanding` | carrying-value equivalence |
| NCI | `MinorityInterest`, `NoncontrollingInterestInConsolidatedEntity` | taxonomy-version equivalence |
| common equity | `StockholdersEquity` | parent-only scope |
| cash/short investments | `CashAndCashEquivalentsAtCarryingValue`, `ShortTermInvestments` | non-overlap/summation |
| class shares | `dei:EntityCommonStockSharesOutstanding` | explicit stock-class dimension and scaling |

Extensions are never admitted by local-name similarity. An extension requires
its own exact definition and mapping evidence.

## Massive-to-Databento crosswalk

The deterministic matcher requires:

1. exact decision timestamp and a Massive snapshot for that date;
2. Massive ticker, primary MIC, CIK, and share-class FIGI;
3. the MIC-specific Databento dataset;
4. an effective-dated Databento raw-symbol-to-instrument-ID mapping;
5. an effective definition with the same dataset, MIC, raw symbol, and
   instrument ID; and
6. one and only one resulting native instrument/publisher tuple.

Ticker alone is never sufficient. Missing matches raise `CROSSWALK_MISSING`;
multiple native tuples raise `CROSSWALK_AMBIGUOUS`.

Databento documents that historical symbols are preserved as originally seen,
symbols may be reused, and mappings have explicit start/end timestamps:
https://databento.com/docs/standards-and-conventions/symbology

### RD-CROSSWALK-001 recommended proposal

Approve content-bound internal IDs derived only after all referenced evidence
has been admitted:

```text
issuer_id material = SEC CIK + exact SEC/Massive CIK crosswalk evidence identity
security_id material = issuer_id + Massive share_class_figi + snapshot evidence identity
listing_id material = security_id + primary MIC + Databento dataset + instrument_id
                      + symbology interval + definition interval + evidence identities
canonicalization = repository canonical JSON
digest = lowercase SHA-256
missing FIGI, CIK, interval, or non-unique match = fail closed
```

This is a proposal requiring approval, not an implemented governing identity.

## Sessions, raw close, and raw volume

`OfficialSessionRecord` requires an official-calendar evidence identity,
timezone, UTC open/close, completed/holiday/cancelled status, and early-close
state. Absence of trades never creates a holiday. Databento status/statistics
may corroborate the venue state but do not replace the official schedule.

For XNAS, XNYS, and XASE, the primary-close resolver accepts only the exact
venue/dataset/instrument/publisher and Databento close statistic type 11. It
does not fall back to OHLCV, midpoint, or consolidated data. Databento documents
the Nasdaq and NYSE-family closing statistics as their closing-cross prices:

- https://databento.com/docs/venues-and-datasets/xnas-itch
- https://databento.com/docs/venues-and-datasets/xnys-pillar
- https://databento.com/docs/schemas-and-data-formats/statistics

Raw volume remains policy-bound. Databento daily bars use UTC dates, and its
documentation warns that aggregation choices vary for trade conditions,
retroactive breaks, timestamps, and block trades. The implemented trade resolver
therefore requires an approved include/exclude condition set, rejects unknown
conditions, duplicate sequences, cancels, and corrections, and clips to the
official primary-venue session. RD-008 must bind the exact condition/auction/
correction policy.

## Taxonomy and SPAC treatment

The public official ticker-types sample establishes `CS` as Common Stock, but
the complete authenticated ticker-types metadata was not available to this
implementation environment. The other observed codes therefore remain
`UNKNOWN_CLASSIFICATION` until their exact official descriptions are admitted.
Even `CS` does not establish operating-company, REIT, BDC, or SPAC status.
Unknown or unresolved classification is ineligible under the existing Screen
v2 exact-class rule; this is fail-closed enforcement, not a new economic
inclusion rule.

No universal post-combination boundary is currently established. It requires an
admitted event, normally a governed SEC 8-K/Super 8-K rule plus exact accession
and effective boundary. `require_spac_boundary` fails when this evidence is
absent. First-price date is never a substitute.

## Shares, market cap, EV, and invested capital

SEC guidance identifies `dei:EntityCommonStockSharesOutstanding` as cover-page
shares and supports class dimensions, but also reports scaling/tagging errors.
The implementation requires explicit class FIGI/security binding, observation
date, public availability, units, accession, and evidence. Missing classes fail.

Proposed total market capitalization:

```text
SUM(raw class-level primary close × PIT class shares)
```

Proposed EV:

```text
total market capitalization
+ short-term debt
+ long-term debt
+ preferred stock
+ noncontrolling interest
- cash and short-term investments
```

Proposed invested capital:

```text
short-term debt
+ long-term debt
+ preferred stock
+ noncontrolling interest
+ common equity
- cash and short-term investments
```

No missing financing component becomes zero. Structural non-reporting of
preferred stock or NCI therefore remains a coverage/mapping decision.

## Proposed denominator policy — not adopted

All actions are `exclude_feature` and all thresholds are in canonical USD:

| Denominator | Threshold |
|---|---:|
| enterprise_value | 1,000,000 |
| average_total_assets | 1,000,000 |
| income_before_tax_for_effective_tax_rate | 100,000 |
| average_invested_capital | 1,000,000 |
| current_revenue | 1,000,000 |
| prior_revenue | 1,000,000 |
| prior_revenue_for_current_growth | 1,000,000 |
| two_year_prior_revenue_for_prior_growth | 1,000,000 |

Existing runtime precedence remains missing, exact-zero, negative-policy, then
positive near-zero threshold. These values remain RD-020 proposals.

## Proposed first governed date

`2025-06-30` is technically qualified as a proposal:

- it is an ordinary Monday session and is not a 2025 NYSE/Nasdaq holiday or
  early-close date;
- Databento coverage beginning in 2018 supplies much more than the required
  126-session seasoning and 60-session liquidity lookbacks;
- SEC filing archives supply prior annual filings; and
- researcher observations establish Massive and Databento access on the date.

This does not prove complete per-security evidence coverage and does not adopt
RD-002B.

## CandidateSet identity

RD-022 remains exactly:

```text
artifact_type
identity_schema_version
authority_status
canonicalization
candidate_set_exact_byte_sha256
candidate_set_byte_length
ranked_frame_digest
screen_v2_configuration_digest
governed_batch_lineage_sha256
eligible_population_digest
selection_rule_digest
production_evidence_manifest_sha256
decision_date
derived_identity_sha256
```

The protected ranking digest remains exactly `security_id`, `decision_date`,
and `composite_score`.

## Remaining decision audit

| Decision | State |
|---|---|
| RD-001 provider topology | `NEEDS_EXTERNAL_EVIDENCE` |
| RD-002A validation range | `READY_TO_ADOPT` |
| RD-002B first date = 2025-06-30 | `READY_TO_ADOPT` |
| RD-004 SEC field/availability catalogue | `TECHNICALLY_UNRESOLVED` |
| RD-008 Databento close/volume product semantics | `TECHNICALLY_UNRESOLVED` |
| RD-013 session/staleness policy | `TECHNICALLY_UNRESOLVED` |
| RD-014 corporate-action/SPAC boundary | `TECHNICALLY_UNRESOLVED` |
| RD-015 PIT class shares | `TECHNICALLY_UNRESOLVED` |
| RD-016 class-summed market cap | `READY_TO_ADOPT` |
| RD-017 component EV | `TECHNICALLY_UNRESOLVED` |
| RD-018 operating-company taxonomy | `TECHNICALLY_UNRESOLVED` |
| RD-019 component invested capital | `TECHNICALLY_UNRESOLVED` |
| RD-020 denominator thresholds | `READY_TO_ADOPT` |
| RD-021 unit normalization | `NEEDS_EXTERNAL_EVIDENCE` |
| RD-022 CandidateSet identity | `READY_TO_ADOPT` |
| RD-CROSSWALK-001 identity scheme | `READY_TO_ADOPT` |
| RD-002C full research range | `NO_LONGER_REQUIRED` for first single-date run |

## Production Admission Decision Bundle design

One later authority subject remains structurally permitted:

```text
subject_type = OTHER_GOVERNED_ARTIFACT
path = docs/research/Screen_v2_Production_Admission_Decision_Bundle_v1.json
title = Screen v2 Production Admission Decision Bundle
version = 1
```

It must use a closed schema binding the exact Screen v2 ApprovalRecordIdentity,
provider/product topology, first date, SEC field and availability catalogue,
Massive semantics, crosswalk rule and identity scheme, Databento datasets and
market rules, session policy, taxonomy, SPAC boundary, shares, market cap, EV,
invested capital, denominator policy, units, RD-022 identity contract, exact
ProductionEvidenceManifest identity, researcher/timestamp, and exact statement:

```text
No realized strategy outcome was examined in making these decisions.
```

It must not be materialized until every unresolved value and external evidence
identity is supplied. It then requires its own exact commit/blob/SHA-256 subject
identity, normal Approval Record v1, and explicit external human approval.
