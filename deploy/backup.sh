#!/usr/bin/env bash
# Respaldo completo: base de datos (pg_dump) + reportes + .env.
# Uso (en la instancia, desde la raiz del repo):  ./deploy/backup.sh [directorio_salida]
# Resultado: backups/auditor_YYYYmmdd_HHMMSS.tar.gz  -> copialo fuera de la instancia (scp).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

STAMP=$(date +%Y%m%d_%H%M%S)
OUT_DIR=${1:-backups}
WORK=$(mktemp -d)
mkdir -p "$OUT_DIR"

echo ">> Volcando base ${POSTGRES_DB:-auditor_contrataciones}..."
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-postgres}" \
  -d "${POSTGRES_DB:-auditor_contrataciones}" -Fc > "$WORK/db.dump"

echo ">> Copiando reportes..."
docker compose exec -T backend tar -C /app/data/reportes -czf - . > "$WORK/reportes.tar.gz"

cp .env "$WORK/env"
git rev-parse HEAD > "$WORK/commit.txt" 2>/dev/null || true

tar -C "$WORK" -czf "$OUT_DIR/auditor_$STAMP.tar.gz" .
rm -rf "$WORK"
echo ">> Listo: $OUT_DIR/auditor_$STAMP.tar.gz"
echo "   (contiene el .env con contrasenas: guardalo en un lugar privado)"
