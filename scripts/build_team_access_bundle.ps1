$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$accessRoot = Join-Path $root "data\office-access"
$accessFile = Join-Path $accessRoot "TEAM_ACCESS.txt"
if (-not (Test-Path $accessFile)) {
    throw "TEAM_ACCESS.txt bulunamadı. Önce initialize_office_server.ps1 çalıştırın."
}

$bundleRoot = Join-Path $accessRoot "research-platform-team-client-v0.5.2"
if (Test-Path $bundleRoot) {
    Remove-Item -LiteralPath $bundleRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $bundleRoot | Out-Null

Copy-Item $accessFile (Join-Path $bundleRoot "TEAM_ACCESS.txt")
Copy-Item (Join-Path $root "OFFICE_TEAM_SETUP.md") $bundleRoot
Copy-Item (Join-Path $PSScriptRoot "install_codex_client.ps1") $bundleRoot
Copy-Item (Join-Path $PSScriptRoot "install_claude_client.ps1") $bundleRoot

$readme = @"
Research Platform Team Client Bundle
Bundle version: 1.0
Platform version: v0.5.2
Date: 2026-07-16

1. TEAM_ACCESS.txt dosyasındaki Server URL ve Bearer token değerlerini alın.
2. Codex için install_codex_client.ps1, Claude Code için install_claude_client.ps1 çalıştırın.
3. Ayrıntılar için OFFICE_TEAM_SETUP.md belgesini okuyun.

Bu ZIP erişim anahtarı içerir. Yalnız yetkili ekip üyeleriyle güvenli kanaldan paylaşın.
"@
[System.IO.File]::WriteAllText(
    (Join-Path $bundleRoot "README.txt"),
    $readme,
    [System.Text.UTF8Encoding]::new($false)
)

$zipPath = Join-Path $accessRoot "research-platform-team-client-v0.5.2.zip"
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path "$bundleRoot\*" -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host "Ekip istemci paketi hazır: $zipPath"
Write-Host "Paket bearer token içerir; güvenli paylaşın."
