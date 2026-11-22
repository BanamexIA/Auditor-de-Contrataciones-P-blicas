#!/usr/bin/env bash
# Respaldo completo: base de datos (pg_dump) + reportes (volumen local y, si aplica, S3) + .env.
# Uso (en la instancia, desde la raiz del repo):  ./deploy/backup.sh [directorio_salida]
# Resultado: backups/auditor_YYYYmmdd_HHMMSS.tar.gz  -> copialo fuera de la instancia (scp).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
DC="docker compose"; docker info >/dev/null 2>&1 || DC="sudo docker compose"

STAMP=$(date +%Y%m%d_%H%M%S)
OUT_DIR=${1:-backups}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT_DIR"

echo ">> Volcando base ${POSTGRES_DB:-auditor_contrataciones} (con duenos y permisos)..."
$DC exec -T db pg_dump -U "${POSTGRES_USER:-postgres}" \
  -d "${POSTGRES_DB:-auditor_contrataciones}" -Fc < /dev/null > "$WORK/db.dump"

echo ">> Reportes del volumen local (incluye los local:// anteriores a S3)..."
$DC exec -T backend tar -C /app/data/reportes -czf - . < /dev/null > "$WORK/reportes.tar.gz"

if [ "${REPORTES_ALMACEN:-local}" = "s3" ] && [ -n "${REPORTES_S3_BUCKET:-}" ]; then
  echo ">> Reportes en S3 (s3://$REPORTES_S3_BUCKET/reportes)..."
  command -v aws >/dev/null || { echo "Falta aws CLI en el host"; exit 1; }
  aws s3 sync "s3://$REPORTES_S3_BUCKET/reportes" "$WORK/s3/reportes" --only-show-errors
  echo "$REPORTES_S3_BUCKET" > "$WORK/s3_bucket.txt"
fi

cp .env "$WORK/env"
git rev-parse HEAD > "$WORK/commit.txt" 2>/dev/null || true

tar -C "$WORK" -czf "$OUT_DIR/auditor_$STAMP.tar.gz" .
echo ">> Listo: $OUT_DIR/auditor_$STAMP.tar.gz ($(du -h "$OUT_DIR/auditor_$STAMP.tar.gz" | cut -f1))"
echo "   Contiene el .env con contrasenas y AUTH_SECRET: guardalo en un lugar privado."
