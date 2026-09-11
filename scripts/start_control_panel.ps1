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

# Read into a table; nothing is written to this process until the panel is actually launched.
#
# `SetEnvironmentVariable(..., "Process")` writes to the CALLING PowerShell, not to a child, so
# loading the file here used to leave the whole of `.env.office` behind in whatever window ran
# `start_server.ps1`. That file is written for the native panel and therefore carries loopback
# addresses -- `DATABASE_URL` points at 127.0.0.1:5433 -- while `docker compose` gives the shell
# environment precedence over `.env`. The next compose command in the same window then injected
# those addresses into the containers, where 127.0.0.1 means the container itself.
#
# Measured 2026-09-11: a second `start_server.ps1` in the same window died at `compose run --rm
# migrate`, and the traceback pointed at the database connection rather than at alembic -- so the
# failure read as a migration problem in a step that had nothing wrong with it.
$ayarlar = @{}
foreach ($satir in (Get-Content -LiteralPath $envFile -Encoding UTF8)) {
    if ($satir -match '^\s*([^#][^=]+)=(.*)$') {
        $ayarlar[$matches[1].Trim()] = $matches[2].Trim()
    }
}

function Ayar($anahtar, $varsayilan = $null) {
    if ($ayarlar.ContainsKey($anahtar) -and $ayarlar[$anahtar]) { return $ayarlar[$anahtar] }
    return $varsayilan
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

$port = Ayar "CONTROL_PANEL_PORT" "8020"
$hostAddress = Ayar "CONTROL_PANEL_HOST" "127.0.0.1"
$allowedNetworks = Ayar "CONTROL_PANEL_ALLOWED_NETWORKS" (Ayar "MCP_ALLOWED_NETWORKS")

if (-not $running) {
    if ($hostAddress -notin @("127.0.0.1", "localhost", "::1") -and -not $allowedNetworks) {
        throw "LAN control panel için CONTROL_PANEL_ALLOWED_NETWORKS zorunludur."
    }
    # A child can only inherit this process's environment -- PowerShell 5.1's Start-Process has
    # no -Environment -- so the settings are written for the length of this call and taken back
    # in `finally`. The panel keeps the environment it has always had; the window does not.
    $onceki = @{}
    try {
        foreach ($anahtar in $ayarlar.Keys) {
            $onceki[$anahtar] = [Environment]::GetEnvironmentVariable($anahtar, "Process")
            [Environment]::SetEnvironmentVariable($anahtar, $ayarlar[$anahtar], "Process")
        }
        $panel = Start-Process -FilePath $venvPython `
            -ArgumentList @(
                "-m", "uvicorn", "research_platform.control_panel:app",
                "--host", $hostAddress, "--port", $port, "--no-access-log"
            ) `
            -WorkingDirectory $root -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput "$root\logs\control-panel.stdout.log" `
            -RedirectStandardError "$root\logs\control-panel.stderr.log"
    } finally {
        # A null restores as "unset", which is what a key that was not there before should be.
        foreach ($anahtar in $onceki.Keys) {
            [Environment]::SetEnvironmentVariable($anahtar, $onceki[$anahtar], "Process")
        }
    }
    Set-Content -Path $pidFile -Value $panel.Id -Encoding ASCII
}

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
$mcpHost = Ayar "MCP_HOST"
if ($hostAddress -eq "0.0.0.0" -and $mcpHost) {
    Write-Host "Office LAN Control Panel: http://${mcpHost}:$port"
}
