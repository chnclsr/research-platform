#!/usr/bin/env bash
# Hesap verisini (kullanicilar, API anahtarlari, Telegram eslemeleri) tasinabilir tek
# bir SQL dosyasina cikarir. Ubuntu sunucuda, proje kokunde calisir:
#
#   ./scripts/linux/export_accounts.sh [accounts.sql]
#
# export_accounts.ps1'in Linux karsiligi -- ayni dosya bicimini uretir, dolayisiyla
# ciktisi hem import_accounts.sh hem import_accounts.ps1 tarafindan okunur.
#
# Parolalar ve API anahtarlari, hashin ICINDE tasinan tuzla saklanir
# (auth.py: scrypt$n$r$p$salt$hash). Disarida bir biber/gizli anahtar yok; dolayisiyla
# bu satirlar baska bir makineye tasindiginda parolalar ve dagitilmis rp_ anahtarlari
# aynen calismaya devam eder -- yeni sunucuda SESSION_SECRET degisse bile. Degisen tek
# sey: acik panel oturumlari duser, herkes bir kez yeniden giris yapar.
#
# pg_dump IKI KEZ cagriliyor. Tek cagride --data-only ciktisi tablolari alfabetik
# siralar; api_keys, users'tan once gelir ve geri yuklerken yabanci anahtar kisiti
# patlar. Sira burada elle veriliyor: once users, sonra ona bagli olanlar.
set -euo pipefail

DOSYA="${1:-accounts.sql}"
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

ORTAK=(-U research -d research --data-only --no-owner --no-privileges)

echo "==> users cikariliyor"
docker compose exec -T postgres pg_dump "${ORTAK[@]}" -t users -f /tmp/_a.sql

echo "==> api_keys + telegram_identities cikariliyor"
docker compose exec -T postgres pg_dump "${ORTAK[@]}" -t api_keys -t telegram_identities -f /tmp/_b.sql

GECICI_A="$(mktemp)"
GECICI_B="$(mktemp)"
docker compose cp postgres:/tmp/_a.sql "$GECICI_A"
docker compose cp postgres:/tmp/_b.sql "$GECICI_B"

cat "$GECICI_A" "$GECICI_B" > "$DOSYA"

rm -f "$GECICI_A" "$GECICI_B"
docker compose exec -T postgres rm -f /tmp/_a.sql /tmp/_b.sql

SAYIM="$(docker compose exec -T postgres psql -U research -d research -t -A \
  -c "select (select count(*) from users) || '|' || (select count(*) from api_keys) || '|' || (select count(*) from telegram_identities)")"

BOYUT="$(du -h "$DOSYA" | cut -f1)"

echo
echo "==> $DOSYA yazildi ($BOYUT)"
echo "    kullanici|anahtar|telegram = $SAYIM"
echo
echo "Windows sunucusuna gonderin:"
echo "  scp $DOSYA PC_8009@10.0.10.223:C:/Users/PC_8009/Desktop/research-platform/"
echo
echo "Dosya parola ve anahtar hashleri icerir. Aktarim bitince buradan silin."
