# Approval Record v1 — Draft Contract

## 1. Status and purpose

This is a documentation-only, closed contract. It creates no approval record
and grants no approval. Architecture v3.1 remains immutable historical evidence;
the exact Architecture v3.2 document remains draft until approved.

An approval is a human event external to the repository. Its trust root is the
researcher's explicit approval of one exact record identity. Recording an ID,
status, or attestation in Entry000 does not create that event. Machine checks
prove byte identity, integrity, provenance, and reference consistency—not the
researcher's intent. No signature is required in v1, and absent a future
approved signature mechanism a verifier MUST NOT call intent cryptographically
proven.

## 2. Path and exact closed schema

Records use `docs/approvals/v1/<approval_id>.json`; `approval_id` is lowercase
ASCII `[a-z0-9][a-z0-9._-]{0,127}` and equals the filename stem. The JSON object
has exactly these keys (no extension maps):

```text
{
  "approval_record_schema_version": 1,
  "approval_id": string,
  "approval_type": "APPROVE" | "SUPERSEDE" | "REVOKE",
  "status": "APPROVED" | "SUPERSEDED" | "REVOKED",
  "researcher_id": string,
  "decided_at_utc": RFC3339-UTC string,
  "subject": SubjectIdentity,
  "no_realized_outcome_attestation": NoOutcomeAttestation,
  "predecessor_approval_record_identity": null | ApprovalRecordIdentity
}
SubjectIdentity = {
  "subject_type": "ARCHITECTURE" | "CONTRACT" | "RESEARCH_INTENT" |
                  "AMENDMENT_LEDGER" | "PACKAGE" | "OTHER_GOVERNED_ARTIFACT",
  "repository_id": string,
  "repository_relative_path": normalized relative string,
  "source_commit": 40-lowercase-hex full Git commit,
  "git_blob": 40-lowercase-hex Git blob,
  "exact_byte_sha256": 64-lowercase-hex,
  "subject_schema_or_document_version": string
}
NoOutcomeAttestation = {
  "statement_version": 1,
  "statement": "No realized strategy outcome was examined in making this approval.",
  "attested_by_researcher_id": string,
  "attested_at_utc": RFC3339-UTC string
}
ApprovalRecordIdentity = {
  "repository_id": string,
  "approval_record_path": normalized relative string,
  "approval_record_commit": 40-lowercase-hex full Git commit,
  "approval_record_git_blob": 40-lowercase-hex Git blob,
  "approval_record_exact_byte_sha256": 64-lowercase-hex
}
```

`source_commit` means a commit whose tree contains the exact subject bytes at
the stated path; it need not be introduction, approval, or freeze commit.
Record identity is exactly the five fields of `ApprovalRecordIdentity` and the
commit must contain the record blob/bytes at the record path.

## 3. Semantics, ordering, and history

`APPROVE/APPROVED` has a null predecessor. `SUPERSEDE/SUPERSEDED` and
`REVOKE/REVOKED` identify the immediately affected prior record. Status is a
fact asserted by that immutable record, not mutable state in an old record.
Every change creates a new path/identity; records and approved subject history
are append-only. Supersession or revocation never edits, deletes, relabels, or
reuses a prior record.

## 4. Verification

Intrinsic consumers validate exact keys, enums, formats, internal subject and
attestation consistency, and SHA-256 over supplied exact bytes. Repository-
backed verification additionally resolves repository, commit tree, path, blob,
and exact bytes. A subject reference is effective only after the researcher has
externally identified and approved the exact approval-record identity.
Conflicts, missing predecessors, unknown versions, additional keys, path
escape, hash/blob mismatch, or inconsistent type/status fail closed.

Approval records may govern the separate amendment ledger, Architecture v3.2,
Screen Specification, Batch 1 intent, and later artifacts. They select no
vendor or deferred threshold, authorize no outcome use, and do not replace the
future Entry001/budget/OPEN/CLOSE boundary.
