# B15-EWP-001 r003 Read-Interface Amendment

Status: **COMPLETE AMENDMENT / EWP-001 NOT REOPENED**
Supersedes: EWP-001 `r002` closure artifact
Scope: approved-archive read-only interface only

The `execution-work-package@1.0.0` contract permits append-only revisioned
amendment evidence. This amendment does not change the original EWP-001
capture authorization, does not change its COMPLETE state, and does not
authorize B15-EWP-002. It adds the governed reader implemented by
`src/historical_source_archive/read_interface.py`.

The reader enumerates approved manifests and exact archive records; filters by
match, cutoff profile, artifact type/domain, and cutoff-visible source
availability; excludes post-cutoff corrections; resolves supersedes chains;
returns exact reference/hash/revision; separates pre-match records from
post-match labels; and emits a deterministic candidate snapshot. It has no
write, update, delete, import, or training-dataset operation and does not use
the runtime's ungoverned internal `records` or `manifests` attributes.
