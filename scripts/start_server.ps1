<#
.SYNOPSIS
    scripts/linux/start_server.sh'in Windows karsiligi: docker yiginini saglikli
    sekilde ayaga kaldirir, kontrol panelini baslatir, uclari dogrular.

.DESCRIPTION
    ESKI start_office_server.ps1 ILE KARISTIRMAYIN. O script natif donemden kalma
    (surum 0.7.0): api/worker/mcp'yi natif surec olarak baslatir, artik var olmayan
    MCP_BEARER_TOKEN'i arar ve Wi-Fi arayuzunun IP'sini dogrular. Bu kurulumda her sey
    compose icinde, natif kalan tek surec kontrol paneli.

    ErrorActionPreference BILEREK "Stop" DEGIL: PowerShell 5.1 native bir exe stderr'e
    yazdiginda her satiri NativeCommandError'a sarar ve "Stop" bunu sonlandirici hataya
    cevirir -- `docker compose` ilerlemesini stderr'e yazar, yani basarili bir kalkis
    script'i oldururdu. Butunluk her cagridan sonra cikis kodu okunarak saglaniyor.
#>
param(
    # Boot'ta varsayilan olarak derleme YOK: imajlar zaten kurulu ve --build her
    # aciliste dakikalar ekler. Kod degistikten sonraki ilk kalkista -Build verin.
    [switch]$Build,
    [switch]$SkipPanel
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Bilgi($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Tamam($m) { Write-Host "[ok] $m" -ForegroundColor Green }
function Hata($m)  { Write-Host "[!!] $m" -ForegroundColor Red }

# docker'in ilerleme ciktisi stderr'e gider ve PowerShell 5.1 onu ErrorRecord'a sarar;
# ekrana hata bloklari olarak basilmasin diye kayitlar burada duz metne cevriliyor.
# Basari/basarisizlik yalnizca cikis kodundan okunur, $? gormezden gelinir.
function Docker-Calistir {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Argumanlar)
    $onceki = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & docker @Argumanlar 2>&1 | ForEach-Object { Write-Host "   $_" -ForegroundColor DarkGray }
    $kod = $LASTEXITCODE
    $ErrorActionPreference = $onceki
    return $kod
}

function EnvDegeri($anahtar, $varsayilan) {
    $satir = Select-String -Path "$root\.env" -Pattern "^$anahtar=(\S+)" | Select-Object -First 1
    if ($satir) { return $satir.Matches[0].Groups[1].Value }
    return $varsayilan
}

if (-not (Test-Path "$root\.env")) { Hata ".env yok. .env.example'dan turetin."; exit 1 }

$durum = 0
$panelPort = EnvDegeri "CONTROL_PANEL_PORT" "8020"
# MCP gateway loopback'e DEGIL, LAN adresine baglanir (compose: "${MCP_BIND_HOST}:8010:8010").
# Saglik kontrolunu 127.0.0.1'e yaparsaniz baglanti reddedilir ve ayakta olan servis
# olu gorunur -- olculdu 2026-09-10.
$bindHost = EnvDegeri "MCP_BIND_HOST" "127.0.0.1"

# --------------------------------------------------------------- Docker Desktop
# Oturum acilisinda Docker Desktop'in daemon'i hazir etmesi dakikalar surebilir;
# gorev AtLogOn tetiklendigi icin buradaki bekleme sart.
Bilgi "Docker Desktop bekleniyor"
$hazir = $false
for ($i = 1; $i -le 60; $i++) {
    $v = docker version --format "{{.Server.Version}}" 2>$null
    if ($LASTEXITCODE -eq 0 -and $v) { $hazir = $true; Tamam "daemon $v"; break }
    Start-Sleep -Seconds 5
}
if (-not $hazir) { Hata "Docker Desktop 5 dakika icinde hazir olmadi."; exit 1 }

# ------------------------------------------------------------------- container'lar
Bilgi "Altyapi container'lari"
if ((Docker-Calistir compose up -d --wait --wait-timeout 300 postgres redis minio crawl4ai) -ne 0) {
    Hata "Altyapi container'lari saglikli baslatilamadi."; exit 1
}
Tamam "postgres, redis, minio, crawl4ai"

Bilgi "Sema"
if ((Docker-Calistir compose run --rm migrate) -ne 0) { Hata "alembic upgrade head basarisiz."; exit 1 }
Tamam "sema guncel"

# Servisler tek tek sayiliyor, "hepsi" denmiyor: --wait, saglikli hale gelmeyen her
# container'i basarisizlik sayar ve 'migrate' isini bitirince kasten cikar.
# Varsayilan kumede birakilirsa saglikli bir kalkis hata gibi raporlanir.
#
# docling ilk acilista modelleri yukler; healthcheck'inin start_period'u 300 s, bu
# yuzden --wait-timeout onun altinda kalamaz.
Bilgi "Uygulama servisleri"
$uygulama = @("docling", "agentsearch-adapter", "api", "worker", "mcp-gateway", "langflow")
if ($Build) {
    $kod = Docker-Calistir compose up -d --build --wait --wait-timeout 600 @uygulama
} else {
    $kod = Docker-Calistir compose up -d --wait --wait-timeout 600 @uygulama
}
if ($kod -ne 0) { Hata "Uygulama servisleri saglikli baslatilamadi."; exit 1 }
Tamam ($uygulama -join ", ")

# telegram-bot bir profilin arkasinda: token yoksa hic baslatilmaz. Bu, panelin
# uyguladigi kuralin aynisi (control_panel.py, _compose_app_services).
#
# -Build BURAYA DA GECMELI. telegram-bot yukaridaki $uygulama kumesinde degil, cunku
# profilin arkasinda. Atlanirsa `up -d` mevcut imaji bulur, derlemez ve hicbir sey
# soylemez -- servis eski kodla calismaya devam eder. Compose dosyasinin docling icin
# uyardigi tuzagin aynisi. Bu kurulumda imaj ilk kez research-platform-api'den
# etiketlenerek olusturuldu (ayni Dockerfile, birebir ayni katmanlar), dolayisiyla
# kod degistikten sonraki ilk -Build'e kadar bayat kalir.
if (Select-String -Path "$root\.env" -Pattern '^TELEGRAM_BOT_TOKEN=.+' -Quiet) {
    if ($Build) {
        $kod = Docker-Calistir compose --profile telegram up -d --build telegram-bot
    } else {
        $kod = Docker-Calistir compose --profile telegram up -d telegram-bot
    }
    if ($kod -eq 0) { Tamam "telegram-bot baslatildi" } else { Hata "telegram-bot baslatilamadi"; $durum = 1 }
}

# SearXNG ana compose projesinin DISINDA, kendi projesinde calisir ve
# research-platform_research agina disaridan baglanir.
#
# --env-file .env SART: compose, env dosyasini compose dosyasinin yaninda arar ve
# scripts/linux/searxng/ altinda .env yoktur; olmadan SEARXNG_SECRET cozulemez ve
# "required variable SEARXNG_SECRET is missing a value" ile durur.
Bilgi "SearXNG"
$searxngCompose = "scripts/linux/searxng/docker-compose.searxng.yml"
$calisan = docker compose --env-file .env -f $searxngCompose ps --quiet 2>$null
if ($LASTEXITCODE -eq 0 -and $calisan) {
    Tamam "zaten calisiyor"
} else {
    if ((Docker-Calistir compose --env-file .env -f $searxngCompose up -d) -eq 0) {
        Tamam "baslatildi"
    } else { Hata "SearXNG baslatilamadi"; $durum = 1 }
}

# ------------------------------------------------------------------ kontrol paneli
# Compose'da degil: natif uvicorn sureci, .venv gerektirir ve ortamini .env.office'ten
# okur (start_control_panel.ps1). Ana .env'i okumaz.
if (-not $SkipPanel) {
    Bilgi "Kontrol paneli"
    & "$PSScriptRoot\start_control_panel.ps1" -NoBrowser -SkipInstall
    if ($LASTEXITCODE -eq 0) { Tamam "panel ayakta" } else { Hata "panel baslatilamadi"; $durum = 1 }
}

# ------------------------------------------------------------------ saglik kontrolu
function Bekle($ad, $url, $limit) {
    for ($i = 1; $i -le $limit; $i++) {
        try {
            Invoke-RestMethod $url -TimeoutSec 5 | Out-Null
            Tamam $ad
            return $true
        } catch {}
        Start-Sleep -Seconds 2
    }
    Hata "$ad yanit vermedi: $url"
    return $false
}

Bilgi "Uclar"
if (-not (Bekle "Research API" "http://127.0.0.1:8000/health" 30)) { $durum = 1 }
if (-not (Bekle "Docling" "http://127.0.0.1:3941/health" 60)) { $durum = 1 }
if (-not (Bekle "Ollama" "http://127.0.0.1:11434/api/tags" 10)) { $durum = 1 }
if (-not $SkipPanel) {
    if (-not (Bekle "Kontrol paneli" "http://127.0.0.1:$panelPort/health" 20)) { $durum = 1 }
}

# MCP gateway kimliksiz istegi 403 ile reddeder; "ayakta" sinyali olarak yanit
# vermesi yeterli, 2xx beklenmez.
$mcpUrl = "http://${bindHost}:8010/mcp"
$mcpAyakta = $false
for ($i = 1; $i -le 30; $i++) {
    try { Invoke-WebRequest $mcpUrl -TimeoutSec 5 -UseBasicParsing | Out-Null; $mcpAyakta = $true; break }
    catch { if ($_.Exception.Response) { $mcpAyakta = $true; break } }
    Start-Sleep -Seconds 2
}
if ($mcpAyakta) { Tamam "MCP gateway" } else { Hata "MCP gateway yanit vermedi: $mcpUrl"; $durum = 1 }

# Redis kuyrugu ayakta olmak yetmez; worker'in kalp atisini birakip birakmadigi
# "kuyruk saglikli ama hicbir is alinmiyor" durumunu ayirt eden tek sinyal.
Bilgi "Worker kuyruk kalp atisi"
$ttl = docker compose exec -T redis redis-cli TTL arq:queue:health-check 2>$null
$ttl = "$ttl".Trim()
if ($ttl -match '^\d+$' -and [int]$ttl -gt 0) { Tamam "kalp atisi ttl=${ttl}s" }
else { Hata "worker kalp atisi yok (ttl=$ttl)"; $durum = 1 }

# ------------------------------------------------------------------------- ozet
# Sekme Go sablonuna "\t" olarak gitmeli. Tek tirnakli PowerShell dizesinde ters tirnak
# kacis karakteri DEGILDIR: "`t" yazilirsa basliga birebir "`t" basilir.
Bilgi "Ozet"
docker compose ps --format 'table {{.Service}}\t{{.Status}}'

Write-Host ""
Write-Host "  MCP (ekip)      http://${bindHost}:8010/mcp"
Write-Host "  Panel (ekip)    http://${bindHost}:${panelPort}"
Write-Host "  API (yerel)     http://127.0.0.1:8000/docs"

exit $durum
