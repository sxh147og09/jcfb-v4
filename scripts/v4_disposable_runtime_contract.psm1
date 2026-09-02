Set-StrictMode -Version Latest

function New-DisposableHostPortEvidenceResult {
    param(
        [bool]$Passed,
        [string]$Status,
        [string]$Message
    )

    return [pscustomobject]@{
        Passed = $Passed
        Status = $Status
        Message = $Message
    }
}

function Test-DisposableHostPortEvidence {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowNull()]
        [object]$NetworkSettingsPorts,
        [Parameter(Mandatory = $true)]
        [AllowNull()]
        [AllowEmptyCollection()]
        [object[]]$DockerPortLines,
        [string]$ExpectedHostAddress = '127.0.0.1',
        [string]$ExpectedHostPort = '55432',
        [string]$ExpectedContainerPort = '5432'
    )

    $containerKey = '{0}/tcp' -f $ExpectedContainerPort
    $portsProperty = $null
    if ($null -ne $NetworkSettingsPorts) {
        $portsProperty = $NetworkSettingsPorts.PSObject.Properties[$containerKey]
    }
    if ($null -eq $portsProperty -or $null -eq $portsProperty.Value) {
        return New-DisposableHostPortEvidenceResult `
            -Passed $false `
            -Status 'BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_MISSING' `
            -Message 'NetworkSettings.Ports does not contain an actual PostgreSQL host port mapping.'
    }

    $bindings = @($portsProperty.Value)
    if ($bindings.Count -eq 0 -or $null -eq $bindings[0]) {
        return New-DisposableHostPortEvidenceResult `
            -Passed $false `
            -Status 'BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_MISSING' `
            -Message 'NetworkSettings.Ports reports no actual PostgreSQL host port mapping.'
    }

    foreach ($binding in $bindings) {
        if ($null -eq $binding) {
            return New-DisposableHostPortEvidenceResult `
                -Passed $false `
                -Status 'BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_MISSING' `
                -Message 'NetworkSettings.Ports contains an empty PostgreSQL host port binding.'
        }

        if ([string]$binding.HostIp -ne $ExpectedHostAddress -or [string]$binding.HostPort -ne $ExpectedHostPort) {
            return New-DisposableHostPortEvidenceResult `
                -Passed $false `
                -Status 'BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_NOT_LOCALHOST' `
                -Message ('The actual PostgreSQL mapping must be bound only to {0}:{1}.' -f $ExpectedHostAddress, $ExpectedHostPort)
        }
    }

    $expectedEndpoint = '{0}:{1}' -f $ExpectedHostAddress, $ExpectedHostPort
    $dockerPorts = @(
        $DockerPortLines |
            ForEach-Object {
                if ($null -ne $_) {
                    $line = ([string]$_).Trim()
                    if ($line.Length -gt 0) {
                        $line
                    }
                }
            }
    )
    if ($dockerPorts.Count -eq 0) {
        return New-DisposableHostPortEvidenceResult `
            -Passed $false `
            -Status 'BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_MISSING' `
            -Message 'docker port returned no actual PostgreSQL host port mapping.'
    }
    if ($dockerPorts.Count -ne 1 -or [string]$dockerPorts[0] -ne $expectedEndpoint) {
        return New-DisposableHostPortEvidenceResult `
            -Passed $false `
            -Status 'BLOCKED_DISPOSABLE_POSTGRES_HOST_PORT_NOT_LOCALHOST' `
            -Message ('docker port did not report the exact loopback mapping {0}.' -f $expectedEndpoint)
    }

    return New-DisposableHostPortEvidenceResult `
        -Passed $true `
        -Status 'PASS' `
        -Message ('Actual NetworkSettings.Ports and docker port both report {0}:{1}->{2}.' -f $ExpectedHostAddress, $ExpectedHostPort, $ExpectedContainerPort)
}

Export-ModuleMember -Function Test-DisposableHostPortEvidence
