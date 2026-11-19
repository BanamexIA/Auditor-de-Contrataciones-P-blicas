#!/usr/bin/env bash
# Restaura un respaldo hecho con backup.sh sobre un stack ya levantado.
# Uso: ./deploy/restore.sh backups/auditor_XXXX.tar.gz
set -euo pipefail
cd "$(dirname "$0")/.."
ARCHIVE=${1:?Uso: restore.sh <respaldo.tar.gz>}
WORK=$(mktemp -d)
tar -C "$WORK" -xzf "$ARCHIVE"

[ -f .env ] || { cp "$WORK/env" .env; echo ">> .env restaurado del respaldo"; }
set -a; . ./.env; set +a

docker compose up -d --build
echo ">> Esperando a la base..."
until docker compose exec -T db pg_isready -U "${POSTGRES_USER:-postgres}" >/dev/null 2>&1; do sleep 2; done

echo ">> Restaurando base (reemplaza los objetos existentes)..."
docker compose exec -T db pg_restore -U "${POSTGRES_USER:-postgres}" \
  -d "${POSTGRES_DB:-auditor_contrataciones}" --clean --if-exists --no-owner \
  --role="${POSTGRES_USER:-postgres}" < "$WORK/db.dump" || echo "   (avisos de pg_restore: revisa arriba si hubo errores reales)"
# Reaplica permisos de los roles de minimo privilegio por si --no-owner los altero
docker compose exec -T db psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-auditor_contrataciones}" \
  -f /docker-entrypoint-initdb.d/00-init.sql >/dev/null 2>&1 || true

echo ">> Restaurando reportes..."
docker compose exec -T backend tar -C /app/data/reportes -xzf - < "$WORK/reportes.tar.gz"

COMMIT=$(cat "$WORK/commit.txt" 2>/dev/null || echo desconocido); rm -rf "$WORK"
docker compose restart backend
echo ">> Restauracion completa. Commit del respaldo: $COMMIT"
