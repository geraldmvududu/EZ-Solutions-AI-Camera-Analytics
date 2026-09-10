import os
import time
import uuid

import cv2
import numpy as np

from app.config import get_settings

settings = get_settings()


def save_snapshot(camera_id: str, frame: np.ndarray) -> str:
    """Writes a real JPEG of `frame` to disk and returns its path (section 28)."""
    camera_dir = os.path.join(settings.snapshot_path, camera_id)
    os.makedirs(camera_dir, exist_ok=True)

    filename = f"{int(time.time())}_{uuid.uuid4().hex[:8]}.jpg"
    file_path = os.path.join(camera_dir, filename)
    cv2.imwrite(file_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return file_path
