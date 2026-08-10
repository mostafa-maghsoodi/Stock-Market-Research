# Batch 1 Research Intent — Draft Decision Record

## Status and governing rule

**Status:** DRAFT proposed detailed record of separately approved Q1, Q2, Q3,
Q5, and Q8 intent. It becomes authoritative only when the researcher explicitly
approves this file's exact immutable identity.
**Architecture:** Architecture v3.2 successor direction; Architecture v3.1
remains immutable historical evidence.
**Research state:** before Batch 2; no vendor selected; no realized outcomes
examined; this draft implements and freezes no artifact.

For every decision below:

`unsupported capability → return to researcher → no silent substitution`

The Screen Specification is outcome-free. Entry 001, budget, durable OPEN,
authorized execution, and CLOSE remain mandatory before realized-outcome use.

## Q1 — Screen objective

### Approved intent

The systematic screen identifies operating-company candidates combining
attractive valuation, strong business economics, and improving fundamentals.
It generates candidates for later deep research and is not a final BUY list.

### Binding conceptual constraint

The screen has exactly three required conceptual dimensions: Valuation,
Business Economics, and Fundamental Change. Its output role is a deterministic
ranked candidate set, not a recommendation or portfolio.

### Deferred decisions

Exact proxies, transformations, missingness, weights, ranking details, candidate
count, and deep-research disposition remain subject to their approved contracts
and data validity.

### Dependencies

- **Source:** survivorship-complete universe, PIT fundamentals, and valid
  historical market data.
- **Architecture:** Architecture v3.2 and a frozen Screen Specification.

### Forbidden silent narrowing and escalation

The screen may not lose one of the three dimensions, become a BUY list, or be
narrowed to currently supported accounting features. Unsupported capability
returns to the researcher without substitution.

## Q2 — Security population

### Approved intent

V1 includes primary-listed common operating-company equities. ADRs, secondary
listings, preferred securities, and ETFs/funds are out of scope. Expansion
requires a later separately governed scope change.

### Binding conceptual constraint

The inclusion and exclusion categories are conceptually fixed. Eligibility is
date-effective and applies to securities, listings, and operating-company type.

### Deferred decisions

Exact exchanges/geographies, vendor field mapping, legal/security taxonomy,
primary-listing determination, identifier mapping, and corporate-event mapping
remain unresolved.

### Dependencies

- **Source:** a survivorship-complete historical security master with
  date-effective listing and security types.
- **Architecture:** L1/universe schema and Screen Specification lineage.

### Forbidden silent narrowing and escalation

Missing classification data may not be replaced with present-day membership,
ticker heuristics, or a current-survivor list. Unsupported classification
capability returns to the researcher.

## Q3 — Survivorship

### Approved intent

Use the full date-effective historical eligible population. Historically
eligible securities remain represented if they later delist, go bankrupt, are
acquired, change ticker or exchange, or otherwise disappear. Current-survivor-
only construction is inadmissible.

### Binding conceptual constraint

A stable security identity, effective-dated eligibility, and complete historical
population are mandatory. Later disappearance cannot erase earlier eligibility.

### Deferred decisions

Exact security-master source, identifier-crosswalk rules, corporate-action and
terminal-event fields, effective timestamps, and coverage start remain
unresolved.

### Dependencies

- **Source:** historical security master, listing history, corporate actions,
  delisting/bankruptcy/acquisition records.
- **Architecture:** PIT L0, investable-universe L1, and frozen universe artifact.

### Forbidden silent narrowing and escalation

No present-day constituent list, active-ticker list, or survivorship proxy is
admissible. A shorter demonstrably valid period may be returned for researcher
approval; data standards cannot be relaxed silently.

## Q5 — Practical investability

### Approved intent

The population must be practically tradable at each historical decision date
and conceptually requires a broad size floor, price floor, liquidity floor, and
listing-seasoning requirement.

### Binding conceptual constraint

All four rule families belong in the primary population. Tiered or multiple
co-primary universes are deferred and are not authorized here.

### Deferred decisions

The thresholds, exact fields, windows, currencies, timestamp conventions,
adjustment conventions, and seasoning duration remain **UNRESOLVED pending
Batch 2**. This record selects none of them.

### Dependencies

- **Source:** historical price, shares/market capitalization, trading volume or
  ADV, listing history, corporate actions, and currency/FX if needed.
- **Architecture:** exact L1 universe artifact and frozen Screen Specification.

### Forbidden silent narrowing and escalation

Batch 2 may establish source capability and present reviewable alternatives; it
may not choose thresholds, omit a rule family, or substitute a vendor default.
Unsupported capability returns to the researcher.

## Q8 — Valuation

### Approved intent

Valuation is **ESSENTIAL** to the first systematic screen. Required dimensions
are Valuation, Business Economics, and Fundamental Change. Valuation may not be
silently removed because historical market data or implementation support is
difficult.

### Binding conceptual constraint

A valuation measure must relate economic/accounting information known at the
decision time to a historically valid contemporaneous price, market
capitalization, or enterprise value. Current price is not a historical input.

### Deferred decisions

Exact valuation proxies, market-data source, price/share/EV construction,
staleness bound, decision timestamp, market session/timezone, currency and
adjustment rules remain unresolved pending Batch 2 and researcher approval.

### Dependencies

- **Source:** audited historical market data and PIT accounting facts with
  compatible lineage and timing.
- **Architecture:** v3.2 valuation and market-role boundaries, accounting
  semantics, Proxy Registry, and Screen Specification.

### Forbidden silent narrowing and escalation

Neither an accounting-only substitute nor deletion of Valuation is permitted.
If historically valid valuation cannot be supported, the issue returns to the
researcher as an explicit architecture/research-scope decision.
