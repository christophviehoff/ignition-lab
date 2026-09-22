# backup-all.ps1 - backs up every Docker volume on this machine
# (ignition-lab stack, grafana, pgvector, and anything else), plus
# a clean SQL dump of the ignition Postgres and the compose project files.
#
# Run from anywhere: .\backup-all.ps1
# Backups land in %USERPROFILE%\docker-backups\<timestamp>\

$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $env:USERPROFILE "docker-backups\$stamp"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

Write-Host "Backing up all Docker volumes to $backupRoot"

# --- Every named volume on this machine (grafana, pgvector, ignition-lab-*, etc) ---
$volumes = docker volume ls -q
foreach ($vol in $volumes) {
    Write-Host "Archiving volume $vol..."
    docker run --rm -v "${vol}:/data" -v "${backupRoot}:/backup" alpine tar czf "/backup/$vol.tar.gz" -C /data .
}

# --- Extra: clean logical dump of the Ignition Postgres (credentials known) ---
$hasIgnitionPg = docker ps --format '{{.Names}}' | Select-String -Quiet '^ignition-postgres$'
if ($hasIgnitionPg) {
    Write-Host "Dumping ignition-postgres..."
    docker exec ignition-postgres pg_dump -U ignition -d ignition -F c -f /tmp/ignition.dump
    docker cp ignition-postgres:/tmp/ignition.dump "$backupRoot\ignition-postgres.dump"
}

# --- Ignition-lab compose project files (not stored in any volume) ---
$composeDir = "C:\Users\cviehoff\Downloads\ignition-lab"
if (Test-Path $composeDir) {
    Copy-Item -Path "$composeDir\docker-compose.yml" -Destination $backupRoot -ErrorAction SilentlyContinue
    Copy-Item -Path "$composeDir\.env" -Destination $backupRoot -ErrorAction SilentlyContinue
    foreach ($folder in @("sim", "sparkplug-sim", "postgres")) {
        $src = Join-Path $composeDir $folder
        if (Test-Path $src) {
            Copy-Item -Path $src -Destination $backupRoot -Recurse
        }
    }
}

Write-Host "Done: $backupRoot"
