import logging
import os
import time
import uuid
from dataclasses import dataclass

import cv2
import numpy as np

from app.config import get_settings
from app.core import object_storage

settings = get_settings()
logger = logging.getLogger("ai-engine.snapshotter")


@dataclass
class SavedSnapshot:
    file_path: str
    storage_key: str | None
    file_size_bytes: int


def save_snapshot(camera: dict, frame: np.ndarray) -> SavedSnapshot:
    """Writes a real JPEG of `frame` to disk (section 28) and uploads it to MinIO/S3
    (Event-First Cloud Storage Phase 1, section 9) — snapshots always go to cloud
    storage regardless of a camera's recording mode, since they're small and are the
    core "evidence" concept the spec is built around. `storage_key` is None (not a
    failure) if the upload itself failed — the caller still has a real local file to
    fall back to serving, exactly as this worked before this phase."""
    camera_id = camera["id"]
    camera_dir = os.path.join(settings.snapshot_path, camera_id)
    os.makedirs(camera_dir, exist_ok=True)

    filename = f"{int(time.time())}_{uuid.uuid4().hex[:8]}.jpg"
    file_path = os.path.join(camera_dir, filename)
    cv2.imwrite(file_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    file_size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    storage_key = object_storage.build_key(camera.get("tenant_id", ""), camera.get("site_id"), camera_id, "snapshots", filename)
    try:
        object_storage.upload_file(file_path, storage_key)
    except Exception:
        logger.warning("Camera %s: snapshot upload to object storage failed, serving from local disk only", camera_id)
        storage_key = None

    return SavedSnapshot(file_path=file_path, storage_key=storage_key, file_size_bytes=file_size_bytes)
