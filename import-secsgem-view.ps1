# import-secsgem-view.ps1 - copies the SecsGemDemo view into the running Ignition gateway
# Run from the ignition-lab folder:  .\import-secsgem-view.ps1
# Or name the project:              .\import-secsgem-view.ps1 -Project MyProject
#
# Close the SecsGemDemo view in the Designer first, and do not save it,
# otherwise the Designer will write its old copy back over this one.

param([string]$Project)

$ErrorActionPreference = "Stop"
$container = "ignition"
$projectsDir = "/usr/local/bin/ignition/data/projects"
$source = Join-Path $PSScriptRoot "secsgem-demo\SecsGemDemo"

if (-not (Test-Path "$source\view.json")) { throw "Cannot find $source\view.json" }

# Pick the project
$projects = docker exec $container ls $projectsDir | Where-Object { $_ -and -not $_.StartsWith(".") }
if (-not $Project) {
    if (@($projects).Count -eq 1) {
        $Project = @($projects)[0]
    } else {
        Write-Host "Several projects found. Run again with -Project <name>:"
        $projects | ForEach-Object { Write-Host "  $_" }
        exit 1
    }
}
if ($projects -notcontains $Project) { throw "Project '$Project' not found. Found: $($projects -join ', ')" }

$viewsDir = "$projectsDir/$Project/com.inductiveautomation.perspective/views"
$dest = "$viewsDir/SecsGemDemo"
Write-Host "Importing SecsGemDemo into project '$Project'"

# Keep the old copy, just in case
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
docker exec -u root $container sh -c "mkdir -p '$viewsDir'; if [ -d '$dest' ]; then mv '$dest' '/tmp/SecsGemDemo-$stamp'; fi"

# Copy the view in and give it the same owner as the project folder
docker cp "$source" "${container}:$dest"
$owner = docker exec $container stat -c "%u:%g" "$projectsDir/$Project"
docker exec -u root $container chown -R $owner "$dest"

# Restart so the gateway rescans the project
Write-Host "Restarting the gateway so it picks up the change..."
docker restart $container | Out-Null

Write-Host "Done. Wait about 30 seconds, then reopen the Designer (or File > Update Project)."
Write-Host "Old copy saved in the container at /tmp/SecsGemDemo-$stamp"
