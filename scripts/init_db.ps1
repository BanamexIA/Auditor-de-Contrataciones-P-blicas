$ErrorActionPreference = "Stop"

docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/00-init.sql'
if ($LASTEXITCODE -ne 0) {
    throw "Database role/schema initialization failed."
}

$sqlFiles = Get-ChildItem -Path ".\etl\sql" -Filter "*.sql" -File | Sort-Object Name
foreach ($sqlFile in $sqlFiles) {
    $command = 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /opt/etl/sql/' + $sqlFile.Name
    docker compose exec -T db sh -c $command
    if ($LASTEXITCODE -ne 0) {
        throw "Database initialization failed while applying $($sqlFile.Name)."
    }
}

Write-Host "Database initialization completed."
