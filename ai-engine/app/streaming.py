"""Real live-view streaming (sections 13/38 — camera wall, mobile camera view). Each
CameraWorker publishes its most recently captured frame (with real bounding-box
overlays drawn from actual tracked detections) here; this module serves those frames
as MJPEG-over-HTTP. It does not run inside the main FastAPI-style request loop of any
other service — it's a small standalone HTTP server on its own port, reachable only
from the backend container over the docker-internal network (never exposed publicly;
nginx never routes to it directly).
"""

import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger("ai-engine.streaming")

_BOUNDARY = "ezframe"
_lock = threading.Lock()
_latest_frames: dict[str, bytes] = {}


def publish_frame(camera_id: str, jpeg_bytes: bytes) -> None:
    with _lock:
        _latest_frames[camera_id] = jpeg_bytes


def clear_frame(camera_id: str) -> None:
    with _lock:
        _latest_frames.pop(camera_id, None)


def _get_frame(camera_id: str) -> bytes | None:
    with _lock:
        return _latest_frames.get(camera_id)


class _MJPEGHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        pass  # silence per-request access logging; ai-engine's own logger covers events

    def do_GET(self) -> None:
        parts = self.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "stream":
            self.send_response(404)
            self.end_headers()
            return
        camera_id = parts[1]

        self.send_response(200)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={_BOUNDARY}")
        self.end_headers()

        try:
            while True:
                frame = _get_frame(camera_id)
                if frame is not None:
                    self.wfile.write(f"--{_BOUNDARY}\r\n".encode())
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                time.sleep(1 / 15)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client disconnected — normal when a viewer closes the page


def start_stream_server(port: int) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), _MJPEGHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="mjpeg-stream-server")
    thread.start()
    logger.info("MJPEG stream server listening on :%d", port)
