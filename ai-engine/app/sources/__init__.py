from urllib.parse import urlparse, urlunparse

from app.backend_client import backend_client
from app.sources.base import FrameSource
from app.sources.opencv_source import OpenCVCaptureSource
from app.sources.simulated_source import SimulatedSource


def _inject_credentials(url: str, username: str, password: str) -> str:
    if not username or "@" in urlparse(url).netloc:
        return url
    parsed = urlparse(url)
    netloc = f"{username}:{password}@{parsed.netloc}" if password else f"{username}@{parsed.netloc}"
    return urlunparse(parsed._replace(netloc=netloc))


def build_source(camera: dict) -> FrameSource:
    source_type = camera["source_type"]

    if source_type == "VIDEO_FILE":
        return OpenCVCaptureSource(camera["video_file_path"], loop=camera.get("loop_video", True))
    if source_type == "WEBCAM":
        return OpenCVCaptureSource(0, loop=False)
    if source_type in ("RTSP", "HTTP_MJPEG", "IP_CAMERA"):
        info = backend_client.get_stream_info(camera["id"])
        if not info or not info.get("stream_url"):
            raise RuntimeError(f"No stream URL available for camera {camera['id']}")
        url = _inject_credentials(info["stream_url"], info.get("username", ""), info.get("password", ""))
        return OpenCVCaptureSource(url, loop=False)
    if source_type == "SIMULATED":
        return SimulatedSource()

    raise ValueError(f"Unknown camera source_type: {source_type}")


__all__ = ["FrameSource", "OpenCVCaptureSource", "SimulatedSource", "build_source"]
