<#
.SYNOPSIS
    Hesap verisini (kullanicilar, API anahtarlari, Telegram eslemeleri) tasinabilir tek
    bir SQL dosyasina cikarir. Windows sunucusunda calisir.

.DESCRIPTION
    Ubuntu'ya gecerken gecmis kosulari degil yalnizca hesaplari tasimak icin.

    Parolalar ve API anahtarlari, hashin ICINDE tasinan tuzla saklanir
    (auth.py: scrypt$n$r$p$salt$hash). Disarida bir biber/gizli anahtar yok; dolayisiyla
    bu satirlar baska bir makineye tasindiginda parolalar ve dagitilmis rp_ anahtarlari
    aynen calismaya devam eder -- yeni sunucuda SESSION_SECRET degisse bile. Degisen tek
    sey: acik panel oturumlari duser, herkes bir kez yeniden giris yapar.

    pg_dump iki kez cagrilip birlestiriliyor. Tek cagride --data-only ciktisi tablolari
    alfabetik siralar; api_keys, users'tan once gelir ve geri yuklerken yabanci anahtar
    kisiti patlar.

    KABUK KULLANILMIYOR. Windows PowerShell 5.1 native bir exe'ye cok satirli argüman
    gecirirken hem gomulu cift tirnaklari tuketiyor (`echo "BEGIN;"` -> `echo BEGIN;;`,
    bash sozdizimi hatasi) hem de satirlari ayri argümanlara boluyor (`set -e` -> `set -`
    + `e`). Ikisi de olculdu. Bu yuzden container icinde hic shell calistirilmiyor:
    pg_dump kendi -f bayragiyla dosyaya yaziyor, birlestirme burada bayt duzeyinde
    yapiliyor. Islem butunlugu geri yuklerken psql --single-transaction ile saglaniyor.
#>
param(
    [string]$OutFile = "accounts.sql"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$ortak = @(
    "-U", "research", "-d", "research",
    "--data-only", "--no-owner", "--no-privileges"
)

Write-Host "==> users cikariliyor" -ForegroundColor Cyan
docker compose exec -T postgres pg_dump @ortak -t users -f /tmp/_a.sql
if ($LASTEXITCODE -ne 0) { throw "pg_dump (users) basarisiz. Postgres ayakta mi? (docker compose ps)" }

Write-Host "==> api_keys + telegram_identities cikariliyor" -ForegroundColor Cyan
docker compose exec -T postgres pg_dump @ortak -t api_keys -t telegram_identities -f /tmp/_b.sql
if ($LASTEXITCODE -ne 0) { throw "pg_dump (api_keys/telegram_identities) basarisiz." }

$gecici = [System.IO.Path]::GetTempPath()
$yolA = Join-Path $gecici "_accounts_a.sql"
$yolB = Join-Path $gecici "_accounts_b.sql"

docker compose cp postgres:/tmp/_a.sql $yolA
if ($LASTEXITCODE -ne 0) { throw "users dokumu kopyalanamadi." }
docker compose cp postgres:/tmp/_b.sql $yolB
if ($LASTEXITCODE -ne 0) { throw "api_keys dokumu kopyalanamadi." }

# Bayt duzeyinde birlestirme: Out-File/Set-Content BOM ve CRLF ekler, psql ilk satirda takilir.
$a = [System.IO.File]::ReadAllBytes($yolA)
$b = [System.IO.File]::ReadAllBytes($yolB)
$hedef = Join-Path $root $OutFile
[System.IO.File]::WriteAllBytes($hedef, $a + $b)

Remove-Item $yolA, $yolB -Force -ErrorAction SilentlyContinue
docker compose exec -T postgres rm -f /tmp/_a.sql /tmp/_b.sql | Out-Null

$sayim = docker compose exec -T postgres psql -U research -d research -t -A -c 'select (select count(*) from users) as k, (select count(*) from api_keys) as a, (select count(*) from telegram_identities) as t'

Write-Host ""
Write-Host "==> $OutFile yazildi ($([math]::Round(($a.Length + $b.Length) / 1KB, 1)) KB)" -ForegroundColor Green
Write-Host "    kullanici|anahtar|telegram = $sayim" -ForegroundColor Green
Write-Host ""
Write-Host "Sunucuya gonderin:" -ForegroundColor Yellow
Write-Host "  scp $OutFile cezeri@10.0.10.171:~/research-platform/"
Write-Host ""
Write-Host "Dosya parola ve anahtar hashleri icerir. Aktarim bitince buradan silin." -ForegroundColor Yellow
