param(
    [Parameter(Mandatory = $true)]
    [string]$ServerIp,
    [Parameter(Mandatory = $true)]
    [string]$Token
)

$ErrorActionPreference = "Stop"
$configDirectory = Join-Path $HOME ".codex"
$configPath = Join-Path $configDirectory "config.toml"
New-Item -ItemType Directory -Force -Path $configDirectory | Out-Null
if (-not (Test-Path $configPath)) {
    [System.IO.File]::WriteAllText(
        $configPath,
        "",
        [System.Text.UTF8Encoding]::new($false)
    )
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item $configPath "$configPath.backup-$timestamp" -Force
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
if ($content -match $pattern) {
    $content = [regex]::Replace($content, $pattern, $block.Trim() + "`r`n`r`n")
} else {
    $content = $content.TrimEnd() + "`r`n`r`n" + $block.Trim() + "`r`n"
}
[System.IO.File]::WriteAllText(
    $configPath,
    $content,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "Codex MCP yapılandırıldı: http://${ServerIp}:8010/mcp"
Write-Host "Token kullanıcı ortam değişkenine kaydedildi ve terminale yazdırılmadı."
Write-Host "Codex'i tamamen kapatıp yeniden açın."
