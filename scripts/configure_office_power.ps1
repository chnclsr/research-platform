$ErrorActionPreference = "Stop"

powercfg /change standby-timeout-ac 0
if ($LASTEXITCODE -ne 0) {
    throw "Prize bağlı uyku ayarı değiştirilemedi."
}
powercfg /change hibernate-timeout-ac 0
if ($LASTEXITCODE -ne 0) {
    throw "Prize bağlı hazırda bekletme ayarı değiştirilemedi."
}

Write-Host "Prize bağlıyken uyku ve hazırda bekletme kapatıldı."
Write-Host "Ekran kapanabilir; araştırma servisleri çalışmaya devam eder."
