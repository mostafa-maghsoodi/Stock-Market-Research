# Entry000 Package v2 — Draft Contract

## 1. Status and trust boundary

Documentation only; not implemented, approved, or frozen. Current production
`freeze_entry_000()` does **not** implement this contract. Architecture v3.1 is
immutable historical evidence. ADR-001 approves v3.2's successor direction, but
exact v3.2 bytes become authority only through external researcher approval of
their immutable identity.

Entry000 preserves evidence; it cannot manufacture approval by containing an
approval ID, status, attestation, component, or approval-record bytes. Human
approval of an exact approval-record identity is the external trust root.
Machine verification proves integrity and consistency, never human intent absent
a future approved signature mechanism.

## 2. Primitive and canonical rules

Every schema is closed: exactly displayed keys, no extension maps. `sha256` is
64 lowercase hex; Git commit/blob are 40 lowercase hex; paths are normalized,
repository-relative, and contain no `..`; timestamps are RFC3339 UTC.
`CanonicalJSON-v1` is UTF-8 JSON with lexicographically sorted object keys,
array order preserved, no insignificant whitespace, finite numbers, and no
Unicode normalization. Exact-byte hashes never normalize content.

## 3. Exact package schema and identities

```text
Entry000PackageV2 = {
 "entry_000_package_schema_version": 2,
 "entry": "000",
 "package_label": string,
 "package_id": sha256,
 "created_at_utc": timestamp,
 "canonicalization_version": "CanonicalJSON-v1",
 "repository_id": string,
 "run_lineage": RunLineage,
 "components": [AuthorityComponent x exactly 6],
 "approval_evidence": [ApprovalEvidence, ...],
 "attestations": PackageAttestations
}
RunLineage = {
 "run1_commit": 40-lowercase-hex,
 "run2_commit": "be1f9973e0aeeaaca80ab8f100a3de9a7a7c72db"
}
PackageAttestations = {
 "no_realized_outcome_statement_version": 1,
 "no_realized_outcome_statement": "No realized strategy outcome was examined in freezing this package.",
 "prior_publication_statement_version": 1,
 "prior_publication_statement": "No Entry000 Package v2 with this semantic package identity or publication path was previously frozen.",
 "legacy_preservation_statement": "This freeze does not overwrite, mutate, relabel, upgrade, or reinterpret any legacy Entry000 or Entry001 artifact.",
 "unresolved_values_remain_unresolved": true
}
```

`package_label` and `created_at_utc` are non-authority publication metadata.
`package_id = SHA256(CanonicalJSON-v1(package object excluding exactly
package_label, package_id, and created_at_utc))`. The publication contains the
complete object; `full_artifact_sha256` is stored only in the sidecar and hashes
the exact complete artifact bytes. Thus labels/times do not change semantic
identity, while every authority/evidence byte and rule does.

## 4. Fixed authority components

```text
AuthorityComponent = {
 "ordinal": 1|2|3|4|5|6,
 "component_role": enum below,
 "authority_class": "historical_source" | "current_authority",
 "repository_relative_path": path,
 "media_type": string,
 "document_or_schema_version": string,
 "source_commit": git_commit,
 "git_blob": git_blob,
 "exact_byte_sha256": sha256,
 "byte_length": nonnegative integer,
 "exact_bytes_base64": canonical base64 string,
 "approval_record_identity": null | ApprovalRecordIdentity
}
```

The array is exactly, without duplicates or alternatives:

1. `HISTORICAL_ARCHITECTURE_V3_1_MARKDOWN`, historical_source,
   `docs/architecture/Architecture_v3.1_Final.md`;
2. `HISTORICAL_ARCHITECTURE_V3_1_PDF`, historical_source,
   `docs/architecture/Architecture_v3.1_Final.pdf`;
3. `SUCCESSOR_ARCHITECTURE_V3_2`, current_authority, its approved path;
4. `SCREEN_SPECIFICATION_CONTRACT_V1`, current_authority, its approved path;
5. `BATCH1_RESEARCH_INTENT`, current_authority, its approved path;
6. `AMENDMENT_LEDGER`, current_authority, its separately approved path.

Historical components require null approval references. Components 3–6 require
non-null, distinct approval-record identities whose subjects exactly equal the
component identities. Presence never approves. The amendment ledger is a
separate component, not an architecture section.

`source_commit` is the full commit whose tree contains the exact approved bytes
at that exact path. It is not necessarily introduction, approval-record, or
freeze commit unless that tree/path/blob condition holds. Decoded embedded bytes
must match byte length, SHA-256, and Git blob.

## 5. Closed approval-evidence closure

```text
ApprovalRecordIdentity = {
 "repository_id": string,
 "approval_record_path": path,
 "approval_record_commit": git_commit,
 "approval_record_git_blob": git_blob,
 "approval_record_exact_byte_sha256": sha256
}
ApprovalEvidence = {
 "approval_record_identity": ApprovalRecordIdentity,
 "approval_record_byte_length": nonnegative integer,
 "approval_record_exact_bytes_base64": canonical base64 string
}
```

`approval_evidence` is ordered lexicographically by
`approval_record_path`, has exactly one element for every distinct referenced
approval identity and no unreferenced element. Decoded bytes match length,
SHA-256, and blob and parse under Approval Record v1. The referenced human
approval event remains external. Supersession/revocation evidence is included
when needed to establish current status; the closure contains the complete
predecessor chain, with each record once, topologically predecessor-first.

## 6. Intrinsic and repository-backed verification

Intrinsic verification requires no repository: decode all component and
approval bytes; validate exact schemas, order, identities, hashes, blob hashes,
approval closure/status, package ID, attestations, and sidecar/full artifact
hash. It reports `INTRINSIC_VERIFIED`, not Git provenance verified.

Repository-backed verification first passes intrinsic verification, then proves
repository identity and that each component/approval commit tree contains the
recorded path, blob, and exact bytes. It reports `REPOSITORY_VERIFIED`. Neither
mode independently proves human intent. Missing repository access can prevent
the stronger mode but cannot prevent intrinsic verification.

## 7. Sidecar, uniqueness, and publication layout

Final publication directory is `artifacts/entry000/v2/<package_id>`; its
artifact path is `entry000.package.json`; sidecar is the same directory's
`entry000.package.sha256` and contains exactly
`<full_artifact_sha256>  entry000.package.json\n`. The package ID uniquely maps
to one semantic payload. The final directory uniquely maps to that ID. A valid
existing final directory makes any retry fail as already published—even if only
label/time differs. An inconsistent, partial, symlinked, or different final path
fails closed and is never replaced.

## 8. Normative publication and failure state machine

Artifact states are exactly `ABSENT`, `BUILDING_PRIVATE`, `READY_PRIVATE`,
`PUBLISHED`, and `FAILED_PRIVATE`; `SUCCESS` is an operation result. Only a
final-path-verified `PUBLISHED` package is authority.

After deriving `package_id` and the final path, acquire a process-held exclusive
lock keyed by exactly `(repository_identity, artifact_type, semantic_identity,
final_publication_path)`, using the package `repository_id`, artifact type
`ENTRY000_PACKAGE_V2`, `package_id`, and section 7 path. The lock exists only
while owned by a live process/file handle and ends automatically on handle close
or process termination. It is not permanent authority state; a stale directory
is not a lock. A live competing owner causes no modification or competing
attempt and returns `LIVE_PUBLICATION_ATTEMPT_EXISTS`; callers may retry later.

Create a uniquely named private attempt directory on the final publication
filesystem and enter `BUILDING_PRIVATE`. Exclusively write canonical package
bytes, flush and `fsync`; write the exact section 7 sidecar bytes, flush and
`fsync`; and `fsync` the private directory. The sidecar contains only its governed
digest binding—no metadata, diagnostics, source values, or outcomes. Intrinsically
verify the complete private publication, then enter `READY_PRIVATE`.

Immediately before rename, recheck that the final directory does not exist. If
absent, atomically rename the complete private directory to it without overwrite,
`fsync` the parent, verify from final paths, enter `PUBLISHED`, release the lock,
and only then return `SUCCESS`.

If a final publication exists and verifies to the same `package_id`, release the
lock and return `ALREADY_EXISTS_VERIFIED`, without publishing anew. If it fails
verification, return `CORRUPT_EXISTING_PUBLICATION`; never repair or overwrite it.
A required path or human label already bound to different semantic content
returns `PUBLICATION_IDENTITY_CONFLICT`. Never rename over, mutate, repair in
place, republish over, or reuse a published artifact/sidecar/label/path for
different semantic content.

Every failure before final publication enters `FAILED_PRIVATE`: the attempt
created no final path or authority; handles close safely and release the process
lock; normal discovery/verifiers ignore the private directory; and retry may use
the same semantic identity, if no valid final exists, only in a new attempt
directory. Private/stale/failed attempts never reserve identity or block retry.
Governed cleanup may delete one only when all hold: no live lock owns it, it is
not the final path, and it cannot verify as `PUBLISHED`. Cleanup never edits or
removes a published artifact. Only valid `PUBLISHED` permanently reserves the
semantic identity, final path, and any uniqueness-governed label.

## 9. Exact legacy dispatch

If `entry_000_package_schema_version` exists, dispatch only an explicitly
supported version; unknown values fail closed. Version 2 must match this schema.
It is never retried as legacy.

If the key is absent, recognize legacy Entry000 v1 only when all hold:

```text
LegacyEntry000V1 exact keys = {
 "entry", "architecture_version", "created_at", "architecture_sha256",
 "architecture_text", "statement", "unresolved_operational_items"
}
entry == "000"
architecture_version == "3.1"
architecture_text MUST be a JSON string
architecture_sha256 == SHA256(exact UTF8 bytes of architecture_text)
created_at MUST be a JSON string matching exactly
  YYYY-MM-DDTHH:MM:SS+00:00 or YYYY-MM-DDTHH:MM:SS.ffffff+00:00
  with valid Gregorian/date/time fields; fractional seconds are either absent
  or exactly six digits, matching datetime.now(timezone.utc).isoformat()
created_at MUST parse as timezone-aware UTC with offset exactly +00:00 and
  Python isoformat() round-trip to the identical input bytes; "Z", offset
  alternatives, whitespace, normalization, and other spellings fail
statement == "No strategy-return results were examined in designing Architecture v3.1."
unresolved_operational_items == [
 "data-audit findings",
 "exact investable-universe values",
 "proxy-registry formulas selected for the cycle",
 "estimate-data admissibility",
 "sample boundaries",
 "numeric specification budget",
 "transaction costs",
 "rebalance frequency and holding period",
 "audit-dependent statistical implementation details"
]
no extra keys; no v2-only keys
artifact bytes == canonical_json(payload) followed by one LF byte
legacy sidecar path == artifact path with ".sha256" appended to its suffix
legacy sidecar bytes == SHA256(canonical_json(payload)) + two ASCII spaces +
artifact basename + one LF byte
```

These are the exact historical producer keys and constants; there are no aliases.
Approximate text, reordered items, or a renamed key fails. Anything else is
unknown/ambiguous and fails. Legacy artifacts are
never wrapped, upgraded, relabeled, rewritten, or reinterpreted as v2, nor are
legacy Entry001 artifacts changed.

## 10. Preconditions and unchanged research boundaries

Components 3–6 and their approval records must already be approved exact bytes;
all execution-time values must be resolved or explicitly remain later-stage
researcher decisions. A changed governing ledger requires new ledger version,
bytes/hash/blob/commit, approval, and package identity. No vendor, sample period,
threshold, candidate rule, or budget is chosen here.

Screen construction remains outcome-free and uses a private verified
`ResolvedScreenSpecification`. Run 2 `GovernedRankingArtifact` retains only
`security_id`, `decision_date`, and `composite_score` in its decision digest.
Future CandidateSet is separate; regeneration identity differs from both
digests. Future Entry001 binds exact applicable screen/regeneration/ranking/
candidate identities before outcomes. Budget/OPEN/CLOSE, essential valuation,
and full/date-effective survivorship remain unchanged.
