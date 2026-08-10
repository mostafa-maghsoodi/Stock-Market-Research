# Amendment Ledger v1 — Draft Contract

## 1. Status, purpose, and authority

This draft defines, but does not create, an approved ledger JSON artifact. The
ledger is separately tracked, immutable, versioned, independently approved
authority—not an embedded Architecture v3.2 section. Any architecture summary
is informational. Architecture v3.1 remains immutable historical evidence and
the exact v3.2 document remains draft until researcher approval.

## 2. Exact closed schemas

The top-level object and every entry have exactly these keys:

```text
{
  "amendment_ledger_schema_version": 1,
  "ledger_version": positive integer,
  "repository_id": string,
  "governing_architecture_identity": ArtifactIdentity,
  "entries": [AmendmentEntry, ...]
}
ArtifactIdentity = {
  "repository_relative_path": normalized relative string,
  "source_commit": 40-lowercase-hex full Git commit,
  "git_blob": 40-lowercase-hex Git blob,
  "exact_byte_sha256": 64-lowercase-hex
}
AmendmentEntry = {
  "ordinal": positive integer,
  "amendment_id": string,
  "decision_class": "INHERITED" | "CLARIFICATION" | "EXTENSION" |
                    "GAP_FILL" | "EXACT_SUPERSESSION",
  "affected_rule_id": string,
  "prior_rule_exact_text_sha256": null | 64-lowercase-hex,
  "replacement_rule_exact_text": null | string,
  "replacement_rule_exact_text_sha256": null | 64-lowercase-hex,
  "effective_boundary": string,
  "decision_record_identity": ArtifactIdentity,
  "decision_approval_record_identity": ApprovalRecordIdentity
}
ApprovalRecordIdentity = {
  "repository_id": string,
  "approval_record_path": normalized relative string,
  "approval_record_commit": 40-lowercase-hex full Git commit,
  "approval_record_git_blob": 40-lowercase-hex Git blob,
  "approval_record_exact_byte_sha256": 64-lowercase-hex
}
```

No unknown/additional keys or arbitrary metadata maps are allowed. Entries are
strictly ordered by contiguous `ordinal` beginning at 1; `amendment_id` is
unique, and `(affected_rule_id, effective_boundary)` is unique. Exact
supersession requires non-null prior hash, replacement text, and matching
replacement hash. Other classes require all three replacement/prior fields be
null unless their approved decision itself supplies an exact replacement, in
which case the class must be `EXACT_SUPERSESSION`.

## 3. Versioning, supersession, and Entry000

An approved ledger is never edited. A change appends or supersedes through a
new complete ledger version at a new immutable identity, followed by a new
ledger approval record. The ledger bytes MUST NOT contain the identity of the
approval record approving those bytes. Earlier ledgers and approval records remain verifiable.
Deletion, ordinal reuse, silent mutation, or reinterpretation fails closed.

Entry000 embeds the exact separately approved ledger bytes, component identity,
and approval-record evidence. Changed governing ledger bytes require a new
ledger version, SHA-256/blob/source commit, ledger approval, and content-derived
Entry000 `package_id`; an existing Entry000 cannot be updated in place. Mere
inclusion does not approve the ledger.

The only permitted construction order is: canonical ledger bytes; ledger
SHA-256/blob/source commit; external human approval; separate Approval Record;
then Entry000 binding of both identities and both sets of exact bytes. Entry
approval references authorize the individual decisions recorded in the ledger;
the ledger's own approval identity exists only in the external Approval Record
and Entry000 approval-evidence closure. This ordering prevents a hash cycle.

## 4. Verification and scope

Verification checks exact schemas, canonical ordering/uniqueness, hashes,
decision-class invariants, approval identities, and Git path/blob/commit
relationships. `source_commit` is any full commit whose tree contains the exact
bytes at the recorded path, not necessarily introduction, approval, or freeze
commit. Intrinsic verification uses embedded bytes; repository-backed checking
adds tree/path/blob proof. Neither mode independently proves the external human
approval event.

The ledger records authority changes only. It chooses no vendor, sample period,
candidate cutoff, threshold, budget, or outcome rule. Screen construction stays
outcome-free; future Entry001 still binds screen, ranking, and applicable
candidate identities before outcomes and preserves budget/OPEN/CLOSE.
