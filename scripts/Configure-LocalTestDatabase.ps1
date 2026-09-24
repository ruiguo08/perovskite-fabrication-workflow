[CmdletBinding()]
param(
    [string]$AdminUser = "postgres",

    [string]$CredentialFile = (
        Join-Path $env:LOCALAPPDATA `
            "PerovskiteWorkflow\test-database.credential.clixml"
    )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$psql = Join-Path $env:ProgramFiles "PostgreSQL\18\bin\psql.exe"
if (-not (Test-Path -LiteralPath $psql)) {
    throw "PostgreSQL 18 psql was not found at $psql"
}

$adminCredential = Get-Credential `
    -UserName $AdminUser `
    -Message "PostgreSQL administrator for local test-database setup"
if (-not $adminCredential) {
    throw "PostgreSQL administrator credential was not supplied."
}
if ($adminCredential.UserName -ne $AdminUser) {
    throw "Expected PostgreSQL administrator role $AdminUser."
}

$randomBytes = [byte[]]::new(32)
$random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$testPassword = $null
$previousPgPassword = $env:PGPASSWORD
try {
    $random.GetBytes($randomBytes)
    $testPassword = ([Convert]::ToBase64String($randomBytes) `
        -replace "\+", "-" -replace "/", "_").TrimEnd("=")

    $env:PGPASSWORD = $adminCredential.GetNetworkCredential().Password
    $sql = @'
SELECT 'CREATE ROLE perovskite_test'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'perovskite_test'
) \gexec
ALTER ROLE perovskite_test
    LOGIN PASSWORD :'test_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
SELECT 'CREATE DATABASE perovskite_test OWNER perovskite_test'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = 'perovskite_test'
) \gexec
ALTER DATABASE perovskite_test OWNER TO perovskite_test;
REVOKE ALL PRIVILEGES ON DATABASE perovskite_test FROM PUBLIC;
GRANT CONNECT ON DATABASE perovskite_test TO perovskite_test;
'@
    $sql | & $psql -X -v ON_ERROR_STOP=1 `
        -h 127.0.0.1 -p 5432 -U $AdminUser -d postgres `
        --set=test_password=$testPassword
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL test role/database setup failed with exit code $LASTEXITCODE."
    }

    $secureTestPassword = ConvertTo-SecureString $testPassword -AsPlainText -Force
    $testCredential = [pscredential]::new("perovskite_test", $secureTestPassword)
    $credentialDirectory = Split-Path $CredentialFile -Parent
    New-Item -ItemType Directory -Path $credentialDirectory -Force | Out-Null
    [pscustomobject]@{
        Test = $testCredential
        Host = "127.0.0.1"
        Port = 5432
        Database = "perovskite_test"
    } | Export-Clixml -LiteralPath $CredentialFile -Force

    $env:PGPASSWORD = $testPassword
    & $psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 5432 `
        -U perovskite_test -d perovskite_test -c "SELECT current_user"
    if ($LASTEXITCODE -ne 0) {
        throw "The saved test credential could not connect."
    }

    Write-Output "Configured encrypted test credential: $CredentialFile"
}
finally {
    $env:PGPASSWORD = $previousPgPassword
    $testPassword = $null
    [Array]::Clear($randomBytes, 0, $randomBytes.Length)
    $random.Dispose()
    $adminCredential = $null
}
