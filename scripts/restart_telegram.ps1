param(
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $EnvFile) {
    $EnvFile = if (Test-Path "$root\.env.office") {
        "$root\.env.office"
    } else {
        "$root\.env.native.example"
    }
}
if (-not [System.IO.Path]::IsPathRooted($EnvFile)) {
    $EnvFile = Join-Path $root $EnvFile
}
Get-Content -LiteralPath $EnvFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable(
            $matches[1].Trim(), $matches[2].Trim(), "Process"
        )
    }
}

$pidFile = "$root\logs\telegram.pid"
if (Test-Path $pidFile) {
    try {
        $oldPid = [int](Get-Content $pidFile)
        Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $oldPid -Timeout 10 -ErrorAction SilentlyContinue
    } catch {}
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

$executable = "$root\.venv\Scripts\research-telegram.exe"
if (-not (Test-Path $executable)) {
    throw "Telegram executable bulunamadi: $executable"
}
$process = Start-Process -FilePath $executable `
    -WorkingDirectory $root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$root\logs\telegram.stdout.log" `
    -RedirectStandardError "$root\logs\telegram.stderr.log"
Set-Content -Path $pidFile -Value $process.Id -Encoding ASCII

Start-Sleep -Seconds 3
if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
    throw "Telegram bot baslatilamadi. logs\telegram.stderr.log dosyasini kontrol edin."
}
Write-Host "Telegram bot yeniden baslatildi (PID $($process.Id))."
