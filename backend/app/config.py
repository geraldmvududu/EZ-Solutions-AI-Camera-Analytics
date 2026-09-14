from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The local-dev SQLite fallback used to be a bare relative path ("./ez_camera_dev.db"),
# which resolves against whatever the CURRENT PROCESS's cwd happens to be — the exact
# same class of bug already fixed once for enrolled-photo storage (see
# scripts/fix_relative_face_paths.py). In practice this project's own tooling
# disagrees on that cwd: the documented dev command is `cd backend && uvicorn ...`
# (cwd = backend/, matching where alembic.ini/versions/ live), but .claude/launch.json
# runs uvicorn with `--app-dir backend` from the repo root instead (cwd = repo root) —
# so the two conventions silently created and grew two DIFFERENT sqlite files, and an
# `alembic upgrade head` run from one cwd never touched the file the other cwd's
# server was actually reading, surfacing as a live "no such column" 500 on every
# request. Anchoring the default to this file's own location makes it invariant to
# whichever cwd launched the process — never used in Docker/production, where
# DATABASE_URL is always set explicitly to the real Postgres URL.
_DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent / "ez_camera_dev.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    tz: str = "UTC"

    # Database
    database_url: str = f"sqlite:///{_DEFAULT_SQLITE_PATH.as_posix()}"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_refresh_secret: str = "dev-only-insecure-refresh-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # Storage
    storage_path: str = "./data"
    recording_path: str = "./data/recordings"
    snapshot_path: str = "./data/snapshots"
    upload_path: str = "./data/uploads"
    ai_model_path: str = "./data/models"

    # AI
    ai_confidence_threshold: float = 0.5
    ai_device: str = "cpu"
    ai_default_fps: int = 5
    ai_model_name: str = "yolov8n"

    # URLs
    api_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    mobile_api_url: str = "http://localhost:8000"

    # Credential encryption (Fernet key, 32 url-safe base64-encoded bytes)
    credential_encryption_key: str = "dev-only-insecure-fernet-key-please-change=="

    # Facial Recognition & Identity Analytics (section 21) — deliberately a separate
    # key from credential_encryption_key above.
    face_recognition_enabled: bool = True
    face_match_threshold: float = 0.85
    face_min_quality: float = 0.70
    face_event_cooldown: int = 30
    face_retention_days: int = 90
    face_image_retention_days: int = 30
    face_embedding_encryption_key: str = "dev-only-insecure-face-fernet-key-please-change=="
    face_model_version: str = "lbph-v1"
    face_path: str = "./data/faces"

    # Bootstrap
    initial_tenant_name: str = "EZ Solutions"
    bootstrap_admin_email: str = "admin@ezsolutions.local"
    bootstrap_admin_password: str = "change_me_on_first_login"

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Internal service auth (used by ai-engine -> backend calls)
    internal_service_token: str = "dev-only-internal-service-token"

    # ai-engine's MJPEG live-view server (backend proxies it — see api/routes/cameras.py)
    ai_engine_stream_url: str = "http://localhost:8090"

    # Event-First Cloud Storage Phase 1 (sections 9/29) — object storage for
    # snapshots/evidence clips/non-continuous recordings. s3_endpoint_url points at
    # MinIO locally (S3-API-compatible); leave it unset in real AWS to use the real
    # regional S3 endpoint via aws_region instead. See app/services/object_storage.py.
    s3_endpoint_url: str | None = None
    # Real bug avoided: s3_endpoint_url is Docker's internal "http://minio:9000" —
    # only reachable from OTHER containers, never from the end user's actual browser.
    # A presigned URL signed against that host would 404/fail to resolve for every
    # real viewer. s3_public_endpoint_url is the address a browser can actually reach
    # (MinIO's port published to the host in docker-compose.yml, same deliberate
    # lab-only exception already made for the backend's own port 8000) and is used
    # ONLY when generating presigned URLs — never for the internal upload/delete
    # calls, which keep using s3_endpoint_url. In real AWS, leave both unset: S3's
    # public regional endpoint is reachable from everywhere, so there's nothing to
    # split.
    s3_public_endpoint_url: str | None = None
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    aws_region: str = "us-east-1"
    aws_s3_bucket: str = "ez-camera-evidence"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
