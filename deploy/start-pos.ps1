$project = Split-Path $PSScriptRoot -Parent
$logs = Join-Path $project 'logs'
$python = Join-Path $project 'backend\venv\Scripts\python.exe'

New-Item -ItemType Directory -Force $logs | Out-Null
Set-Location (Join-Path $project 'backend')

$env:DJANGO_DEBUG = '0'
$env:DJANGO_ALLOWED_HOSTS = 'localhost,127.0.0.1'

while ($true) {
    $log = Join-Path $logs ("server-{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))

    Add-Content -Path $log -Value "`r`n[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting Waitress..."

    & $python -m waitress --listen=127.0.0.1:8080 --threads=8 config.wsgi:application 2>&1 |
        ForEach-Object {
            Add-Content -Path $log -Value "$_"
        }

    $exitCode = $LASTEXITCODE

    Add-Content -Path $log -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Waitress exited with code $exitCode. Restarting in 5 seconds."
    Start-Sleep -Seconds 5
}