[CmdletBinding()]
param(
    [string]$PythonExecutable = "",

    [string]$CredentialFile = (
        Join-Path $env:LOCALAPPDATA `
            "PerovskiteWorkflow\test-database.credential.clixml"
    ),

    [switch]$PostgreSQLOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $PythonExecutable) {
    $repositoryRoot = Split-Path $PSScriptRoot -Parent
    $virtualEnvironmentPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
    $condaPython = if ($env:CONDA_PREFIX) {
        Join-Path $env:CONDA_PREFIX "python.exe"
    }
    else {
        $null
    }

    if (Test-Path -LiteralPath $virtualEnvironmentPython) {
        $PythonExecutable = $virtualEnvironmentPython
    }
    elseif ($condaPython -and (Test-Path -LiteralPath $condaPython)) {
        $PythonExecutable = $condaPython
    }
    else {
        $PythonExecutable = (Get-Command python -ErrorAction Stop).Source
    }
}

if (-not (Test-Path -LiteralPath $PythonExecutable)) {
    throw "Python executable does not exist: $PythonExecutable"
}

function Get-DatabaseUrlFromCredential {
    param(
        [Parameter(Mandatory)]
        [pscredential]$Credential,

        [Parameter(Mandatory)]
        [string]$DatabaseName
    )

    $encodedUser = $null
    $encodedPassword = $null
    try {
        $encodedUser = [uri]::EscapeDataString($Credential.UserName)
        $encodedPassword = [uri]::EscapeDataString(
            $Credential.GetNetworkCredential().Password
        )
        return (
            "postgresql+asyncpg://{0}:{1}@127.0.0.1:5432/{2}" -f
            $encodedUser,
            $encodedPassword,
            $DatabaseName
        )
    }
    finally {
        $encodedPassword = $null
        $encodedUser = $null
    }
}

function Invoke-ProjectPython {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    & $PythonExecutable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw (
            "$PythonExecutable $($Arguments -join ' ') failed " +
            "with exit code $LASTEXITCODE."
        )
    }
}

function Assert-LocalTestDatabaseUrl {
    param(
        [Parameter(Mandatory)]
        [string]$DatabaseUrl
    )

    try {
        $parsed = [uri]$DatabaseUrl
    }
    catch {
        throw "PEROVSKITE_TEST_POSTGRESQL_URL is not a valid URL."
    }
    $username = [uri]::UnescapeDataString(($parsed.UserInfo -split ":", 2)[0])
    $databaseName = [uri]::UnescapeDataString(
        $parsed.AbsolutePath.TrimStart("/")
    )
    if (
        $parsed.Scheme -ne "postgresql+asyncpg" -or
        -not $parsed.IsLoopback -or
        $username -ne "perovskite_test" -or
        $databaseName -ne "perovskite_test"
    ) {
        throw (
            "Refusing to run tests: use role perovskite_test against the " +
            "loopback perovskite_test database."
        )
    }
}

$previousTestUrl = $env:PEROVSKITE_TEST_POSTGRESQL_URL
$testUrl = $previousTestUrl

if (-not $testUrl -and $CredentialFile) {
    if (-not (Test-Path -LiteralPath $CredentialFile)) {
        throw (
            "Test credential does not exist. Run " +
            "scripts\Configure-LocalTestDatabase.ps1 first."
        )
    }

    try {
        $storedCredentials = Import-Clixml -LiteralPath $CredentialFile
    }
    catch [System.Security.Cryptography.CryptographicException] {
        throw (
            "The test credential is encrypted for your Windows account. " +
            "Run this script as that account; Codex must use approved " +
            "user-context execution."
        )
    }
    if ($storedCredentials.Test -isnot [pscredential]) {
        throw "Credential file must contain a PSCredential property named Test."
    }
    if ($storedCredentials.Test.UserName -ne "perovskite_test") {
        throw "The Test credential must be for PostgreSQL role perovskite_test."
    }

    $testUrl = Get-DatabaseUrlFromCredential `
        -Credential $storedCredentials.Test `
        -DatabaseName "perovskite_test"
    $storedCredentials = $null
}

if (-not $testUrl) {
    throw (
        "PEROVSKITE_TEST_POSTGRESQL_URL is not configured. " +
        "Run scripts\Configure-LocalTestDatabase.ps1 first."
    )
}
if (-not $testUrl.StartsWith("postgresql+asyncpg://")) {
    throw "PEROVSKITE_TEST_POSTGRESQL_URL must use postgresql+asyncpg."
}
Assert-LocalTestDatabaseUrl -DatabaseUrl $testUrl

$previousUrl = $env:PEROVSKITE_DATABASE_URL
try {
    $env:PEROVSKITE_TEST_POSTGRESQL_URL = $testUrl
    $env:PEROVSKITE_DATABASE_URL = $testUrl
    Invoke-ProjectPython -Arguments @("-m", "alembic", "upgrade", "head")
    Invoke-ProjectPython -Arguments @("-m", "alembic", "current")
    Invoke-ProjectPython -Arguments @("-m", "alembic", "check")
    Invoke-ProjectPython -Arguments @("-m", "web.admin_cli", "check-database")

    if ($PostgreSQLOnly) {
        Invoke-ProjectPython -Arguments @(
            "-m", "unittest", "tests.test_postgresql_integration", "-v"
        )
    }
    else {
        Invoke-ProjectPython -Arguments @(
            "-m", "unittest", "discover", "-s", "tests", "-v"
        )
    }
}
finally {
    $env:PEROVSKITE_DATABASE_URL = $previousUrl
    $env:PEROVSKITE_TEST_POSTGRESQL_URL = $previousTestUrl
    $testUrl = $null
}
