# Entry 000 Architecture Package v2 — Draft Contract

## 1. Status and scope

**Status:** DRAFT — contract only; not implemented or frozen.
**Proposed schema:** `entry_000_package_schema_version: 2`.
**Current governing architecture:** Architecture v3.2, after approval.

Architecture v3.1 remains immutable historical evidence. This contract freezes
an ordered, provenance-bound architecture package and does not rewrite v3.1.
No realized strategy outcome has been examined, and no Entry artifact has been
frozen. No vendor is selected.

The existing `graham_research.governance.freeze_entry_000()` does **not**
implement this contract. It hard-codes Architecture `3.1`, accepts one arbitrary
text string, and lacks a component manifest and source provenance.

## 2. Package identity

The closed top-level payload must contain:

- `entry: "000"`;
- `entry_000_package_schema_version: 2`;
- immutable `package_id`;
- `current_governing_architecture_version: "3.2"`;
- `created_at` in UTC;
- canonicalization algorithm/version;
- ordered `components` manifest;
- Run 1 and Run 2 source commit identities;
- approval identifiers;
- amendment-ledger identity;
- Batch 1 decision-record identity; and
- structured approval and no-outcome attestations.

Unknown or missing fields fail closed.

## 3. Ordered component manifest

Components must appear in a schema-fixed deterministic role order:

1. `historical_architecture_markdown` —
   `docs/architecture/Architecture_v3.1_Final.md`;
2. `historical_architecture_pdf` —
   `docs/architecture/Architecture_v3.1_Final.pdf`;
3. `successor_architecture` —
   `docs/architecture/Architecture_v3.2_Draft.md` until approval creates an
   approved successor path;
4. `screen_specification_contract` — approved descendant of
   `docs/architecture/Screen_Specification_v1_Draft.md`;
5. `batch1_research_intent` — approved descendant of
   `docs/research/Batch1_Research_Intent_Draft.md`; and
6. `amendment_supersession_ledger` — the approved ledger identified by v3.2.

Draft components cannot be frozen as approved authority merely because their
paths are listed here. Before Entry 000, each current-authority component must
have an explicit approval ID and approved immutable identity.

Each component record must contain exactly:

- deterministic ordinal;
- component role;
- authority class (`historical_source` or `current_authority`);
- repository-relative source path;
- media/content type;
- SHA-256 of exact bytes;
- Git blob ID where the component is tracked;
- source commit ID where available;
- document/schema version;
- approval identifier or explicit historical-source designation; and
- inclusion rationale.

The v3.1 components are `historical_source`; v3.2 and approved subordinate
contracts are `current_authority`. Matching content does not permit a component
to change roles.

## 4. Source commits and approval identities

The package must separately bind:

- Run 1 commit `587051d`;
- Run 2 commit `be1f9973e0aeeaaca80ab8f100a3de9a7a7c72db`;
- the exact commit containing approved architecture components;
- ADR-001, ADR-002, ADR-003, and ADR-004;
- the approval identity for the completed Architecture v3.2;
- the approval identity for the Screen Specification contract; and
- the Batch 1 Q1/Q2/Q3/Q5/Q8 decision-record identity.

Abbreviated commits may be displayed, but stored provenance must use the full
object identity resolved and attested at freeze time.

## 5. Amendment and Batch 1 identities

The amendment ledger must have its own component role, schema/version, path,
SHA-256, Git provenance, and approval identity. It must distinguish inherited,
clarified, extended, gap-filled, and exactly superseded rules.

The Batch 1 record must bind only Q1, Q2, Q3, Q5, and Q8 and preserve unresolved
operational values. It must include the escalation rule:

`unsupported capability → return to researcher → no silent substitution`

## 6. No-outcome and approval attestations

Attestations must be structured records rather than one hard-coded sentence.
They must identify the attested scope, statement version, approving actor/ID,
timestamp, and relevant component/package digest. Required statements include:

1. original v3.1 is preserved as historical evidence;
2. v3.2 is the approved successor authority;
3. no realized strategy outcome was examined in approving the architecture
   package or its screen-stage boundary;
4. no Entry 000 or Entry 001 existed before this freeze operation; and
5. unresolved operational decisions remain unresolved rather than defaulted.

The implementation may verify structure and identity; it cannot infer the truth
of researcher attestations and therefore requires explicit approval inputs.

## 7. Deterministic canonicalization

The package digest must be computed from canonical UTF-8 JSON using a named,
versioned algorithm: exact-key objects, lexicographically sorted object keys,
schema-prescribed component-array order, no insignificant whitespace, normalized
UTC timestamps, lowercase SHA-256 hexadecimal, full Git object IDs, and no NaN
or infinity. Component hashes are over exact file bytes, not normalized text.

The package must not embed an untyped concatenation of component text as an
alternative identity.

## 8. Freeze and sidecar semantics

Freeze must:

1. require a clean, explicitly identified repository and full commit;
2. resolve every prescribed path inside that repository;
3. read and hash every exact component;
4. resolve tracked Git blob IDs and source commits where available;
5. validate roles, order, versions, approvals, attestations and exact keys;
6. canonicalize the complete payload;
7. atomically create the artifact without overwrite; and
8. atomically create a sidecar containing the package SHA-256 and artifact name.

A sidecar failure makes the freeze incomplete and must be surfaced for
quarantine; it must never be reported as a successful Entry 000.

## 9. Verification semantics

Verification must independently:

- validate schema/version and exact keys;
- recompute package and sidecar digests;
- verify deterministic component order;
- rehash available repository components and compare exact bytes;
- verify path, role, authority class, blob and commit provenance;
- verify mandatory historical and current-authority components;
- verify approval and no-outcome attestation structure; and
- reject unsupported schema versions without fallback to v1 behavior.

Verification of an archived package may use its embedded manifest and preserved
component bytes or a separately defined archival bundle; repository revalidation
must be reported distinctly from intrinsic package verification.

## 10. Mandatory failures

- **Wrong order:** fail when ordinals or role order differ from the schema.
- **Missing component:** fail when either v3.1 source, v3.2 authority, Screen
  Specification contract, Batch 1 record, or amendment ledger is absent.
- **Hash mismatch:** fail when component bytes, stored SHA-256, package digest,
  or sidecar disagree.
- **Arbitrary-text substitution:** fail when a supplied blob lacks the required
  tracked path, role, component identity, and provenance, even if its prose is
  similar.
- **Provenance mismatch:** fail on wrong repository, dirty tree, wrong commit or
  blob, path escape, role substitution, or approval mismatch.
- **Overwrite:** fail if artifact or sidecar already exists.
- **Draft-as-approved:** fail if a current-authority component lacks the required
  approval identity.

## 11. Compatibility and migration

Existing Entry 000 behavior is schema v1 in substance even though it lacks a
package schema field. Existing artifacts must remain verifiable according to
their original rules and must never be silently upgraded or relabeled as v2.

Migration is a new freeze of an approved v2 package, not mutation of an old
artifact. A v2 loader must dispatch explicitly by schema and reject ambiguous
payloads. Architecture v3.1 text embedded in an old artifact remains only that
artifact's historical content; it does not prove the v2 package identities.

Future schema versions must preserve v2 verification or provide a separately
versioned verifier. No compatibility path may weaken no-overwrite, provenance,
component-order, approval, or no-outcome checks.

## 12. Required implementation tests

Tests must cover exact keys and schema dispatch; deterministic canonicalization;
component ordering; exact byte hashes for Markdown and PDF; Git path/blob/commit
provenance; clean/dirty trees; path escape; missing/duplicate/wrong-role
components; arbitrary text substitution; changed approval IDs; malformed
attestations; package and sidecar tampering; no-overwrite and partial-write
failure; v1 verification without reinterpretation; v1-to-v2 non-mutation; and
unsupported future-version rejection.
