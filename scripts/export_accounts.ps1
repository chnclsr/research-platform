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
#>
param(
    [string]$OutFile = "accounts.sql"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> Hesap tablolari cikariliyor" -ForegroundColor Cyan

# Dokumu container icinde uret, sonra disari kopyala. Ciktiyi PowerShell borusundan
# gecirmek dosyaya BOM ve CRLF ekler; psql ilk satirda takilir.
$dumpCmd = @'
set -e
pg_dump -U research -d research --data-only --no-owner --no-privileges -t users > /tmp/_a.sql
pg_dump -U research -d research --data-only --no-owner --no-privileges -t api_keys -t telegram_identities > /tmp/_b.sql
{ echo "BEGIN;"; cat /tmp/_a.sql /tmp/_b.sql; echo "COMMIT;"; } > /tmp/accounts.sql
rm -f /tmp/_a.sql /tmp/_b.sql
'@

docker compose exec -T postgres bash -c $dumpCmd
if ($LASTEXITCODE -ne 0) { throw "pg_dump basarisiz. Postgres container'i ayakta mi? (docker compose ps)" }

docker compose cp postgres:/tmp/accounts.sql $OutFile
if ($LASTEXITCODE -ne 0) { throw "Dosya kopyalanamadi." }
docker compose exec -T postgres rm -f /tmp/accounts.sql | Out-Null

$sayim = docker compose exec -T postgres psql -U research -d research -t -A -c "select (select count(*) from users) || ' kullanici, ' || (select count(*) from api_keys) || ' anahtar, ' || (select count(*) from telegram_identities) || ' telegram eslemesi'"

Write-Host "==> $OutFile yazildi -- $sayim" -ForegroundColor Green
Write-Host ""
Write-Host "Sunucuya gonderin:" -ForegroundColor Yellow
Write-Host "  scp $OutFile kullanici@sunucu:~/research-platform/"
Write-Host ""
Write-Host "Dosya parola ve anahtar hashleri icerir. Aktarim bitince buradan silin." -ForegroundColor Yellow
