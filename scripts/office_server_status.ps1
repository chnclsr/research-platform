$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env.office"
if (-not (Test-Path $envFile)) {
    throw ".env.office bulunamadı. initialize_office_server.ps1 çalıştırın."
}

$environment = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        $environment[$matches[1].Trim()] = $matches[2].Trim()
    }
}
$headers = @{ Authorization = "Bearer $($environment.MCP_BEARER_TOKEN)" }
$healthUrl = "http://$($environment.MCP_HOST):$($environment.MCP_PORT)/health"

$result = [ordered]@{
    mcp_url = "http://$($environment.MCP_HOST):$($environment.MCP_PORT)/mcp"
    mcp_health = "unavailable"
    api_health = "unavailable"
    processes = @{}
}
try {
    $result.mcp_health = (Invoke-RestMethod $healthUrl -Headers $headers -TimeoutSec 3).status
} catch {
    $result.mcp_health = $_.Exception.Message
}
try {
    $result.api_health = (Invoke-RestMethod "$($environment.RESEARCH_API_URL)/health" -TimeoutSec 15).status
} catch {
    $result.api_health = $_.Exception.Message
}
foreach ($name in @("api", "worker", "mcp", "telegram")) {
    $pidFile = Join-Path $root "logs\$name.pid"
    if (Test-Path $pidFile) {
        $processId = [int](Get-Content $pidFile)
        $result.processes[$name] = [bool](Get-Process -Id $processId -ErrorAction SilentlyContinue)
    } else {
        $result.processes[$name] = $false
    }
}
$result | ConvertTo-Json -Depth 4
