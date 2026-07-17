$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$accessRoot = Join-Path $root "data\office-access"
$accessFile = Join-Path $accessRoot "TEAM_ACCESS.txt"
if (-not (Test-Path -LiteralPath $accessFile)) { throw "TEAM_ACCESS.txt bulunamadi." }

$access = Get-Content -LiteralPath $accessFile -Raw -Encoding UTF8
$serverIp = [regex]::Match($access, 'Server URL:\s*http://([^:/\s]+):8010/mcp').Groups[1].Value
$token = [regex]::Match($access, 'Bearer token:\s*(\S+)').Groups[1].Value
if (-not $serverIp -or -not $token) { throw "TEAM_ACCESS.txt icinden sunucu veya token okunamadi." }

$version = "0.6.1"
$bundleName = "research-platform-team-client-v$version"
$bundleRoot = Join-Path $accessRoot $bundleName
if (Test-Path $bundleRoot) { Remove-Item -LiteralPath $bundleRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $bundleRoot | Out-Null

$dotenv = @"
# Research Platform team client v$version
SERVER_IP=$serverIp
RESEARCH_MCP_TOKEN=$token
DELIVERY_MODE=both
POLL_SECONDS=10
RESEARCH_OUTPUT_DIR=%USERPROFILE%\Desktop\can-sagligi-deep-research
"@
[IO.File]::WriteAllText((Join-Path $bundleRoot ".env"), $dotenv, [Text.UTF8Encoding]::new($false))
@("install_codex_client.ps1", "install_claude_client.ps1", "setup-research-output.ps1", "sync-research-reports.ps1") |
    ForEach-Object { Copy-Item (Join-Path $PSScriptRoot $_) $bundleRoot }
Copy-Item (Join-Path $root "OFFICE_TEAM_SETUP.md") $bundleRoot
Copy-Item (Join-Path $root "RESEARCH_SETUP.md") $bundleRoot

$readme = @"
Research Platform Team Client
Paket surumu: v$version
Belge surumu: 2.0
Tarih: 2026-07-17

Codex:  .\install_codex_client.ps1
Claude: .\install_claude_client.ps1

Script .env dosyasini otomatik okur. Masaustunde can-sagligi-deep-research
klasorunu olusturur ve tamamlanan yeni islerin ham+sonuc ZIP paketlerini otomatik indirir.

Bu paket gizli bearer token icerir. Yalniz yetkili ekip uyeleriyle paylasin.
"@
[IO.File]::WriteAllText((Join-Path $bundleRoot "README.txt"), $readme, [Text.UTF8Encoding]::new($false))
$zipPath = Join-Path $accessRoot "$bundleName.zip"
if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Compress-Archive -Path "$bundleRoot\*" -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host "Ekip istemci paketi hazir: $zipPath"
