param(
    [Parameter(Mandatory = $true)]
    [string]$BotToken,
    [long[]]$AllowedUserIds = @(),
    [long[]]$AllowedChatIds = @()
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env.office"
if (-not (Test-Path $envFile)) {
    throw ".env.office bulunamadı. Önce initialize_office_server.ps1 çalıştırın."
}

$lines = Get-Content $envFile -Encoding UTF8
$userIdJson = if ($AllowedUserIds.Count) {
    "[" + (($AllowedUserIds | ForEach-Object { $_.ToString() }) -join ",") + "]"
} else { "[]" }
$chatIdJson = if ($AllowedChatIds.Count) {
    "[" + (($AllowedChatIds | ForEach-Object { $_.ToString() }) -join ",") + "]"
} else { "[]" }
$updates = @{
    TELEGRAM_BOT_TOKEN = $BotToken
    TELEGRAM_ALLOWED_USER_IDS = $userIdJson
    TELEGRAM_ALLOWED_CHAT_IDS = $chatIdJson
}
foreach ($key in $updates.Keys) {
    $replacement = "$key=$($updates[$key])"
    if ($lines -match "^$key=") {
        $lines = $lines -replace "^$key=.*$", $replacement
    } else {
        $lines += $replacement
    }
}
[System.IO.File]::WriteAllLines($envFile, $lines, [System.Text.UTF8Encoding]::new($false))

Write-Host "Telegram yapılandırması kaydedildi; token gösterilmedi."
if (-not $AllowedUserIds -and -not $AllowedChatIds) {
    Write-Host "Botu başlatıp Telegram'da /whoami yazın; araştırma komutları allowlist eklenene kadar kapalıdır."
}
