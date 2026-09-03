# JCFB V4 Pre-BATCH-04 Local Execution

## Boundary

The real PostgreSQL runtime gate must be launched by the operator's Windows
PowerShell in `F:\Projects\jcfb-v4`, where Docker Desktop's local named-pipe
permission is available. Codex implements and statically verifies the executor
but must not connect to Docker/PostgreSQL or claim that the 20 smoke and 15
enforcement cases ran here.

BATCH-04 remains a hard gate. This procedure does not change V4-018/V4-019,
does not apply the original design migrations, does not connect Production or
Supabase, and does not touch JCFB V3.3.3.

## Prepare the project-scoped environment

```powershell
Set-Location F:\Projects\jcfb-v4
. .\scripts\activate_jcfb_v4_runtime.ps1
```

If the local execution policy blocks the repository script, allow it only in
the current process:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
. .\scripts\activate_jcfb_v4_runtime.ps1
```

All project cache, temporary, virtual-environment, report, and disposable
PostgreSQL data paths should now be under `F:\Projects\jcfb-v4\.runtime\`.

## Configure the disposable database

Copy `.env.runtime-validation.example` to
`.env.runtime-validation.local` and set a fresh, disposable password. The
local file is ignored by Git. Do not paste the password into a command line,
report, screenshot, or chat message.

The disposable connection contract must contain these non-secret endpoint
settings as well as the database, owner, and password values:

```text
JCFB_V4_RUNTIME_DB_HOST=127.0.0.1
JCFB_V4_RUNTIME_DB_PORT=55432
JCFB_V4_RUNTIME_DB_SSLMODE=disable
```

The compose file publishes only `127.0.0.1:55432` to container port `5432`.
The service uses a project-scoped ordinary bridge network; it intentionally
does not use `internal: true` because the prior Docker Desktop/WSL2 evidence
showed the declared binding without an actual `NetworkSettings.Ports` entry.
Readiness checks both actual `NetworkSettings.Ports` and `docker port`, so an
older container that shows healthy but has no exact loopback host port is
blocked before the Python connector.

The disposable network, loopback-only host binding, ephemeral credentials,
F-drive data bind, and Production hard-block together provide the isolation
boundary. Removing `internal: true` does not expose a public host port.

Start and check the local container explicitly:

```powershell
.\scripts\v4_disposable_runtime.ps1 -Action start
.\scripts\v4_disposable_runtime.ps1 -Action readiness
```

The compose file binds PostgreSQL data to the repository-relative
`.runtime\postgres` directory. It does not use a new Docker named volume.

## Verify, then plan

The default runner mode is plan-only. Both commands below are no-write:

```powershell
python -m tools.migration_harness --repo-root . canonical-hash
.\scripts\v4_run_prebatch04_runtime_validation.ps1 -PlanOnly
```

The plan report should show 9/9 hash matches, 20 smoke bindings, 15
enforcement bindings, no connector invocation, and no SQL execution. It is
written, when requested, to `.runtime\reports\prebatch04\` and contains no
credential value.

## Explicit disposable apply

After the container is healthy and the local project environment contains the
optional `psycopg` dependency, the only disposable apply command is:

```powershell
.\scripts\v4_run_prebatch04_runtime_validation.ps1 -ApplyDisposable
```

The wrapper imports only the expected local environment values, rechecks
Docker readiness, verifies hashes, validates the target, applies candidates
0001 through 0009, records history, prepares the disposable role simulation,
and executes all 20 smoke plus 15 enforcement handlers in isolated
transactions. A missing environment value, driver, wrong target identity,
hash mismatch, partial history, failed preflight, failed schema check, or
unexpected case outcome stops the run with a specific redacted reason. The
report distinguishes a connector that was not invoked from a refused
connection, authentication failure, target identity mismatch, driver absence,
SQL apply failure, and runtime validation failure. Each expected rejection
must match its declared SQLSTATE and stable database mechanism; a generic SQL
error does not pass.

The report also records `DISPOSABLE_ROLE_SIMULATION` when local-only
`backend`, `executor`, or `auditor` fixtures are created. This does not emulate
Supabase Auth, and the Advisor-specific check remains
`NOT_RUN_IN_DISPOSABLE`. Staging readiness is emitted as
`READY_FOR_PRODUCTION_REVIEW` only when migrations 9/9, smoke 20/20,
enforcement 15/15, schema/security checks, and all hard gates pass.

The wrapper always calls
`F:\Projects\jcfb-v4\.runtime\python-venv\Scripts\python.exe`; it does not
fall back to a global Python interpreter.

The wrapper never accepts a Production target. A staging run needs a separately
reviewed non-secret target descriptor and must be invoked through the Python
executor rather than by changing the disposable wrapper's target. Even a
successful disposable run never executes BATCH-04 and never changes
V4-018/V4-019.

## Capture and teardown

Review the redacted latest pointer and the immutable per-run files after local
execution:

```text
.runtime\reports\prebatch04\latest.json
.runtime\reports\prebatch04\runs\<run_id>\prebatch04_runtime_validation.json
.runtime\reports\prebatch04\runs\<run_id>\prebatch04_runtime_validation.md
```

The report writer never overwrites an earlier run. Use the persisted `run_id`,
timestamps, `git_head`, and `runtime_summary_lines` to match the terminal
summary to one exact invocation; the selector also scans all run directories
when recovering the newest valid report.

Stop the container when finished:

```powershell
.\scripts\v4_disposable_runtime.ps1 -Action stop
```

Only after saving the evidence and confirming it is no longer needed, destroy
the disposable container and its F-drive data directory:

```powershell
.\scripts\v4_disposable_runtime.ps1 -Action destroy -ConfirmDestroy
```

The destroy action is scoped to `F:\Projects\jcfb-v4\.runtime\postgres` and
does not remove source, reports, or any other project directory.
