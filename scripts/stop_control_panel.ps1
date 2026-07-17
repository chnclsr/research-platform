$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pidFile = "$root\logs\control-panel.pid"

function Stop-ProcessTree {
    param([int]$ProcessId)
    $children = Get-CimInstance Win32_Process |
        Where-Object { $_.ParentProcessId -eq $ProcessId }
    foreach ($child in $children) { Stop-ProcessTree -ProcessId $child.ProcessId }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

if (Test-Path $pidFile) {
    try { Stop-ProcessTree -ProcessId ([int](Get-Content $pidFile)) } catch {}
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}
Write-Host "Research Platform Control Panel durduruldu."
