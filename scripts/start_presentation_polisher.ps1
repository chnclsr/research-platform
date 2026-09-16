param(
    [switch]$Restart
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

New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null
$pidFile = "$root\logs\presentation-polisher.pid"
$port = 3942
$hostAddress = "0.0.0.0"

if ($Restart -and (Test-Path $pidFile)) {
    try {
        $oldPid = [int](Get-Content $pidFile)
        Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
    } catch {}
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

$running = $false
if (Test-Path $pidFile) {
    try {
        $existingPid = [int](Get-Content $pidFile)
        $running = [bool](Get-Process -Id $existingPid -ErrorAction SilentlyContinue)
    } catch {}
    if (-not $running) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }
}

# Also verify port is not held by another process
if (-not $running) {
    $portOwner = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
                 Select-Object -First 1 -ExpandProperty OwningProcess
    if ($portOwner) {
        $proc = Get-Process -Id $portOwner -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -match "python") {
            $running = $true
            Set-Content -Path $pidFile -Value $portOwner -Encoding ASCII
        }
    }
}

if (-not $running) {
    $polisher = Start-Process -FilePath $venvPython `
        -ArgumentList @("-m", "uvicorn", "scripts.presentation_polisher_service:app", "--host", $hostAddress, "--port", $port, "--no-access-log") `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$root\logs\presentation-polisher.stdout.log" `
        -RedirectStandardError "$root\logs\presentation-polisher.stderr.log"
    Set-Content -Path $pidFile -Value $polisher.Id -Encoding ASCII
}

$url = "http://127.0.0.1:$port"
$healthy = $false
for ($attempt = 1; $attempt -le 20; $attempt++) {
    try {
        $health = Invoke-RestMethod "$url/health" -TimeoutSec 2
        if ($health.status -eq "ok") { $healthy = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}

if (-not $healthy) {
    throw "Presentation Polisher sağlık kontrolü başarısız: $url"
}

Write-Host "Presentation Polisher Service: $url [agy=$($health.agy), soffice=$($health.soffice)]"
