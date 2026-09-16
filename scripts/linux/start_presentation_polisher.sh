#!/usr/bin/env bash
# Start the authenticated agy/LibreOffice bridge on a Linux host.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
ROOT="$PWD"
PID_FILE="$ROOT/logs/presentation-polisher.pid"
PORT="${PRESENTATION_POLISHER_PORT:-3942}"
RESTART="${1:-}"

env_value() {
  local name="$1" line value
  line="$(grep -E "^${name}=" "$ROOT/.env" 2>/dev/null | tail -n 1 || true)"
  value="${line#*=}"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

# No fallback to SERVICE_TOKEN: the service lets an agent run commands on this host.
TOKEN="$(env_value PRESENTATION_POLISHER_TOKEN)"
[[ -n "$TOKEN" ]] || { echo "PRESENTATION_POLISHER_TOKEN ayarlanmamis (.env); SERVICE_TOKEN yerine gecmez." >&2; exit 1; }
export PRESENTATION_POLISHER_TOKEN="$TOKEN"
for name in PRESENTATION_POLISHER_MAX_BYTES PRESENTATION_POLISHER_MAX_CONCURRENT \
            PRESENTATION_POLISHER_AGY_TIMEOUT_S PRESENTATION_POLISHER_REQUEST_BUDGET_S \
            PRESENTATION_POLISHER_SOFFICE_TIMEOUT_S PRESENTATION_POLISHER_AGY_SANDBOX \
            PRESENTATION_POLISHER_AGY_MODEL PRESENTATION_POLISHER_PROMPT_FILE; do
  value="$(env_value "$name")"
  if [[ -n "$value" ]]; then export "$name=$value"; else unset "$name"; fi
done

mkdir -p "$ROOT/logs"
PYTHON="$ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"

port_pids() {
  ss -ltnp "sport = :$PORT" 2>/dev/null |
    sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | sort -u
}

is_polisher() {
  local pid="$1"
  [[ -r "/proc/$pid/cmdline" ]] && tr '\0' ' ' < "/proc/$pid/cmdline" |
    grep -q 'scripts.presentation_polisher_service:app'
}

if [[ "$RESTART" == "--restart" ]]; then
  targets="$( { [[ -f "$PID_FILE" ]] && cat "$PID_FILE"; port_pids; } | sort -u )"
  while read -r pid; do
    [[ -n "$pid" ]] || continue
    if is_polisher "$pid"; then kill "$pid" 2>/dev/null || true; fi
  done <<< "$targets"
  rm -f "$PID_FILE"
  for _ in {1..20}; do [[ -z "$(port_pids)" ]] && break; sleep 0.25; done
  [[ -z "$(port_pids)" ]] || { echo "Presentation Polisher portu birakilmadi: $PORT" >&2; exit 1; }
fi

owners="$(port_pids)"
if [[ -n "$owners" ]]; then
  while read -r pid; do
    is_polisher "$pid" || { echo "Port $PORT baska bir surec tarafindan kullaniliyor: $pid" >&2; exit 1; }
  done <<< "$owners"
else
  nohup "$PYTHON" -m uvicorn scripts.presentation_polisher_service:app \
    --host 0.0.0.0 --port "$PORT" --no-access-log \
    >> "$ROOT/logs/presentation-polisher.stdout.log" \
    2>> "$ROOT/logs/presentation-polisher.stderr.log" &
fi

for _ in {1..30}; do
  if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null; then break; fi
  sleep 0.5
done
if ! curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null; then
  while read -r pid; do
    [[ -n "$pid" ]] && is_polisher "$pid" && kill "$pid" 2>/dev/null || true
  done <<< "$(port_pids)"
  rm -f "$PID_FILE"
  echo "Presentation Polisher saglik kontrolu basarisiz." >&2
  exit 1
fi
owner="$(port_pids | head -n 1)"
[[ -n "$owner" ]] || { echo "Presentation Polisher port sahibi bulunamadi." >&2; exit 1; }
printf '%s\n' "$owner" > "$PID_FILE"
echo "Presentation Polisher Service: http://127.0.0.1:$PORT"
