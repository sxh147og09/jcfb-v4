# JCFB V4 F: Drive Historical Archive Storage Policy

Policy identity: `v4-f-drive-historical-archive-storage@1.0.0`

## Approved locations

The approved project-drive root for future historical source archive records
is:

`F:\Projects\jcfb-v4\approved_data\historical_source_archive\`

Governance manifests, schemas, contracts, and validators remain tracked under
the repository `config/`, `docs/`, `scripts/`, and `tests/` paths. The archive
population is not committed by this amendment.

## Forbidden locations

`.runtime\` is disposable runtime/cache/PostgreSQL state and is never an
approved historical source. `src/data\` remains a source boundary and is not a
historical archive. `tests/fixtures\` is synthetic test material and cannot
be counted as training data. C: drive temporary files, unmanaged desktop
exports, V3.3.3 repositories, and database/Supabase storage are not approved
archive locations.

## File and hash boundary

Future archive objects must be append-only, have a deterministic match and
revision path, retain the original payload/image/file hash, and include a
canonical manifest hash. A manifest must identify source, source reference,
source timestamp, capture/observation time, ingestion time, cutoff, kickoff,
market/context type, and eligibility. Hash mismatch, path escape, missing
provenance, or unverifiable time is fail-closed.

This policy approves the storage location and governance boundary only. It
does not claim that the directory exists, that a historical population is
available, or that any import has occurred.
