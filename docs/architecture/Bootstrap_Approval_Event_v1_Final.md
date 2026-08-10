# Bootstrap Approval Event v1 — Final Recording Contract

## 1. Status and purpose

**Status: FINAL — approval state is external to these bytes.**

This documentation/provenance-format contract prescribes the sole durable,
machine-readable record of the one-time Approval Record v1 bootstrap event
authorized by A9-06. It closes only the durable-recording-format dependency.
It makes no implementation or research decision.

This contract document is not the bootstrap event, is not part of the authority
bootstrap chain, grants no bootstrap approval, and creates no approval. It only
defines how an already-completed external human approval event must be recorded.

## 2. Scope and exact bootstrap subject identity

The event may memorialize only the researcher's external approval, under the
one-time A9-06 bootstrap rule, of this exact immutable subject identity:

```text
repository_identity: mostafa-maghsoodi/Stock-Market-Research
subject_path: docs/architecture/Approval_Record_v1_Final.md
subject_source_commit: 445d36128b5a2916bb2abff0b9f5ef1ecba10cad
subject_git_blob_id: b409f764589cce3fb7c4c09aa482a60c8e5744ba
subject_exact_byte_sha256: 0429caf8684804221810c8cb7025d12ad9816506a92a93b18159ec26ebe1314d
```

No other subject or authority may use this exception. The artifact is evidence
and provenance only: it does not self-attest or replace human approval, act as
an Approval Record, approve another subject, establish a reusable bootstrap
mechanism, or become an Entry000 component.

## 3. Sole event path and uniqueness

The only permitted artifact path is exactly:

`docs/approvals/bootstrap/Approval_Record_v1_Bootstrap_Event_v1.json`

There may be exactly one v1 bootstrap-event artifact for Approval Record v1.
No alternate path, alias, duplicate, or second bootstrap-event record is
permitted.

## 4. Exact closed JSON schema

The event is one JSON object with exactly the following keys and no additional
keys:

```text
{
  "bootstrap_event_schema_version": integer,
  "event_id": string,
  "event_type": string,
  "authority_basis": string,
  "recording_role": string,
  "repository_identity": string,
  "subject_path": string,
  "subject_source_commit": string,
  "subject_git_blob_id": string,
  "subject_exact_byte_sha256": string,
  "decision": string,
  "approval_statement": string,
  "approver_identity": {
    "identity_scheme": string,
    "identity_value": string,
    "role": string
  },
  "approval_timestamp": string,
  "recorded_after_external_human_approval": boolean
}
```

`approver_identity` is itself an exact-key object containing exactly
`identity_scheme`, `identity_value`, and `role`. Unknown or additional keys at
either level are forbidden and fail verification.

## 5. Exact field types and constants

- `bootstrap_event_schema_version` is the integer `1`.
- `event_id` is the string `APPROVAL-RECORD-V1-BOOTSTRAP`.
- `event_type` is the string
  `ONE_TIME_APPROVAL_RECORD_V1_BOOTSTRAP`.
- `authority_basis` is the string `A9-06`.
- `recording_role` is the string `PROVENANCE_ONLY_NON_AUTHORITY`.
- `repository_identity` is the string
  `mostafa-maghsoodi/Stock-Market-Research`.
- `subject_path` is the string
  `docs/architecture/Approval_Record_v1_Final.md`.
- `subject_source_commit` is the string
  `445d36128b5a2916bb2abff0b9f5ef1ecba10cad`.
- `subject_git_blob_id` is the string
  `b409f764589cce3fb7c4c09aa482a60c8e5744ba`.
- `subject_exact_byte_sha256` is the string
  `0429caf8684804221810c8cb7025d12ad9816506a92a93b18159ec26ebe1314d`.
- `decision` is the string `APPROVED`.
- `approval_statement` is a non-empty UTF-8 string reproducing exactly the
  human bootstrap approval statement actually made by the researcher. It must
  not be generated before that human event.
- `approver_identity.identity_scheme` is exactly one value from the closed enum
  `researcher_id` or `repository_account`.
- `approver_identity.identity_value` is a non-empty canonical string supplied
  by the researcher at the actual approval event.
- `approver_identity.role` is the string `researcher_approver`.
- `approval_timestamp` is a canonical UTC RFC3339 timestamp with microseconds
  and `Z`. It records the actual external human approval event, cannot precede
  that event, and must not be invented during A12.
- `recorded_after_external_human_approval` is the JSON Boolean `true`.

## 6. Canonicalization

The repository file is UTF-8. Every object serializes its keys in lexicographic
Unicode-codepoint order, with no insignificant whitespace and with JSON
booleans and literals in standard lowercase form. Exactly one LF follows the
canonical JSON object. Accordingly, the top-level serialized key order is:

```text
approval_statement
approval_timestamp
approver_identity
authority_basis
bootstrap_event_schema_version
decision
event_id
event_type
recorded_after_external_human_approval
recording_role
repository_identity
subject_exact_byte_sha256
subject_git_blob_id
subject_path
subject_source_commit
```

The nested serialized key order is `identity_scheme`, `identity_value`, then
`role`. The repository SHA-256 and Git blob identity later bind the resulting
exact file bytes. No self-hash field is included, and no Approval Record
identity for the bootstrap-event artifact is required.

## 7. Trust boundary and creation timing

Human approval occurs outside the bootstrap-event JSON. The JSON may be created
only strictly after the researcher has actually made the human bootstrap
approval statement. Creating, writing, staging, committing, retaining, or
verifying the JSON does not create approval. The artifact is only a durable
historical record of the earlier external event.

Machine verification cannot independently prove that the researcher intended
approval. The external researcher approval remains the authority trust root;
the event record is non-authoritative provenance evidence of that event.

## 8. Verification semantics

Machine verification can and must verify the exact closed schema and types,
all constants, the sole path and uniqueness rule, the exact bootstrap subject
identity, repository/path/commit/blob/hash consistency, canonical bytes, and
the declared event structure. Mismatch, omission, an unknown key, an alternate
path, duplication, noncanonical bytes, or a false timing declaration fails
closed.

Machine verification cannot, from the JSON alone, prove that the external
human event occurred or that the human actually intended approval. Verification
therefore must not treat event existence, `decision`, the approval statement,
or the timestamp as independent proof of human intent.

## 9. One-time rule and relationship to Approval Record v1

This record is usable once and only for the exact Approval Record v1 Final
subject identity in Section 2. It cannot be reused for any later approval,
other subject, changed bytes, or second bootstrap. Every later authority
approval must use the normal Approval Record v1 process. A second bootstrap or
any change to this rule requires a new approved architecture amendment.

This artifact is not an Approval Record and is not a replacement for Approval
Record v1. No normal Approval Record approves this bootstrap-event artifact,
and none is required before the one-time Approval Record v1 bootstrap may
occur. Requiring one would introduce a new bootstrap cycle. This narrow
exception cannot be applied to any other authority subject.

## 10. Architecture provenance and approval history

At its sole prescribed path, the artifact satisfies the A9 requirement that
the completed one-time bootstrap event be recorded in architecture provenance
and approval history. It is a provenance record, not an ADR or authority
decision. This Final recording contract itself is documentation authorized by
A12, is not the event, and is not authority-bootstrap evidence.

## 11. Amendment Ledger relationship

The event artifact is not an Amendment Ledger decision entry and adds no entry
to the Amendment Ledger. It does not amend, supersede, or interpret a ledger
decision. Any future change to this contract or its prescribed format requires
a new approved architecture amendment; it may not be made by editing either
this Final contract or the one-time event.

## 12. Entry000 relationship

The event artifact is not one of Entry000's six fixed authority components, is
not a seventh component, and is not Approval Record evidence for any Entry000
component. Entry000 must not treat it as an approval mechanism. The event
remains repository-level architecture provenance and approval-history evidence
outside the closed Entry000 v2 package object; therefore the fixed Entry000
schema and component array require no semantic change.

## 13. Explicit non-authorization

Neither this contract nor the future event JSON creates or claims approval.
Neither authorizes implementation, research, realized-outcome access, a freeze,
Batch 2, or any normal Approval Record, ledger, ADR, architecture, package, or
other governed subject. The future JSON may record only an external bootstrap
approval that has already occurred.
