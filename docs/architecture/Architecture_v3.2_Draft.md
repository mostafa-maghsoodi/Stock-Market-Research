# Architecture v3.2 — Draft

## 1. Identity and status

**Status:** DRAFT — not final, not frozen
**Authority:** ADR-001 approves v3.2 as the post-Run-2 successor direction.
This exact document becomes governing authority only after the researcher
explicitly approves its immutable repository/path/commit/blob/SHA-256 identity.
Until that external human approval event, it remains draft text.
**Stage:** post-Run-2, before Entry 000 and before the Batch 2 data audit.
**Outcome attestation:** no realized strategy outcome was examined in preparing
this draft.

Architecture v3.2 is the proposed post-Run-2 successor architecture.
Architecture v3.1 remains immutable historical evidence. Nothing in this draft
rewrites v3.1 or represents a later decision as part of the original source.

## 2. Provenance from Architecture v3.1

The historical source components are:

1. `docs/architecture/Architecture_v3.1_Final.md`, the searchable historical
   representation; and
2. `docs/architecture/Architecture_v3.1_Final.pdf`, the preserved historical
   artifact.

Their exact identities belong in the future Entry 000 package manifest. Textual
equivalence between the two formats is not asserted merely because their titles
match. Both files remain unchanged. The implementation lineage is Run 1 commit
`587051d1aa77d2634a364c76061016bfca7dccc0` followed by Run 2 commit
`be1f9973e0aeeaaca80ab8f100a3de9a7a7c72db`. The canonical repository
identity for this authority system is exactly
`mostafa-maghsoodi/Stock-Market-Research`; case and spelling are significant.

## 3. Architecture authority hierarchy

For post-Run-2 work, authority descends in this order:

1. explicitly approved researcher decisions and ADRs;
2. Architecture v3.2, once approved;
3. approved subordinate contracts, including the Screen Specification;
4. the frozen Entry 000 architecture package;
5. a frozen Screen Specification for screen production;
6. the full frozen Entry 001 for outcome evaluation;
7. executable schemas and code, which implement but cannot invent authority.

Architecture v3.1 remains the historical predecessor and provenance source.
Where v3.2 does not amend it, its principles are inherited. Implementation
behavior alone never amends either architecture.

### 3.1 Authority materialization and approval bootstrap

ADR-001 through ADR-004 are four separately addressable `ADR_RECORD` subjects
at their governed repository paths. Each ADR requires its own Approval Record;
an Architecture v3.2 Approval Record cannot substitute for any ADR Approval
Record. The first machine-verifiable Amendment Ledger contains exactly four
entries, in order, for ADR-001, ADR-002, ADR-003, and ADR-004. Batch 1
Q1/Q2/Q3/Q5/Q8 is not duplicated in that ledger because Batch 1 Research Intent
is a separate Entry000 current-authority component. The first ledger path is
exactly
`docs/architecture/amendments/Amendment_Ledger_v1.0.0.json`.

Preliminary researcher authorization may direct preparation of a subject but is
not governing approval. Except for the single bootstrap below, governing
approval occurs only after subject bytes and their source commit/path/blob/
SHA-256 are known, an Approval Record is created and committed, its exact record
identity is known, and the researcher explicitly approves that identity.
Decision Approval Records must complete that sequence before their decisions
are eligible for ledger inclusion. The completed ledger follows the same
sequence after its own source commit and becomes authority only when the
researcher approves its exact committed ledger Approval Record identity;
Entry000 may then bind it.

The only bootstrap exception is
`docs/architecture/Approval_Record_v1_Final.md`. After that Final contract is
committed, the researcher may directly approve exactly its immutable
repository/path/source-commit/blob/SHA-256 subject identity. This exception
approves no other subject, is not reusable, and must be recorded in architecture
provenance and approval history without a self-referential Approval Record.
Every later approval uses Approval Record v1. A second bootstrap requires a new
approved architecture amendment.

Final documents use stable status semantics equivalent to `Status: FINAL —
approval state is external to these bytes.` A Final document does not
self-attest approval; governing effect is determined externally, and document
Final status is separate from implementation and freeze status. The canonical
repository identity in every governed identity is exactly
`mostafa-maghsoodi/Stock-Market-Research`, never a path, URL, branch, short SHA,
or display name.

## 4. Amendment methodology

Every later change must have an approval identifier, classify itself as a
clarification, extension, gap fill, or exact supersession, cite the affected
rule, state its effective boundary, and identify required contract changes.
Exact supersession requires both the old and replacement rule. Absence of a
current implementation is not supersession. Historical source files are never
edited to make later approval appear contemporaneous.

## 5. Run 1 reconciliation

Run 1 operationalized v3.1 without silently changing its research objective:

- PIT facts acquired explicit availability, reporting-period, frequency,
  restatement, and source-provenance semantics.
- The Proxy Registry received a closed executable representation and digest.
- Entry 001 received a versioned, strict schema and unresolved-value gate.
- Ranking received deterministic rank, missingness, weighting, and tie rules.
- Rank IC became explicitly cross-sectional by decision date; standalone,
  nested, and leave-one-out became distinct inputs.
- environment and source-control attestations became load-bearing.
- live/LLM output was separated from historically eligible research.
- market-role alignment and a survivorship-complete universe remained blocked
  rather than being guessed.

These are clarifications, extensions, and specification-gap fills. This draft
claims no exact v3.1 supersession from Run 1.

## 6. Run 2 reconciliation

Run 2 added portfolio/outcome binding governance:

- immutable governed fact and held-return source manifests;
- research-vintage, source-native-vintage, content, audit, and manifest binding;
- an independent held-return source;
- a content-bound ranked artifact and ranking-configuration digest;
- exact portfolio timing and economic-return convention attestation;
- deterministic, outcome-free preflight;
- a durable, append-only OPEN/CLOSE/blocked register;
- atomic research-budget reservation at OPEN;
- result lineage copied from a verified OPEN;
- pre-OPEN blocking of nonresearch portfolio outcome classes; and
- a universal authorized outcome-execution boundary.

Run 2 does not license outcome evaluation before Entry 001 or OPEN. Its
preflight/ranking preparation boundary is outcome-free. This draft claims no
exact v3.1 supersession from Run 2.

## 7. Batch 1 approved intent

The proposed detailed record of the separately approved Q1/Q2/Q3/Q5/Q8 intent
is `docs/research/Batch1_Research_Intent_Draft.md`. It becomes authoritative
only when the researcher approves its exact immutable identity.

- **Q1:** the screen finds operating-company candidates combining attractive
  valuation, strong business economics, and improving fundamentals; it is not a
  BUY list.
- **Q2:** V1 covers primary-listed common operating-company equities and
  excludes ADRs, secondary listings, preferred securities, and ETFs/funds.
- **Q3:** the historical eligible population is full and date-effective;
  current-survivor-only construction is inadmissible.
- **Q5:** broad size, price, liquidity, and seasoning rules are required in
  concept; exact operational values remain unresolved pending Batch 2.
- **Q8:** Valuation, Business Economics, and Fundamental Change are all required.
  Valuation is essential and cannot be silently dropped.

## 8. Unresolved decision ledger

The following remain unresolved and must not acquire defaults in this draft:

| ID | Decision | Resolution authority/time |
|---|---|---|
| U-001 | data vendor and exact source products | researcher after Batch 2 evidence |
| U-002 | universe thresholds, fields, windows, currencies, timestamps, adjustments, seasoning duration | researcher after Batch 2 |
| U-003 | exact accounting normalization and denominator thresholds | researcher after data audit |
| U-004 | exact surviving Proxy Registry formulas | audit plus researcher approval |
| U-005 | sample boundaries | researcher decision after reviewing valid PIT coverage |
| U-006 | exact specification budget | researcher before Entry 001/outcomes |
| U-007 | portfolio timing, costs, terminal/cash rules, and statistical procedures | researcher before Entry 001/outcomes |
| U-008 | valid historical market-price/EV construction and market-role alignment | Batch 2 evidence and researcher approval |

Unsupported capability must return to the researcher; it cannot trigger silent
substitution or narrowing.

## 9. Historical PIT-data principles

Historical inputs must reproduce what was knowable at each decision timestamp.
Material values require source provenance, actual availability timestamps,
explicit first-reported/restated identity, and an approved restatement policy.
Backfilled data, current classifications, current prices, nearest-date snapping,
and later survivor membership cannot masquerade as contemporaneous facts.
Coverage evidence may demonstrate that only a shorter period satisfies the PIT
standard and may propose that period to the researcher. It never automatically
selects or freezes sample boundaries; those remain a researcher decision.

## 10. Survivorship-complete universe requirement

Every historically eligible security remains representable after delisting,
bankruptcy, acquisition, ticker change, exchange change, or disappearance. A
universe derived from current survivors is invalid. Eligibility must be computed
from date-effective security and listing facts, not future status.

## 11. Practical-investability intent

The primary population must be practically tradable at each decision date and
must include conceptually a broad size floor, price floor, liquidity floor, and
listing-seasoning requirement. Exact thresholds, fields, windows, currencies,
timestamp conventions, adjustment conventions, and seasoning duration remain
unresolved. Tiered or co-primary universes are not authorized by this draft.

## 12. Historical security-master boundary

A future governed security-master layer must provide stable security identity,
date-effective listing and security types, primary-listing status, ticker and
exchange history, and corporate terminal events. It must separately identify
eligibility facts and terminal-return accounting. The current implementation
does not supply this survivorship-complete layer; Batch 2 must audit capability
before its schema is finalized.

## 13. Valuation historical-market-data requirement

Valuation is essential to the first screen. A valid historical valuation proxy
must align an approved price, market capitalization, or enterprise value with
accounting facts knowable at the same decision time and must bind source,
currency, adjustment, shares/capitalization, and staleness semantics. Current
prices may not stand in for historical prices. If valid capability is absent,
the issue returns to the researcher; Valuation is not silently removed.

## 14. Market-role timing/alignment blocker

Market-derived roles require an audited observation timestamp, decision cutoff,
market session and timezone, adjustment semantics, and exact alignment rule.
Calendar-date equality alone does not prove economic alignment. Until those
rules are approved, market-role proxies remain unfreezable.

## 15. Accounting normalization boundary

Accounting field identity, unit/currency treatment, fiscal-period selection,
restatement policy, numerator/denominator construction, sign treatment,
near-zero/negative-denominator behavior, and missingness must be explicit and
PIT. No unresolved convention or denominator threshold is selected here.

## 16. Proxy Registry boundary

Every admitted proxy must have an exact identity, construct/dimension, formula,
source fields and roles, temporal alignment, accounting normalization,
transformations, direction, missingness/exclusion rules, economic rationale,
provenance, implementation identity, and digest participation. The registry is
frozen for a screen; a budget is not a substitute for enumerating proxies.

## 17. Screen Specification stage

The separate Screen Specification governs only:

`historical universe → PIT facts → accounting semantics → Proxy Registry → ranking configuration → GovernedRankingArtifact`

It is not a BUY list, portfolio specification, or outcome-evaluation
specification. It cannot consume, calculate, inspect, summarize, serialize, or
expose realized outcomes. Screen construction consumes no outcome-research slot
and requires no OPEN/CLOSE. The detailed proposed contract is
`docs/architecture/Screen_Specification_v1_Draft.md`.

## 18. Ranking, candidate-set, and regeneration identities

The existing Run 2 `GovernedRankingArtifact` retains its exact semantic
boundary: its decision-bearing `ranked_content_digest` covers only ordered
`security_id`, `decision_date`, and `composite_score`, and its governed ranking
selector may read only those fields. This digest is not broadened for screening.

A separate future `GovernedCandidateSetArtifact`, never the ranking artifact,
will apply a frozen membership/cutoff rule before deep research. It must bind
the frozen Screen Specification, exact ranking identity/digest, ranking
configuration digest, membership-rule digest, cutoff-rule digest, tie-break
digest, decision-date set, exact candidate rows, and reproducibility lineage.
Candidate count and threshold remain unresolved; no rule is selected here.

A distinct `screen_regeneration_identity` binds the resolved/frozen Screen
Specification, universe and security-master digests, immutable snapshots,
accounting and Proxy Registry digests, ranking configuration, dimensions,
decision-date-set digest, code and environment identities, canonicalization,
the exact ranking digest, and (when produced) exact candidate-set digest. Thus
`ranked_content_digest != screen_regeneration_identity !=
candidate_set_artifact_digest`.

## 19. Entry 000 architecture-package semantics

Entry 000 becomes a versioned package, not an arbitrary text-blob hash. It must
distinguish original v3.1 historical components from v3.2 current authority and
bind deterministic order, paths, roles, SHA-256 identities, Git provenance,
Run 1 and Run 2 commits, ADR approvals, Batch 1 record, amendment ledger, and
no-outcome attestations. The draft package contract is
`docs/architecture/Entry000_Package_v2_Draft.md`. This draft performs no freeze.

## 20. Entry 001 full-experiment semantics

Entry 001 remains the complete experiment freeze required before any realized-
outcome evaluation. In addition to existing Run 1/2 fields, a future schema must
bind the exact frozen Screen Specification, screen-regeneration identity,
ranking artifact identity/digest, and, when applicable, candidate-set
identity/digest, with lineage, data vintage, and commits. Neither another
ranking nor another candidate set may be substituted after outcomes are seen.

## 21. Outcome-governance boundary

Outcome-bearing use includes forward returns, rank IC against realized returns,
realized quantile/decile returns, long-short realized spreads, portfolio returns,
Sharpe, drawdown, hit rate, realized Rule-17 comparisons, and every statistic
derived from future realized outcomes. Every such use requires:

`full Entry 001 → specification budget → durable OPEN → authorized outcome-bearing execution → CLOSE`

No screen label, diagnostic label, preview, or data-correction label bypasses
this boundary.

## 22. Specification-budget semantics

Outcome-free Screen Specification construction and deterministic ranking consume
no outcome-research slot. Every authorized research-specification OPEN reserves
one slot under Run 2. Pre-OPEN failures consume no slot; post-OPEN failure or
abandonment does not silently release one. Any future release or invalidation
mechanism requires separate approval.

## 23. OPEN/CLOSE semantics

All deterministic preflight must complete before OPEN without emitting an
outcome statistic. OPEN must be durable, uniquely identified, content-bound,
append-only, and revalidated before authorization. Only authorized execution may
first use realized values to produce a result. CLOSE records completion, failure,
or abandonment without rewriting OPEN. Run class is immutable after OPEN.

## 24. Data-vintage and source-manifest binding

Governed inputs bind a research-vintage bundle, source-native vintage, source
kind and ID, exact content digest, audit-artifact digest, source-manifest digest,
and approved provenance class. A held-return manifest additionally binds the
economic-return convention. No runtime vintage string may override frozen
lineage. No vendor is selected by this draft.

## 25. LLM evidence-sidecar boundary

LLMs may extract structured, source-linked evidence and assist measurement or
economic validation. Deterministic code calculates financial signals. Current
or live LLM output, later amendments, and model-held later knowledge are not
historically PIT facts. The evidence sidecar cannot introduce an unregistered
rank input or bypass Screen Specification lineage.

## 26. Future deep-research boundary

The ranked candidate set feeds later company-specific research, including deep
valuation and evidence review. That work is downstream of candidate generation
and is not authorized to mutate the frozen historical screen. Any use of
realized outcomes remains governed by Entry 001 and OPEN.

## 27. Future BUY/HOLD/SELL boundary

Neither a Screen Specification nor its ranked candidates are BUY, HOLD, or SELL
recommendations. A future recommendation/decision system requires separately
approved objectives, evidence standards, portfolio/risk rules, human authority,
and governance. No such system is approved here.

## 28. Unsupported capabilities

Currently unsupported pending later governed work include the complete
historical security master and universe engine; historical market-price/EV and
market-role alignment; audited vendor integration; final accounting and
denominator conventions; exact investability rules; terminal/cash and unequal-
holding-period accounting; and the Screen Specification and Entry 000 v2 machine
schemas. Unsupported capability is not permission to approximate silently.

## 29. Changelog

| Version | Status | Change |
|---|---|---|
| 3.1 | immutable historical source | closed pre-return architecture |
| 3.2 Draft | draft | records ADR-001 through ADR-004, Run 1/2 reconciliation, and Batch 1 intent |

## 30. Informational amendment summary; separate ledger controls

The table below is informational only. The machine-verifiable amendment ledger
is a separately tracked, immutable, versioned artifact, independently approved
and separately bound by Entry000. Changed governing ledger bytes require a new
ledger version, bytes/hash/blob/commit, ledger approval, and Entry000 identity;
an approved ledger is never silently mutated.

| ID | Classification | Effect |
|---|---|---|
| ADR-001 | approved successor authority | establishes v3.2 while preserving v3.1 unchanged |
| ADR-002 | approved extension | adds a separately frozen, outcome-free Screen Specification stage |
| ADR-003 | approved boundary clarification/extension | screen construction needs no slot or OPEN; every realized-outcome use retains full Run 2 governance |
| ADR-004 | approved Entry 000 contract replacement direction | future Entry 000 is a provenance-bound architecture package, not an arbitrary text blob |
| B1-Q1/Q2/Q3/Q5/Q8 | approved research intent | constrains future specification without selecting deferred operational values |

The ledger does not claim that v3.1 originally contained these later rules.
