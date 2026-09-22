# backup.ps1 - one-shot backup of the ignition-lab Docker stack
# Run from the ignition-lab folder: .\backup.ps1

$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $PSScriptRoot "backups\$stamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

Write-Host "Backing up ignition-lab to $backupDir"

# --- Postgres: proper SQL dump (portable across Postgres versions) ---
Write-Host "Dumping Postgres..."
docker exec ignition-postgres pg_dump -U ignition -d ignition -F c -f /tmp/ignition.dump
docker cp ignition-postgres:/tmp/ignition.dump "$backupDir\ignition-postgres.dump"

# --- Named volumes: raw tar via a throwaway alpine container ---
$volumes = @("ignition-lab-ignition-data", "ignition-lab-emqx-data")
foreach ($vol in $volumes) {
    Write-Host "Archiving volume $vol..."
    docker run --rm -v "${vol}:/data" -v "${backupDir}:/backup" alpine tar czf "/backup/$vol.tar.gz" -C /data .
}

# --- Everything not stored in a volume ---
Write-Host "Copying compose project files..."
Copy-Item -Path "$PSScriptRoot\docker-compose.yml" -Destination $backupDir -ErrorAction SilentlyContinue
Copy-Item -Path "$PSScriptRoot\.env" -Destination $backupDir -ErrorAction SilentlyContinue
foreach ($folder in @("sim", "sparkplug-sim", "postgres")) {
    $src = Join-Path $PSScriptRoot $folder
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $backupDir -Recurse
    }
}

Write-Host "Done: $backupDir"
