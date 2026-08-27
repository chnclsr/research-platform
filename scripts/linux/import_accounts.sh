#!/usr/bin/env bash
# export_accounts.ps1'in urettigi accounts.sql dosyasini yeni sunucuya yukler.
# Ubuntu sunucuda, proje kokunde calisir:
#
#   ./scripts/linux/import_accounts.sh accounts.sql
#
# Onkosul: 'docker compose up -d' ile postgres ayakta ve 'migrate' servisi
# alembic upgrade head'i tamamlamis olmali (tablolar var, icleri bos).
set -euo pipefail

DOSYA="${1:-accounts.sql}"
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

[[ -f "$DOSYA" ]] || { echo "Dosya bulunamadi: $DOSYA" >&2; exit 1; }

echo "==> Hedef veritabani kontrol ediliyor"
MEVCUT="$(docker compose exec -T postgres psql -U research -d research -t -A \
    -c "select count(*) from users" 2>/dev/null || echo "HATA")"

if [[ "$MEVCUT" == "HATA" ]]; then
  echo "users tablosu okunamadi. Once semayi olusturun:" >&2
  echo "  docker compose run --rm migrate" >&2
  exit 1
fi

if [[ "$MEVCUT" != "0" ]]; then
  # Ustune yazmak birincil anahtar catismasi verir ve islem geri alinir; yine de
  # kullaniciyi bilincli bir karara zorlamak, yarim yuklenmis bir hesap tablosundan iyi.
  echo "Hedefte zaten $MEVCUT kullanici var. Bu script yalnizca bos bir hesap" >&2
  echo "tablosuna yukler. Sifirlamak icin:" >&2
  echo "  docker compose exec -T postgres psql -U research -d research \\" >&2
  echo "    -c 'truncate telegram_identities, api_keys, users cascade'" >&2
  exit 1
fi

echo "==> Yukleniyor: $DOSYA"
docker compose cp "$DOSYA" postgres:/tmp/accounts.sql
# --single-transaction: dokum artik BEGIN/COMMIT tasimiyor (export tarafinda
# PowerShell tirnak yutmasi yuzunden kaldirildi). Yarim yuklenmis bir hesap
# tablosuna dusmemek icin butunluk burada saglaniyor.
docker compose exec -T postgres psql -U research -d research \n  --single-transaction -v ON_ERROR_STOP=1 -f /tmp/accounts.sql
docker compose exec -T postgres rm -f /tmp/accounts.sql

echo "==> Sonuc"
docker compose exec -T postgres psql -U research -d research -c \
  "select email, role, is_active, (select count(*) from api_keys k where k.user_id = u.id and k.revoked_at is null) as aktif_anahtar from users u order by email"

echo
echo "Parolalar ve dagitilmis rp_ anahtarlari degismedi -- kimsenin yeni anahtar almasi"
echo "gerekmiyor. Yalnizca panel oturumlari dustu, herkes bir kez yeniden giris yapar."
