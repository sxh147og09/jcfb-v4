# JCFB V4 Canonical Migration Hash 1.0

## Scope

This profile applies only to the nine runtime candidates under
`database/migrations/v4_runtime_candidate/`. The original design migrations
under `database/migrations/v4/` remain design-only artifacts and are not
rewritten or treated as deployment approval.

The machine-readable source of truth is
`0000_runtime_candidate_manifest.json`. The Markdown manifest is the review
surface and must agree with the JSON manifest and the SQL headers.

## Canonical input

Each digest is serialized as `sha256:<64 lowercase hexadecimal characters>`.
The hash input is a framed byte sequence containing:

1. profile marker `v4-canonical-json@1.0`;
2. canonicalization version `v4-canonical-migration@1.0.0`;
3. canonical JSON metadata, encoded as UTF-8 with sorted keys and compact
   separators;
4. canonical SQL bytes.

The stable metadata fields are exactly:

`migration_id`, `sequence` (zero-padded four-character text), `name`,
`migration_version`, `depends_on`, `schema_contract_version`, `authored_at`,
and the repository-relative candidate `file` path with `/` separators.

Execution-time or mutable fields are excluded: `applied_at`, `applied_by`,
`execution_duration`, `deployment_host`, and `status`.

SQL canonicalization is deliberately lexical rather than a SQL formatter:

- decode as UTF-8 and remove a UTF-8 BOM if present;
- normalize CRLF and CR to LF;
- remove horizontal trailing spaces and tabs from every line;
- preserve SQL tokens, comments, internal whitespace, statement order, and
  dollar-quoted bodies;
- remove trailing blank lines and emit exactly one final LF;
- normalize the two self-hash header values and the current 0009 registry seed
  value to `<SELF_HASH>` only during digest calculation.

The verifier still requires the actual generated digest in both SQL headers,
the JSON manifest, the Markdown manifest, and the 0009 registry seed rows.
Therefore changing a header or seed value is detected even though the
self-reference is excluded from its own digest calculation.

## Commands

From the formal F-drive workspace:

```powershell
Set-Location F:\Projects\jcfb-v4
python -m tools.migration_harness --repo-root . canonical-hash
python -m tools.migration_harness --repo-root . canonical-hash --write
```

`canonical-hash` is verification-only. `--write` is the explicit maintenance
operation that updates only the runtime-candidate package. Re-run the verifier
after any SQL or stable-metadata change. A changed SQL byte or stable metadata
field must produce a different digest and a manifest mismatch until the
manifest is deliberately regenerated and reviewed.

The verifier is also called by `scripts/validate_v4_runtime_candidates.ps1`.
It fails closed on a pending marker, a mismatch, a path escape, a dependency
drift, a missing SQL header, or a 0009 seed mismatch.

## Review boundary

Generated hashes make the disposable/staging candidate package reproducible;
they do not approve Production, Supabase, BATCH-04, V4-018, or V4-019.
