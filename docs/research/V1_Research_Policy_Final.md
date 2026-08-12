# V1 Research Policy — Final

## 1. Status and authority

**Status:** FINAL — approval state is external to these bytes. This document
does not self-attest approval; governing approval is established externally
under the applicable approved Approval Record v1 mechanism for its exact
immutable repository/path/source-commit/blob/SHA-256 identity.
**Subject type:** `RESEARCH_INTENT`.
**Document version:** `1.0`.
**Architecture:** Architecture v3.2 successor authority; Architecture v3.1
remains immutable historical evidence.
**Research state:** ex-ante V1 policy resolved; production provider and data
evidence deferred; no realized strategy outcome examined for this
specification.

The researcher adopted this V1 research policy before examination of realized
strategy outcomes for this specification. Creating, committing, merging, or
referencing these bytes does not make them governing. Governing effect begins
only after the researcher explicitly approves the exact final merged Approval
Record identity that binds this subject.

For every rule below:

`unsupported capability → return to researcher → no silent substitution`

## 2. Policy state and production-readiness boundary

The policy state is `RESOLVED_RESEARCH_POLICY`.

The production evidence state is `DEFERRED_PROVIDER_AND_DATA_EVIDENCE`.

Resolved research policy does not imply verified data evidence, repository
identity verification, or production execution readiness. This subject selects
no provider, verifies no field catalog or archive, freezes no Screen
Specification, and authorizes no production CandidateSet.

## 3. Accounting and point-in-time policy

The reporting basis is `ANNUAL`. The restatement policy is `FIRST_REPORTED`.
Duration accounting observations require explicit `period_start` and
`period_end`. No period boundary may be silently inferred where governed source
evidence is insufficient.

No accounting value may be imputed merely to make a proxy executable. Current
or live Company Facts are not historical point-in-time evidence unless their
exact historical observation and public-availability provenance are separately
established.

## 4. Historical timing policy

The market alignment policy is
`PRIOR_COMPLETED_PRIMARY_MARKET_SESSION`. A market observation used by the
screen must come from the most recent fully completed primary-market session
admissible under the governed decision cutoff.

Accounting information consumed by the screen must have been publicly
available before the applicable governed cutoff. Same-day closing values must
not be combined with information that became public only after that close.

Historical session calendars, timestamps, holidays, and exchange-local timing
must be explicit and provider-backed. No missing market timestamp or session
boundary may be silently inferred.

## 5. Market scope

The market country is `UNITED_STATES`. Included primary exchanges are exactly,
in this order:

1. `NYSE`;
2. `NASDAQ`; and
3. `NYSE_AMERICAN`.

The base currency is `USD`. A security outside this market scope is not V1
eligible. No foreign-exchange policy is selected for V1 eligibility because
the V1 scope consists of USD primary listings.

## 6. Point-in-time universe filters

Every universe rule is point-in-time. Present-day security attributes may not
substitute for historical attributes.

### 6.1 Size

The size metric is `TOTAL_MARKET_CAPITALIZATION`, with a minimum of
`USD 500000000`.

### 6.2 Price

The price metric is `RAW_PRIMARY_LISTING_CLOSE`, with a minimum of `USD 5`.

### 6.3 Liquidity

Daily dollar volume is:

`RAW_PRIMARY_LISTING_CLOSE * RAW_PRIMARY_LISTING_VOLUME`

The measurement is the `MEDIAN` over 60 completed primary-market sessions. The
minimum is `USD 2000000`.

### 6.4 Seasoning

The minimum seasoning requirement is 126 completed primary-market sessions.

## 7. Security eligibility

V1 includes primary-listed common operating-company equity securities.

V1 excludes:

- ADRs;
- preferred equity;
- ETFs;
- mutual funds;
- closed-end funds;
- BDCs;
- REITs;
- SPACs before a completed business combination;
- rights;
- warrants;
- units;
- when-issued securities; and
- other non-common-equity instruments.

### 7.1 SPAC successors

A pre-business-combination SPAC is excluded. After a completed business
combination, the successor operating-company security may become eligible only
after satisfying the V1 126-session seasoning requirement measured from the
governed post-combination eligibility boundary.

### 7.2 Foreign issuers

A foreign-domiciled issuer may be eligible only when its United States
common-equity listing is historically demonstrated to be the primary listing
and every other V1 eligibility requirement passes.

### 7.3 Multiple common share classes

Only one representative eligible common-equity class per issuer may enter the
V1 cross-sectional universe. Resolution follows exactly this order:

1. the historically authoritative primary common class;
2. if unresolved, the otherwise eligible primary common class with the highest
   governed 60-session median dollar volume; and
3. if still tied, ascending stable `security_id`.

An issuer may not be duplicated solely because it has multiple common share
classes.

## 8. Proxy order and common constraints

The exact proxy order is:

1. `fcf_ev`;
2. `ebit_ev`;
3. `gross_profitability`;
4. `roic`;
5. `operating_margin_change`;
6. `fcf_margin_change`; and
7. `revenue_acceleration`.

Accounting observations use `ANNUAL` and `FIRST_REPORTED` unless an exact role
is an instant market or balance-sheet observation. No imputation, silent proxy
substitution, silent vendor-field equivalence, or silently inferred XBRL
equivalence is permitted. Every vendor/native mapping requires an explicit
governed field catalog.

Any proxy whose exact canonical fields, periods, provenance, or timing cannot
be validated remains unavailable rather than being silently redefined.

## 9. Proxy semantics

### 9.1 FCF/EV

The conceptual formula is:

```text
(operating_cash_flow - abs(capital_expenditures))
/
enterprise_value
```

Exact CFO, capital-expenditure, and enterprise-value canonical fields remain
subject to future governed field-catalog verification. Market timing must
satisfy the V1 historical timing policy.

### 9.2 EBIT/EV

The conceptual formula is:

```text
operating_income
/
enterprise_value
```

Operating income is the V1 EBIT proxy only when the governed field catalog
validates its exact canonical definition. Market timing must satisfy the V1
historical timing policy.

### 9.3 Gross profitability

The conceptual formula is:

```text
gross_profit_FY0
/
average(total_assets_FY0, total_assets_FY_minus_1)
```

Reported gross profit is preferred. Derived revenue minus cost must not
substitute unless separately governed as an exact canonical field construction.

### 9.4 ROIC

The existing deterministic calculator structure is retained only where every
canonical input is explicitly governed. A vendor's precomputed ROIC field may
not substitute. Exact invested-capital semantics remain deferred to a future
governed field/proxy catalog.

### 9.5 Operating-margin change

The conceptual formula is:

```text
operating_income_FY0 / revenue_FY0
-
operating_income_FY_minus_1 / revenue_FY_minus_1
```

### 9.6 FCF-margin change

The conceptual formula is:

```text
(operating_cash_flow_FY0 - abs(capital_expenditures_FY0))
/
revenue_FY0

minus

(operating_cash_flow_FY_minus_1 - abs(capital_expenditures_FY_minus_1))
/
revenue_FY_minus_1
```

### 9.7 Revenue acceleration

Revenue acceleration retains the existing governed three-annual-period V1
structure using matched, consecutive fiscal periods.

## 10. Missingness and denominators

No missing accounting or market value is imputed. Missing essential inputs
make the affected proxy unavailable.

Existing governed exact-zero and negative-denominator behavior is preserved.
V1 introduces no universal arbitrary floating-point near-zero threshold. Any
economically material near-zero rule must be denominator-aware and separately
governed, and realized outcomes must not be used to choose it.

## 11. Required dimensions and valuation coverage

The required dimensions are exactly, in this order:

1. `VALUATION`;
2. `BUSINESS_ECONOMICS`; and
3. `FUNDAMENTAL_CHANGE`.

All three are mandatory. No accounting-only or two-dimension CandidateSet path
is permitted.

Both `fcf_ev` and `ebit_ev` are mandatory for CandidateSet eligibility. A
security missing either proxy is ineligible for the V1 CandidateSet. Private,
outcome-free accounting diagnostics may still execute where otherwise
admissible, but no security may enter CandidateSet through silent valuation
omission.

## 12. Aggregation

V1 uses the existing governed cross-sectional percentile-rank transformation.
Within each dimension, eligible proxy ranks receive equal weight. Across the
three required dimensions, each dimension receives equal weight.

A dimension must not receive greater total weight merely because it contains
more proxies. No `skipna`-based silent reweighting is permitted for required V1
coverage.

## 13. CandidateSet policy

The selection rule is `TOP 100` per approved decision date. Ordering is:

1. `composite_score` descending; then
2. stable `security_id` ascending.

There is one CandidateSet and no tiers. CandidateSet remains separate from the
GovernedRankingArtifact and is not a BUY list.

The protected GovernedRankingArtifact digest scope remains exactly:

1. `security_id`;
2. `decision_date`; and
3. `composite_score`.

CandidateSet must not mutate or expand that digest scope.

If fewer than 100 governed eligible securities remain after all mandatory V1
rules, processing fails closed with an explicit
`INSUFFICIENT_ELIGIBLE_POPULATION` diagnostic. Top 100 must not be silently
redefined as all available securities.

## 14. Screen Specification succession

Screen Specification v1 remains immutable historical authority and must not be
patched or rewritten. The intended successor is Screen Specification v2, which
must later distinguish policy resolution, provider/data evidence resolution,
repository identity verification, and production execution readiness.

This research-policy subject does not create Screen Specification v2, ADR-005,
or a successor Amendment Ledger.

## 15. Deferred provider and data evidence

The following remain unresolved production-execution blockers:

- production provider/product topology;
- exact historical sample boundaries;
- provider-native immutable identifiers;
- vendor/native field mappings;
- production field-catalog identities;
- security-master provider identity;
- issuer/security/listing crosswalk evidence;
- production historical market-data product;
- provider/archive evidence identities;
- exact missing-session or stale-price bound;
- exact corporate-action timestamp and effective-event implementation;
- exact PIT shares, market-capitalization, and enterprise-value source
  construction;
- exact historical operating-company taxonomy source;
- exact canonical invested-capital field construction;
- denominator-specific near-zero materiality values;
- ungoverned unit-normalization details; and
- exact production CandidateSet evidence identities.

None may be converted into a default.

## 16. Provider status

No production provider is selected. Free or public data may be used only for
development, fixtures, provider-neutral adapters, and coverage diagnostics,
with explicit limitations. It must not be represented as satisfying the
governed production capability contract.

A real governed historical CandidateSet remains blocked until all required
production capabilities and evidence are verified.

## 17. Outcome, research-purpose, and transaction boundary

The V1 screen is a broad fundamental research funnel combining attractive
valuation, strong business economics, and improving fundamentals. CandidateSet
feeds later deep research; it is not a BUY list.

This policy does not authorize portfolio construction, trading, money movement,
or realized-outcome evaluation. Entry001, the specification budget, durable
OPEN, authorized execution, and CLOSE remain mandatory before any realized
strategy outcome use.

These internal research-governance decisions and attestations are not a legal
signature, contract, investment-management agreement, fiduciary undertaking,
or authorization for any person or system to transact or move money.

## 18. Immutability and future changes

Once governing, this V1 policy remains immutable. No historical parameter may
be silently retuned because another value later produces better performance.

Any future research-policy change influenced by realized outcomes requires a
successor specification under the applicable authority, Entry001, budget,
OPEN/CLOSE, provenance, and outcome-governance boundaries. It must never rewrite
this V1 subject or represent the later decision as contemporaneous with it.
