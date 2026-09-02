# JCFB V4 Disposable Runtime Enablement 1.0

## Current state

BLOCKED_ENV_SETUP_REQUIRED

The repository package is ready, but this Windows host cannot provide a
disposable PostgreSQL runtime yet:

| Check | Result |
|---|---|
| Docker command | NO — BLOCKED_DOCKER_NOT_INSTALLED |
| Docker daemon | NO |
| psql command | NO |
| Ports 5432–5434 | No listener detected |
| Existing Docker/PostgreSQL app registration | Not detected |
| Disposable PostgreSQL available now | NO |

No installer was downloaded or run. No database was started, contacted, or
written. No Production Supabase target was inspected.

## Package included in this remediation

- docker-compose.runtime-validation.yml
  - PostgreSQL 16 Alpine baseline
  - explicit local container name jcfb-v4-disposable-pg
  - host binding 127.0.0.1:55432 only
  - project-scoped ordinary bridge network
  - F-drive bind at .runtime/postgres
  - healthcheck and no restart policy
- .env.runtime-validation.example
  - database and owner placeholders
  - empty password placeholder only
- scripts/v4_disposable_runtime.ps1
  - start, readiness, stop, and confirmed destroy
  - refuses to proceed when Docker, its daemon, or the local ephemeral
    password is unavailable
  - does not apply migrations

The local file .env.runtime-validation.local is ignored and must never be
committed. Its password is not present in this repository or in the report.

## Minimum user action

1. Install Docker Desktop manually from the official Docker distribution.
2. Start Docker Desktop and wait until its local engine reports ready.
3. In the repository root, copy
   .env.runtime-validation.example to .env.runtime-validation.local.
4. Set a fresh ephemeral local password in that ignored file. Do not paste the
   value into chat, commit it, or place it in logs.
5. Start the package:

   .\scripts\v4_disposable_runtime.ps1 -Action start

6. Confirm readiness:

   .\scripts\v4_disposable_runtime.ps1 -Action readiness

The wrapper uses only DISPOSABLE_LOCAL, binds only to localhost port 55432,
and does not contain a Production Supabase connection path. It will report a
blocked status instead of bypassing a missing prerequisite.

## Network and actual-port safety

The disposable PostgreSQL service uses the Compose project's ordinary bridge
network. It intentionally does not use `internal: true`: operator evidence on
Docker Desktop/WSL2 showed that the internal network could leave the declared
host binding in `HostConfig.PortBindings` while the actual
`NetworkSettings.Ports` remained empty. The wrapper now requires both actual
`NetworkSettings.Ports` and `docker port` to report exactly
`127.0.0.1:55432 -> 5432` before readiness can pass.

Isolation is provided by the disposable project network, the loopback-only
host binding, fresh ephemeral credentials, the F-drive data bind, and the
Production hard-block. Removing `internal: true` does not create a public host
listener; the published host address remains fixed to `127.0.0.1`.

## Cleanup

Stop while preserving the F-drive data bind:

.\scripts\v4_disposable_runtime.ps1 -Action stop

Destroy the named temporary container and its F-drive data directory after validation:

.\scripts\v4_disposable_runtime.ps1 -Action destroy -ConfirmDestroy

The destroy action has an explicit confirmation switch and is scoped to the
named disposable runtime only. Starting this package still does not apply
V4 migrations; the next approved Pre-BATCH-04 runtime gate must perform that
separately.
