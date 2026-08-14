# A22 data-admission packets

Status: provider-neutral implementation material. These bytes are not governing
authority, provider evidence, production admission, or a CandidateSet.

## Authority conclusion

Architecture v3.2 places executable schemas/code below approved researcher
decisions and subordinate contracts. V1 Research Policy Section 15 and Screen
v2 Section 12 expressly leave the production items unresolved and prohibit
turning them into defaults. The sample-validation range can be recorded by the
existing non-production admission mechanism. Provider selection, production
sample dates, mappings, and economic/timing policies remain researcher
decisions under Architecture v3.2. They need a new exact authority subject and
normal Approval Record v1 handling before production use.

The code may derive hashes and exact byte identities after admission; derived
identities prove content, not human approval.

The production gate therefore carries an explicit empty approved-decision
authority registry and reports every required decision ID as unresolved. It
does not scan committed Approval Records and mistake their existence for the
researcher's external approval event.

## RESEARCHER DECISION PACKET — ALL REMAINING HUMAN INPUTS

The machine-readable packet is returned by:

```text
PYTHONPATH=src python -m graham_research.cli a22-admission-audit
```

Required before the first real run:

| ID | Decision | Authority path |
|---|---|---|
| RD-001 | Production provider/product topology | `NEW_AUTHORITY_REQUIRED` |
| RD-002A | Initial production-validation range | `EXISTING_PRODUCTION_FREEZE_MECHANISM` |
| RD-002B | First governed screen decision date | `NEW_AUTHORITY_REQUIRED` |
| RD-004 | Native/canonical mappings and field catalog | `NEW_AUTHORITY_REQUIRED` |
| RD-008 | Historical market-data product | `NEW_AUTHORITY_REQUIRED` |
| RD-013 | Missing-session/stale-price bound | `NEW_AUTHORITY_REQUIRED` |
| RD-014 | Corporate-action continuity/effective-event policy | `NEW_AUTHORITY_REQUIRED` |
| RD-015 | PIT total-shares construction | `NEW_AUTHORITY_REQUIRED` |
| RD-016 | Total-market-capitalization construction | `NEW_AUTHORITY_REQUIRED` |
| RD-017 | Enterprise-value construction | `NEW_AUTHORITY_REQUIRED` |
| RD-018 | Historical operating-company taxonomy source/mapping | `NEW_AUTHORITY_REQUIRED` |
| RD-019 | Invested-capital canonical construction | `NEW_AUTHORITY_REQUIRED` |
| RD-020 | Denominator-specific near-zero materiality | `NEW_AUTHORITY_REQUIRED` |
| RD-021 | Unit/currency normalization | `NEW_AUTHORITY_REQUIRED` |
| RD-022 | Governing CandidateSet evidence identity schema | `NEW_AUTHORITY_REQUIRED` |
| RD-CROSSWALK-001 | Massive-to-Databento identity/listing crosswalk | `NEW_AUTHORITY_REQUIRED` |

RD-002C, the full intended historical research range, is required before
multi-date historical research but not before the first single-date screen.
The CLI packet records the exact question, governing clause, allowed domain,
tradeoffs, downstream field, successor implications, and attestation need for
every decision.

### Copy-pastable declaration template

```text
A22 RESEARCHER DECISION DECLARATION — VALUES NOT YET SUPPLIED

researcher_id = <REQUIRED>
decided_at_utc = <REQUIRED ISO-8601 UTC>
no_realized_outcome_statement =
  No realized strategy outcome was examined in making these decisions.

RD-001.provider_product_topology = <LEGAL PROVIDER(S), PRODUCT ID(S), JOIN TOPOLOGY>

RD-002A.validation_start = <YYYY-MM-DD>
RD-002A.validation_end = <YYYY-MM-DD>
RD-002B.first_governed_screen_decision_date = <YYYY-MM-DD>
RD-002C.full_research_start = <YYYY-MM-DD | DEFERRED>
RD-002C.full_research_end = <YYYY-MM-DD | DEFERRED>

RD-004.field_catalog =
  <EFFECTIVE-DATED NATIVE/CANONICAL MAPPINGS AND EVIDENCE IDENTITIES>

RD-008.historical_market_data_product =
  <LEGAL PROVIDER, PRODUCT ID/VERSION, RAW CLOSE/VOLUME PRODUCT>

RD-013.age_metric = <CALENDAR_TIME | COMPLETED_SESSION_COUNT | BOTH>
RD-013.maximum_age = <POSITIVE VALUE WITH UNIT>
RD-013.missing_session_behavior = <EXPLICIT FAIL-CLOSED RULE>

RD-014.ticker_change = <IDENTITY/CONTINUITY RULE>
RD-014.split = <RAW-DATA/SHARES/IDENTITY RULE>
RD-014.reverse_split = <RAW-DATA/SHARES/IDENTITY RULE>
RD-014.merger = <PREDECESSOR/SUCCESSOR RULE>
RD-014.spinoff = <PREDECESSOR/SUCCESSOR RULE>
RD-014.delisting = <TERMINAL/CONTINUITY RULE>
RD-014.exchange_transfer = <LISTING CONTINUITY RULE>
RD-014.spac_business_combination = <BOUNDARY/IDENTITY RULE>
RD-014.effective_timestamp_rule = <EXPLICIT RULE>

RD-015.total_shares_concept = <EXACT CANONICAL CONCEPT>
RD-015.source_or_construction = <NATIVE FIELD OR COMPONENT FORMULA>
RD-015.public_availability_rule = <EXPLICIT RULE>

RD-016.total_market_cap_construction =
  <NATIVE TOTAL MARKET CAP MAPPING | RAW CLOSE TIMES PIT TOTAL SHARES>
RD-016.timing_alignment = <EXPLICIT PRIOR-SESSION RULE>

RD-017.enterprise_value_construction =
  <NATIVE EV MAPPING | ENUMERATED COMPONENT FORMULA>
RD-017.timing_alignment = <EXPLICIT RULE>

RD-018.operating_company_taxonomy =
  <NATIVE TAXONOMY SOURCE, EFFECTIVE-DATED INCLUDED/EXCLUDED MAPPING>

RD-019.invested_capital_construction = <EXACT COMPONENTS/SIGNS>
RD-019.period_and_timing = <EXPLICIT RULE>

RD-020.enterprise_value = <THRESHOLD USD; ACTION>
RD-020.average_total_assets = <THRESHOLD USD; ACTION>
RD-020.income_before_tax_for_effective_tax_rate = <THRESHOLD USD; ACTION>
RD-020.average_invested_capital = <THRESHOLD USD; ACTION>
RD-020.current_revenue = <THRESHOLD USD; ACTION>
RD-020.prior_revenue = <THRESHOLD USD; ACTION>
RD-020.prior_revenue_for_current_growth = <THRESHOLD USD; ACTION>
RD-020.two_year_prior_revenue_for_prior_growth = <THRESHOLD USD; ACTION>

RD-021.per_field_normalization =
  <NATIVE UNIT, POSITIVE SCALE, CANONICAL UNIT, CURRENCY RULE, EFFECTIVE RANGE>

RD-022.governing_identity_fields = <EXACT CLOSED FIELD LIST>
RD-022.canonicalization = <EXACT APPROVED CANONICALIZATION>

RD-CROSSWALK-001.identity_scheme =
  <EXACT CONTENT-BOUND ISSUER/SECURITY/LISTING IDENTITY SCHEME>
RD-CROSSWALK-001.match_rule =
  <DECISION DATE + MASSIVE TICKER/PRIMARY MIC/SHARE-CLASS FIGI + DATABENTO
   DATASET/HISTORICAL SYMBOLOGY/INSTRUMENT ID/DEFINITION INTERVAL>
RD-CROSSWALK-001.missing_or_ambiguous_behavior = <FAIL CLOSED>

I understand that this declaration is project-governance input only. It is not
trading, transaction, portfolio-construction, or money-movement authority.
```

The declarations whose authority path is `NEW_AUTHORITY_REQUIRED` do not become
governing merely by filling this template. They need a valid authority subject,
source commit/path/blob/SHA-256 identity, Approval Record v1, and explicit human
approval. For RD-002B/C, current authority does not specify the exact subject
schema, but Architecture v3.2 still requires a new authority subject and normal
Approval Record before either value may govern.

## PROVIDER EVIDENCE PACKET — ALL REQUIRED EXTERNAL EVIDENCE

The closed 25-capability specification is
`PROVIDER_CAPABILITY_SPECIFICATION` in `graham_research.admission`. Each entry
contains `capability_id`, `required`, `evidence_type`, minimum documentation,
minimum sample, machine-verifiable acceptance test, and fail-closed behavior.

### A. Fundamentals

CAP-005 through CAP-008: annual PIT facts, explicit duration boundaries,
first-reported/revision pairs, public timestamps, filing/accession/native IDs,
and extract vintage.

### B. Security master

CAP-009, CAP-010, CAP-012, CAP-013: active plus inactive/delisted coverage,
effective-dated master records, primary-listing history, and historical taxonomy.

### C. Market data

CAP-015 through CAP-017: raw unadjusted close, raw volume, and PIT total-shares
evidence with exact definitions and timestamps.

### D. Exchange sessions

CAP-018: exchange-local timezone, open, close, completed/holiday/cancelled status,
and historical coverage.

### E. Corporate actions

CAP-014: native event IDs, announcement/effective timestamps, predecessor/
successor lineage, splits, mergers, spinoffs, delistings, transfers, and SPAC
business-combination boundaries where present.

### F. Identifiers/crosswalks

CAP-011 and CAP-019: immutable native issuer/security/listing IDs and effective-
dated internal/native crosswalks.

### G. Field metadata/mappings

CAP-020, CAP-021, CAP-025: native definitions, units/scales/currencies, effective
ranges, and exact native-to-canonical mapping evidence. Name similarity is not
evidence.

### H. Archival/reproducibility

CAP-004, CAP-023, CAP-024: retention/reproduction rights, native vintage/archive
identity, immutable detached bytes, and reproducible SHA-256.

### I. Entitlement

CAP-003: dated entitlement scope for each required product.

### J. Samples

CAP-001, CAP-002, and CAP-022 plus the sample-bearing capabilities above:
provider/product/version metadata, coverage boundaries, and the detached sample
files referenced by the non-evidence admission pack.

Different capability groups may come from different products or providers.
Every cross-provider issuer/security/listing or field join then requires its own
effective-dated, content-bound crosswalk evidence. No provider is selected here.

## CandidateSet identity boundary

`CandidateSetDerivedIdentity` binds exact CandidateSet bytes, byte length,
ranking digest, Screen v2 configuration digest, batch lineage, eligible-
population digest, selection-rule digest, decision date, and admitted production-
manifest digest. It is reproducible and fail-closed on mismatch. Its status is
exactly `NON_GOVERNING_DERIVED_IDENTITY`.

This closes the internal hashing implementation but not the governing portion
of EXT-022. The protected ranking digest remains exactly `security_id`,
`decision_date`, and `composite_score`.

## Denominator packet

Every denominator is in canonical USD. Exact zero always excludes the feature
under the existing type invariant. Negative behavior remains whatever the
applicable frozen denominator policy explicitly binds; code does not choose it.

| Denominator | Proxy use |
|---|---|
| enterprise_value | fcf_ev, ebit_ev |
| average_total_assets | gross_profitability |
| income_before_tax_for_effective_tax_rate | roic |
| average_invested_capital | roic |
| current_revenue | operating_margin_change, fcf_margin_change |
| prior_revenue | operating_margin_change, fcf_margin_change |
| prior_revenue_for_current_growth | revenue_acceleration |
| two_year_prior_revenue_for_prior_growth | revenue_acceleration |

Near-zero handling cannot be disabled as a shortcut under the current runtime
schema: it requires a positive finite, denominator-specific absolute threshold.
No universal threshold is permitted.

## Validation commands

```text
PYTHONPATH=src python -m graham_research.cli \
  validate-provider-sample-v2 path/to/sample-pack.json --repository .

PYTHONPATH=src python -m graham_research.cli a22-admission-audit
```

The structural template at
`examples/non_evidence/provider_sample_admission.template.json` intentionally
contains no evidence. Its false capability flags, null paths, placeholder
hashes, and `PROVIDER_SAMPLE_CANDIDATE_NOT_ADMITTED` status prevent accidental
production admission.
