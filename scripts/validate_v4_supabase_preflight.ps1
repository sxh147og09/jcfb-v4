[CmdletBinding()]
param(
    [string]$RepoRoot
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) {
    Write-Output 'JCFB_V4_SUPABASE_PREFLIGHT_PLAN=FAIL'
    Write-Output 'FAIL: Python is unavailable for the read-only preflight validator.'
    exit 1
}

$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $RepoRoot
    $jsonOutput = & $python.Source -m tools.migration_harness --repo-root $RepoRoot supabase-preflight
    if ($LASTEXITCODE -ne 0) {
        Write-Output 'JCFB_V4_SUPABASE_PREFLIGHT_PLAN=FAIL'
        Write-Output 'FAIL: Supabase preflight validator process failed.'
        exit 1
    }
    try {
        $report = ($jsonOutput -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        Write-Output 'JCFB_V4_SUPABASE_PREFLIGHT_PLAN=FAIL'
        Write-Output 'FAIL: Supabase preflight validator output was not valid JSON.'
        exit 1
    }
}
finally {
    Set-Location -LiteralPath $previousLocation
}

$requiredPasses = [ordered]@{
    contract_status = $report.status -eq 'PASS'
    preflight_status = $report.supabase_preflight_plan -eq 'PASS'
    production_project_ref = $report.production_project_ref -eq 'icndieflfvydixtehgzu'
    production_target_identity = $report.production_target_identity -eq 'KNOWN'
    production_apply_closed = $report.production_apply_allowed -eq $false
    explicit_apply_approval_required = $report.explicit_apply_approval_required -eq $true
    baseline_migration_history = $report.checks.baseline_migration_history.status -eq 'PASS'
    baseline_schema_object_identities = $report.checks.baseline_schema_object_identities.status -eq 'PASS'
    schema_baseline_diff_contract = $report.checks.schema_baseline_diff_contract.status -eq 'PASS'
    security_advisor_baseline = $report.checks.security_advisor_baseline.status -eq 'PASS'
    performance_advisor_baseline = $report.checks.performance_advisor_baseline.status -eq 'PASS'
    pre_existing_security_debt_isolated = $report.checks.pre_existing_security_debt_isolated.status -eq 'PASS'
    advisor_before_after_contract = $report.checks.advisor_before_after_contract.status -eq 'PASS'
    partial_apply_detection = $report.checks.partial_apply_detection.status -eq 'PASS'
    forward_fix_recovery = $report.checks.forward_fix_recovery.status -eq 'PASS'
    post_apply_verification = $report.checks.post_apply_verification.status -eq 'PASS'
    v333_isolation = $report.checks.v333_isolation.status -eq 'PASS'
    canonical_hashes = $report.checks.canonical_hashes.status -eq 'PASS'
    secret_policy = $report.checks.secret_policy.status -eq 'PASS'
    production_db_writes = $report.execution_boundary.production_db_writes_performed -eq 'NO'
    supabase_writes = $report.execution_boundary.supabase_writes_performed -eq 'NO'
    batch_04 = $report.execution_boundary.batch_04_executed -eq 'NO'
    v4_018_v4_019 = $report.execution_boundary.v4_018_v4_019_changed -eq 'NO'
    v333_mutated = $report.execution_boundary.v333_mutated -eq 'NO'
    next_stage = $report.next_stage -eq 'BATCH_04_PRODUCTION_READINESS_FINAL_REVIEW_3'
}
$failedChecks = @($requiredPasses.GetEnumerator() | Where-Object { $_.Value -ne $true })
if ($failedChecks.Count -gt 0) {
    Write-Output 'JCFB_V4_SUPABASE_PREFLIGHT_PLAN=FAIL'
    foreach ($failedCheck in $failedChecks) {
        Write-Output ("FAIL: {0}" -f $failedCheck.Key)
    }
    foreach ($issue in @($report.issues)) {
        Write-Output ("FAIL: {0} {1}" -f $issue.code, $issue.message)
    }
    exit 1
}

Write-Output 'JCFB_V4_SUPABASE_PREFLIGHT_PLAN=PASS'
Write-Output 'PRODUCTION_PROJECT_REF=icndieflfvydixtehgzu'
Write-Output 'BASELINE_MIGRATION_HISTORY=9/9 CAPTURED'
Write-Output 'BASELINE_SCHEMA_OBJECT_IDENTITIES=PASS'
Write-Output 'SECURITY_ADVISOR_BASELINE=PASS'
Write-Output 'PERFORMANCE_ADVISOR_BASELINE=PASS'
Write-Output 'SCHEMA_BASELINE_DIFF_CONTRACT=PASS'
Write-Output 'ADVISOR_BEFORE_AFTER_CONTRACT=PASS'
Write-Output 'PARTIAL_APPLY_DETECTION=PASS'
Write-Output 'FORWARD_FIX_RECOVERY=PASS'
Write-Output 'POST_APPLY_VERIFICATION_PLAN=PASS'
Write-Output 'PRODUCTION_HARD_BLOCK=PASS'
Write-Output 'EXPLICIT_APPLY_APPROVAL_REQUIRED=PASS'
Write-Output 'CANONICAL_HASHES=9/9 PASS'
Write-Output 'PRODUCTION_SUPABASE_WRITES=NO'
Write-Output 'BATCH_04_EXECUTED=NO'
Write-Output 'V4_018_V4_019_CHANGED=NO'
Write-Output 'NEXT_STAGE=BATCH_04_PRODUCTION_READINESS_FINAL_REVIEW_3'
exit 0
