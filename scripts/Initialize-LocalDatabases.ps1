[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-PostgreSqlUrl {
    param(
        [Parameter(Mandatory)]
        [string]$VariableName
    )

    $value = [Environment]::GetEnvironmentVariable($VariableName, "Process")
    if (-not $value) {
        throw "$VariableName is not configured. Run scripts\Set-LocalDatabaseUrls.ps1 first."
    }
    if (-not $value.StartsWith("postgresql+asyncpg://")) {
        throw "$VariableName must use postgresql+asyncpg."
    }
    return $value
}

function Invoke-ProjectPython {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    & python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "python $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

function Initialize-Database {
    param(
        [Parameter(Mandatory)]
        [string]$Label,

        [Parameter(Mandatory)]
        [string]$DatabaseUrl
    )

    Write-Output "Initializing $Label database..."
    $previousUrl = $env:PEROVSKITE_DATABASE_URL
    try {
        $env:PEROVSKITE_DATABASE_URL = $DatabaseUrl
        Invoke-ProjectPython -Arguments @("-m", "alembic", "upgrade", "head")
        Invoke-ProjectPython -Arguments @("-m", "alembic", "current")
        Invoke-ProjectPython -Arguments @("-m", "alembic", "check")
        Invoke-ProjectPython -Arguments @("-m", "web.admin_cli", "check-database")
    }
    finally {
        $env:PEROVSKITE_DATABASE_URL = $previousUrl
    }
}

$applicationUrl = Assert-PostgreSqlUrl -VariableName "PEROVSKITE_DATABASE_URL"
$testUrl = Assert-PostgreSqlUrl -VariableName "PEROVSKITE_TEST_POSTGRESQL_URL"

Initialize-Database -Label "application" -DatabaseUrl $applicationUrl
Initialize-Database -Label "test" -DatabaseUrl $testUrl

Write-Output "Both databases are migrated and match the current SQLAlchemy metadata."
