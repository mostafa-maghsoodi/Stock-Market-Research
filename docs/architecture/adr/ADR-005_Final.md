# ADR-005 — Screen Specification v2 Succession and Policy/Data-Evidence Separation

## ADR ID

`ADR-005`

## Title

Screen Specification v2 Succession and Policy/Data-Evidence Separation

## Document version

`1.0`

## Status

FINAL — approval state is external to these bytes. This document does not
self-attest approval. Governing effect is determined only by the applicable
external Approval Record identity and human approval process.

## Decision

Screen Specification v1 remains immutable historical authority. Screen
Specification v2 is the successor contract for future governed screen
instances.

Research-policy resolution and production-data readiness are separate states.
Policy resolution alone must never imply production execution readiness.
Production execution requires separate verification and authority binding of:

- provider evidence;
- field-catalog evidence;
- historical security-master evidence;
- archive evidence;
- timing evidence;
- source/native mapping evidence; and
- exact provenance evidence.

The governing V1 Research Policy is the research-policy predecessor and context
for Screen Specification v2. Production provider and data evidence remains
unresolved until separately verified and authority-bound.

## Preserved governance invariants

Existing Run 1 governance remains unchanged, including point-in-time selection,
exact provenance, denominator governance, verified registry requirements, no
fallback, clean-tree gating, and governed feature semantics.

Existing Run 2 governance remains unchanged, including the specification
budget, durable OPEN/CLOSE lifecycle, Specification Register semantics,
outcome-free preflight, and the prohibition on realized-outcome use before
authorization.

The GovernedRankingArtifact retains its exact protected digest scope:

1. `security_id`;
2. `decision_date`; and
3. `composite_score`.

CandidateSet remains a separate governed artifact. It is not a renamed or
expanded GovernedRankingArtifact and is not a BUY list.

## Screen Specification v2 boundary

The future Screen Specification v2 contract must separately define a closed
representation of:

1. policy resolution;
2. provider and data-evidence resolution;
3. repository identity verification; and
4. production execution readiness.

It must preserve the invariant that `POLICY_RESOLVED` does not imply
`PRODUCTION_EXECUTION_READY`. Exact enum names and the complete closed schema
remain future Screen Specification v2 contract-design matters. This ADR
establishes the authority direction but does not create that contract.

## Provider and data status

No production provider is selected. This decision does not resolve:

- provider or product topology;
- historical sample boundaries;
- provider-native identities;
- field mappings;
- field-catalog bytes;
- security-master evidence;
- historical market-data product;
- source or archive identities;
- missing-session or stale-price bounds;
- corporate-action timing implementation;
- PIT shares, market-capitalization, or enterprise-value construction;
- operating-company taxonomy source;
- invested-capital construction;
- denominator-specific near-zero materiality; or
- ungoverned normalization details.

These remain production-execution blockers and must not acquire defaults from
this ADR.

## Amendment Ledger semantics

The later Amendment Ledger entry for this decision has exactly these semantic
values:

```text
amendment_id = ADR-005
decision_class = EXTENSION
affected_rule_id = SCREEN_SPECIFICATION_SUCCESSION_AND_READINESS_SEPARATION
effective_boundary = POST_V1_POLICY_ADOPTION_BEFORE_SCREEN_V2_PRODUCTION_INSTANCE
prior_rule_exact_text_sha256 = null
replacement_rule_exact_text = null
replacement_rule_exact_text_sha256 = null
```

ADR-005 is an extension and does not perform exact-text supersession. It must
not be reclassified as `EXACT_SUPERSESSION`.

## Required later authority and contract changes

After ADR-005 becomes governing, a future Amendment Ledger v1.1.0 may add it as
ordinal 5 under the separately supplied ledger design and approval sequence. A
future Screen Specification v2 contract may then implement this decision's
successor direction and readiness separation.

Architecture v3.2 remains governing. No Architecture v3.3 or other successor
Architecture document is required, and Architecture v3.2 is not modified.

The existing Amendment Ledger v1.0.0, Screen Specification v1, and Entry000
remain immutable and unchanged. Any later governing-ledger and Entry000
succession must follow their separately approved versioning and approval
contracts.

## Scope

This decision is limited to the Screen Specification v2 succession direction,
the separation of resolved research policy from verified production evidence,
and preservation of the existing screen, ranking, CandidateSet, and outcome
governance boundaries.

## Outcome and transaction boundary

The V1 policy was adopted ex ante. No realized strategy outcome is required for
this succession, and screen construction remains outcome-free. Any outcome
evaluation remains subject to the existing Run 2 Entry001, budget, durable
OPEN, authorized execution, and CLOSE requirements.

This ADR creates no portfolio, trading, transaction, or money-movement
authority. It is solely an internal research-project governance and audit-trail
decision.

## What this decision does NOT authorize

It does not create or approve Screen Specification v2, Amendment Ledger v1.1.0,
a new Entry000, a production provider, provider evidence, a field catalog, a
production screen instance, a CandidateSet, realized-outcome access, portfolio
construction, trading, or money movement.

## Relationship to the V1 Research Policy

`docs/research/V1_Research_Policy_Final.md` is the separately governing
`RESEARCH_INTENT` predecessor and policy context for this decision. Its approval
does not approve ADR-005, and ADR-005 does not modify or replace it.

## Relationship to Architecture v3.2

ADR-005 operates under Architecture v3.2's amendment methodology. It extends
the subordinate Screen Specification direction while preserving Architecture
v3.2 unchanged.

## Relationship to Amendment Ledger

This ADR is an independently addressable `ADR_RECORD` subject intended for the
future Amendment Ledger v1.1.0 only after ADR-005 receives governing approval.
Its presence in a future ledger cannot substitute for its own Approval Record
and external human approval.

## Relationship to Entry000

This ADR is not an additional member of the existing Entry000 six-component
array. Existing Entry000 bytes and repository-verified identity remain
unchanged. Any future binding through a successor governing ledger requires the
separate authority and package-versioning process.

## Researcher approval boundary

Preliminary authorization to prepare this subject is not governing approval.
Governing approval occurs only after these exact subject bytes are committed,
an Approval Record identifying their path/source-commit/blob/SHA-256 is created
and committed, and the researcher explicitly approves the exact final merged
Approval Record identity.
