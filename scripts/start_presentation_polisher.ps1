param(
    [switch]$Restart
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# agy, Antigravity girisini yalniz masaustu oturumunda gorur. SSH ya da servis olarak
# (oturum 0) kalkan polisher saglikli gorunur ama her istek "agy-auth-required" ile
# ozgun sunumu dondurur (olculdu 2026-09-16).
if ((Get-Process -Id $PID).SessionId -eq 0) {
    throw "Presentation Polisher oturum 0'dan (SSH/servis) baslatilamaz: agy girisi burada gorunmez. Sunucu ekranindaki konsoldan calistirin."
}

function Get-DotEnvValue([string]$Name) {
    $match = Get-Content -LiteralPath "$root\.env" -ErrorAction SilentlyContinue |
             Where-Object { $_ -match "^$([regex]::Escape($Name))=" } |
             Select-Object -Last 1
    if (-not $match) { return "" }
    $value = ($match -split "=", 2)[1].Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    return $value
}

# SERVICE_TOKEN'a geri dusulmez: servis ajana komut calistirma yetkisi veriyor.
$polisherToken = Get-DotEnvValue "PRESENTATION_POLISHER_TOKEN"
if (-not $polisherToken) {
    throw "PRESENTATION_POLISHER_TOKEN ayarlanmamis (.env). SERVICE_TOKEN yerine gecmez."
}
$env:PRESENTATION_POLISHER_TOKEN = $polisherToken
# Gunluk dosyasi aksi halde Windows kod sayfasiyla (cp1254) yazilir ve ajanin Turkce ozeti
# UTF-8 okuyan araclarda bozuk gorunur (olculdu 2026-09-16).
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
foreach ($setting in @("PRESENTATION_POLISHER_MAX_BYTES", "PRESENTATION_POLISHER_MAX_CONCURRENT",
                       "PRESENTATION_POLISHER_AGY_TIMEOUT_S", "PRESENTATION_POLISHER_REQUEST_BUDGET_S",
                       "PRESENTATION_POLISHER_SOFFICE_TIMEOUT_S", "PRESENTATION_POLISHER_AGY_SANDBOX",
                       "PRESENTATION_POLISHER_AGY_MODEL", "PRESENTATION_POLISHER_PROMPT_FILE")) {
    $value = Get-DotEnvValue $setting
    # .env'den kaldirilan bir ayar, ayni konsolun onceki calismasindan kalan degerle yasamasin.
    if ($value) { Set-Item -Path "Env:$setting" -Value $value }
    else { Remove-Item -Path "Env:$setting" -ErrorAction SilentlyContinue }
}

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

function Get-PortOwners {
    return @(
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    )
}

function Test-PolisherProcess([int]$ProcessId) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    return [bool]($process -and $process.CommandLine -match "scripts\.presentation_polisher_service:app")
}

# Calisan surec basladigi koddan devam eder. Servis dosyasi sonradan degistiyse surec
# bayattir ve yeniden baslatilmalidir; ayni kural kontrol panelinde de uygulaniyor.
if (-not $Restart) {
    $serviceFile = Get-Item "$root\scripts\presentation_polisher_service.py" -ErrorAction SilentlyContinue
    foreach ($owner in (Get-PortOwners)) {
        $process = Get-Process -Id $owner -ErrorAction SilentlyContinue
        if ($serviceFile -and $process -and (Test-PolisherProcess $owner) -and
            $serviceFile.LastWriteTime -gt $process.StartTime) {
            Write-Host "[..] Presentation Polisher kodu surecten yeni; yeniden baslatiliyor" -ForegroundColor Yellow
            $Restart = $true
        }
    }
}

if ($Restart) {
    $targets = @()
    if (Test-Path $pidFile) {
        try { $targets += [int](Get-Content $pidFile) } catch {}
    }
    $targets += Get-PortOwners
    foreach ($target in ($targets | Where-Object { $_ } | Select-Object -Unique)) {
        if (Test-PolisherProcess $target) {
            Stop-Process -Id $target -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    for ($attempt = 1; $attempt -le 20 -and (Get-PortOwners); $attempt++) {
        Start-Sleep -Milliseconds 250
    }
    if (Get-PortOwners) { throw "Presentation Polisher portu yeniden baslatma icin birakilmadi: $port" }
}

$running = $false
$portOwners = Get-PortOwners
if ($portOwners) {
    $wrongOwner = $portOwners | Where-Object { -not (Test-PolisherProcess $_) } | Select-Object -First 1
    if ($wrongOwner) {
        throw "Port $port baska bir surec tarafindan kullaniliyor (PID $wrongOwner)."
    }
    $running = $true
    Set-Content -Path $pidFile -Value $portOwners[0] -Encoding ASCII
}

if (-not $running) {
    $polisher = Start-Process -FilePath $venvPython `
        -ArgumentList @("-m", "uvicorn", "scripts.presentation_polisher_service:app", "--host", $hostAddress, "--port", $port, "--no-access-log") `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$root\logs\presentation-polisher.stdout.log" `
        -RedirectStandardError "$root\logs\presentation-polisher.stderr.log"
}

$url = "http://127.0.0.1:$port"
$healthy = $false
$health = $null
for ($attempt = 1; $attempt -le 20; $attempt++) {
    try {
        $health = Invoke-RestMethod "$url/health" -TimeoutSec 2
        if ($health.status -eq "ok") { $healthy = $true; break }
    } catch {
        # 503 (degraded) govdesi de hangi bagimliligin eksik oldugunu soyler.
        try { $health = $_.ErrorDetails.Message | ConvertFrom-Json } catch {}
    }
    Start-Sleep -Milliseconds 500
}

if (-not $healthy) {
    foreach ($owner in (Get-PortOwners)) {
        if (Test-PolisherProcess $owner) {
            Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    $detay = if ($health) { " [agy=$($health.agy), soffice=$($health.soffice), token=$($health.authentication), istem=$($health.prompt)]" } else { "" }
    throw "Presentation Polisher sağlık kontrolü başarısız: $url$detay"
}

$actualOwner = Get-PortOwners | Select-Object -First 1
if (-not $actualOwner -or -not (Test-PolisherProcess $actualOwner)) {
    throw "Presentation Polisher saglikli gorunuyor ancak port sahibi dogrulanamadi."
}
Set-Content -Path $pidFile -Value $actualOwner -Encoding ASCII

Write-Host "Presentation Polisher Service: $url [agy=$($health.agy), soffice=$($health.soffice), sandbox=$($health.sandbox), sure=$($health.agent_timeout_s)s]"
