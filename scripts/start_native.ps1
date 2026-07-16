param(
    [string]$EnvFile = "",
    [switch]$SkipInstall
)

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

if (-not (Test-Path "$root\.venv\Scripts\python.exe")) {
    & $python -m venv "$root\.venv"
}
$venvPython = "$root\.venv\Scripts\python.exe"
if (-not $SkipInstall -or -not (Test-Path "$root\.venv\Scripts\research-api.exe")) {
    & $venvPython -m pip install -e "$root"
}

if (-not $EnvFile) {
    $EnvFile = if (Test-Path "$root\.env.native") {
        "$root\.env.native"
    } else {
        "$root\.env.native.example"
    }
}
if (-not [System.IO.Path]::IsPathRooted($EnvFile)) {
    $EnvFile = Join-Path $root $EnvFile
}
if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Ortam dosyası bulunamadı: $EnvFile"
}

Get-Content -LiteralPath $EnvFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable(
            $matches[1].Trim(),
            $matches[2].Trim(),
            "Process"
        )
    }
}

New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null

foreach ($name in @("api", "worker", "mcp", "telegram")) {
    $pidFile = "$root\logs\$name.pid"
    if (Test-Path $pidFile) {
        $processId = [int](Get-Content $pidFile)
        if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
            throw "$name zaten çalışıyor (PID $processId). Önce stop_native.ps1 kullanın."
        }
        Remove-Item $pidFile -Force
    }
}

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

Set-Content -Path "$root\logs\api.pid" -Value $api.Id -Encoding ASCII
Set-Content -Path "$root\logs\worker.pid" -Value $worker.Id -Encoding ASCII
Set-Content -Path "$root\logs\mcp.pid" -Value $mcp.Id -Encoding ASCII

$telegram = $null
if ($env:TELEGRAM_BOT_TOKEN) {
    $telegram = Start-Process -FilePath "$root\.venv\Scripts\research-telegram.exe" `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$root\logs\telegram.stdout.log" `
        -RedirectStandardError "$root\logs\telegram.stderr.log"
    Set-Content -Path "$root\logs\telegram.pid" -Value $telegram.Id -Encoding ASCII
}

Write-Host "Native API PID: $($api.Id), worker PID: $($worker.Id), MCP PID: $($mcp.Id)"
if ($telegram) { Write-Host "Telegram PID: $($telegram.Id)" }
