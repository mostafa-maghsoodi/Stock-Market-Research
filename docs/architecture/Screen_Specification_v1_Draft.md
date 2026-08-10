# Screen Specification v1 — Draft Contract

## 1. Status and authority

Documentation only: not implemented, approved, or frozen. ADR-001 approves the
v3.2 successor direction, but the exact Architecture v3.2 bytes govern only
following external researcher approval of their immutable identity. Architecture
v3.1 remains immutable historical evidence. Entry000 inclusion does not create
human approval; the separately approved amendment ledger remains separate.

This contract is outcome-free. It selects no vendor, sample boundary, candidate
count/cutoff, investability threshold, accounting threshold, or Proxy formula.
Valuation, Business Economics, and Fundamental Change are mandatory; historical
eligibility is full/date-effective and never current-survivor-only. Coverage may
support a shorter-period proposal, never an automatic choice.

## 2. Closed notation and primitive rules

Every object below has exactly the displayed keys; additional/missing keys fail.
Arrays preserve order and contain no duplicates unless stated. `sha256` is 64
lowercase hex, `git_commit`/`git_blob` are 40 lowercase hex, paths are normalized
repository-relative paths without `..`, timestamps are RFC3339 UTC, and dates
are ISO `YYYY-MM-DD`. `CanonicalJSON-v1` means UTF-8, sorted object keys, array
order preserved, no insignificant whitespace, finite JSON numbers, and no
Unicode normalization. Digests cover its exact bytes unless `exact_byte_sha256`
is specified.

## 3. Exact top-level schema

```text
FrozenScreenSpecification = {
 "screen_specification_schema_version": 1,
 "screen_specification_id": sha256,
 "canonicalization_version": "CanonicalJSON-v1",
 "entry000_reference": Entry000Reference,
 "governing_architecture_reference": ArtifactReference,
 "universe_reference": UniverseReference,
 "security_master_reference": SecurityMasterReference,
 "pit_fact_sources": [SourceRecord, ...],
 "accounting_reference": AccountingReference,
 "proxy_registry_reference": ProxyRegistryReference,
 "required_dimensions": RequiredDimensions,
 "ranking_reference": RankingReference,
 "decision_date_set": DecisionDateSet,
 "research_vintage": ResearchVintage,
 "code_identities": CodeIdentities,
 "environment_identity": EnvironmentIdentity,
 "output_contract": OutputContract,
 "candidate_contract": CandidateContract,
 "approval_references": [ApprovalReference, ...],
 "attestations": ScreenAttestations
}
```

`screen_specification_id = SHA256(CanonicalJSON-v1(top-level object excluding
only screen_specification_id))`; nothing else is excluded.

## 4. Identity and approval references

```text
ArtifactReference = {
 "repository_id": string, "repository_relative_path": path,
 "source_commit": git_commit, "git_blob": git_blob,
 "exact_byte_sha256": sha256, "schema_or_document_version": string
}
Entry000Reference = {
 "entry_000_package_schema_version": 2, "package_id": sha256,
 "full_artifact_sha256": sha256, "publication_path": path
}
ApprovalReference = {
 "repository_id": string, "approval_record_path": path,
 "approval_record_commit": git_commit,
 "approval_record_git_blob": git_blob,
 "approval_record_exact_byte_sha256": sha256
}
```

Approval references must independently approve the exact screen, governing
architecture, Entry000 current-authority inputs, and governing ledger as
applicable. Referencing approval metadata never creates human approval.

## 5. Closed governed sources, projections, manifests, and columns

Every schema in this section is exact-key and admits no extension, metadata,
or user-defined payload map. `canonical_id` is a nonempty ASCII string matching
`[a-z0-9][a-z0-9._:-]{0,127}`. All SHA-256 values are 64 lowercase hex.

```text
ArchiveReference = {
 "archive_kind": "REPOSITORY_BLOB" | "CONTENT_ADDRESSED_ARCHIVE",
 "archive_uri": string, "raw_archive_sha256": sha256,
 "byte_length": nonnegative integer
}
FieldIdentity = {
 "field_namespace": "ACCOUNTING" | "MARKET" | "SECURITY_MASTER" |
                    "CLASSIFICATION",
 "field_id": canonical_id,
 "field_catalog_digest": sha256
}
ColumnRecord = {
 "column_name": canonical_id,
 "logical_type": "STRING" | "BOOLEAN" | "INTEGER" | "DECIMAL" |
                 "DATE" | "TIMESTAMP_UTC",
 "nullable": boolean,
 "column_role": "SECURITY_ID" | "DECISION_TIMESTAMP" |
   "AVAILABILITY_TIMESTAMP" | "ACCOUNTING_VALUE" | "MARKET_VALUE" |
   "CLASSIFICATION_VALUE" | "SECURITY_MASTER_VALUE" |
   "REPORTING_FREQUENCY" | "PERIOD_TYPE" | "FISCAL_YEAR" |
   "FISCAL_QUARTER" | "FORM_TYPE" | "ACCESSION_ID" | "VERSION_ID" |
   "REVISION_ID" | "PERIOD_END" | "EFFECTIVE_FROM" | "EFFECTIVE_TO" |
   "SOURCE_NATIVE_VINTAGE" | "PROVENANCE_ID",
 "field_identity": null | FieldIdentity,
 "unit_or_currency": null | string
}
SourceManifest = {
 "manifest_schema_version": 1, "manifest_id": canonical_id,
 "archive_manifest_sha256": sha256, "row_count": nonnegative integer,
 "primary_key_columns": [canonical_id, ...],
 "columns": [ColumnRecord, ...],
 "canonical_row_order": [canonical_id, ...]
}
GovernedSourceProjection = {
 "projection_schema_version": 1,
 "raw_archive": ArchiveReference,
 "declared_projected_columns": [canonical_id, ...],
 "row_order_columns": [canonical_id, ...],
 "canonicalization_identity": "CanonicalJSON-v1",
 "snapshot_id": canonical_id,
 "snapshot_sha256": sha256,
 "projected_byte_length": nonnegative integer
}
ColumnReferences = {
 "security_id_column": canonical_id,
 "decision_timestamp_column": null | canonical_id,
 "availability_timestamp_column": null | canonical_id,
 "reporting_frequency_column": null | canonical_id,
 "period_type_column": null | canonical_id,
 "fiscal_year_column": null | canonical_id,
 "fiscal_quarter_column": null | canonical_id,
 "form_type_column": null | canonical_id,
 "accession_id_column": null | canonical_id,
 "version_id_column": null | canonical_id,
 "revision_id_column": null | canonical_id,
 "period_end_column": null | canonical_id,
 "effective_from_column": null | canonical_id,
 "effective_to_column": null | canonical_id,
 "source_native_vintage_column": canonical_id,
 "provenance_id_column": canonical_id
}
SourceRecord = {
 "source_id": canonical_id,
 "source_kind": "PIT_ACCOUNTING_FACTS" | "HISTORICAL_MARKET_FACTS" |
   "HISTORICAL_SECURITY_MASTER_FACTS" |
   "HISTORICAL_CLASSIFICATION_FACTS",
 "provenance_class": "VENDOR_ARCHIVE" | "PUBLIC_ARCHIVE" |
                     "INTERNAL_ARCHIVE",
 "source_native_vintage": string,
 "research_vintage_id": string,
 "projection": GovernedSourceProjection,
 "manifest": SourceManifest,
 "column_references": ColumnReferences
}
```

`source_id`, `manifest_id`, and each Approval Record identity are unique within
one FrozenScreenSpecification. `snapshot_id` is the projection lookup identity;
`snapshot_sha256` alone is the exact-byte authority. Repeated `snapshot_id` is
permitted only when the complete SourceRecord identity fields and all archive,
manifest, and projected-byte digests are identical; the verifier otherwise
rejects a duplicate/conflict. Within a manifest, `column_name` is unique. Each
primary-key and canonical-order name is unique, both arrays are nonempty, and
each name resolves exactly once to `columns`. `declared_projected_columns`
equals the manifest column names in manifest order, and `row_order_columns`
equals `canonical_row_order`.

Every non-null `ColumnReferences` value resolves exactly once to a declared
column with its same-named role. `security_id_column` is always non-null and has
role `SECURITY_ID`. Applicability is exact:

* `PIT_ACCOUNTING_FACTS` requires every reference non-null except
  `decision_timestamp_column`, `effective_from_column`, and
  `effective_to_column`; those three are null. Its value columns use
  `ACCOUNTING_VALUE`.
* `HISTORICAL_MARKET_FACTS` requires security, decision, availability,
  provenance, source-native-vintage, and at least one `MARKET_VALUE` column;
  all reporting/fiscal/form/accession/version/revision/period-end/effectivity
  references are null.
* `HISTORICAL_SECURITY_MASTER_FACTS` requires security, availability,
  effective-from, effective-to, provenance, source-native-vintage, and at least
  one `SECURITY_MASTER_VALUE` column; decision and accounting references are
  null.
* `HISTORICAL_CLASSIFICATION_FACTS` has the same required references as security
  master and at least one `CLASSIFICATION_VALUE`; decision and accounting
  references are null.

Every source requires exactly one `SOURCE_NATIVE_VINTAGE` and one `PROVENANCE_ID`
column, referenced respectively by `source_native_vintage_column` and
`provenance_id_column`. A required reference
that is unavailable, null, missing, duplicated, undeclared, multiply resolving,
or role-mismatched fails closed.

Only the four value roles have non-null `field_identity`; all other roles require
null. Namespace compatibility is exact: accounting/accounting, market/market,
security-master/security-master, and classification/classification. The bound
catalog digest identifies an independently approved closed field catalog;
`field_id` must occur there and be classified `SCREEN_STAGE_ADMISSIBLE` for the
matching family. An unresolved/unapproved catalog or absent field classification
fails production freeze. This selects no vendor field or mapping.

### 5.1 Governed projection and structural outcome exclusion

The verifier starts with retained immutable raw/archive bytes, projects exactly
the declared approved columns, orders rows by the complete canonical row order,
encodes them with the stated canonicalization, materializes those projected
bytes, and computes `snapshot_sha256` over exactly those bytes. Governed APIs
consume only those bytes. Raw extra columns are not projected, are not governed,
and cannot be silently ignored inside a snapshot claimed as governed: physical
columns of the governed projection must equal the manifest set. Thus
`raw_archive_sha256` may differ from `snapshot_sha256`; both are retained, while
only the latter identifies selection-bearing bytes.

A broad value role grants no admission. The exact catalog must exclude forward
or held-period return, benchmark return, future price change, realized label,
rank IC, quantile/decile or portfolio result, hit rate, Rule-17 result,
outcome-derived classification or metadata, and every value using information
after the decision timestamp. No outcome, return, future, or generic role exists.
No arbitrary metadata, extension map, diagnostic payload/frame, callback,
auxiliary frame, sidecar, user dictionary, free-form source, or undeclared
column can be represented. Catalog ambiguity fails closed; name heuristics never
grant or deny admission.

Operational logs, if any, are outside authority and selection, are not referenced
by FrozenScreenSpecification or consumed by governed APIs, do not affect artifact
identity or ranking/candidate selection, and contain no source-row, feature, or
outcome-derived value. They may contain only artifact ID, operation ID,
timestamp, and a closed non-data error/result code. Richer logging requires a
future approved change. The sole frozen-artifact sidecar is the exact digest
sidecar in section 13.

## 6. Universe and historical security master

```text
UniverseReference = {
 "artifact": ArtifactReference, "artifact_digest": sha256,
 "eligibility_rule_digest": sha256,
 "required_rule_families": ["SIZE","PRICE","LIQUIDITY","SEASONING"],
 "operational_values_state": "UNRESOLVED_RESEARCHER_DECISION"
}
SecurityMasterReference = {
 "artifact": ArtifactReference, "artifact_digest": sha256,
 "snapshot": ArchiveReference, "manifest": SourceManifest,
 "stable_security_id_column": string, "effective_from_column": string,
 "effective_to_column": string, "listing_type_column": string,
 "security_type_column": string, "primary_listing_column": string,
 "terminal_event_column": string,
 "survivorship_policy": "FULL_DATE_EFFECTIVE"
}
```

The universe is primary-listed common operating-company equities and excludes
ADRs, secondary listings, preferreds, and funds/ETFs. Delisted, bankrupt,
acquired, renamed, and transferred securities remain representable.

## 7. Accounting, Proxy Registry, dimensions, and ranking

```text
AccountingReference = {
 "artifact": ArtifactReference, "accounting_semantics_digest": sha256,
 "field_taxonomy_digest": sha256, "unit_currency_policy_digest": sha256,
 "fiscal_period_policy_digest": sha256, "restatement_policy_digest": sha256,
 "alignment_policy_digest": sha256, "denominator_policy_digest": sha256,
 "missingness_policy_digest": sha256
}
ProxyRegistryReference = {
 "artifact": ArtifactReference, "proxy_registry_digest": sha256,
 "proxy_count": positive integer
}
RequiredDimensions = {
 "ordered_dimensions": ["VALUATION","BUSINESS_ECONOMICS","FUNDAMENTAL_CHANGE"],
 "valuation_required": true
}
RankingReference = {
 "ranking_configuration_id": string,
 "ranking_configuration_digest": sha256,
 "artifact": ArtifactReference,
 "ranked_digest_scope": ["security_id","decision_date","composite_score"],
 "selector_read_scope": ["security_id","decision_date","composite_score"]
}
```

All accounting choices and proxies must be resolved in an approved frozen
instance; this draft supplies no defaults. The two ranking scopes are exact,
ordered, and immutable Run 2 semantics.

## 8. Dates, vintage, code, and environment

```text
DecisionDateSet = {
 "dates": [date, ...], "decision_date_set_digest": sha256,
 "sample_boundary_authority": "RESEARCHER_APPROVED"
}
ResearchVintage = {
 "research_vintage_id": string, "as_of_utc": timestamp,
 "source_native_vintages_digest": sha256
}
CodeIdentity = {
 "role": "UNIVERSE" | "SECURITY_MASTER" | "FEATURE" | "ACCOUNTING" | "RANKING",
 "repository_id": string, "git_commit": git_commit, "tree_dirty": false
}
CodeIdentities = { "ordered_identities": [CodeIdentity, ...], "digest": sha256 }
EnvironmentIdentity = {
 "environment_manifest_sha256": sha256,
 "lockfile_exact_byte_sha256": sha256,
 "runtime_name": string, "runtime_version": string,
 "platform": string
}
```

Dates are strictly increasing. Their digest covers `CanonicalJSON-v1(dates)`.
Coverage can prompt a researcher proposal only. Code roles occur exactly once.

## 9. Output, candidate, regeneration, and unresolved contracts

```text
OutputContract = {
 "governed_ranking_artifact_schema_version": integer,
 "ranked_content_digest_algorithm": "RUN2_RANKED_CONTENT_V1",
 "ranked_content_columns": ["security_id","decision_date","composite_score"],
 "row_order_rule": "decision_date_asc_then_governed_rank_order",
 "forbidden_field_classes": ["HELD_RETURN","FORWARD_RETURN","BENCHMARK_RETURN",
   "REALIZED_LABEL","REALIZED_DIAGNOSTIC"]
}
UnresolvedValue = {
 "state": "UNRESOLVED_RESEARCHER_DECISION", "decision_id": string
}
CandidateContract = {
 "artifact_kind": "GovernedCandidateSetArtifact",
 "artifact_schema_status": "FUTURE_SEPARATE_GOVERNED_ARTIFACT",
 "membership_rule": UnresolvedValue, "cutoff_rule": UnresolvedValue,
 "candidate_count_or_threshold": UnresolvedValue,
 "required_binding_fields": ["frozen_screen_specification_id",
   "governed_ranking_artifact_identity","ranked_content_digest",
   "ranking_configuration_digest","membership_rule_digest",
   "cutoff_rule_digest","tie_break_rule_digest","decision_date_set_digest",
   "candidate_rows_digest","reproduction_lineage_digest"]
}
ScreenAttestations = {
 "no_realized_outcome_statement_version": 1,
 "no_realized_outcome_statement": "No realized strategy outcome was used in constructing this screen.",
 "no_live_substitution": true, "full_date_effective_survivorship": true,
 "no_vendor_selected_by_contract": true,
 "no_deferred_threshold_selected_by_contract": true
}
```

`GovernedRankingArtifact → frozen candidate rule →
GovernedCandidateSetArtifact → deep research`. CandidateSet is not implemented
here and is never a renamed ranking artifact. Its eventual digest covers its
entire closed artifact.

```text
SourceSnapshotReferenceV1 = {
 "source_kind": "PIT_ACCOUNTING_FACTS" | "HISTORICAL_MARKET_FACTS" |
   "HISTORICAL_SECURITY_MASTER_FACTS" |
   "HISTORICAL_CLASSIFICATION_FACTS",
 "source_id": canonical_id,
 "snapshot_id": canonical_id,
 "snapshot_sha256": sha256,
 "archive_manifest_sha256": sha256
}
ScreenRegenerationIdentityV1 = {
 "screen_regeneration_schema_version": 1,
 "screen_specification_id": sha256,
 "screen_specification_sha256": sha256,
 "universe_artifact_sha256": sha256,
 "security_master_artifact_sha256": sha256,
 "source_snapshot_references": [SourceSnapshotReferenceV1, ...],
 "accounting_semantics_sha256": sha256,
 "proxy_registry_sha256": sha256,
 "ranking_configuration_sha256": sha256,
 "required_dimensions": ["Valuation","Business Economics","Fundamental Change"],
 "decision_date_set_digest": sha256,
 "code_identities": CodeIdentities,
 "environment_manifest_sha256": sha256,
 "canonicalization_identity": "CanonicalJSON-v1",
 "ranked_artifact_sha256": sha256,
 "ranked_content_digest": sha256,
 "candidate_set_state": "not_produced" | "produced",
 "candidate_set_artifact_sha256": null | sha256
}
```

The record has exactly those eighteen keys and no others. `sha256` fields are
exactly 64 lowercase hexadecimal characters; `screen_specification_id` is the
canonical FrozenScreenSpecification semantic ID. Snapshot references are sorted
ascending by `(source_kind, source_id, snapshot_id)`, are unique, and equal the
verified source kind/ID, projection snapshot ID/SHA, and manifest
`archive_manifest_sha256` of every frozen SourceRecord exactly once.
`code_identities` is the complete already-defined closed `CodeIdentities` record,
not a digest alias. Required dimensions have exactly the displayed spelling and
order.

`candidate_set_artifact_sha256` is JSON null iff state is `not_produced`. For
`produced` it is a non-null SHA-256 of a verified governed CandidateSet; an
unresolved membership/cutoff/count rule can never be `produced`. The identity is
exactly `screen-regeneration-v1:` followed by the 64-lowercase-hex SHA-256 of
`CanonicalJSON-v1` serialization of this exact eighteen-key record. No self/outer
ID is stored in or hashed with the record. `canonicalization_identity` equals the
FrozenScreenSpecification canonicalization identity.

Creation/publication timestamp, human label, runtime/publication path,
operational log, diagnostic data, and temporary-attempt identity are outside the
record and digest. `ranked_content_digest` differs from the prefixed screen
regeneration identity; when produced, the CandidateSet artifact digest also
differs from it. GovernedRankingArtifact and CandidateSet remain distinct.

## 10. Runtime capability and API boundary

`FrozenScreenSpecification → governed verify/load →
ResolvedScreenSpecification → private issuance → governed screen APIs`.
`ResolvedScreenSpecification` is an immutable opaque capability with no public
constructor, serializer-based constructor, copy-with override, or mutation API.
Only the verifier may issue it after exact schema, approval, byte/hash, archive,
lineage, version, and outcome-free checks. It accepts no runtime replacement of
source, configuration, date, vintage, code, or environment and is never persisted
as a reusable capability; process restart requires reload and reverification.

Governed feature/ranking/screen functions accept that capability plus only the
bound archived inputs. Their signatures MUST NOT accept held/forward/benchmark
returns, realized labels or diagnostics, outcome callbacks, or arbitrary
auxiliary frames. They cannot inspect, calculate, serialize, log, or emit an
outcome. Failures publish no partial ranking or candidate artifact.

## 11. Entry001 and unchanged outcome governance

A future Entry001, before realized outcomes, binds the exact frozen screen,
screen-regeneration identity, GovernedRankingArtifact identity and exact
three-column digest, and any produced GovernedCandidateSetArtifact identity and
digest. It also binds the applicable lineage so substitution is impossible.
Screening uses no research-budget slot and no OPEN/CLOSE. Realized-outcome work
still requires full Entry001, available specification budget, durable OPEN,
authorized execution, and append-only CLOSE. Deep research and future
BUY/HOLD/SELL remain separate, later-governed stages.

## 12. Verification and implementation status

Unknown versions/keys, unresolved execution values, duplicate identities,
unretained sources, live substitution, hash/provenance mismatch, dirty code,
outcome-bearing inputs, or selector scope expansion fail closed. Intrinsic checks
use retained exact bytes; repository-backed checks add Git proof. This document
implements no Python, schema, freeze, CandidateSet, Batch 2, or outcome access.

## 13. Screen publication and failure state machine

Artifact states are exactly `ABSENT`, `BUILDING_PRIVATE`, `READY_PRIVATE`,
`PUBLISHED`, and `FAILED_PRIVATE`; `SUCCESS` is an operation result, not an
artifact state. Only final-path-verified `PUBLISHED` is authority.

The process derives semantic identity and final path, then acquires a
process-held exclusive lock keyed by exactly `(repository_identity,
artifact_type, semantic_identity, final_publication_path)`, where artifact type
is `FROZEN_SCREEN_SPECIFICATION_V1`. The lock exists only while its live process
or file handle owns it and is automatically released on handle close or process
termination. It is not authority; a stale private directory is not a lock. If
another live owner exists, the process does not touch that attempt or create a
competing publication and returns `LIVE_PUBLICATION_ATTEMPT_EXISTS`; retry is
allowed later.

Under the lock, create a unique private attempt directory on the final
publication filesystem and enter `BUILDING_PRIVATE`. The final publication
directory is `artifacts/screens/v1/<screen_specification_id>` and its artifact
path is `screen-specification.json`. Write canonical artifact bytes exclusively,
flush and `fsync`; write only the
ASCII sidecar `screen-specification.json.sha256` with exact bytes
`<SHA256(exact artifact bytes)>  screen-specification.json\n`, flush and
`fsync`; then `fsync` the private directory. The sidecar contains no other byte,
metadata, diagnostic, source, or outcome value. Verify the complete private
publication and enter `READY_PRIVATE`.

Immediately before publication, recheck final-path absence. If absent,
atomically rename the complete private directory to the final directory without
overwrite, `fsync` the parent directory, verify from final paths, enter
`PUBLISHED`, release the lock, and only then return `SUCCESS`.

If the final publication exists and verifies to the same semantic identity,
release the lock and return `ALREADY_EXISTS_VERIFIED`; this creates nothing. If
it fails verification, return `CORRUPT_EXISTING_PUBLICATION`. If a required path
or human label is bound to different semantic content, return
`PUBLICATION_IDENTITY_CONFLICT`. All fail closed without rename, mutation,
in-place repair, or overwrite.

Every pre-publication failure enters `FAILED_PRIVATE`: this attempt created no
final path or authority; all handles close safely and release the process lock;
normal discovery/verifiers ignore its private directory; and retry of the same
semantic identity, when no valid final publication exists, uses a new private
attempt. Private/stale/failed attempts never reserve identity or block retry.
Governed cleanup may delete one only when all hold: no live lock owns it, it is
not the final path, and it cannot verify as `PUBLISHED`. Cleanup never edits or
removes published material. Only valid `PUBLISHED` permanently reserves semantic
identity, final path, and any uniqueness-governed human label. Never rename over,
mutate, repair, or republish over a final artifact or sidecar, or reuse its
label/path for different semantic content.
