param(
    [string]$ServerIp,
    [string]$Token,
    [string]$DotEnvPath = (Join-Path $PSScriptRoot ".env")
)

$ErrorActionPreference = "Stop"
function Import-DotEnv([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
        $parts = $trimmed.Split("=", 2)
        [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"').Trim("'"), "Process")
    }
}
Import-DotEnv $DotEnvPath
if (-not $ServerIp) { $ServerIp = $env:SERVER_IP }
if (-not $Token) { $Token = $env:RESEARCH_MCP_TOKEN }
if (-not $ServerIp) { throw "SERVER_IP .env icinde bulunamadi." }

# v0.10.1: kimlik bilgisi artik KISIYE OZEL bir API anahtari. Paylasilan jeton kaldirildi
# cunku onunla baslatilan kosunun sahibi olmuyordu ve API sahipsiz kosuyu reddediyor.
# Paketle gelen .env herkeste ayni oldugu icin oradan gelen bir deger kabul edilmez.
if ($Token -notlike "rp_*") {
    Write-Host ""
    Write-Host "Kendi API anahtariniz gerekiyor (rp_ ile baslar)."
    Write-Host "  Panelden: Hesabim -> API anahtarlari -> Yeni anahtar"
    Write-Host "  Ya da yoneticiden: research-admin issue-key <e-posta> --name codex"
    Write-Host ""
    $Token = (Read-Host "API anahtari").Trim()
}
if ($Token -notlike "rp_*") { throw "Gecersiz anahtar: 'rp_' ile baslamali." }

$configDirectory = Join-Path $HOME ".codex"
$configPath = Join-Path $configDirectory "config.toml"
New-Item -ItemType Directory -Force -Path $configDirectory | Out-Null
if (-not (Test-Path $configPath)) { [System.IO.File]::WriteAllText($configPath, "", [Text.UTF8Encoding]::new($false)) }
Copy-Item $configPath "$configPath.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')" -Force
[Environment]::SetEnvironmentVariable("RESEARCH_MCP_TOKEN", $Token, "User")
$env:RESEARCH_MCP_TOKEN = $Token

$block = @"
[mcp_servers.research_platform]
enabled = true
required = false
url = "http://${ServerIp}:8010/mcp"
bearer_token_env_var = "RESEARCH_MCP_TOKEN"
startup_timeout_sec = 20.0
tool_timeout_sec = 3600.0
"@
$content = Get-Content $configPath -Raw -Encoding UTF8
$pattern = '(?ms)^\[mcp_servers\.research_platform\]\s*.*?(?=^\[|\z)'
if ($content -match $pattern) { $content = [regex]::Replace($content, $pattern, $block.Trim() + "`r`n`r`n") }
else { $content = $content.TrimEnd() + "`r`n`r`n" + $block.Trim() + "`r`n" }
[System.IO.File]::WriteAllText($configPath, $content, [Text.UTF8Encoding]::new($false))

& (Join-Path $PSScriptRoot "setup-research-output.ps1") -DotEnvPath $DotEnvPath
Write-Host "Codex MCP yapilandirildi: http://${ServerIp}:8010/mcp"
Write-Host "Codex'i tamamen kapatip yeniden acin."
