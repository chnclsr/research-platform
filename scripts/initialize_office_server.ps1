param(
    [string]$InterfaceAlias = "Wi-Fi",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function New-RandomToken {
    param([int]$Bytes = 32)
    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($buffer).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Get-NetworkCidr {
    param([string]$Address, [int]$PrefixLength)
    $bytes = [System.Net.IPAddress]::Parse($Address).GetAddressBytes()
    $remaining = $PrefixLength
    for ($index = 0; $index -lt $bytes.Length; $index++) {
        $bits = [Math]::Max(0, [Math]::Min(8, $remaining))
        $mask = if ($bits -eq 0) { 0 } else { (0xFF -shl (8 - $bits)) -band 0xFF }
        $bytes[$index] = $bytes[$index] -band $mask
        $remaining -= $bits
    }
    return "$([System.Net.IPAddress]::new($bytes).ToString())/$PrefixLength"
}

$address = Get-NetIPAddress -InterfaceAlias $InterfaceAlias -AddressFamily IPv4 `
    -ErrorAction Stop |
    Where-Object { $_.IPAddress -notlike "169.254.*" } |
    Select-Object -First 1
if (-not $address) {
    throw "$InterfaceAlias üzerinde kullanılabilir IPv4 adresi bulunamadı."
}

$officeEnv = Join-Path $root ".env.office"
if ((Test-Path $officeEnv) -and -not $Force) {
    Write-Host ".env.office zaten var; değiştirilmedi."
    exit 0
}

$apiToken = New-RandomToken
$mcpToken = New-RandomToken
$networkCidr = Get-NetworkCidr -Address $address.IPAddress -PrefixLength $address.PrefixLength

$lines = Get-Content "$root\.env.native.example" -Encoding UTF8
$values = @{
    "API_TOKEN" = $apiToken
    "API_HOST" = "127.0.0.1"
    "API_PORT" = "8000"
    "RESEARCH_API_URL" = "http://127.0.0.1:8000"
    "MCP_TRANSPORT" = "streamable-http"
    "MCP_HOST" = $address.IPAddress
    "MCP_PORT" = "8010"
    "MCP_BEARER_TOKEN" = $mcpToken
    "MCP_ALLOWED_ORIGINS" = "[]"
    "MCP_ALLOWED_NETWORKS" = "[`"$networkCidr`"]"
}
foreach ($key in $values.Keys) {
    $replacement = "$key=$($values[$key])"
    if ($lines -match "^$key=") {
        $lines = $lines -replace "^$key=.*$", $replacement
    } else {
        $lines += $replacement
    }
}
[System.IO.File]::WriteAllLines($officeEnv, $lines, [System.Text.UTF8Encoding]::new($false))

$accessDirectory = Join-Path $root "data\office-access"
New-Item -ItemType Directory -Force -Path $accessDirectory | Out-Null
$accessFile = Join-Path $accessDirectory "TEAM_ACCESS.txt"
$access = @"
Research Platform Office Access
Version: 0.5.0
Date: 2026-07-16

Server URL: http://$($address.IPAddress):8010/mcp
Health URL: http://$($address.IPAddress):8010/health
Allowed network: $networkCidr
Bearer token: $mcpToken

Bu dosyayı yalnız yetkili ekip üyeleriyle güvenli kanaldan paylaşın.
Her istemcide RESEARCH_MCP_TOKEN ortam değişkeni bearer token değerine ayarlanmalıdır.
"@
[System.IO.File]::WriteAllText($accessFile, $access, [System.Text.UTF8Encoding]::new($false))

Write-Host "Ofis yapılandırması hazırlandı."
Write-Host "MCP adresi: http://$($address.IPAddress):8010/mcp"
Write-Host "Allowlist: $networkCidr"
Write-Host "Ekip erişim dosyası: $accessFile"
Write-Host "Token terminale yazdırılmadı."
