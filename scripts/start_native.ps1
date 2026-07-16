$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$pythonCandidates = @(
    "$root\.venv\Scripts\python.exe",
    "$env:LOCALAPPDATA\anaconda3\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
)
$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) { throw "Python 3.11+ bulunamadı." }

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $python -m venv .venv
}
$venvPython = "$root\.venv\Scripts\python.exe"
& $venvPython -m pip install -e "."

$nativeEnv = if (Test-Path ".env.native") { ".env.native" } else { ".env.native.example" }
Get-Content $nativeEnv | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

New-Item -ItemType Directory -Force -Path logs | Out-Null
$api = Start-Process -FilePath "$root\.venv\Scripts\research-api.exe" `
    -WorkingDirectory $root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$root\logs\api.stdout.log" `
    -RedirectStandardError "$root\logs\api.stderr.log"
$worker = Start-Process -FilePath "$root\.venv\Scripts\research-worker.exe" `
    -WorkingDirectory $root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$root\logs\worker.stdout.log" `
    -RedirectStandardError "$root\logs\worker.stderr.log"
$mcp = Start-Process -FilePath "$root\.venv\Scripts\research-mcp.exe" `
    -WorkingDirectory $root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$root\logs\mcp.stdout.log" `
    -RedirectStandardError "$root\logs\mcp.stderr.log"

Set-Content -Path "$root\logs\api.pid" -Value $api.Id
Set-Content -Path "$root\logs\worker.pid" -Value $worker.Id
Set-Content -Path "$root\logs\mcp.pid" -Value $mcp.Id

$telegram = $null
if ($env:TELEGRAM_BOT_TOKEN -and (
    $env:TELEGRAM_ALLOWED_USER_IDS -ne "[]" -or $env:TELEGRAM_ALLOWED_CHAT_IDS -ne "[]"
)) {
    $telegram = Start-Process -FilePath "$root\.venv\Scripts\research-telegram.exe" `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$root\logs\telegram.stdout.log" `
        -RedirectStandardError "$root\logs\telegram.stderr.log"
    Set-Content -Path "$root\logs\telegram.pid" -Value $telegram.Id
}

Write-Host "Native API PID: $($api.Id), worker PID: $($worker.Id), MCP PID: $($mcp.Id)"
if ($telegram) { Write-Host "Telegram PID: $($telegram.Id)" }
