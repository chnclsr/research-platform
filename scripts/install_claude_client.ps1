param(
    [Parameter(Mandatory = $true)]
    [string]$ServerIp,
    [Parameter(Mandatory = $true)]
    [string]$Token
)

$ErrorActionPreference = "Stop"
[Environment]::SetEnvironmentVariable("RESEARCH_MCP_TOKEN", $Token, "User")
$env:RESEARCH_MCP_TOKEN = $Token

$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude) {
    throw "Claude Code CLI bulunamadı. Kurduktan sonra bu scripti yeniden çalıştırın."
}

$configuration = @{
    type = "http"
    url = "http://${ServerIp}:8010/mcp"
    headers = @{
        Authorization = 'Bearer ${RESEARCH_MCP_TOKEN}'
    }
} | ConvertTo-Json -Compress -Depth 4

& $claude.Source mcp remove research-platform --scope user 2>$null
& $claude.Source mcp add-json research-platform $configuration --scope user
if ($LASTEXITCODE -ne 0) {
    throw "Claude MCP yapılandırması eklenemedi."
}

Write-Host "Claude Code MCP yapılandırıldı: http://${ServerIp}:8010/mcp"
Write-Host "Token kullanıcı ortam değişkenine kaydedildi ve terminale yazdırılmadı."
Write-Host "Claude Code'u tamamen kapatıp yeniden açın."
