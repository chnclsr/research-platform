<#
.SYNOPSIS
    Ollama sunucusunu oturum acilisinda calisacak ve cokerse otomatik
    yeniden baslatacak zamanlanmis goreve baglar.

.DESCRIPTION
    Ollama arka plan daemon'ini (ollama serve) Windows Gorev Zamanlayici'ya
    ekler. Gorev:
    - Oturum acilisinda otomatik baslar (AtLogOn).
    - Surec cokerse veya kapanirsa 1 dakika icinde yeniden baslatir (RestartCount / RestartInterval).
    - Sure siniri olmadan (3650 gun) surekli ayakta kalir.
#>
param(
    [string]$TaskName = "Ollama Server"
)

$ErrorActionPreference = "Stop"

$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (-not (Test-Path $ollamaExe)) {
    throw "Ollama calistirilabilir dosyasi bulunamadi: $ollamaExe"
}

$action = New-ScheduledTaskAction `
    -Execute $ollamaExe `
    -Argument "serve" `
    -WorkingDirectory (Split-Path $ollamaExe)

$kimlik = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $kimlik

$principal = New-ScheduledTaskPrincipal `
    -UserId $kimlik `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
    throw "Gorev kaydedilemedi: $TaskName"
}

Write-Host "Ollama otomatik baslatma gorevi kaydedildi: $TaskName" -ForegroundColor Green
Write-Host "Tetikleyici: Oturum acilisi ($kimlik)"
Write-Host "Kural: Surec durursa 1 dakika icinde otomatik yeniden baslatilir."
