#!/usr/bin/env bash
# office_server_status.ps1'in Linux karsiligi. Hicbir sey baslatmaz, yalnizca bakar.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

sor() {  # sor <ad> <url> [jq-yolu]
  local ad="$1" url="$2"
  local cevap
  if cevap="$(curl -fsS --max-time 5 "$url" 2>&1)"; then
    printf '  \033[1;32m%-16s\033[0m %s\n' "$ad" "$(echo "$cevap" | head -c 160)"
  else
    printf '  \033[1;31m%-16s\033[0m erisilemedi\n' "$ad"
  fi
}

PANEL_PORT="$(grep -E '^CONTROL_PANEL_PORT=' .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')"

echo "== Container'lar =="
docker compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'

echo
echo "== SearXNG =="
docker compose -f scripts/linux/searxng/docker-compose.searxng.yml ps \
  --format 'table {{.Service}}\t{{.Status}}' 2>/dev/null || echo "  calismiyor"

echo
echo "== Uclar =="
sor "API"      "http://127.0.0.1:8000/health"
sor "MCP"      "http://127.0.0.1:8010/health"
sor "Docling"  "http://127.0.0.1:3941/health"
sor "Panel"    "http://127.0.0.1:${PANEL_PORT:-1111}/health"
sor "AgentSearch" "http://127.0.0.1:3940/health"
sor "Ollama"   "http://127.0.0.1:11434/api/tags"

echo
echo "== Worker kuyrugu =="
TTL="$(docker compose exec -T redis redis-cli TTL arq:queue:health-check 2>/dev/null | tr -d '[:space:]')"
if [[ "${TTL:--2}" -gt 0 ]]; then
  printf '  \033[1;32m%-16s\033[0m kalp atisi ttl=%ss\n' "heartbeat" "$TTL"
else
  printf '  \033[1;31m%-16s\033[0m yok (ttl=%s) -- worker is almiyor\n' "heartbeat" "${TTL:--2}"
fi

echo
echo "== GPU =="
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader \
    | sed 's/^/  /'
  # Asil soru kartin var olup olmadigi degil, docling'in ONA baglanip baglanamadigi.
  # /health cihazi bildirir; "cpu" yaziyorsa GPU overlay devrede degil demektir.
  printf '  docling cihazi: %s\n' \
    "$(curl -fsS --max-time 5 http://127.0.0.1:3941/health 2>/dev/null || echo 'okunamadi')"
else
  echo "  nvidia-smi yok"
fi

echo
echo "== Kontrol paneli servisi =="
systemctl is-active research-control-panel 2>/dev/null | sed 's/^/  /' || echo "  birim yok"
