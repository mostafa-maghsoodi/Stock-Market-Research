# Screen Specification v2 — Final

## 1. Identity, status, and purpose

**Status:** FINAL — approval state is external to these bytes. This document
does not self-attest approval; governing approval is established externally
under Approval Record v1 for its exact immutable repository/path/source-commit/
blob/SHA-256 identity.

**Subject type:** `CONTRACT`.

**Document version:** `2`.

**Repository:** `mostafa-maghsoodi/Stock-Market-Research`.

This contract is the prospective successor Screen Specification for future
governed screen instances. It materializes the resolved V1 research policy and
the separation between policy resolution, provider/data evidence, repository
identity verification, and production execution readiness. It does not create
a frozen screen instance, select a provider, admit production data, produce a
CandidateSet, or authorize realized-outcome use.

Screen Specification v1 remains immutable historical authority. Screen v2 is a
successor contract, never an edit, replacement of historical bytes, or
retroactive reinterpretation of Screen v1.

## 2. Governing authority and succession

Architecture v3.2 remains governing. No Architecture v3.3 is required. The
succession direction is authorized by ADR-005 as recorded at ordinal 5 of the
governing Amendment Ledger v1.1.0. The resolved research-policy content comes
from the separately governing V1 Research Policy.

The governing authority identities are:

```text
V1 Research Policy subject:
  path = docs/research/V1_Research_Policy_Final.md
  source_commit = e7203620c7a452cf82bcf032072e4237062fd156
  git_blob = a77866c5b8f9bca5982b3fbbc3c117120017e43c
  exact_byte_sha256 = 183b27f1058bd89d9616f71660b42160fadacc144639abab635c205b853a26de

V1 Research Policy ApprovalRecordIdentity:
  approval_record_commit = a450e4faf86ade46f44d27609f413c41e169f17d
  approval_record_git_blob = f210ae96f6308ffef871b3c180ece4a4a631b694
  approval_record_exact_byte_sha256 = 10dbf5a21ee6525ff3ab7e0f7df56c503d9f55387a70d3380e8c630370155783

ADR-005 subject:
  path = docs/architecture/adr/ADR-005_Final.md
  source_commit = 76e90e16b56efcefc3917c4b8f90452a1ba717ff
  git_blob = 7295884030bd6fafce5a61446e3d2e2d130385a2
  exact_byte_sha256 = fad80ff32b8ffdb137bc84e417e0253ac67a0221d1f664c5d3847a7fed077f0a

ADR-005 ApprovalRecordIdentity:
  approval_record_commit = 7174753bf6e829ab411b63c2854a0b0b0c0c2a57
  approval_record_git_blob = de0285465a9e9e6d0f3ff821849ae08bbe68dd17
  approval_record_exact_byte_sha256 = 73fc3a9c6c9510dd9ecb590c8d23cbd0183f097a681227f039ea68a024a4b535

Amendment Ledger v1.1.0 subject:
  path = docs/architecture/amendments/Amendment_Ledger_v1.1.0.json
  source_commit = ee59804fcab50a05702f6d0b9dca7cac831f9998
  git_blob = 182e97396455a63ed085a7fd8b14c5fc688a53ed
  exact_byte_sha256 = 806d1bc8cf0597ba37e8dd71879dd35f46758ac508aaf1459faa6df9d6e3e686

Amendment Ledger v1.1.0 ApprovalRecordIdentity:
  approval_record_commit = 435237524ae5131cde8aafe8f40bfd838a97cf40
  approval_record_git_blob = 61bed41de87be0a8ee198631a0bc6a65243478fc
  approval_record_exact_byte_sha256 = 9259bde004e08a9189db497925f484caec55cdb3139c379531d247c1e26f9305
```

Every identity above uses repository ID exactly
`mostafa-maghsoodi/Stock-Market-Research`. Document existence or an embedded
identity does not manufacture human approval.

## 3. Closed policy/evidence/identity/readiness state

Every future Screen v2 production-readiness record has exactly these keys:

```text
ScreenV2ReadinessState = {
  "research_policy_state": "RESOLVED_RESEARCH_POLICY",
  "provider_and_data_evidence_state":
    null | "RESOLVED_PROVIDER_AND_DATA_EVIDENCE",
  "repository_identity_state":
    null | "VERIFIED_REPOSITORY_IDENTITIES",
  "production_execution_state":
    null | "PRODUCTION_EXECUTION_READY",
  "production_prerequisite_results": ProductionPrerequisiteResults
}

ProductionPrerequisiteResults = {
  "approved_governing_screen_v2_identity": boolean,
  "required_architecture_and_ledger_authority_verified": boolean,
  "provider_and_data_evidence_resolved": boolean,
  "pit_provider_capability_verified": boolean,
  "security_master_verified": boolean,
  "historical_universe_evidence_verified": boolean,
  "field_catalog_verified": boolean,
  "market_timing_and_session_evidence_verified": boolean,
  "source_native_mappings_verified": boolean,
  "exact_provenance_verified": boolean,
  "mandatory_proxy_coverage_verified": boolean,
  "required_valuation_coverage_verified": boolean,
  "implementation_and_configuration_identities_consistent": boolean
}
```

No additional keys or state tokens are permitted. `null` means the corresponding
positive state has not been established; it is not permission to infer a state.
At contract materialization, the research-policy state is resolved and the
other three states are null.

`PRODUCTION_EXECUTION_READY` is valid if and only if both other positive state
tokens are present and every exact boolean in `ProductionPrerequisiteResults`
is `true`. If any prerequisite is false, absent, unverified, inconsistent, or
unresolved, `production_execution_state` must be null and execution fails
closed without a CandidateSet.

Therefore:

```text
RESOLVED_RESEARCH_POLICY != PRODUCTION_EXECUTION_READY
RESOLVED_RESEARCH_POLICY does not imply PRODUCTION_EXECUTION_READY
```

## 4. Accounting and point-in-time policy

The exact accounting policy is:

```text
reporting_basis = ANNUAL
restatement_policy = FIRST_REPORTED
```

Duration accounting observations require explicit `period_start` and
`period_end`. No period boundary may be silently inferred. No accounting or
market value is imputed. Current or live Company Facts are historically
inadmissible unless the exact historical observation and its historical public-
availability provenance are separately established.

Accounting information must have been public before the applicable governed
decision cutoff. Present-day revised facts may not masquerade as historical
first-reported facts.

## 5. Historical market timing and market scope

The exact market alignment policy is:

```text
market_alignment_policy = PRIOR_COMPLETED_PRIMARY_MARKET_SESSION
```

The market observation is the most recent fully completed primary-market
session admissible under the governed decision cutoff. A same-day close must
not be combined with accounting information that became public only after that
close. Exchange calendars, session boundaries, holidays, timestamps, and
exchange-local timing must be explicit and provider-backed. Missing sessions or
timestamps are never silently inferred.

The exact market scope is:

```text
market_country = UNITED_STATES
included_primary_exchanges = [NYSE, NASDAQ, NYSE_AMERICAN]
base_currency = USD
```

The exchange order is authoritative. No foreign-exchange policy is required
for V1 eligibility because eligible securities are USD primary listings.

## 6. Point-in-time universe policy

Every eligibility test is point-in-time. Present-day attributes cannot
substitute for historical attributes.

```text
SIZE:
  metric = TOTAL_MARKET_CAPITALIZATION
  minimum = USD 500000000

PRICE:
  metric = RAW_PRIMARY_LISTING_CLOSE
  minimum = USD 5

LIQUIDITY:
  daily_dollar_volume =
    RAW_PRIMARY_LISTING_CLOSE * RAW_PRIMARY_LISTING_VOLUME
  measurement = MEDIAN
  window = 60 completed primary-market sessions
  minimum = USD 2000000

SEASONING:
  minimum = 126 completed primary-market sessions
```

The eligible class is primary-listed common operating-company equity. The
following are excluded exactly: ADR, preferred equity, ETF, mutual fund,
closed-end fund, BDC, REIT, pre-combination SPAC, rights, warrants, units,
when-issued securities, and every other non-common-equity instrument.

A post-combination SPAC successor may become eligible only after 126 completed
primary-market sessions from the governed post-combination boundary. A foreign
issuer is eligible only when the United States common listing is historically
established as the primary listing and all other requirements pass.

Only one representative eligible common-equity class per issuer is permitted.
Resolution order is exactly:

1. authoritative historical primary common class;
2. if unresolved, the highest governed 60-session median dollar volume among
   otherwise eligible primary common classes; and
3. if still tied, stable `security_id` ascending.

An issuer cannot be duplicated solely because it has multiple share classes.

## 7. Exact proxy registry policy

The exact proxy order is:

1. `fcf_ev`;
2. `ebit_ev`;
3. `gross_profitability`;
4. `roic`;
5. `operating_margin_change`;
6. `fcf_margin_change`; and
7. `revenue_acceleration`.

Accounting observations are `ANNUAL` and `FIRST_REPORTED` unless an exact role
is an instant market or balance-sheet role. There is no imputation, silent
proxy substitution, silent vendor-field equivalence, or silent XBRL-field
equivalence. Exact native/canonical mappings require a separately governed
field catalog.

Any proxy whose canonical fields, point-in-time provenance, source
availability, period structure, market timing, denominator validity, or mapping
evidence cannot be governed and verified remains unavailable. It is never
silently redefined.

### 7.1 FCF/EV

```text
(operating_cash_flow - abs(capital_expenditures)) / enterprise_value
```

Exact CFO, capital-expenditure, and enterprise-value fields require future
governed field-catalog validation. Market roles use the historical timing rule.
If any exact required input is unverified, the proxy is unavailable.

### 7.2 EBIT/EV

```text
operating_income / enterprise_value
```

Operating income is the approved EBIT proxy only when its exact canonical
definition is validated. A vendor-precomputed EBIT/EV field cannot substitute.

### 7.3 Gross profitability

```text
gross_profit_FY0 / average(total_assets_FY0, total_assets_FY_minus_1)
```

Reported gross profit is required where available. `revenue - cost` cannot
silently substitute; any derived gross-profit path requires separate governing
authority.

### 7.4 ROIC

The existing deterministic ROIC calculator is retained only when every exact
canonical input is governed and validated. Vendor-precomputed ROIC cannot
substitute. Exact invested-capital construction remains a production field/
proxy-catalog blocker until separately governed.

### 7.5 Operating-margin change

```text
operating_income_FY0 / revenue_FY0
- operating_income_FY_minus_1 / revenue_FY_minus_1
```

The annual periods must be matched and consecutive.

### 7.6 FCF-margin change

```text
(operating_cash_flow_FY0 - abs(capital_expenditures_FY0)) / revenue_FY0
-
(operating_cash_flow_FY_minus_1 - abs(capital_expenditures_FY_minus_1))
  / revenue_FY_minus_1
```

The annual periods must be matched and consecutive.

### 7.7 Revenue acceleration

The existing deterministic three-annual-period structure is retained. Periods
must be matched and consecutive. The formula cannot be silently altered or
redefined because data is unavailable.

## 8. Missingness and denominator governance

Missing essential input makes the affected proxy unavailable. There is no
imputation, field substitution, proxy substitution, or silent dimension-level
omission where mandatory coverage applies.

Existing exact-zero and negative-denominator behavior and precedence remain
unchanged. No universal arbitrary near-zero floating-point threshold is
introduced. Any economically material near-zero rule must be denominator-aware,
separately governed, fixed ex ante, and never chosen using realized outcomes.

## 9. Dimensions, ranking, and aggregation

Required dimensions are exactly, in order:

1. `VALUATION`;
2. `BUSINESS_ECONOMICS`; and
3. `FUNDAMENTAL_CHANGE`.

All three are mandatory. Both `fcf_ev` and `ebit_ev` are mandatory for
CandidateSet eligibility; a security missing either cannot enter the V1
CandidateSet. Separately admissible private accounting diagnostics do not
create an accounting-only CandidateSet route.

The rank transformation is the existing governed
`cross_sectional_percentile_rank`. Within a dimension, eligible governed proxy
ranks receive equal weight. A dimension with more proxies does not receive
greater total weight. Across dimensions, the three required dimensions receive
exactly equal weight. Required coverage is not silently reweighted through
`skipna` behavior.

The GovernedRankingArtifact protected digest and selector scope remain exactly:

```text
[security_id, decision_date, composite_score]
```

CandidateSet membership is not added to or substituted into that scope.

## 10. CandidateSet contract boundary

CandidateSet remains a separate governed artifact. Its resolved V1 policy is:

```text
selection_rule = TOP 100
ordering = [composite_score descending, stable security_id ascending]
candidate_sets = 1
tiers = none
```

If fewer than 100 fully governed eligible securities remain, processing fails
closed with diagnostic meaning exactly
`INSUFFICIENT_ELIGIBLE_POPULATION`. `TOP 100` never means “all available.”

This contract does not create a CandidateSet. A CandidateSet is not a BUY list
and does not authorize portfolio construction, trading, transactions, or money
movement.

## 11. Preserved Run 1 and Run 2 invariants

Run 1 invariants remain unchanged, including point-in-time selection, exact
provenance, denominator governance, verified Proxy Registry requirements, no
fallback, clean-tree gating, governed feature semantics, and fail-closed
resolution of missing authority.

Run 2 invariants remain unchanged, including the specification budget, durable
OPEN/CLOSE lifecycle, Specification Register semantics, outcome-free preflight,
universal authorized outcome execution, and the prohibition on realized-
outcome use before full authorization.

Screen construction consumes no realized-outcome research slot and requires no
OPEN/CLOSE outcome run merely to construct the screen. Realized-outcome
evaluation still requires full Entry001, available budget, durable OPEN,
authorized execution, and CLOSE. No outcome can influence these Screen v2
policy bytes.

## 12. Deferred production provider and data evidence

The following production prerequisites are unresolved blockers, in exact order:

1. production provider/product topology;
2. exact historical sample boundaries;
3. provider-native immutable security identifiers;
4. vendor/native field mappings;
5. production field-catalog identity;
6. survivorship-complete and historically valid security-master evidence;
7. issuer/security/listing crosswalk evidence;
8. exact production historical market-data product;
9. provider/archive evidence identities;
10. archive/reproducibility rights where required for governed research;
11. entitlement/access evidence where relevant;
12. historical exchange-calendar/session evidence;
13. exact missing-session/stale-price bound;
14. corporate-action timing and effective-event treatment;
15. point-in-time shares construction;
16. total market-capitalization construction;
17. enterprise-value construction;
18. historical operating-company taxonomy source;
19. exact invested-capital field construction;
20. denominator-specific near-zero materiality values;
21. unresolved unit-normalization details;
22. production CandidateSet evidence identities; and
23. exact production provider capability verification.

No item acquires a default, selected source, inferred identity, or resolved
state from this contract.

## 13. Provider policy and historical-data limitation

No production provider is selected. Free or public data may be used only for
development, fixtures, provider-neutral adapter work, and coverage diagnostics,
with explicit limitations. Such data is not production-admissible unless it
actually satisfies the complete governed capability and evidence contract.

Current or live SEC Company Facts alone are historically inadmissible for
point-in-time research unless exact historical observation and historical
public-availability provenance are separately established. Present-day revised
facts cannot silently represent historical first-reported facts.

## 14. Production execution gate

Production execution cannot produce a real governed CandidateSet unless the
closed readiness state in Section 3 verifies all of the following:

- approved governing Screen v2 identity;
- required Architecture and Ledger authority;
- resolved provider/data evidence;
- verified point-in-time provider capability;
- verified security master;
- verified historical-universe evidence;
- verified field catalog;
- verified market timing/session evidence;
- verified source/native mappings;
- exact provenance;
- all mandatory proxy coverage semantics;
- required valuation coverage; and
- implementation/configuration identity consistency.

Every identity is verified using the existing repository/path/commit/blob/
exact-byte-SHA convention where applicable. Document existence is not
repository verification. An unresolved, missing, conflicting, or unverified
mandatory prerequisite fails closed: production execution remains blocked and
no CandidateSet is produced.

## 15. Existing implementation and Entry000 boundaries

The current repository implementation preserves the Screen v1 closed artifact,
outcome-free preflight, protected ranking scope, and separate unproduced
CandidateSet boundary. It does not implement, freeze, or publish a production
Screen v2 instance. Existing code and tests are not modified by this contract.

Entry000 remains unchanged. This contract does not modify package ID
`f7ee66db47f1ebd0b4258507995b2f57e1c7e3b1f8c5139492a0005957bdb914`,
rewrite the current six-component package, or create a successor Entry000.
Any future package succession is separate governed work.

## 16. Immutability and future changes

Once governing, these Screen v2 bytes remain immutable. They apply
prospectively to future governed screen instances and never rewrite Screen v1.
The V1 policy remains immutable.

After the first governed realized outcome, any outcome-influenced change must
create a successor specification, preserve Screen v2 unchanged, identify the
change as hypothesis-driven and/or outcome-informed, follow the existing
outcome-governance process, and never silently retune V1 parameters.

## 17. Approval, production, and transaction boundary

Creating or committing these bytes, creating or committing an Approval Record,
opening or merging a pull request, or referencing this contract does not make
Screen v2 governing. Governing effect begins only after the researcher
explicitly approves the exact final merged ApprovalRecordIdentity for these
subject bytes.

Even after that approval, production execution remains blocked until Section 3
and Section 14 pass with separately admitted evidence. This contract creates no
provider binding, production screen instance, CandidateSet, outcome authority,
portfolio, recommendation, trading authority, transaction authority, fiduciary
undertaking, or money-movement authority.
