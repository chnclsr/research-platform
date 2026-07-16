$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Stop-ProcessTree {
    param([int]$ProcessId)
    $children = Get-CimInstance Win32_Process |
        Where-Object { $_.ParentProcessId -eq $ProcessId }
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId $child.ProcessId
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

$processIds = New-Object System.Collections.Generic.HashSet[int]
foreach ($name in @("api", "worker", "mcp", "telegram")) {
    $pidFile = "$root\logs\$name.pid"
    if (Test-Path $pidFile) {
        [void]$processIds.Add([int](Get-Content $pidFile))
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

$rootPattern = [regex]::Escape($root)
Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -match "$rootPattern\\\.venv\\Scripts\\research-(api|worker|mcp|telegram)\.exe$"
} | ForEach-Object {
    [void]$processIds.Add([int]$_.ProcessId)
}

foreach ($processId in $processIds) {
    Stop-ProcessTree -ProcessId $processId
}

Write-Host "Research Platform native süreçleri durduruldu."
