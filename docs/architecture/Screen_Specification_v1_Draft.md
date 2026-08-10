# Screen Specification v1 — Draft Contract

## 1. Status, purpose, and authority

**Status:** DRAFT — not implemented, final, or frozen.
**Authority:** subordinate contract proposed under Architecture v3.2 and
ADR-002/ADR-003. Architecture v3.1 remains immutable historical evidence.

The Screen Specification freezes only the deterministic path from a historical
eligible population through PIT facts, accounting semantics, Proxy Registry,
and ranking configuration to a ranked candidate set. It is not a BUY list,
portfolio specification, or outcome-evaluation specification.

No vendor is selected. No realized outcome has been examined. No Entry artifact
or Screen Specification has been frozen.

## 2. Versioning and relationship to Entry 000

The proposed contract version is `screen_specification_schema_version: 1`.
Entry 000 must bind the governing Architecture v3.2 and this approved contract
identity before a production freeze is authoritative. A frozen screen instance
must record the Entry 000 package schema, package ID, and package digest; it may
not accept an arbitrary architecture string.

Any semantic field, digest scope, canonicalization, or required-lineage change
requires a new schema version. Existing frozen versions remain immutable.

## 3. Proposed closed top-level contract

A future implementation should use an exact-key object containing:

- schema and artifact identity;
- Entry 000 package identity/digest;
- governing architecture version;
- universe and security-master lineage;
- PIT fact-source lineage and source manifests;
- accounting-semantics identity/digest;
- Proxy Registry identity/digest;
- required dimensions;
- ranking-configuration identity/digest;
- research-vintage bundle;
- code commit identities and clean-tree attestation;
- candidate-artifact schema and digest scope;
- deterministic canonicalization identifier;
- creation and approval attestations.

Unknown keys, missing keys, unresolved required execution values, and mismatched
versions fail closed.

## 4. Allowed inputs

Only inputs participating in candidate construction are allowed:

1. a frozen, date-effective universe artifact;
2. its survivorship-complete security-master lineage;
3. governed PIT fact datasets and manifests;
4. approved accounting identities and normalization semantics;
5. a frozen Proxy Registry;
6. the required dimensions Valuation, Business Economics, and Fundamental
   Change;
7. a frozen ranking configuration;
8. source and research-vintage identities;
9. exact feature-generation and ranking code commits; and
10. deterministic decision dates and candidate-output rules.

## 5. Forbidden inputs and operations

The contract and every API implementing it must reject:

- any held-return source or held-return manifest;
- benchmark-return sources;
- forward-return fields;
- future price change or other realized-outcome fields;
- portfolio returns, holdings accounting, transaction costs, or terminal-return
  inputs;
- IC, realized quantile/decile, long-short, backtest, Sharpe, drawdown, hit-rate,
  or realized Rule-17 evaluation parameters;
- outcome callbacks, outcome joins, cached outcome statistics, and outcome-
  derived labels; and
- current-survivor membership or current/live data substituted for historical
  PIT inputs.

It cannot consume, calculate, inspect, summarize, serialize, log, or expose any
realized future outcome. Structural absence is required; redaction after
calculation is not compliance.

## 6. Universe identity and security-master lineage

The frozen universe input must bind an artifact ID, schema version, SHA-256,
eligibility-rule digest, decision-date range, and ordered source lineage. The
security-master record must bind source ID, source-native vintage, content,
manifest and audit-artifact digests, stable identifier scheme, and date-effective
listing/security-status semantics.

It must support primary-listed common operating-company equities and exclude
ADRs, secondary listings, preferred securities, and ETFs/funds. It must retain
historically eligible names after delisting, bankruptcy, acquisition, ticker or
exchange change, or disappearance. Current-survivor-only construction fails.

Practical-investability rule families—size, price, liquidity, and seasoning—are
required, but their exact thresholds, fields, windows, currencies, timestamps,
adjustments, and duration remain unresolved pending Batch 2.

## 7. PIT fact-source lineage

Every fact source must bind source-manifest schema, kind, source ID,
research-vintage bundle, source-native vintage, content SHA-256, audit-artifact
SHA-256, manifest SHA-256, and provenance class. Facts must retain their actual
availability timestamp, reporting-period identity, version/restatement identity,
unit, and accession or equivalent provenance. Runtime lineage overrides are
forbidden.

## 8. Accounting semantics identity

The specification must bind a versioned accounting-semantics artifact and digest
covering field taxonomy, units/currencies, fiscal-period selection, restatement
policy, alignment, numerator/denominator construction, sign, missingness,
transformations, and negative/zero/near-zero denominator actions. No exact
normalization or denominator threshold is chosen in this draft.

## 9. Proxy Registry and required dimensions

The specification must bind the exact Proxy Registry digest and its schema and
artifact identities. Every proxy must be executable and fully resolved for the
screen. The required dimensions are exactly:

1. Valuation;
2. Business Economics; and
3. Fundamental Change.

Valuation is essential. Inability to obtain historically valid market data
returns the issue to the researcher; it does not permit deletion or an
accounting-only silent substitute.

## 10. Ranking configuration

The exact ranking-configuration digest must bind feature transformations,
direction, missingness/coverage rules, feature-to-dimension mapping, dimension
combination, final combination, sector treatment if approved, candidate count or
selection rule if applicable, deterministic tie-break, numeric canonicalization,
and implementation schema version. A runtime override is forbidden.

## 11. Data vintage, source manifests, and code identity

All input manifests must agree with the Screen Specification research-vintage
bundle while retaining independent native-vintage identities. The specification
must bind feature-generation, universe-construction, accounting, and ranking Git
commit identities. Each must be a full commit ID from the attested repository.
Creation requires a clean working tree; the attestation must bind repository
identity, commit, and `dirty: false`. No data vendor is selected here.

## 12. Deterministic candidate artifact

The candidate artifact must have a versioned schema, canonical row ordering,
canonical scalar/date/score encoding, and exact decision-bearing digest scope.
At minimum its bound selection identity includes stable `security_id`, decision
timestamp/date, and final composite score. Any eligibility or selection field
read by the selector must also be content-bound. Selector authority must never
exceed digest scope.

The artifact must bind:

- frozen Screen Specification digest;
- universe/security-master digests;
- fact-source lineage;
- accounting-semantics digest;
- Proxy Registry digest;
- ranking-configuration digest;
- research-vintage bundle;
- relevant commits; and
- ranked content digest and digest-scope identifier.

## 13. Output allowlist

Outputs are limited to the frozen manifest/lineage, verification metadata,
eligibility/exclusion evidence needed to reproduce the screen, PIT feature and
dimension values where explicitly in the versioned schema, and deterministic
candidate identity/rank/score fields.

No forward return, held return, benchmark return, realized IC, realized bucket
return, spread, portfolio statistic, or other future-outcome derivative may
appear in the artifact, auxiliary columns, logs, diagnostics, or sidecars.

## 14. Relationship to Entry 001 and outcome governance

Screen construction consumes no outcome-research slot and requires no OPEN or
CLOSE. Entry 001 remains mandatory before any outcome evaluation. A later Entry
001 must bind, without runtime substitution:

- exact Screen Specification artifact ID, schema, and SHA-256;
- exact ranked-artifact ID, schema, digest, and digest scope;
- exact ranked-artifact lineage;
- exact universe, sources, manifests, research and native vintages;
- exact accounting, Proxy Registry, and ranking digests; and
- exact relevant commits.

Only after full Entry 001, budget availability, and durable OPEN may authorized
execution access realized outcomes; it must then append CLOSE. A different
screen or candidate artifact cannot be substituted after outcome observation.

## 15. Immutability, no-overwrite, and verification

Freeze must canonicalize and hash a fully resolved exact-key payload, write it
once, and write a companion digest sidecar. Neither file may pre-exist. Partial
writes must fail visibly. Verification must rehash the payload, validate the
sidecar, schema, exact keys, component digests, ordering, provenance, clean-tree
attestation, and candidate-artifact linkage. Verification never calculates an
outcome.

## 16. Failure semantics

Missing, malformed, unresolved, unknown, nonfinite, inconsistent, dirty,
unverifiable, future-dated, outcome-bearing, or lineage-mismatched inputs fail
closed before candidate publication. Unsupported source capability triggers:

`unsupported capability → return to researcher → no silent substitution`

Failure before any outcome OPEN consumes no outcome-research slot. The system
must not emit a partially governed candidate artifact.

## 17. Migration and compatibility

The current governed ranked artifact is Entry-001-bound and must not be silently
reinterpreted as Screen Specification v1. Migration requires a new schema or an
explicit dual-authority field, deterministic conversion rules, and tests proving
that old Entry 001 artifacts retain their original meaning. Unknown future
versions fail closed. Frozen v1 artifacts remain verifiable under v1 rules.

## 18. Required implementation tests

Before implementation can be approved, tests must cover:

- exact schema keys/version and unknown-version rejection;
- unresolved/malformed value rejection;
- direct-constructor/capability forgery rejection;
- freeze, sidecar, no-overwrite, and partial-write behavior;
- hash, order, provenance, vintage, component and commit tampering;
- clean/dirty repository attestations;
- current-survivor and date-effectivity failures;
- Proxy Registry, accounting and ranking semantic changes changing digests;
- deterministic reproduction and row-order canonicalization;
- selector authority not exceeding digest scope;
- absence and rejection of held, benchmark and forward returns;
- absence and rejection of IC, buckets, spreads, backtests and outcome callbacks;
- no outcome-research budget use and no OPEN/CLOSE during screen construction;
- Entry 001 binding the exact screen and rejecting substitutions;
- durable OPEN preceding the first outcome-bearing operation; and
- backward-version verification and explicit migration rejection.
