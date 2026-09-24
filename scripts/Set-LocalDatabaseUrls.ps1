[CmdletBinding()]
param(
    [ValidateSet("Both", "Application", "Test")]
    [string]$Scope = "Both",

    [ValidateSet("127.0.0.1", "localhost")]
    [string]$DatabaseHost = "127.0.0.1",

    [ValidateRange(1, 65535)]
    [int]$DatabasePort = 5432
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Set-PromptedDatabaseUrl {
    param(
        [Parameter(Mandatory)]
        [string]$VariableName,

        [Parameter(Mandatory)]
        [string]$DatabaseUser,

        [Parameter(Mandatory)]
        [string]$DatabaseName
    )

    $securePassword = $null
    $credential = $null
    $encodedPassword = $null
    try {
        $securePassword = Read-Host "Password for PostgreSQL role $DatabaseUser" -AsSecureString
        $credential = [pscredential]::new($DatabaseUser, $securePassword)
        $encodedPassword = [uri]::EscapeDataString(
            $credential.GetNetworkCredential().Password
        )
        $databaseUrl = (
            "postgresql+asyncpg://{0}:{1}@{2}:{3}/{4}" -f
            $DatabaseUser,
            $encodedPassword,
            $DatabaseHost,
            $DatabasePort,
            $DatabaseName
        )
        [Environment]::SetEnvironmentVariable(
            $VariableName,
            $databaseUrl,
            "Process"
        )
    }
    finally {
        $encodedPassword = $null
        $credential = $null
        $securePassword = $null
    }
}

if ($Scope -in @("Both", "Application")) {
    $applicationParameters = @{
        VariableName = "PEROVSKITE_DATABASE_URL"
        DatabaseUser = "perovskite_app"
        DatabaseName = "perovskite_registry"
    }
    Set-PromptedDatabaseUrl @applicationParameters
    Write-Output "Configured the application database URL for this PowerShell process."
}

if ($Scope -in @("Both", "Test")) {
    $testParameters = @{
        VariableName = "PEROVSKITE_TEST_POSTGRESQL_URL"
        DatabaseUser = "perovskite_test"
        DatabaseName = "perovskite_test"
    }
    Set-PromptedDatabaseUrl @testParameters
    Write-Output "Configured the test database URL for this PowerShell process."
}

Write-Output "No password was written to disk. Closing this PowerShell clears the URLs."
