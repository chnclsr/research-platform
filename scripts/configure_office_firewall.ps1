param(
    [string]$InterfaceAlias = "Wi-Fi"
)

$ErrorActionPreference = "Stop"
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Bu işlem yönetici yetkisi ister. PowerShell'i yönetici olarak açıp scripti tekrar çalıştırın."
}

$address = Get-NetIPAddress -InterfaceAlias $InterfaceAlias -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "169.254.*" } |
    Select-Object -First 1
if (-not $address) { throw "$InterfaceAlias IPv4 adresi bulunamadı." }

$displayName = "Research Platform Services - Office LAN"
@("Research Platform MCP - Office LAN", $displayName) | ForEach-Object {
    Get-NetFirewallRule -DisplayName $_ -ErrorAction SilentlyContinue
} |
    Remove-NetFirewallRule
New-NetFirewallRule `
    -DisplayName $displayName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalAddress $address.IPAddress `
    -LocalPort 8010,8020 `
    -RemoteAddress LocalSubnet `
    -Profile Domain,Private,Public `
    -Description "Research Platform MCP ve kontrol paneli; uygulama katmanı CIDR allowlist ile korunur." |
    Out-Null

Write-Host "Firewall kuralı eklendi: $displayName"
Write-Host "Yalnız LocalSubnet -> $($address.IPAddress):8010,8020"
