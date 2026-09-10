from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    tz: str = "UTC"

    # Database
    database_url: str = "sqlite:///./ez_camera_dev.db"

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

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
