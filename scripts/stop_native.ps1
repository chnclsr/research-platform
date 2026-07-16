$root = Split-Path -Parent $PSScriptRoot
foreach ($name in @("api", "worker", "mcp", "telegram")) {
    $pidFile = "$root\logs\$name.pid"
    if (Test-Path $pidFile) {
        $processId = [int](Get-Content $pidFile)
        Stop-Process -Id $processId -ErrorAction SilentlyContinue
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }
}
