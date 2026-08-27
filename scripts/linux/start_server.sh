#!/usr/bin/env bash
# start_office_server.ps1'in Linux karsiligi.
#
# Windows kurulumunda api/worker/mcp natif surecler olarak calisiyordu ve script
# onlari PID dosyalariyla kovaliyordu. Burada hepsi compose icinde; geriye tek natif
# surec olarak kontrol paneli kaliyor, o da systemd'ye devredildi. Bu yuzden script
# kisa: compose'u saglikli sekilde ayaga kaldir, paneli baslat, uclari dogrula.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

bilgi() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
tamam() { printf '\033[1;32m[ok] %s\033[0m\n' "$*"; }
hata()  { printf '\033[1;31m[!!] %s\033[0m\n' "$*" >&2; }

[[ -f .env ]] || { hata ".env yok. .env.example'dan turetin."; exit 1; }

bilgi "Altyapi container'lari"
docker compose up -d --wait --wait-timeout 300 postgres redis minio crawl4ai

bilgi "Sema"
docker compose run --rm migrate

bilgi "Uygulama servisleri"
# Servisler tek tek sayiliyor, "hepsi" denmiyor: --wait, calisir ya da saglikli hale
# gelmeyen her container'i basarisizlik sayar ve 'migrate' isini bitirince kasten
# cikar. Varsayilan kumede birakilirsa saglikli bir kalkis hata gibi raporlanir.
#
# docling ilk acilista modelleri yukler; healthcheck'inin start_period'u 300 s, bu
# yuzden --wait-timeout onun altinda kalamaz.
docker compose up -d --build --wait --wait-timeout 600     docling agentsearch-adapter api worker mcp-gateway langflow

# telegram-bot bir profilin arkasinda: token yoksa hic baslatilmaz. Bu, panelin
# uyguladigi kuralin aynisi (control_panel.py, _compose_app_services).
if grep -qE '^TELEGRAM_BOT_TOKEN=.+' .env; then
  docker compose --profile telegram up -d telegram-bot
  tamam "telegram-bot baslatildi"
fi

bilgi "SearXNG"
if docker compose -f scripts/linux/searxng/docker-compose.searxng.yml ps --quiet 2>/dev/null | grep -q .; then
  tamam "zaten calisiyor"
else
  docker compose -f scripts/linux/searxng/docker-compose.searxng.yml up -d
fi

bilgi "Kontrol paneli"
if systemctl list-unit-files | grep -q '^research-control-panel.service'; then
  sudo systemctl restart research-control-panel
  tamam "systemd birimi yeniden baslatildi"
else
  hata "research-control-panel.service kurulu degil -- UBUNTU_MIGRATION.md'deki systemd adimi"
fi

# ---------------------------------------------------------------- saglik kontrolu
bekle() {  # bekle <ad> <url> <deneme>
  local ad="$1" url="$2" limit="${3:-30}"
  for ((i = 1; i <= limit; i++)); do
    if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then tamam "$ad"; return 0; fi
    sleep 2
  done
  hata "$ad yanit vermedi: $url"
  return 1
}

bilgi "Uclar"
DURUM=0
bekle "Research API"   "http://127.0.0.1:8000/health"  30 || DURUM=1
bekle "MCP gateway"    "http://127.0.0.1:8010/health"  30 || DURUM=1
bekle "Docling"        "http://127.0.0.1:3941/health"  60 || DURUM=1
bekle "Ollama"         "http://127.0.0.1:11434/api/tags" 10 || DURUM=1
PANEL_PORT="$(grep -E '^CONTROL_PANEL_PORT=' .env | cut -d= -f2 | tr -d '[:space:]')"
bekle "Kontrol paneli" "http://127.0.0.1:${PANEL_PORT:-1111}/health" 20 || DURUM=1

# Redis kuyrugu ayakta olmak yetmez; worker'in kalp atisini birakip birakmadigi
# "kuyruk sagliklı ama hicbir is alinmiyor" durumunu ayirt eden tek sinyal.
bilgi "Worker kuyruk kalp atisi"
TTL="$(docker compose exec -T redis redis-cli TTL arq:queue:health-check 2>/dev/null | tr -d '[:space:]' || echo -2)"
if [[ "$TTL" -gt 0 ]]; then tamam "kalp atisi ttl=${TTL}s"; else hata "worker kalp atisi yok (ttl=$TTL)"; DURUM=1; fi

bilgi "Ozet"
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
LAN_IP="$(hostname -I | awk '{print $1}')"
echo
echo "  MCP (ekip)      http://${LAN_IP}:8010/mcp"
echo "  Panel (ekip)    http://${LAN_IP}:${PANEL_PORT:-1111}"
echo "  API (yerel)     http://127.0.0.1:8000/docs"
exit $DURUM
