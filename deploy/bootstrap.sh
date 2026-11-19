#!/usr/bin/env bash
# Monta el sistema en una instancia NUEVA (Ubuntu 22.04/24.04 o Amazon Linux 2023).
# Sirve igual para AWS Academy, una cuenta AWS normal del cliente o cualquier servidor Linux.
#
# Uso:
#   curl -fsSL https://raw.githubusercontent.com/BanamexIA/Auditor-de-Contrataciones-P-blicas/main/deploy/bootstrap.sh | bash
#   # o, con respaldo:  bash bootstrap.sh /ruta/auditor_XXXX.tar.gz
# Variables opcionales: REPO_URL, BRANCH, APP_DIR, AGENT_MODEL, SKIP_OLLAMA=1
set -euo pipefail
REPO_URL=${REPO_URL:-https://github.com/BanamexIA/Auditor-de-Contrataciones-P-blicas.git}
BRANCH=${BRANCH:-main}
APP_DIR=${APP_DIR:-$HOME/auditor}
BACKUP=${1:-}
[ -n "$BACKUP" ] && BACKUP=$(realpath "$BACKUP")

echo ">> 1/5 Docker"
if ! command -v docker >/dev/null; then
  if command -v apt-get >/dev/null; then
    sudo apt-get update -y && sudo apt-get install -y git curl
    curl -fsSL https://get.docker.com | sudo sh
  else
    sudo dnf install -y docker git
    sudo mkdir -p /usr/local/lib/docker/cli-plugins
    sudo curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
      -o /usr/local/lib/docker/cli-plugins/docker-compose
    sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  fi
  sudo systemctl enable --now docker
  sudo usermod -aG docker "$USER"
fi
DOCKER="docker"; docker info >/dev/null 2>&1 || DOCKER="sudo docker"

echo ">> 2/5 Codigo"
[ -d "$APP_DIR/.git" ] || git clone -b "$BRANCH" "$REPO_URL" "$APP_DIR"
cd "$APP_DIR" && git pull --ff-only || true

echo ">> 3/5 .env"
if [ ! -f .env ]; then
  if [ -n "$BACKUP" ]; then
    tar -xzf "$BACKUP" ./env -O > .env
  else
    cp .env.example .env
    for v in POSTGRES_PASSWORD ETL_USER_PASSWORD AGENT_RO_PASSWORD; do
      sed -i "s|^$v=.*|$v=$(openssl rand -hex 16)|" .env
    done
    # El backend se conecta como ETL_USER
    sed -i "s|^DB_PASSWORD=.*|DB_PASSWORD=$(grep ^ETL_USER_PASSWORD= .env | cut -d= -f2)|" .env
    echo "   .env generado con contrasenas aleatorias"
  fi
fi

echo ">> 4/5 Ollama"
if [ "${SKIP_OLLAMA:-0}" != "1" ]; then
  command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | sh
  # Escucha en todas las interfaces para que el contenedor lo alcance via host.docker.internal.
  # NO abras el puerto 11434 en el Security Group.
  sudo mkdir -p /etc/systemd/system/ollama.service.d
  printf '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0"\n' | sudo tee /etc/systemd/system/ollama.service.d/host.conf >/dev/null
  sudo systemctl daemon-reload && sudo systemctl restart ollama
  sleep 3
  set -a; . ./.env; set +a
  ollama pull "${AGENT_MODEL:-qwen2.5:7b}"
  [ -n "${OLLAMA_EMBEDDING_MODEL:-}" ] && ollama pull "$OLLAMA_EMBEDDING_MODEL"
fi

echo ">> 5/5 Stack"
if [ -n "$BACKUP" ]; then
  if [ "$DOCKER" = "docker" ]; then bash deploy/restore.sh "$BACKUP"; else sudo -E bash deploy/restore.sh "$BACKUP"; fi
else
  $DOCKER compose up -d --build
  echo "   Base vacia: corre el ETL (etl/) para cargar datos."
fi
$DOCKER compose ps
echo ">> Listo. Backend en 127.0.0.1:${BACKEND_PORT_HOST:-5000} (usa tunel SSH: ssh -L 5000:localhost:5000 ...)"
