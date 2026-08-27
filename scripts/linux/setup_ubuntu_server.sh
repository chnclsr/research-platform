#!/usr/bin/env bash
# Research Platform -- Ubuntu sunucu on hazirligi.
#
# Compose yigininin ihtiyac duydugu ama compose'un ICINDE OLMAYAN her seyi kurar:
# Docker Engine, NVIDIA container runtime, host uzerinde Ollama, ve modeller.
# Idempotenttir: kurulu olani atlar, ikinci kez calistirmak zarar vermez.
#
#   ./scripts/linux/setup_ubuntu_server.sh 192.168.1.0/24
#
# Tek argüman ofis LAN'inin CIDR'i. Verilmezse guvenlik duvari adimi atlanir.
set -euo pipefail

LAN_CIDR="${1:-}"
KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

bilgi()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
uyari()  { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
tamam()  { printf '\033[1;32m[ok] %s\033[0m\n' "$*"; }

if [[ $EUID -eq 0 ]]; then
  echo "Bu scripti root olarak degil, sudo yetkisi olan normal kullaniciyla calistirin." >&2
  exit 1
fi

# --------------------------------------------------------------- Docker Engine
bilgi "Docker Engine ve compose eklentisi"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  tamam "Docker zaten kurulu: $(docker --version)"
else
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
  fi
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
      docker-buildx-plugin docker-compose-plugin
  tamam "Docker kuruldu"
fi

if ! id -nG "$USER" | tr ' ' '\n' | grep -qx docker; then
  sudo usermod -aG docker "$USER"
  uyari "Kullanici 'docker' grubuna eklendi. Grubun gecerli olmasi icin OTURUMU KAPATIP ACIN"
  uyari "(veya 'newgrp docker'). Aksi halde bundan sonraki docker komutlari izin hatasi verir."
fi

# ------------------------------------------------------- NVIDIA container araclari
bilgi "NVIDIA GPU destegi"
if ! command -v nvidia-smi >/dev/null 2>&1; then
  uyari "nvidia-smi bulunamadi. Once NVIDIA surucusunu kurun:"
  uyari "  sudo ubuntu-drivers install"
  uyari "  sudo reboot"
  uyari "Surucu kurulup makine yeniden baslatildiktan sonra bu scripti tekrar calistirin."
else
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
  if ! dpkg -s nvidia-container-toolkit >/dev/null 2>&1; then
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
      | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
      | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
      | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
    sudo apt-get update
    sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    tamam "nvidia-container-toolkit kuruldu ve docker runtime'i yapilandirildi"
  else
    tamam "nvidia-container-toolkit zaten kurulu"
  fi

  # docling imajinin hangi torch tekerlegiyle derlenecegini surucu belirler.
  # Yanlis secim container'i "no CUDA device" ile dusurur -- docling bunu kasten
  # yapar, cunku CPU ve GPU ciktisi ayni degil ve content_hash o metnin sha256'si.
  CUDA_SURUM="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1 | cut -d. -f1)"
  if   [[ "$CUDA_SURUM" -ge 580 ]]; then ONERI="cu132"
  elif [[ "$CUDA_SURUM" -ge 570 ]]; then ONERI="cu128"
  elif [[ "$CUDA_SURUM" -ge 525 ]]; then ONERI="cu126"
  else ONERI="cpu"; fi
  bilgi "Surucu ana surumu $CUDA_SURUM -> .env icine su satiri yazin: TORCH_VARIANT=$ONERI"
fi

# ------------------------------------------------------------------------ Ollama
bilgi "Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
  tamam "Ollama kuruldu"
else
  tamam "Ollama zaten kurulu: $(ollama --version 2>/dev/null | head -1)"
fi

# LINUX'A OZGU VE ATLANMASI KOLAY: Ollama varsayilan olarak 127.0.0.1'e baglanir.
# Windows'ta Docker Desktop'in host.docker.internal'i bunu yine de bulurdu; Linux'ta
# host-gateway docker koprusunun IP'sine cozulur ve loopback'e bagli Ollama'ya
# container'lardan ERISILEMEZ. Worker sessizce her LLM cagrisinda hata alir.
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<'OLLAMA_EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
# Modeller bellekte kalsin: her kosunun ilk cagrisinda yeniden yuklemek
# arastirma boru hattinin en pahali sessiz gecikmesi.
Environment="OLLAMA_KEEP_ALIVE=30m"
OLLAMA_EOF
sudo systemctl daemon-reload
sudo systemctl enable --now ollama
sudo systemctl restart ollama
tamam "Ollama 0.0.0.0:11434 uzerinde (guvenlik duvari disariya kapatir)"

bilgi "Modeller indiriliyor (ilk seferde uzun surer)"
for model in "qwen3:4b-instruct-2507-q4_K_M" "embeddinggemma:300m-qat-q4_0" "qwen3.5:4b"; do
  if ollama list 2>/dev/null | grep -q "^${model%%:*}"; then
    tamam "$model zaten var"
  else
    ollama pull "$model"
  fi
done

# --------------------------------------------------------------- Guvenlik duvari
if [[ -n "$LAN_CIDR" ]]; then
  bilgi "Guvenlik duvari ($LAN_CIDR)"
  sudo apt-get install -y ufw
  sudo ufw allow 22/tcp comment 'ssh'
  sudo ufw allow from "$LAN_CIDR" to any port 1111 proto tcp comment 'research control panel'
  sudo ufw --force enable
  sudo ufw status verbose
  uyari "DIKKAT: docker'in yayinladigi portlar (MCP 8010) ufw'yi ATLAR."
  uyari "MCP'yi LAN ile sinirlamak icin .env icinde MCP_BIND_HOST'u sunucunun LAN IP'sine"
  uyari "sabitleyin ya da DOCKER-USER zincirine kural yazin -- UBUNTU_MIGRATION.md'ye bakin."
else
  uyari "LAN CIDR verilmedi, guvenlik duvari adimi atlandi."
fi

bilgi "Hazir. Sirada: .env olusturma ve 'docker compose up -d --build'"
echo "Proje kokü: $KOK"
