# Screen v2 production-readiness interface

This developer interface implements the deterministic portion of Screen
Specification v2. It is not governing authority, production evidence, a
provider selection, or a CandidateSet.

Run the outcome-free preflight from the repository root:

```text
PYTHONPATH=src python -m graham_research.cli production-readiness-v2 \
  --repository .
```

Run the complete 65-capability implementation audit with:

```text
PYTHONPATH=src python -m graham_research.cli production-audit-v2
```

An evidence manifest may be supplied only when its referenced evidence is
present in the repository and its provider, product, native vintage, effective
range, and exact content identities are known:

```text
PYTHONPATH=src python -m graham_research.cli production-readiness-v2 \
  --repository . \
  --evidence-manifest path/to/admitted-production-evidence.json
```

The JSON manifest is parsed as a closed `ProductionEvidenceManifest`. Unknown
or missing keys fail. Its capability map must have exactly the capabilities
declared by `REQUIRED_CAPABILITIES`. Its embedded field catalog is also closed;
all required canonical concepts must have a native mapping and independently
verifiable mapping/source evidence. An `EvidenceIdentity` references separate,
immutable evidence bytes—it does not self-hash the JSON object that contains
the identity.

Positive readiness additionally requires:

- exact governing Architecture, Screen v1/v2, V1 Policy, ADR-005, Ledger, and
  Entry000 identities;
- exact admitted implementation commit in the checked-out ancestry and a clean worktree;
- every referenced evidence file to match its SHA-256;
- all provider capabilities to be explicitly true;
- complete provider/native field mappings and proxy input coverage;
- denominator-specific governance and a valid provenance chain; and
- the exact Screen v2 executable-configuration digest.

Absent or invalid evidence leaves `production_execution_state` null, reports
every false gate, returns `FIRST_REAL_RUN_BLOCKED`, and creates no CandidateSet.
Fixtures and current/live facts cannot establish positive production state.

The `CandidateSet` contract remains separate from the
`GovernedRankingArtifact`. The protected ranking digest scope remains exactly
`security_id`, `decision_date`, and `composite_score`. Candidate selection is
exactly 100 rows ordered by composite score descending and stable security ID
ascending. Fewer than 100 fully eligible rows raises
`INSUFFICIENT_ELIGIBLE_POPULATION`; no partial CandidateSet is returned.
