param(
    [string]$InterfaceAlias = "Wi-Fi"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path "$root\.env.office")) {
    & "$PSScriptRoot\initialize_office_server.ps1" -InterfaceAlias $InterfaceAlias
}

$dockerReady = $false
for ($attempt = 1; $attempt -le 60; $attempt++) {
    try {
        $serverVersion = docker version --format "{{.Server.Version}}" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $dockerReady = $true
            break
        }
    } catch {}
    Start-Sleep -Seconds 5
}
if (-not $dockerReady) {
    throw "Docker Desktop 5 dakika içinde hazır olmadı."
}

docker compose up -d postgres redis minio crawl4ai
if ($LASTEXITCODE -ne 0) {
    throw "Yerel altyapı container'ları başlatılamadı."
}

& "$PSScriptRoot\stop_native.ps1"
& "$PSScriptRoot\start_native.ps1" -EnvFile "$root\.env.office" -SkipInstall

$environment = @{}
Get-Content "$root\.env.office" -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        $environment[$matches[1].Trim()] = $matches[2].Trim()
    }
}
$currentAddress = Get-NetIPAddress -InterfaceAlias $InterfaceAlias -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "169.254.*" } |
    Select-Object -First 1
if (-not $currentAddress -or $currentAddress.IPAddress -ne $environment.MCP_HOST) {
    throw "Wi-Fi IP değişti. initialize_office_server.ps1 -Force çalıştırıp erişim paketini yenileyin."
}

$headers = @{ Authorization = "Bearer $($environment.MCP_BEARER_TOKEN)" }
$healthUrl = "http://$($environment.MCP_HOST):$($environment.MCP_PORT)/health"
$healthy = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
        $health = Invoke-RestMethod $healthUrl -Headers $headers -TimeoutSec 3
        if ($health.status -eq "healthy") {
            $healthy = $true
            break
        }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $healthy) {
    throw "MCP gateway sağlık kontrolü başarısız: $healthUrl"
}

$status = [ordered]@{
    version = "0.4.2"
    started_at = (Get-Date).ToUniversalTime().ToString("o")
    mcp_url = "http://$($environment.MCP_HOST):$($environment.MCP_PORT)/mcp"
    health_url = $healthUrl
    api_url = $environment.RESEARCH_API_URL
    telegram_enabled = [bool]$environment.TELEGRAM_BOT_TOKEN
}
$status | ConvertTo-Json | Set-Content "$root\logs\office-status.json" -Encoding UTF8
Write-Host "Research Platform ofis sunucusu çalışıyor."
Write-Host "MCP: $($status.mcp_url)"
Write-Host "API yalnız localhost üzerinde: $($status.api_url)"
