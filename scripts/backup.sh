#!/bin/bash
# Backs up PostgreSQL, camera/rule/incident configuration (all in the same DB dump),
# and the .env configuration file. Recordings/snapshots are NOT included by default —
# they're large; pass --with-media to include them. Run from the project root:
#   ./scripts/backup.sh [--with-media]
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

echo "Backing up PostgreSQL database..."
POSTGRES_USER=$(grep -m1 '^POSTGRES_USER=' .env | cut -d= -f2- | tr -d "\"'" || true)
POSTGRES_DB=$(grep -m1 '^POSTGRES_DB=' .env | cut -d= -f2- | tr -d "\"'" || true)
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-ezsolutions}" "${POSTGRES_DB:-ez_camera_analytics}" \
    | gzip > "$BACKUP_DIR/database.sql.gz"

echo "Backing up environment configuration..."
cp .env "$BACKUP_DIR/.env.backup"

if [[ "${1:-}" == "--with-media" ]]; then
    echo "Backing up recordings and snapshots (this may take a while)..."
    tar -czf "$BACKUP_DIR/recordings.tar.gz" -C data recordings
    tar -czf "$BACKUP_DIR/snapshots.tar.gz" -C data snapshots
fi

echo "Backup complete: $BACKUP_DIR"
echo "Nothing was deleted — old backups are kept until you remove them manually."
