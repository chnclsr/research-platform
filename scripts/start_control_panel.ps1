param(
    [switch]$NoBrowser,
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
& $venvPython -c "import research_platform.control_panel" 2>$null
if ($LASTEXITCODE -ne 0) {
    if ($SkipInstall) { throw "Control panel modülü kurulu değil." }
    & $venvPython -m pip install -e "$root"
    if ($LASTEXITCODE -ne 0) { throw "Control panel paketi kurulamadı." }
}

$envFile = "$root\.env.office"
if (-not (Test-Path $envFile)) { $envFile = "$root\.env.native.example" }
Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null
$pidFile = "$root\logs\control-panel.pid"
$running = $false
if (Test-Path $pidFile) {
    try {
        $existingPid = [int](Get-Content $pidFile)
        $running = [bool](Get-Process -Id $existingPid -ErrorAction SilentlyContinue)
    } catch {}
    if (-not $running) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }
}

if (-not $running) {
    $port = if ($env:CONTROL_PANEL_PORT) { $env:CONTROL_PANEL_PORT } else { "8020" }
    $panel = Start-Process -FilePath $venvPython `
        -ArgumentList @(
            "-m", "uvicorn", "research_platform.control_panel:app",
            "--host", "127.0.0.1", "--port", $port, "--no-access-log"
        ) `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$root\logs\control-panel.stdout.log" `
        -RedirectStandardError "$root\logs\control-panel.stderr.log"
    Set-Content -Path $pidFile -Value $panel.Id -Encoding ASCII
}

$port = if ($env:CONTROL_PANEL_PORT) { $env:CONTROL_PANEL_PORT } else { "8020" }
$url = "http://127.0.0.1:$port"
$healthy = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
        $health = Invoke-RestMethod "$url/health" -TimeoutSec 2
        if ($health.status -eq "healthy") { $healthy = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}
if (-not $healthy) { throw "Control panel sağlık kontrolü başarısız: $url" }

if (-not $NoBrowser) { Start-Process $url }
Write-Host "Research Platform Control Panel: $url"
