<#
.SYNOPSIS
    Telegram bot kimlik bilgilerini HEM .env HEM .env.office icine yazar.

.DESCRIPTION
    ESKI configure_telegram.ps1 BU KURULUMDA EKSIK KALIR: yalnizca .env.office'e yazar.
    Bu, api/worker/bot natif surecken dogruydu. Simdi bot compose icinde ve compose
    degiskenleri ANA .env'den cozuyor -- token yalnizca .env.office'te olursa
    `${TELEGRAM_BOT_TOKEN}` bos gelir ve telegram profili hic baslamaz.

    Iki dosya da gerekiyor, farkli tuketiciler icin:
      .env         -> telegram-bot container'inin ortami (compose interpolasyonu)
      .env.office  -> kontrol paneli. Paneli calistiran natif surec ortamini buradan
                      okur; token yoksa panel botu denetlenen servisler listesine hic
                      almaz (control_panel.py, _compose_app_services) ve hesap baglama
                      linkini (t.me/<bot>?start=<kod>) uretemez.

    Token kabuk gecmisine dusmesin diye parametre olarak DEGIL, sorularak alinir.

    -BotUsername verilmezse token ile Telegram'in getMe ucuna sorulur. Botun kendi
    API'si oldugu icin ek bir kimlik bilgisi gerekmez ve degeri elle aramaktan daha
    guvenilirdir.

.EXAMPLE
    .\scripts\set_telegram.ps1 -AllowedUserIds 6647206289,1413812810,1366273717
#>
param(
    [string]$BotUsername,
    [long[]]$AllowedUserIds = @(),
    [long[]]$AllowedChatIds = @(),
    # Eski sunucudan tasirken allowlist'i degistirmek istemiyorsaniz verin: yalnizca
    # token ve kullanici adi guncellenir, ID listelerine dokunulmaz.
    [switch]$KeepAllowLists
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

$guvenli = Read-Host "Telegram bot token" -AsSecureString
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($guvenli)
try {
    $token = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
if (-not $token) { throw "Token bos birakilamaz." }

if (-not $BotUsername) {
    # Botun kendi API'si: token zaten ona ait, ek bir sir gonderilmiyor. Panelin hesap
    # baglama linki (t.me/<bot>?start=<kod>) bu degere bagli oldugu icin bos birakmak
    # baglamayi sessizce bozar.
    Write-Host "Kullanici adi verilmedi, Telegram'a soruluyor (getMe)..." -ForegroundColor Cyan
    try {
        $me = Invoke-RestMethod "https://api.telegram.org/bot$token/getMe" -TimeoutSec 20
        if ($me.ok -and $me.result.username) {
            $BotUsername = $me.result.username
            Write-Host "bulundu: @$BotUsername" -ForegroundColor Green
        } else {
            Write-Host "getMe beklenen yaniti vermedi; TELEGRAM_BOT_USERNAME yazilmayacak." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "getMe basarisiz: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "401/404 geldiyse token yanlistir -- o durumda bot da hic calismaz." -ForegroundColor Yellow
        Write-Host "TELEGRAM_BOT_USERNAME yazilmayacak." -ForegroundColor Yellow
    }
}

$degerler = [ordered]@{ TELEGRAM_BOT_TOKEN = $token }
if ($BotUsername) { $degerler["TELEGRAM_BOT_USERNAME"] = $BotUsername.TrimStart("@") }
if (-not $KeepAllowLists) {
    $degerler["TELEGRAM_ALLOWED_USER_IDS"] = "[" + (($AllowedUserIds | ForEach-Object { $_.ToString() }) -join ",") + "]"
    $degerler["TELEGRAM_ALLOWED_CHAT_IDS"] = "[" + (($AllowedChatIds | ForEach-Object { $_.ToString() }) -join ",") + "]"
}

foreach ($dosya in @("$root\.env", "$root\.env.office")) {
    if (-not (Test-Path $dosya)) {
        Write-Host "atlandi (yok): $dosya" -ForegroundColor Yellow
        continue
    }
    $satirlar = @(Get-Content -LiteralPath $dosya -Encoding UTF8)
    foreach ($anahtar in $degerler.Keys) {
        $yeni = "$anahtar=$($degerler[$anahtar])"
        $bulundu = $false
        for ($i = 0; $i -lt $satirlar.Count; $i++) {
            if ($satirlar[$i] -match "^$anahtar=") { $satirlar[$i] = $yeni; $bulundu = $true }
        }
        if (-not $bulundu) { $satirlar += $yeni }
    }
    # BOM'suz UTF-8: compose ve pydantic-settings ilk satirda BOM gorurse anahtar adinin
    # basina gorunmez bir karakter eklenmis gibi okur ve o satir sessizce kaybolur.
    [System.IO.File]::WriteAllLines($dosya, $satirlar, [System.Text.UTF8Encoding]::new($false))
    Write-Host "guncellendi: $(Split-Path -Leaf $dosya)" -ForegroundColor Green
}

$token = $null
Write-Host ""
Write-Host "Token gosterilmedi. Simdi botu baslatin:" -ForegroundColor Cyan
Write-Host "  docker compose --profile telegram up -d telegram-bot"
Write-Host ""
Write-Host "ONCE ESKI SUNUCUDAKI BOTU DURDURUN. Telegram bir token icin tek getUpdates" -ForegroundColor Yellow
Write-Host "tuketicisine izin verir; ikisi birden calisirsa mesajlar iki sunucu arasinda" -ForegroundColor Yellow
Write-Host "rastgele bolunur." -ForegroundColor Yellow
