param([string]$DotEnvPath = (Join-Path $PSScriptRoot ".env"))

$ErrorActionPreference = "Stop"
$installDirectory = Join-Path $env:LOCALAPPDATA "ResearchPlatformClient"
$outputDirectory = Join-Path ([Environment]::GetFolderPath("Desktop")) "can-sagligi-deep-research"
New-Item -ItemType Directory -Force -Path $installDirectory,$outputDirectory | Out-Null

if (-not (Test-Path -LiteralPath $DotEnvPath)) { throw ".env bulunamadi: $DotEnvPath" }
Copy-Item -LiteralPath $DotEnvPath -Destination (Join-Path $installDirectory ".env") -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "sync-research-reports.ps1") `
    -Destination (Join-Path $installDirectory "sync-research-reports.ps1") -Force

$syncScript = Join-Path $installDirectory "sync-research-reports.ps1"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $syncScript -InitializeOnly

$taskName = "Research Platform Report Sync"
$arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$syncScript`" -Loop"
try {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Settings $settings -Description "Research Platform tamamlanan raporlarini masaustune indirir." `
        -Force | Out-Null
    Start-ScheduledTask -TaskName $taskName
} catch {
    $startup = [Environment]::GetFolderPath("Startup")
    $launcher = Join-Path $startup "Research Platform Report Sync.cmd"
    $command = "@start `"`" powershell.exe $arguments"
    [System.IO.File]::WriteAllText($launcher, $command, [System.Text.Encoding]::ASCII)
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList $arguments
}

Write-Host "Otomatik rapor esitleme etkin."
Write-Host "Hedef klasor: $outputDirectory"
Write-Host "Yapilandirma: $installDirectory"
