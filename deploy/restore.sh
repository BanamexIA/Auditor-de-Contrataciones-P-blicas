#!/usr/bin/env bash
# Restaura un respaldo de backup.sh. Pensado para un volumen de base NUEVO (instancia nueva):
# 00-init.sql ya creo los roles, asi pg_restore conserva duenos y permisos tal cual.
# Uso: ./deploy/restore.sh backups/auditor_XXXX.tar.gz
# Si los reportes estaban en S3, define REPORTES_S3_BUCKET en .env con el bucket de la cuenta nueva.
set -euo pipefail
cd "$(dirname "$0")/.."
ARCHIVE=${1:?Uso: restore.sh <respaldo.tar.gz>}
DC="docker compose"; docker info >/dev/null 2>&1 || DC="sudo docker compose"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
tar -C "$WORK" -xzf "$ARCHIVE"

[ -f .env ] || { cp "$WORK/env" .env; echo ">> .env restaurado del respaldo"; }
set -a; . ./.env; set +a
PGU=${POSTGRES_USER:-postgres}; PGD=${POSTGRES_DB:-auditor_contrataciones}

COMMIT=$(cat "$WORK/commit.txt" 2>/dev/null || echo desconocido)
HEAD=$(git rev-parse HEAD 2>/dev/null || echo desconocido)
if [ "$COMMIT" != "$HEAD" ]; then
  echo "!! El respaldo es del commit $COMMIT y el codigo esta en $HEAD."
  echo "   Si hay migraciones nuevas en etl/sql/ desde ese commit, aplicalas despues con psql -f."
fi

echo ">> Levantando base..."
$DC up -d --build db
until $DC exec -T db pg_isready -U "$PGU" -d "$PGD" </dev/null >/dev/null 2>&1; do sleep 2; done
$DC stop backend >/dev/null 2>&1 || true

echo ">> Restaurando base..."
$DC exec -T db pg_restore -U "$PGU" -d "$PGD" --clean --if-exists --exit-on-error < "$WORK/db.dump"

if [ -f "$WORK/s3_bucket.txt" ]; then
  OLD=$(cat "$WORK/s3_bucket.txt")
  NEW=${REPORTES_S3_BUCKET:?Define REPORTES_S3_BUCKET en .env con el bucket de la cuenta nueva}
  echo ">> Subiendo reportes a s3://$NEW/reportes ..."
  aws s3 sync "$WORK/s3/reportes" "s3://$NEW/reportes" --sse AES256 --only-show-errors
  if [ "$OLD" != "$NEW" ]; then
    echo ">> Reescribiendo URIs s3://$OLD/ -> s3://$NEW/ en audit.reportes"
    $DC exec -T db psql -U "$PGU" -d "$PGD" -v ON_ERROR_STOP=1 \
      -c "UPDATE audit.reportes SET uri = replace(uri, 's3://$OLD/', 's3://$NEW/') WHERE uri LIKE 's3://$OLD/%';" </dev/null
  fi
fi

echo ">> Levantando backend y restaurando reportes locales..."
$DC up -d --build backend
until $DC exec -T backend true </dev/null >/dev/null 2>&1; do sleep 2; done
$DC exec -T backend tar -C /app/data/reportes -xzf - < "$WORK/reportes.tar.gz"

echo ">> Restauracion completa (respaldo del commit $COMMIT)."
if [ "${REPORTES_ALMACEN:-local}" = "s3" ]; then
  echo "   Verifica S3: $DC exec backend python -m backend.reportes verificar"
fi
