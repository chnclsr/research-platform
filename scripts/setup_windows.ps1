$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop bulunamadı. Docker'ı kurup yeniden çalıştırın."
}
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ".env oluşturuldu. API_TOKEN ve MINIO_SECRET_KEY değerlerini değiştirin."
}
if (-not (Test-Path ".env.native")) {
    Copy-Item ".env.native.example" ".env.native"
    foreach ($key in @("API_TOKEN", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "CRAWL4AI_API_TOKEN", "CRAWL4AI_SECRET_KEY")) {
        $line = Get-Content ".env" | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
        if ($line) {
            $value = $line.Split('=', 2)[1]
            (Get-Content ".env.native") -replace "^$key=.*$", "$key=$value" | Set-Content ".env.native"
        }
    }
}

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    $candidate = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (Test-Path $candidate) { $ollama = $candidate }
}
if (-not $ollama) { throw "Ollama bulunamadı." }

$ollamaPath = if ($ollama -is [string]) { $ollama } else { $ollama.Source }
& $ollamaPath pull qwen3:4b-instruct-2507-q4_K_M
& $ollamaPath pull embeddinggemma:300m-qat-q4_0
docker compose config --quiet
docker compose run --rm --entrypoint python crawl4ai -m playwright install chromium
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Tam Docker kurulumu başarısız; native API/worker fallback başlatılıyor."
    docker compose up -d postgres redis minio
    & "$PSScriptRoot\start_native.ps1"
}
Write-Host "API: http://localhost:8000/docs"
Write-Host "Langflow: http://localhost:7860"
Write-Host "MinIO: http://localhost:9001"
