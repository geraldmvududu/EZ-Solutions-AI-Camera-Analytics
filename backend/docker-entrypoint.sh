#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
python - <<'PYEOF'
import time
import sys

from sqlalchemy import create_engine, text
from app.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url)

for attempt in range(30):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database is ready.")
        sys.exit(0)
    except Exception as exc:
        print(f"Database not ready yet (attempt {attempt + 1}/30): {exc}")
        time.sleep(2)

print("Database never became ready — exiting.")
sys.exit(1)
PYEOF

echo "Running database migrations..."
alembic upgrade head

echo "Running bootstrap (idempotent)..."
python -m scripts.bootstrap

echo "Starting application..."
exec "$@"
