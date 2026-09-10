from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_url: str = "http://localhost:8000"
    internal_service_token: str = "dev-only-internal-service-token"

    recording_path: str = "./data/recordings"
    snapshot_path: str = "./data/snapshots"

    ai_device: str = "cpu"
    ai_confidence_threshold: float = 0.5

    # MJPEG live-view server (section 13/38) — only reachable inside the docker
    # network; the backend proxies it to authenticated dashboard/mobile clients.
    stream_port: int = 8090
    stream_fps: int = 12
    stream_jpeg_quality: int = 70

    # How often (seconds) to poll the backend for the current active-camera list.
    camera_discovery_interval_seconds: int = 15
    camera_heartbeat_interval_seconds: int = 10

    # How long (seconds) a tracked object must remain inside a LOITERING zone before
    # the default threshold applies if the zone doesn't specify its own.
    default_loitering_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
