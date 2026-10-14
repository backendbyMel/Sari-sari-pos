$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$env:DJANGO_DEBUG = '0'
$env:DJANGO_ALLOWED_HOSTS = 'localhost,127.0.0.1'

Write-Host '1. Backup'
& (Join-Path $PSScriptRoot 'backup-pos.ps1')

Write-Host '2. Stop the server'
Stop-ScheduledTask -TaskName 'POS Server' -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'waitress' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host '3. Update the backend'
Set-Location (Join-Path $project 'backend')
& .\venv\Scripts\python.exe -m pip install -r requirements.txt
& .\venv\Scripts\python.exe manage.py migrate
& .\venv\Scripts\python.exe manage.py collectstatic --noinput

Write-Host '4. Build the app'
Set-Location (Join-Path $project 'frontend')
npm install
npm run build

Write-Host '5. Start the server'
Start-ScheduledTask -TaskName 'POS Server'
Write-Host 'Done. Wait about 30 seconds, then open http://localhost:8080 and run: python manage.py check_integrity'