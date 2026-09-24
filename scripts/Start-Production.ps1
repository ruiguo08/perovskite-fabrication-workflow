[CmdletBinding()]
param(
    [string]$PythonExecutable = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path $PSScriptRoot -Parent
if (-not $PythonExecutable) {
    $PythonExecutable = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonExecutable)) {
    throw "Python executable does not exist: $PythonExecutable"
}

if (-not $env:PEROVSKITE_DATABASE_URL) {
    throw "PEROVSKITE_DATABASE_URL is required."
}
try {
    $databaseUrl = [uri]$env:PEROVSKITE_DATABASE_URL
}
catch {
    throw "PEROVSKITE_DATABASE_URL is not a valid URL."
}
$databaseUser = [uri]::UnescapeDataString(($databaseUrl.UserInfo -split ":", 2)[0])
if (
    $databaseUrl.Scheme -ne "postgresql+asyncpg" -or
    $databaseUser -ne "perovskite_app"
) {
    throw "Production must use the restricted PostgreSQL role perovskite_app."
}

if ($env:PEROVSKITE_REQUIRE_HTTPS -notin @("1", "true", "TRUE", "yes", "YES", "on", "ON")) {
    throw "PEROVSKITE_REQUIRE_HTTPS must be true in production."
}
if (-not $env:PEROVSKITE_ALLOWED_HOSTS -or $env:PEROVSKITE_ALLOWED_HOSTS.Contains("*")) {
    throw "PEROVSKITE_ALLOWED_HOSTS must contain explicit host names only."
}

& $PythonExecutable -c "import sys; sys.exit('Python 3.14 or newer is required') if sys.version_info < (3, 14) else None"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.14 or newer is required."
}

& $PythonExecutable -m web.admin_cli check-database
if ($LASTEXITCODE -ne 0) {
    throw "The database is unavailable or its migrations are incomplete."
}

& $PythonExecutable -m web
if ($LASTEXITCODE -ne 0) {
    throw "The production web server exited with code $LASTEXITCODE."
}
