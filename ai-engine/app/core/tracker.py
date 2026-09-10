"""A real (if simple) multi-object tracker: greedy nearest-centroid association across
frames, per section 18/51 ("use a suitable tracking implementation such as ByteTrack or
another maintainable tracker"). Each track gets a persistent integer ID that survives
brief gaps (max_disappeared frames) so "Person #1827 entering/leaving a zone" is a real,
continuous identity rather than a fresh ID every frame.
"""

import math

from app.detectors.base import Detection


class Track:
    def __init__(self, track_id: int, detection: Detection) -> None:
        self.id = track_id
        self.detection = detection
        self.disappeared = 0
        self.history: list[tuple[float, float]] = [self._centroid(detection)]

    @staticmethod
    def _centroid(detection: Detection) -> tuple[float, float]:
        return (detection.x + detection.width / 2, detection.y + detection.height / 2)

    @property
    def centroid(self) -> tuple[float, float]:
        return self.history[-1]

    def update(self, detection: Detection) -> None:
        self.detection = detection
        self.disappeared = 0
        self.history.append(self._centroid(detection))
        if len(self.history) > 50:
            self.history.pop(0)


class CentroidTracker:
    def __init__(self, max_disappeared: int = 15, max_distance: float = 0.15) -> None:
        self._next_id = 1
        self._tracks: dict[int, Track] = {}
        self._max_disappeared = max_disappeared
        self._max_distance = max_distance

    def update(self, detections: list[Detection]) -> dict[int, Detection]:
        """Associates `detections` with existing tracks (or creates new ones), returns
        {track_id: detection} for everything visible this frame."""
        if not detections:
            for track in list(self._tracks.values()):
                track.disappeared += 1
                if track.disappeared > self._max_disappeared:
                    del self._tracks[track.id]
            return {}

        unmatched_detections = list(range(len(detections)))
        matched: dict[int, Detection] = {}

        for track_id, track in list(self._tracks.items()):
            best_idx, best_dist = None, self._max_distance
            for idx in unmatched_detections:
                dist = self._distance(track.centroid, Track._centroid(detections[idx]))
                if dist < best_dist:
                    best_idx, best_dist = idx, dist
            if best_idx is not None:
                track.update(detections[best_idx])
                matched[track_id] = detections[best_idx]
                unmatched_detections.remove(best_idx)
            else:
                track.disappeared += 1
                if track.disappeared > self._max_disappeared:
                    del self._tracks[track_id]

        for idx in unmatched_detections:
            track = Track(self._next_id, detections[idx])
            self._tracks[self._next_id] = track
            matched[self._next_id] = detections[idx]
            self._next_id += 1

        return matched

    @staticmethod
    def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def history_for(self, track_id: int) -> list[tuple[float, float]]:
        track = self._tracks.get(track_id)
        return track.history if track else []
