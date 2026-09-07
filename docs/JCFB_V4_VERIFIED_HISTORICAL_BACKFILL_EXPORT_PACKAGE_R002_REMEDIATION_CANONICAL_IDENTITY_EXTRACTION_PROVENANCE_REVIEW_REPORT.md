# JCFB V4 VERIFIED HISTORICAL BACKFILL EXPORT PACKAGE r002 REMEDIATION & CANONICAL IDENTITY / EXTRACTION PROVENANCE REVIEW REPORT

**Review date:** 2026-09-05  
**Workspace:** F:\Projects\jcfb-v4  
**Review class:** read-only contract review and runtime-ready revision preparation  
**Archive write:** NO  
**Package materialization:** NO

## 1. Executive decision

The active repository contracts provide a deterministic JSON substantive-hash rule, the formal export-package identity, the V4-020 canonical-match derivation rule, and no-write V4-025/V4-026/V4-027 review boundaries. The actual r001 handoff package is not present in the current readable staging area: staging contains only .gitkeep, and the final historical archive contains zero files.

There is therefore a strict distinction between contract preparation and real package readiness:

| Decision | Result | Basis |
|---|---|---|
| PACKAGE_R002_REMEDIATION_READINESS | BLOCKED | Canonical JSON rule is frozen, but no r001 package is available for r002 materialization; active contract does not define reproducible ZIP byte serialization or formally bind an exclusion manifest. |
| CANONICAL_MATCH_IDENTITY_READINESS | BLOCKED | The UUIDv5 derivation is deterministic, but the 40 actual package mappings and V4-020-required competition/team IDs are not locally available and cannot be inferred from names or lottery numbers. |
| EXTRACTION_PROVENANCE_REVIEW_READINESS | BLOCKED | The no-write review path is implementable, but the 64 raw PNGs, metadata snapshots, and candidate mapping are not present for execution. |
| INTAKE_RUNTIME_AUTHORIZATION_READINESS | BLOCKED | r002 has not been materialized and independently revalidated. |
| Current Training Readiness | BLOCKED / TRAINING_DATA_INSUFFICIENT | Archive records and usable training samples remain zero. |

PACKAGE_R002_REMEDIATION_READINESS = BLOCKED does not mean the repository contract is absent. It means the real r002 package cannot be declared ready from the current evidence boundary.

## 2. Active contract evidence

The review used these active repository artifacts:

- config/prediction_training/v4_batch15_verified_historical_backfill_export_package_schema.json
- config/prediction_training/v4_batch15_verified_historical_backfill_import_manifest_schema.json
- config/prediction_training/v4_batch15_verified_historical_backfill_contract.json
- src/historical_backfill_intake/__init__.py
- tools/canonical_intake/match_identity.py
- tools/canonical_intake/official_screenshot.py
- tools/canonical_intake/official_availability.py
- tools/canonical_intake/official_ledger.py
- docs/V4_020_CANONICAL_MATCH_IDENTITY_IMPLEMENTATION.md
- docs/V4_025_OFFICIAL_SCREENSHOT_OCR_IMPLEMENTATION.md
- docs/V4_026_OFFICIAL_MARKET_AVAILABILITY_IMPLEMENTATION.md
- docs/V4_027_OFFICIAL_ODDS_PROVENANCE_LEDGER_IMPLEMENTATION.md

The active package identity is exactly:

    verified-historical-backfill-export-package@1.0.0

The active historical intake identity is additive to B15-EWP-001, remains separate from PROSPECTIVE_CAPTURE, and has archive_write_authorized = false.

## 3. A — Frozen package canonicalization specification

### 3.1 Algorithm identity

    algorithm: SHA-256
    profile: v4-canonical-json@1.0
    encoding: UTF-8
    object key order: recursive lexicographic order
    array order: preserve semantic order
    JSON separators: comma and colon without whitespace
    ensure_ascii: false
    digest representation: sha256:<64 lowercase hexadecimal characters>

The runtime implementation is equivalent to:

    json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

No newline, indentation, platform encoding, locale sorting, or implicit timestamp normalization is part of the active rule.

### 3.2 Manifest substantive hash

For each import manifest, the active runtime hashes all manifest fields except:

    manifest_substantive_hash
    exported_at
    export_package_hash

UNKNOWN is the literal string "UNKNOWN". It is a real canonical value and is not converted to null, an empty string, a missing field, or a current timestamp. null remains distinct from UNKNOWN and is included when the contract permits it, for example revision_lineage.supersedes on revision 1.

### 3.3 Package substantive hash

The active package substantive body is:

1. Start with every top-level package field.
2. Exclude created_at, exported_at, package_substantive_hash, and package_sha256.
3. Replace each manifests[] item with the same object after excluding its export_package_hash and nested package_substantive_hash fields.
4. Canonicalize the resulting object with v4-canonical-json@1.0.
5. Compute SHA-256 and store it as package_substantive_hash.

The stable package inputs therefore include the file manifest, metadata manifest, all manifest-bound hashes and identities, manifest substantive hashes, and every other non-excluded package field. The raw image bytes are not embedded directly in this JSON digest; their identity enters through original_file_sha256. Metadata bytes enter through metadata_snapshot_sha256.

The active implementation is authoritative where the short schema wording is less explicit: both nested export_package_hash and nested package_substantive_hash are removed before computing the package substantive body.

### 3.4 Array and manifest ordering

Arrays are not sorted by the runtime. Semantic order is preserved. The r002 materializer must therefore keep one stable index across:

    file_manifest[i]
    metadata_manifest[i]
    manifests[i]

The corresponding manifest_id, original file hash, metadata snapshot hash, and Library identity must bind at the same index. If the r001 package does not expose a reproducible semantic order, r002 preparation must stop; an agent must not silently sort or regroup the arrays.

### 3.5 Package object hash versus ZIP hash

The active field named package_sha256 is computed by the current runtime as a canonical JSON hash of the complete package object after excluding only package_sha256. It is not a hash of ZIP container bytes.

The ZIP SHA-256 is a separate byte-level identity. The active repository contract does not specify ZIP member order, member timestamps, extra fields, compression method/level, external attributes, or a canonical ZIP writer. Consequently:

- the prior r001 ZIP hash cannot be independently reproduced from the active JSON contract alone;
- package_sha256 must not be populated with the ZIP byte hash;
- r002 needs a separately approved ZIP serialization profile and an explicit ZIP-byte hash field/binding before the final ZIP can be called reproducible.

This is a real r002 blocker, not a reason to change the substantive JSON rule.

### 3.6 Exclusion manifest boundary

The active export-package schema does not require an exclusion_manifest, does not define its member ordering, and does not define a dedicated hash binding. The current generic runtime would include an extra top-level exclusion field in the substantive JSON body because it is not on the exclusion list, but it would not validate its structure or bind it to the file/metadata manifests.

Therefore the only safe r002 decision is:

    Exclusion manifest hash inclusion = NOT FORMALLY FROZEN BY ACTIVE PACKAGE CONTRACT

The r002 package must add a governed exclusion-manifest field/binding (or an approved additive schema revision) before package readiness can become READY. The three previously reported exclusions remain expected review inputs:

    1 betting slip
    2 generated prediction dashboards
    all excluded artifacts = EXCLUDED, never RAW_FACT

## 4. B — Contract identity alignment

r002 must use:

    contract_version = verified-historical-backfill-export-package@1.0.0

It must not retain:

    chatgpt-library-handoff-export-package@1.0.0

The minimum r002 structural changes are:

| Area | r002 requirement |
|---|---|
| Package identity | Formal verified-historical-backfill-export-package@1.0.0 |
| Package revision | Integer 2; revision lineage must identify the r001 predecessor |
| Source origin | CHATGPT_LIBRARY_EXPORT |
| File binding | One file entry per original file with original SHA-256 and Library identity |
| Metadata binding | One immutable metadata snapshot entry per file and snapshot SHA-256 |
| Match binding | A resolved V4-020 canonical match identity per accepted raw artifact |
| Extraction binding | V4-025 evidence-compatible extraction/provenance record per artifact |
| Exclusions | Explicit, structured exclusion records bound to excluded source identities |
| Hash boundary | Active v4-canonical-json@1.0 substantive body plus separately specified ZIP bytes hash |
| Revision lineage | supersedes r001 package identity and both prior hash identities when available |

The current package validator accepts the formal contract identity and revision, but it does not yet validate all of the additional r002 structures above. This is why the r002 materialization remains blocked rather than being silently treated as valid merely because extra JSON fields are tolerated.

## 5. C — Canonical match identity review

### 5.1 Exact derivation rule

V4-020 defines:

    business_key = data_date + ":" + official_match_no
    canonical_match_id = UUIDv5(
      namespace = 8d3d4fd0-4701-5c5d-9fe2-90bb9d36b020,
      name = "match|" + business_key
    )

The lottery number is therefore an input to the business key; it is not itself the canonical match ID.

The identity resolver additionally requires the canonical structural fingerprint:

    competition_id | home_team_id | away_team_id | kickoff_at_normalized_to_UTC

Ordered home/away orientation is significant. A competition, team-orientation, timezone, or kickoff conflict returns BLOCKED / REQUIRES_REVIEW; values are not chosen by plausibility.

### 5.2 Snapshot binding

Two screenshots for one match must resolve to the same canonical_match_id. Snapshot time, image hash, Library identity, or extracted market payload may differ without creating a second match identity. A conflict in structural identity blocks the candidate and retains both observations.

### 5.3 Can all 40 be generated now?

Not from the current readable repository state. The staging area contains no candidate mapping, raw PNG, metadata snapshot, or r001 package. In addition, the active import-manifest schema only requires canonical_match_identity fields named canonical_match_id, competition, home, and away; it does not formally require data_date, official_match_no, competition_id, home_team_id, or away_team_id.

Accordingly:

    Derivation rule = READY and exact
    40/40 package identity review = NOT VERIFIED
    CANONICAL_MATCH_IDENTITY_READINESS = BLOCKED

Names must not be converted into team IDs without an approved deterministic mapping. Missing competition or team identity is a blocker. Kickoff conflicts are blockers. No identity may be generated from 010, 013, or any other lottery number alone.

## 6. D — Unknown timestamp policy

The following remain literal UNKNOWN unless independent raw-byte or Library metadata evidence exists:

    source_timestamp
    captured_at
    observed_at

chatgpt_upload_timestamp has exactly one permitted meaning:

    artifact existed no later than this timestamp

It is not bookmaker publication time, official publish time, source odds time, capture time, or observation time. An upload before kickoff only permits review-level progression to PROCEED_TO_EXPORT_INTAKE_VERIFICATION; it does not prove availability at an earlier prediction cutoff.

| Question | Decision under active contracts |
|---|---|
| Does UNKNOWN block structural package validation? | No, if the field is present literally as UNKNOWN and no conflict exists. |
| Does it block a no-write VALID_FOR_INTAKE dry run? | Not by itself. With known kickoff and upload-before-kickoff, the current dry-run can return VALID_FOR_INTAKE; that state is only a separate intake-authorization input, not archive eligibility. |
| Does it block ELIGIBLE_FOR_AS_OF_TRAINING? | Yes. V4-022/V4-027 require a known declared availability basis satisfying availability_at <= prediction_cutoff_at < kickoff_at; capture, observation, ingestion, or upload time cannot substitute for an unknown source time. |

The current 64-artifact set must therefore remain out of ELIGIBLE_FOR_AS_OF_TRAINING while these source/capture/observation fields are unknown. prediction_cutoff_at = UNKNOWN independently prevents a formal cutoff decision.

## 7. E — Official odds extraction provenance review

### 7.1 Required r002 artifact record

Each of the 64 artifact records must bind:

    artifact identity and original filename
    original PNG bytes SHA-256
    ChatGPT Library file identity/reference
    metadata snapshot hash
    canonical_match_id
    kickoff_at and source match facts
    extraction_method = OCR | MANUAL_TRANSCRIPTION | OCR_PLUS_MANUAL
    raw extraction text for each market that is verified
    typed structured market payload
    image hash binding
    reviewer and reviewed_at
    overall verification state
    market-level coverage states
    exact cutoff-visible RQSPF handicap line, when present
    contradiction/conflict state and all competing candidates
    extraction/evidence payload hash
    provenance hash and provenance root
    revision/supersedes lineage

The five market keys are exactly:

    SPF, RQSPF, EXACT_SCORE, TOTAL_GOALS, HTFT

V4-025 requires raw_text plus a typed payload for a VERIFIED market; NOT_VERIFIED, UNAVAILABLE, BLOCKED, and CONFLICTED states cannot expose an accepted official payload. A conflicted market must retain at least two typed candidates and their raw extraction text.

### 7.2 Review flow without archive write

The deterministic no-write scope is:

1. Read only from the approved staging package.
2. Verify each original PNG hash and metadata snapshot binding.
3. Resolve the V4-020 identity; block missing/conflicting structural facts.
4. Construct V4-025 screenshot evidence with image hash, extraction method, market-level raw text/payload, verification state, contradiction state, and evidence/payload/provenance hashes.
5. Run V4-026 market availability independently for all five markets.
6. Run V4-027 provenance/time review only when the selected source time is known.
7. Emit per-artifact and per-match review records in staging only.
8. Keep PENDING_INTAKE_VERIFICATION until all required provenance and conflicts are resolved; do not call it archive accepted or training eligible.

This flow is compatible with the existing V4-025/V4-026/V4-027 local append-only in-memory boundaries and performs no database or archive write. It is therefore implementation-feasible, but it cannot be executed in this task because the 64 raw artifacts and associated manifests are not readable locally.

### 7.3 Review-state conclusion

    No-write extraction review path = READY_FOR_EXECUTION_WHEN_PACKAGE_IS_PRESENT
    Actual 64-artifact extraction provenance review = NOT EXECUTED
    EXTRACTION_PROVENANCE_REVIEW_READINESS = BLOCKED

## 8. F — SPF-missing special cases

The following remain engine-specific and must not trigger whole-match rejection:

    2026-09-02 / 010 / S01
    2026-09-04 / 013 / S01
    2026-09-04 / 013 / S02

The active role rules remain:

- OUTCOME: requires SPF availability;
- HANDICAP: requires an exact cutoff-visible RQSPF line;
- GOALS: independently evaluates Total Goals;
- HTFT: independently requires halftime and fulltime labels.

Missing SPF can make OUTCOME review-ineligible while leaving HANDICAP, GOALS, or HTFT independently reviewable when their own evidence is complete. A missing RQSPF line blocks HANDICAP only; a different market must not be substituted.

## 9. G — r002 revision specification

The following is the complete preparation specification. It is a revision plan, not a generated package and not an archive-intake authorization.

    package_contract_identity:
      verified-historical-backfill-export-package@1.0.0
    package_revision: 2
    acquisition_mode: VERIFIED_HISTORICAL_BACKFILL
    source_origin: CHATGPT_LIBRARY_EXPORT
    supersedes:
      contract_identity: chatgpt-library-handoff-export-package@1.0.0
      zip_sha256: 22395904315cb6ef17ad11a3328ae3072975a200a9d035e1810962d81edddfd2
      substantive_sha256: NOT_ACCEPTED_UNTIL_RECOMPUTED_UNDER_ACTIVE_RULE
    canonicalization:
      algorithm_id: v4-canonical-json@1.0
      digest: SHA-256
      encoding: UTF-8
      object_keys: recursive_lexicographic
      arrays: preserve_semantic_order
      separators: comma_and_colon_without_whitespace
      unknown_semantics: literal_string_UNKNOWN
      null_semantics: distinct_literal_null_only_where_contract_allows
      package_substantive_excludes:
        - created_at
        - exported_at
        - package_substantive_hash
        - package_sha256
      nested_manifest_substantive_excludes:
        - export_package_hash
        - package_substantive_hash
      raw_hash_binding: original_file_sha256
      metadata_hash_binding: metadata_snapshot_sha256
      exclusion_manifest_binding: BLOCKED_UNTIL_FORMALLY_DEFINED
    zip_hash:
      meaning: SHA-256 of final ZIP bytes, distinct from package_substantive_hash and package_sha256
      serialization_profile: BLOCKED_UNTIL_ACTIVE_CONTRACT_ADDS_REPRODUCIBLE_ZIP_RULE
    manifest_schema:
      file_manifest: 64 entries, one per original PNG
      metadata_manifest: 64 entries, index-aligned with file_manifest
      import_manifests: 64 entries, index-aligned with both manifests
      canonical_matches: 40 entries only after V4-020 identity resolution
      extraction_provenance: 64 records, one per artifact
      exclusions: explicit records for generated/betting-slip artifacts, bound to source identity
    identity:
      rule: UUIDv5(namespace, match_pipe_data_date_colon_official_match_no)
      namespace: 8d3d4fd0-4701-5c5d-9fe2-90bb9d36b020
      structural_fingerprint: competition_id|home_team_id|away_team_id|kickoff_utc
    timestamps:
      source_timestamp: preserve UNKNOWN unless independent evidence exists
      captured_at: preserve UNKNOWN unless independent evidence exists
      observed_at: preserve UNKNOWN unless independent evidence exists
      chatgpt_upload_timestamp: artifact existed no later than upload timestamp
    extraction:
      contracts: V4-025, V4-026, V4-027
      verification: per-market and overall state, raw text, typed payload, conflicts, hashes
    spf_missing: engine_specific_only
    archive_write: FORBIDDEN

The supersedes.zip_sha256 above is the prior handoff hash supplied by the continuation context; it was not re-read from a local ZIP in this turn. It is a lineage pointer, not current verification evidence. The prior substantive hash is deliberately not accepted until r002 recomputes it under the active rule.

Before r002 can be marked ready, the materializer must additionally provide:

1. the real r001 package or equivalent immutable predecessor evidence;
2. a formally bound exclusion-manifest structure;
3. a reproducible ZIP serialization profile and explicit final ZIP-byte hash;
4. 40 V4-020-resolvable identities with no conflicts;
5. 64 extraction provenance records with V4-025-compatible states and hashes;
6. deterministic recomputation of every manifest hash, package substantive hash, package-object hash, and final ZIP-byte hash;
7. a second no-write validation pass showing no archive mutation.

## 10. H — Final governance decision

    PACKAGE_R002_REMEDIATION_READINESS = BLOCKED
    CANONICAL_MATCH_IDENTITY_READINESS = BLOCKED
    EXTRACTION_PROVENANCE_REVIEW_READINESS = BLOCKED
    INTAKE_RUNTIME_AUTHORIZATION_READINESS = BLOCKED
    Current Training Readiness = BLOCKED / TRAINING_DATA_INSUFFICIENT

The following prohibited actions were not performed:

    historical_source_archive write
    archive record/revision creation
    EWP-002 rerun
    EWP-003 rerun
    EWP-005 authorization
    model fit, calibration, promotion
    V4-076 / V4-052..055 execution
    Production, Supabase, migration, or V3.3.3 modification

## 11. Validation evidence

    focused no-write validator: PASS
    focused backfill unit tests: 11 / 11 PASS
    git diff --check: PASS
    HEAD: 2f858065092a83baa41676a4e8f4458a029db0a0
    working tree before this report: CLEAN
    historical_source_archive file count: 0
    historical_backfill_staging: .gitkeep only

This report is the only materialized artifact from this review. It does not create an archive record, change training counts, or authorize the next runtime phase.

## 12. Only permitted next scope

Provide the real r001 package, or its complete immutable raw/metadata/mapping contents, under the approved F-drive staging root. Then perform r002 materialization and the same no-write revalidation. Do not proceed to archive intake until the package, canonical identities, extraction provenance, substantive hashes, and final ZIP-byte hash all pass independently.

