Set-StrictMode -Version Latest

function ConvertFrom-ReadinessKeyValueOutput {
    [CmdletBinding()]
    param(
        [Parameter()]
        [AllowNull()]
        [AllowEmptyCollection()]
        [object[]]$OutputLines = @()
    )

    $fields = [ordered]@{}
    foreach ($outputItem in @($OutputLines)) {
        if ($null -eq $outputItem) {
            continue
        }

        $text = [string]$outputItem
        foreach ($line in ($text -split '\r?\n')) {
            if ([string]::IsNullOrWhiteSpace($line)) {
                continue
            }
            if ($line -notmatch '^\s*(?<key>[A-Z][A-Z0-9_]*)\s*=\s*(?<value>\S(?:.*\S)?)\s*$') {
                continue
            }

            $key = $Matches['key']
            $value = $Matches['value'].Trim()
            if ($fields.Contains($key)) {
                throw ("Readiness output contains duplicate key: {0}." -f $key)
            }
            $fields.Add($key, $value)
        }
    }

    return ,$fields
}

function New-ReadinessGateResult {
    param(
        [bool]$Passed,
        [string]$Reason,
        [System.Collections.IDictionary]$Fields
    )

    return [pscustomobject]@{
        Passed = $Passed
        Reason = $Reason
        Fields = $Fields
    }
}

function Test-DisposableReadinessOutput {
    [CmdletBinding()]
    param(
        [Parameter()]
        [AllowNull()]
        [AllowEmptyCollection()]
        [object[]]$OutputLines = @(),
        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    $fields = [ordered]@{}
    try {
        $fields = ConvertFrom-ReadinessKeyValueOutput -OutputLines $OutputLines
    }
    catch {
        return New-ReadinessGateResult -Passed $false -Reason $_.Exception.Message -Fields $fields
    }

    if ($ExitCode -ne 0) {
        return New-ReadinessGateResult -Passed $false -Reason ("Readiness helper returned exit code {0}." -f $ExitCode) -Fields $fields
    }

    foreach ($requiredKey in @(
        'DISPOSABLE_RUNTIME_READINESS',
        'TARGET_IDENTITY',
        'MIGRATIONS_APPLIED'
    )) {
        if (-not $fields.Contains($requiredKey)) {
            return New-ReadinessGateResult -Passed $false -Reason ("Readiness output is missing required key: {0}." -f $requiredKey) -Fields $fields
        }
    }

    if ([string]$fields['DISPOSABLE_RUNTIME_READINESS'] -ne 'PASS') {
        return New-ReadinessGateResult -Passed $false -Reason 'Readiness output is not DISPOSABLE_RUNTIME_READINESS=PASS.' -Fields $fields
    }
    if ([string]$fields['TARGET_IDENTITY'] -ne 'DISPOSABLE_LOCAL') {
        return New-ReadinessGateResult -Passed $false -Reason 'Readiness output target identity is not DISPOSABLE_LOCAL.' -Fields $fields
    }
    if ([string]$fields['MIGRATIONS_APPLIED'] -ne 'NO') {
        return New-ReadinessGateResult -Passed $false -Reason 'MIGRATIONS_APPLIED must be NO before disposable apply.' -Fields $fields
    }

    return New-ReadinessGateResult -Passed $true -Reason 'Disposable readiness keys and exit code passed.' -Fields $fields
}

Export-ModuleMember -Function ConvertFrom-ReadinessKeyValueOutput, Test-DisposableReadinessOutput
