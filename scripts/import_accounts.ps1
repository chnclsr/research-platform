<#
.SYNOPSIS
    export_accounts.sh / export_accounts.ps1'in urettigi accounts.sql dosyasini bu
    Windows sunucusuna yukler.

.DESCRIPTION
    import_accounts.sh'in Windows karsiligi. Ubuntu'dan Windows'a donerken hesaplari
    tasimak icin.

    Onkosul: 'docker compose up -d' ile postgres ayakta ve 'migrate' servisi
    alembic upgrade head'i tamamlamis olmali (tablolar var, icleri bos).

    Parolalar ve API anahtarlari tuzu hashin icinde tasir (auth.py:
    scrypt$n$r$p$salt$hash). Disarida gizli anahtar olmadigi icin tasindiktan sonra
    parolalar da dagitilmis rp_ anahtarlari da aynen calisir. Yalnizca acik panel
    oturumlari duser.

    KABUK KULLANILMIYOR. PowerShell 5.1 native bir exe'ye cok satirli argüman gecirirken
    gomulu tirnaklari tuketiyor ve satirlari ayri argümanlara boluyor (export_accounts.ps1
    basligindaki olcumlere bakin). Bu yuzden SQL dosya olarak kopyalanip psql'e -f ile
    veriliyor, hicbir yerde inline SQL metni gecirilmiyor.
#>
param(
    [string]$InFile = "accounts.sql"
)

# ErrorActionPreference BILEREK "Stop" DEGIL. PowerShell 5.1, native bir exe stderr'e
# yazdiginda her satiri NativeCommandError'a sariyor; "Stop" ile bu sonlandirici hataya
# donusuyor. `docker compose cp` ilerleme satirini ("Copying ... to ...") stderr'e
# yaziyor ve komut basariyla donse bile script oluyor (olculdu 2026-09-10). Butunluk
# burada her native cagrinin ardindan $LASTEXITCODE'u acikca kontrol ederek saglaniyor.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path $InFile)) { throw "Dosya bulunamadi: $InFile" }

Write-Host "==> Hedef veritabani kontrol ediliyor" -ForegroundColor Cyan
$mevcut = docker compose exec -T postgres psql -U research -d research -t -A -c 'select count(*) from users'
if ($LASTEXITCODE -ne 0) {
    Write-Host "users tablosu okunamadi. Once semayi olusturun:" -ForegroundColor Red
    Write-Host "  docker compose run --rm migrate" -ForegroundColor Red
    exit 1
}
$mevcut = "$mevcut".Trim()

if ($mevcut -ne "0") {
    # Ustune yazmak birincil anahtar catismasi verir ve islem geri alinir; yine de
    # kullaniciyi bilincli bir karara zorlamak, yarim yuklenmis bir hesap tablosundan iyi.
    Write-Host "Hedefte zaten $mevcut kullanici var. Bu script yalnizca bos bir hesap" -ForegroundColor Red
    Write-Host "tablosuna yukler. Sifirlamak icin:" -ForegroundColor Red
    Write-Host "  docker compose exec -T postgres psql -U research -d research -c 'truncate telegram_identities, api_keys, users cascade'" -ForegroundColor Red
    exit 1
}

Write-Host "==> Yukleniyor: $InFile" -ForegroundColor Cyan
# `docker compose cp` ilerlemesini stderr'e yaziyor; PowerShell 5.1 bunu ErrorRecord'a
# sarip ekrana hata gibi basiyor. Kayit yalnizca bu cagri boyunca bastiriliyor --
# basari/basarisizlik $LASTEXITCODE'dan okunuyor, $? gormezden geliniyor.
$oncekiTercih = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
docker compose cp $InFile postgres:/tmp/accounts.sql 2>&1 | Out-Null
$kopyaKodu = $LASTEXITCODE
$ErrorActionPreference = $oncekiTercih
if ($kopyaKodu -ne 0) { throw "Dosya postgres konteynerine kopyalanamadi." }

# --single-transaction: dokum BEGIN/COMMIT tasimiyor. Yarim yuklenmis bir hesap
# tablosuna dusmemek icin butunluk burada saglaniyor.
docker compose exec -T postgres psql -U research -d research --single-transaction -v ON_ERROR_STOP=1 -f /tmp/accounts.sql
if ($LASTEXITCODE -ne 0) {
    docker compose exec -T postgres rm -f /tmp/accounts.sql | Out-Null
    throw "psql geri yukleme basarisiz. Islem geri alindi, hesap tablosu bos kaldi."
}
docker compose exec -T postgres rm -f /tmp/accounts.sql | Out-Null

Write-Host "==> Sonuc" -ForegroundColor Green
docker compose exec -T postgres psql -U research -d research -c "select email, role, is_active, (select count(*) from api_keys k where k.user_id = u.id and k.revoked_at is null) as aktif_anahtar from users u order by email"

Write-Host ""
Write-Host "Parolalar ve dagitilmis rp_ anahtarlari degismedi -- kimsenin yeni anahtar almasi" -ForegroundColor Yellow
Write-Host "gerekmiyor. Yalnizca panel oturumlari dustu, herkes bir kez yeniden giris yapar." -ForegroundColor Yellow
