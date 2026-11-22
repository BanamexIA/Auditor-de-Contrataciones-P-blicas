#!/usr/bin/env bash
# Monta el sistema en una instancia NUEVA (Ubuntu 22.04/24.04 o Amazon Linux 2023).
# Sirve para AWS Academy, la cuenta AWS del cliente o cualquier servidor Linux.
#
#   bash bootstrap.sh                       # instalacion limpia (base vacia; luego corre el ETL)
#   bash bootstrap.sh auditor_XXXX.tar.gz   # instancia nueva a partir de un respaldo
#
# Variables opcionales:
#   REPO_URL, BRANCH, APP_DIR (default /opt/auditor/app)
#   TS_AUTHKEY      clave de Tailscale para unir la instancia al tailnet (inferencia en laptops)
#   TS_HOSTNAME     nombre en el tailnet (default auditor-ec2)    TS_TAGS  p.ej. tag:servidor
#   S3_BUCKET       bucket de reportes en la cuenta nueva (se escribe en REPORTES_S3_BUCKET)
#   LOCAL_OLLAMA=1  instala Ollama en la propia instancia (sin laptops; requiere >= 8 GB RAM)
set -euo pipefail
REPO_URL=${REPO_URL:-https://github.com/BanamexIA/Auditor-de-Contrataciones-P-blicas.git}
BRANCH=${BRANCH:-main}
APP_DIR=${APP_DIR:-/opt/auditor/app}
BACKUP=${1:-}
if [ -n "$BACKUP" ]; then BACKUP=$(realpath "$BACKUP"); fi

echo ">> 1/5 Docker, git, aws CLI"
if command -v apt-get >/dev/null; then
  sudo apt-get update -y && sudo apt-get install -y git curl openssl unzip
else
  sudo dnf install -y git openssl unzip
fi
if ! command -v docker >/dev/null; then
  if command -v apt-get >/dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
  else
    sudo dnf install -y docker
    sudo mkdir -p /usr/local/lib/docker/cli-plugins
    sudo curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
      -o /usr/local/lib/docker/cli-plugins/docker-compose
    sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  fi
  sudo systemctl enable --now docker
  sudo usermod -aG docker "$USER"
fi
if ! command -v aws >/dev/null; then
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o /tmp/awscli.zip
  (cd /tmp && unzip -q -o awscli.zip && sudo ./aws/install)
fi

echo ">> 2/5 Codigo en $APP_DIR"
sudo mkdir -p "$(dirname "$APP_DIR")" && sudo chown "$USER" "$(dirname "$APP_DIR")"
[ -d "$APP_DIR/.git" ] || git clone -b "$BRANCH" "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"
git pull --ff-only || true

echo ">> 3/5 .env"
if [ ! -f .env ]; then
  if [ -n "$BACKUP" ]; then
    tar -xzf "$BACKUP" ./env -O > .env
    echo "   .env tomado del respaldo"
  else
    cp .env.example .env
    for v in POSTGRES_PASSWORD ETL_USER_PASSWORD AGENT_RO_PASSWORD BACKEND_PASSWORD; do
      sed -i "s|^$v=.*|$v=$(openssl rand -hex 16)|" .env
    done
    sed -i "s|^AUTH_SECRET=.*|AUTH_SECRET=$(openssl rand -hex 32)|" .env
    # El ETL (en el host) se conecta como ETL_USER
    sed -i "s|^DB_PASSWORD=.*|DB_PASSWORD=$(grep '^ETL_USER_PASSWORD=' .env | cut -d= -f2)|" .env
    echo "   .env generado con contrasenas y AUTH_SECRET aleatorios"
  fi
fi
if [ -n "${S3_BUCKET:-}" ]; then
  if grep -q '^REPORTES_S3_BUCKET=' .env; then
    sed -i "s|^REPORTES_S3_BUCKET=.*|REPORTES_S3_BUCKET=$S3_BUCKET|" .env
  else
    echo "REPORTES_S3_BUCKET=$S3_BUCKET" >> .env
  fi
fi
set -a; . ./.env; set +a

echo ">> 4/5 Inferencia"
if [ "${LOCAL_OLLAMA:-0}" = "1" ]; then
  command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | sh
  # Para que el contenedor lo alcance via host.docker.internal. NO abras 11434 en el Security Group.
  sudo mkdir -p /etc/systemd/system/ollama.service.d
  printf '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0"\n' | sudo tee /etc/systemd/system/ollama.service.d/host.conf >/dev/null
  sudo systemctl daemon-reload && sudo systemctl restart ollama && sleep 3
  ollama pull "${AGENT_MODEL:-qwen2.5:7b}"
  if [ -n "${OLLAMA_EMBEDDING_MODEL:-}" ]; then ollama pull "$OLLAMA_EMBEDDING_MODEL"; fi
else
  command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sh
  if [ -n "${TS_AUTHKEY:-}" ]; then
    sudo tailscale up --authkey "$TS_AUTHKEY" --hostname "${TS_HOSTNAME:-auditor-ec2}" \
      ${TS_TAGS:+--advertise-tags "$TS_TAGS"}
  else
    echo "   Sin TS_AUTHKEY: corre 'sudo tailscale up --hostname auditor-ec2' y abre el enlace."
  fi
fi

if [ "${REPORTES_ALMACEN:-local}" = "s3" ]; then
  # El contenedor usa el rol de la instancia por IMDSv2: necesita hop limit 2.
  TOKEN=$(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60" || true)
  IID=$(curl -s -m 2 -H "X-aws-ec2-metadata-token: $TOKEN" \
    http://169.254.169.254/latest/meta-data/instance-id || true)
  if [ -n "$IID" ]; then
    aws ec2 modify-instance-metadata-options --instance-id "$IID" --region "${AWS_REGION:-us-east-1}" \
      --http-put-response-hop-limit 2 --http-endpoint enabled >/dev/null \
      || echo "   !! No pude subir el hop limit de IMDS; ver docs/contratos/reportes.md"
  fi
  aws s3api head-bucket --bucket "${REPORTES_S3_BUCKET:-sin-bucket}" >/dev/null 2>&1 \
    || echo "   !! Bucket '${REPORTES_S3_BUCKET:-}' inaccesible: crealo (privado) y asigna LabInstanceProfile a la instancia."
fi

echo ">> 5/5 Stack"
if [ -n "$BACKUP" ]; then
  bash deploy/restore.sh "$BACKUP"
else
  sudo docker compose up -d --build
  echo "   Base vacia: corre el ETL (etl/run_etl.py) para cargar datos y da de alta usuarios."
fi
sudo docker compose ps
echo ">> Listo. Backend en 127.0.0.1:${BACKEND_PORT_HOST:-5000} (tunel: ssh -L 5000:localhost:5000 ...)"
echo "   Laptops: sudo docker compose exec backend python -m backend.agentes listar"
