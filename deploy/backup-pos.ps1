param([string]$Dest = 'D:\POS-Backups')   
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent

$vars = @{}
Get-Content (Join-Path $project 'backend\.env') | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') { $vars[$Matches[1]] = $Matches[2].Trim('"').Trim("'") }
}
$pgDump = Get-ChildItem 'C:\Program Files\PostgreSQL' -Recurse -Filter pg_dump.exe | Select-Object -First 1 -ExpandProperty FullName

New-Item -ItemType Directory -Force $Dest | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$env:PGPASSWORD = $vars['POS_DB_PASSWORD']
try {
    & $pgDump -h $vars['POS_DB_HOST'] -p $vars['POS_DB_PORT'] -U $vars['POS_DB_USER'] -d $vars['POS_DB_NAME'] -F c -f (Join-Path $Dest "pos_$stamp.dump")
    if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }
} finally { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue }

$reports = Join-Path $project 'backend\reports'
if (Test-Path $reports) { Copy-Item $reports (Join-Path $Dest "reports_$stamp") -Recurse }

Get-ChildItem $Dest -Filter 'pos_*.dump' | Where-Object LastWriteTime -lt (Get-Date).AddDays(-30) | Remove-Item
Get-ChildItem $Dest -Directory -Filter 'reports_*' | Where-Object LastWriteTime -lt (Get-Date).AddDays(-30) | Remove-Item -Recurse
Write-Host "Backup done: $Dest\pos_$stamp.dump"