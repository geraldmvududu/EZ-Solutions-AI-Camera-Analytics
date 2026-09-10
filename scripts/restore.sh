#!/bin/bash
# Restores a backup created by backup.sh. Usage:
#   ./scripts/restore.sh backups/20260910_020000
# This OVERWRITES the current database — it will ask for confirmation first.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

BACKUP_DIR="${1:?Usage: ./scripts/restore.sh <backup-directory>}"

if [[ ! -f "$BACKUP_DIR/database.sql.gz" ]]; then
    echo "No database.sql.gz found in $BACKUP_DIR" >&2
    exit 1
fi

read -rp "This will REPLACE the current database with the backup in $BACKUP_DIR. Continue? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

source .env

echo "Restoring PostgreSQL database..."
gunzip -c "$BACKUP_DIR/database.sql.gz" | docker compose exec -T postgres psql -U "${POSTGRES_USER:-ezsolutions}" "${POSTGRES_DB:-ez_camera_analytics}"

if [[ -f "$BACKUP_DIR/recordings.tar.gz" ]]; then
    echo "Restoring recordings..."
    tar -xzf "$BACKUP_DIR/recordings.tar.gz" -C data
fi

if [[ -f "$BACKUP_DIR/snapshots.tar.gz" ]]; then
    echo "Restoring snapshots..."
    tar -xzf "$BACKUP_DIR/snapshots.tar.gz" -C data
fi

echo "Restore complete. Restart the backend so it picks up the restored state:"
echo "  docker compose restart backend"
