$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Error "Python virtual environment was not found at $python. Run: python -m pip install -e '.[dev]'"
    exit 1
}

$secureToken = $null
$tokenBstr = [IntPtr]::Zero
$token = $null
$exitCode = 1

try {
    $secureToken = Read-Host -Prompt 'Paste your STRATZ token for this local launch' -AsSecureString
    $tokenBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenBstr)

    if ([string]::IsNullOrWhiteSpace($token)) {
        Write-Error 'Token was empty. The app was not started.'
    }
    else {
        [Environment]::SetEnvironmentVariable('STRATZ_API_TOKEN', $token, 'Process')
        & $python -m dota_support_draft
        $exitCode = $LASTEXITCODE
    }
}
finally {
    [Environment]::SetEnvironmentVariable('STRATZ_API_TOKEN', $null, 'Process')
    $token = $null
    if ($tokenBstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenBstr)
        $tokenBstr = [IntPtr]::Zero
    }
    if ($null -ne $secureToken) {
        $secureToken.Dispose()
    }
}

exit $exitCode
