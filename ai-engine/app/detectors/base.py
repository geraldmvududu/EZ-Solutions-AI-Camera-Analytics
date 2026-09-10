from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class Detection:
    object_type: str  # PERSON, CAR, TRUCK, BUS, MOTORCYCLE, BICYCLE, ANIMAL, BACKPACK, BAG, SUITCASE
    confidence: float
    # Normalized 0-1 bounding box relative to frame width/height.
    x: float
    y: float
    width: float
    height: float


class Detector(ABC):
    """Real object-detection interface (section 51's AIEngine.detect()/classify()).
    Every implementation must return actual inference results for the given frame —
    never synthetic/random detections."""

    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[Detection]: ...
