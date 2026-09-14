<#
.SYNOPSIS
    start_server.ps1'i oturum acilisinda calisacak zamanlanmis goreve baglar.

.DESCRIPTION
    TETIKLEYICI NEDEN ONSTART DEGIL, ATLOGON. Docker Desktop bu makinede bir Windows
    servisi degil: daemon'i HKCU\...\Run altindaki "Docker Desktop.exe" ile, yani
    KULLANICI OTURUMU ACILDIGINDA baslar (com.docker.service yalnizca yardimci servis,
    Manual/Stopped). Sistem acilisinda tetiklenen bir gorev Docker'i bulamaz; GUI
    uygulamasi oldugu icin Session 0'dan baslatilamaz da.

    BU YUZDEN SUNUCU KENDILIGINDEN AYAGA KALKSIN ISTIYORSANIZ OTOMATIK OTURUM ACMA
    SART. Aksi halde her yeniden baslatmadan sonra birinin makineye giris yapmasi
    gerekir. Kurulum notlarina bakin.

    Kontrol paneli icin AYRICA register_control_panel.ps1 CALISTIRMAYIN: start_server.ps1
    paneli zaten baslatiyor, iki gorev ayni portu almaya calisir.

    Ollama'yi bu gorev dogrudan kapsamaz -- ayrica register_ollama_autostart.ps1
    calistirilarak Ollama icin ayri bir kalici gorev tanimlanmistir.
#>
param(
    [string]$TaskName = "Research Platform Server"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot "start_server.ps1"

if (-not (Test-Path $script)) { throw "Bulunamadi: $script" }

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" `
    -WorkingDirectory $root

# $env:USERDOMAIN KULLANMAYIN. Etki alanina katilmamis bir makinede degeri "WORKGROUP"
# olur ve "WORKGROUP\kullanici" gecerli bir asil degildir: Register-ScheduledTask
# "Parametre hatali" (0x80070057) verir. Yerel hesapta alan adi bilgisayar adidir.
# WindowsIdentity her iki durumda da dogru "ALAN\kullanici" bicimini dondurur.
$kimlik = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $kimlik

$principal = New-ScheduledTaskPrincipal `
    -UserId $kimlik `
    -LogonType Interactive `
    -RunLevel Limited

# Docker Desktop'in daemon'i hazir etmesi dakikalar surebilir; start_server.ps1 zaten
# 5 dakika bekliyor. RestartCount, o pencereyi de asan yavas acilislar icin emniyet.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

# Register-ScheduledTask basarisizligini sonlandirici olmayan bir CimException olarak
# bildirebiliyor; dogrulamadan "kaydedildi" yazmak yanlis guven verir.
if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
    throw "Gorev kaydedilemedi: $TaskName"
}

Write-Host "Otomatik baslatma kaydedildi: $TaskName" -ForegroundColor Green
Write-Host "Tetikleyici: oturum acilisi ($kimlik)"
Write-Host ""
Write-Host "Otomatik oturum acma kapaliysa sunucu yeniden baslatmadan sonra" -ForegroundColor Yellow
Write-Host "kendiliginden AYAGA KALKMAZ -- Docker Desktop oturum gerektiriyor." -ForegroundColor Yellow
