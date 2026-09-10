from abc import ABC, abstractmethod

import numpy as np


class FrameSource(ABC):
    """Common interface for every camera source type (section 8). A concrete
    implementation owns the actual capture device/file handle and yields real decoded
    frames — nothing downstream cares whether a frame came from a file, a webcam, or an
    RTSP stream."""

    @abstractmethod
    def read(self) -> np.ndarray | None:
        """Returns the next BGR frame, or None if the source is exhausted/unavailable."""

    @abstractmethod
    def release(self) -> None: ...

    @property
    def fps_hint(self) -> float:
        return 15.0
