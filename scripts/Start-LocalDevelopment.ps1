[CmdletBinding()]
param(
    [switch]$EnableDocs,

    [string]$PythonExecutable = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path $PSScriptRoot -Parent
if (-not $PythonExecutable) {
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

function Assert-LocalApplicationDatabaseUrl {
    param(
        [Parameter(Mandatory)]
        [string]$DatabaseUrl
    )

    try {
        $parsed = [uri]$DatabaseUrl
    }
    catch {
        throw "PEROVSKITE_DATABASE_URL is not a valid URL."
    }
    $username = [uri]::UnescapeDataString(($parsed.UserInfo -split ":", 2)[0])
    $databaseName = [uri]::UnescapeDataString(
        $parsed.AbsolutePath.TrimStart("/")
    )
    if (
        $parsed.Scheme -ne "postgresql+asyncpg" -or
        -not $parsed.IsLoopback -or
        $username -ne "perovskite_app" -or
        $databaseName -ne "perovskite_registry"
    ) {
        throw (
            "Local development may only use role perovskite_app against " +
            "the loopback perovskite_registry database."
        )
    }
}

if (-not (Test-Path -LiteralPath $PythonExecutable)) {
    throw "Python executable does not exist: $PythonExecutable"
}

if (-not $env:PEROVSKITE_DATABASE_URL) {
    & (Join-Path $PSScriptRoot "Set-LocalDatabaseUrls.ps1") -Scope Application
}
$databaseUrl = $env:PEROVSKITE_DATABASE_URL
Assert-LocalApplicationDatabaseUrl -DatabaseUrl $databaseUrl

Invoke-ProjectPython -Arguments @(
    "-c",
    "import sys; sys.exit('Python 3.14 or newer is required') if sys.version_info < (3, 14) else None"
)
Invoke-ProjectPython -Arguments @("-m", "alembic", "upgrade", "head")
Invoke-ProjectPython -Arguments @("-m", "alembic", "check")
Invoke-ProjectPython -Arguments @("-m", "web.admin_cli", "check-database")

$previousRequireHttps = $env:PEROVSKITE_REQUIRE_HTTPS
$previousEnableDocs = $env:PEROVSKITE_ENABLE_DOCS
try {
    $env:PEROVSKITE_REQUIRE_HTTPS = "false"
    $env:PEROVSKITE_ENABLE_DOCS = if ($EnableDocs) { "true" } else { "false" }
    Write-Output "Starting local development server at http://localhost:8000/login"
    Write-Warning "HTTP mode is for this computer only; do not expose port 8000 to the network."
    & $PythonExecutable -m web
    if ($LASTEXITCODE -ne 0) {
        throw "The local web server exited with code $LASTEXITCODE."
    }
}
finally {
    $env:PEROVSKITE_REQUIRE_HTTPS = $previousRequireHttps
    $env:PEROVSKITE_ENABLE_DOCS = $previousEnableDocs
}
