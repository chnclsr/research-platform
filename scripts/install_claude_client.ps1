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
    Write-Host "  Ya da yoneticiden: research-admin issue-key <e-posta> --name claude-code"
    Write-Host ""
    $Token = (Read-Host "API anahtari").Trim()
}
if ($Token -notlike "rp_*") { throw "Gecersiz anahtar: 'rp_' ile baslamali." }

[Environment]::SetEnvironmentVariable("RESEARCH_MCP_TOKEN", $Token, "User")
$env:RESEARCH_MCP_TOKEN = $Token
$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude) { throw "Claude Code CLI bulunamadi. Kurduktan sonra scripti yeniden calistirin." }

# 'mcp add-json' bu surumlerde "Invalid input" veriyor; belgelenen yol 'add --transport'.
# Anahtar dogrudan gomulmuyor: ${RESEARCH_MCP_TOKEN} olarak yaziliyor ve Claude Code onu
# calisma aninda ortamdan cozuyor, boylece ~/.claude.json icinde duz metin anahtar durmaz.
& $claude.Source mcp remove research-platform --scope user 2>$null
& $claude.Source mcp add --transport http research-platform "http://${ServerIp}:8010/mcp" `
    --header "Authorization: Bearer `${RESEARCH_MCP_TOKEN}" --scope user
if ($LASTEXITCODE -ne 0) { throw "Claude MCP yapilandirmasi eklenemedi." }

& (Join-Path $PSScriptRoot "setup-research-output.ps1") -DotEnvPath $DotEnvPath
Write-Host "Claude Code MCP yapilandirildi: http://${ServerIp}:8010/mcp"
Write-Host ""
Write-Host "ONEMLI: Calisan terminaller RESEARCH_MCP_TOKEN'i gormez (eski ortam blogu)."
Write-Host "Claude Code'u YENI bir terminalden acin, yoksa 'Failed to connect' alirsiniz."
Write-Host "Dogrulama: claude mcp list  ->  '/ Connected' gormelisiniz."
