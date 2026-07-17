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
if (-not $ServerIp -or -not $Token) { throw "SERVER_IP ve RESEARCH_MCP_TOKEN .env icinde bulunamadi." }

[Environment]::SetEnvironmentVariable("RESEARCH_MCP_TOKEN", $Token, "User")
$env:RESEARCH_MCP_TOKEN = $Token
$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude) { throw "Claude Code CLI bulunamadi. Kurduktan sonra scripti yeniden calistirin." }

$configuration = @{
    type = "http"
    url = "http://${ServerIp}:8010/mcp"
    headers = @{ Authorization = 'Bearer ${RESEARCH_MCP_TOKEN}' }
} | ConvertTo-Json -Compress -Depth 4
& $claude.Source mcp remove research-platform --scope user 2>$null
& $claude.Source mcp add-json research-platform $configuration --scope user
if ($LASTEXITCODE -ne 0) { throw "Claude MCP yapilandirmasi eklenemedi." }

& (Join-Path $PSScriptRoot "setup-research-output.ps1") -DotEnvPath $DotEnvPath
Write-Host "Claude Code MCP yapilandirildi: http://${ServerIp}:8010/mcp"
Write-Host "Claude Code'u tamamen kapatip yeniden acin."
