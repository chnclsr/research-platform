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
    control_panel_health = "unavailable"
    redis_health = "unavailable"
    worker_queue_heartbeat_ttl_seconds = -2
    processes = @{}
}
try {
    $result.mcp_health = (Invoke-RestMethod $healthUrl -Headers $headers -TimeoutSec 3).status
} catch {
    $result.mcp_health = $_.Exception.Message
}
try {
    $apiHealth = Invoke-RestMethod "$($environment.RESEARCH_API_URL)/health" -TimeoutSec 15
    $result.api_health = $apiHealth.status
    $result.redis_health = $apiHealth.checks.redis
} catch {
    $result.api_health = $_.Exception.Message
}
try {
    $panelHealth = Invoke-RestMethod "http://127.0.0.1:8020/health" -TimeoutSec 3
    $result.control_panel_health = $panelHealth.status
} catch {
    $result.control_panel_health = $_.Exception.Message
}
try {
    $ttl = docker exec research-platform-redis-1 redis-cli TTL arq:queue:health-check
    if ($LASTEXITCODE -eq 0) {
        $result.worker_queue_heartbeat_ttl_seconds = [int]$ttl
    }
} catch {}
foreach ($name in @("api", "worker", "mcp", "telegram", "control-panel")) {
    $pidFile = Join-Path $root "logs\$name.pid"
    if (Test-Path $pidFile) {
        $processId = [int](Get-Content $pidFile)
        $result.processes[$name] = [bool](Get-Process -Id $processId -ErrorAction SilentlyContinue)
    } else {
        $result.processes[$name] = $false
    }
}
$result.processes["worker_operational"] = (
    [bool]$result.processes["worker"] -and
    $result.redis_health -eq "ok" -and
    $result.worker_queue_heartbeat_ttl_seconds -gt 0
)
$result | ConvertTo-Json -Depth 4
