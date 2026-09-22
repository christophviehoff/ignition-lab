# import-views.ps1 - copies Perspective views into the running Ignition gateway
# Run from the ignition-lab folder:
#   .\pump-demo\import-views.ps1 -Project lab
# Every folder under -Source is copied into the project's views folder, for
# example pump-demo\views\Pumps becomes the Pumps folder in the Designer.
#
# Close these views in the Designer first and do not save them.

param(
    [string]$Project,
    [string]$Source = (Join-Path $PSScriptRoot "views")
)

$ErrorActionPreference = "Stop"
$container = "ignition"
$projectsDir = "/usr/local/bin/ignition/data/projects"

if (-not (Test-Path $Source)) { throw "Cannot find $Source" }

$projects = docker exec $container ls $projectsDir | Where-Object { $_ -and -not $_.StartsWith(".") }
if (-not $Project) {
    if (@($projects).Count -eq 1) { $Project = @($projects)[0] }
    else {
        Write-Host "Several projects found. Run again with -Project <name>:"
        $projects | ForEach-Object { Write-Host "  $_" }
        exit 1
    }
}
if ($projects -notcontains $Project) { throw "Project '$Project' not found. Found: $($projects -join ', ')" }

$viewsDir = "$projectsDir/$Project/com.inductiveautomation.perspective/views"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$owner = docker exec $container stat -c "%u:%g" "$projectsDir/$Project"
docker exec -u root $container mkdir -p $viewsDir

Get-ChildItem -Path $Source -Directory | ForEach-Object {
    $name = $_.Name
    $dest = "$viewsDir/$name"
    Write-Host "Importing $name into project '$Project'"
    docker exec -u root $container sh -c "if [ -d '$dest' ]; then mv '$dest' '/tmp/$name-$stamp'; fi"
    docker cp $_.FullName "${container}:$dest"
    docker exec -u root $container chown -R $owner "$dest"
}

Write-Host "Restarting the gateway so it picks up the change..."
docker restart $container | Out-Null
Write-Host "Done. Wait about 30 seconds, then reopen the Designer."
