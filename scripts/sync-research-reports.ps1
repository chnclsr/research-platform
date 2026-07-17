param(
    [string]$ConfigDirectory = (Join-Path $env:LOCALAPPDATA "ResearchPlatformClient"),
    [string]$OutputDirectory,
    [string]$RunId,
    [switch]$Force,
    [switch]$Loop,
    [switch]$InitializeOnly
)

$ErrorActionPreference = "Stop"

function Import-DotEnv([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { throw ".env bulunamadi: $Path" }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
        $parts = $trimmed.Split("=", 2)
        [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"').Trim("'"), "Process")
    }
}

Import-DotEnv (Join-Path $ConfigDirectory ".env")
if (-not $env:SERVER_IP -or -not $env:RESEARCH_MCP_TOKEN) {
    throw ".env icinde SERVER_IP ve RESEARCH_MCP_TOKEN zorunludur."
}

$mode = if ($env:DELIVERY_MODE) { $env:DELIVERY_MODE.ToLowerInvariant() } else { "both" }
if ($mode -notin @("raw", "result", "both")) { throw "DELIVERY_MODE raw, result veya both olmali." }
$pollSeconds = if ($env:POLL_SECONDS) { [Math]::Max(5, [int]$env:POLL_SECONDS) } else { 10 }
$outputDirectory = if ($OutputDirectory) {
    $OutputDirectory
} elseif ($env:RESEARCH_OUTPUT_DIR) {
    [Environment]::ExpandEnvironmentVariables($env:RESEARCH_OUTPUT_DIR)
} else {
    Join-Path ([Environment]::GetFolderPath("Desktop")) "can-sagligi-deep-research"
}
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$statePath = Join-Path $ConfigDirectory "downloaded-runs.txt"
$logPath = Join-Path $ConfigDirectory "sync.log"
$seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
if (Test-Path -LiteralPath $statePath) {
    foreach ($id in Get-Content -LiteralPath $statePath) { if ($id.Trim()) { [void]$seen.Add($id.Trim()) } }
}
$headers = @{ Authorization = "Bearer $env:RESEARCH_MCP_TOKEN" }
$baseUrl = "http://$($env:SERVER_IP):8010/client/v1"
$terminal = @("completed", "completed_incomplete", "failed", "cancelled")

function Write-SyncLog([string]$Message) {
    $entry = "$(Get-Date -Format o) $Message"
    Add-Content -LiteralPath $logPath -Value $entry -Encoding UTF8
}

function Save-Seen([string]$RunId) {
    if ($seen.Add($RunId)) { Add-Content -LiteralPath $statePath -Value $RunId -Encoding ASCII }
}

function Sync-Once {
    $runs = if ($RunId) {
        @(Invoke-RestMethod -Method Get -Uri "$baseUrl/research-runs/$RunId" -Headers $headers -TimeoutSec 30)
    } else {
        @((Invoke-RestMethod -Method Get -Uri "$baseUrl/research-runs?limit=200" `
            -Headers $headers -TimeoutSec 30) | ForEach-Object { $_ })
    }
    foreach ($run in ($runs | Sort-Object created_at)) {
        if ($terminal -notcontains [string]$run.status -or ($seen.Contains([string]$run.id) -and -not $Force)) { continue }
        if ($InitializeOnly) { Save-Seen ([string]$run.id); continue }

        $title = [string]$run.protocol.title
        $safeTitle = ($title -replace '[^\p{L}\p{Nd}._-]+', '-').Trim('-')
        if (-not $safeTitle) { $safeTitle = "research" }
        if ($safeTitle.Length -gt 60) { $safeTitle = $safeTitle.Substring(0, 60).Trim('-') }
        $date = ([datetimeoffset]$run.created_at).ToLocalTime().ToString("yyyyMMdd-HHmmss")
        $stem = "${date}_${safeTitle}_$($run.id)"

        $metadataPath = Join-Path $outputDirectory "${stem}_status.json"
        [System.IO.File]::WriteAllText(
            $metadataPath,
            ($run | ConvertTo-Json -Depth 20),
            [System.Text.UTF8Encoding]::new($false)
        )

        if ([string]$run.status -in @("completed", "completed_incomplete")) {
            $finalPath = Join-Path $outputDirectory "${stem}_${mode}.zip"
            $temporaryPath = "$finalPath.partial"
            try {
                Invoke-WebRequest -Method Get -Uri "$baseUrl/research-runs/$($run.id)/delivery/$mode" `
                    -Headers $headers -OutFile $temporaryPath -TimeoutSec 3600 -UseBasicParsing
                Add-Type -AssemblyName System.IO.Compression.FileSystem
                $archive = [System.IO.Compression.ZipFile]::OpenRead($temporaryPath)
                try { if ($archive.Entries.Count -eq 0) { throw "ZIP bos." } } finally { $archive.Dispose() }
                Move-Item -LiteralPath $temporaryPath -Destination $finalPath -Force
                Write-SyncLog "downloaded run=$($run.id) mode=$mode file=$([IO.Path]::GetFileName($finalPath))"
                Save-Seen ([string]$run.id)
            } catch {
                Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
                Write-SyncLog "retry run=$($run.id) error=$($_.Exception.Message)"
            }
        } else {
            Write-SyncLog "terminal run=$($run.id) status=$($run.status); status JSON saved"
            Save-Seen ([string]$run.id)
        }
    }
}

$created = $false
$mutex = [Threading.Mutex]::new($false, "Local\ResearchPlatformReportSync", [ref]$created)
if (-not $created) { exit 0 }
try {
    do {
        try { Sync-Once } catch { Write-SyncLog "poll_error=$($_.Exception.Message)" }
        if ($Loop) { Start-Sleep -Seconds $pollSeconds }
    } while ($Loop)
} finally {
    $mutex.Dispose()
}
