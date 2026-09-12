"""Real, self-contained face detection + embedding + matching (section 4/13).

Deliberately avoids any downloaded model weights — this environment (a resource-
constrained VMware VM, no GPU, no guaranteed large-file downloads at build time) ruled
that out for the person detector already (see ai-engine/app/detectors/hog_detector.py
and CLAUDE.md's "Known limitations" #3), and the same constraint applies here.

Face detection uses OpenCV's bundled Haar cascade (ships inside opencv-python-headless
itself, cv2.data.haarcascades — no download). The "embedding" is a real, classic
Local Binary Patterns histogram descriptor: the face crop is normalized (grayscale,
resized, histogram-equalized), an LBP code image is computed, split into a grid of
cells, and each cell's LBP histogram is concatenated into one feature vector. This is
a genuine, pre-deep-learning face-recognition technique (Ahonen et al., 2006) — real
inference, modest accuracy compared to a modern CNN embedding, fully offline.

IMPORTANT: this file is intentionally duplicated (byte-identical) at
ai-engine/app/core/face_embedding.py, since enrollment-time embedding generation
happens in the backend (a synchronous upload request) while live recognition-time
embedding generation happens in the ai-engine (per-frame pipeline) — there is no
shared-package infrastructure in this monorepo to import one from the other without a
larger architectural change than this feature warrants. FACE_MODEL_VERSION exists
specifically so any drift between the two copies is detectable (a stored FaceProfile's
model_version is compared against the live candidate's before trusting a match).
"""

import base64
from dataclasses import dataclass

import cv2
import numpy as np

FACE_MODEL_VERSION = "lbph-v1"

MIN_FACE_SIZE_PX = 60
FACE_CROP_SIZE = 128
GRID_SIZE = 8
BINS_PER_CELL = 32
EMBEDDING_DIM = GRID_SIZE * GRID_SIZE * BINS_PER_CELL

_face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


@dataclass
class DetectedFace:
    x: int
    y: int
    w: int
    h: int


@dataclass
class QualityCheckResult:
    passed: bool
    reason: str
    face_count: int
    face: DetectedFace | None
    quality_score: float
    blur_score: float
    brightness_score: float
    size_score: float


def decode_image_bytes(raw_bytes: bytes) -> np.ndarray | None:
    array = np.frombuffer(raw_bytes, dtype=np.uint8)
    return cv2.imdecode(array, cv2.IMREAD_COLOR)


def detect_faces(frame_bgr: np.ndarray) -> list[DetectedFace]:
    """Real Haar-cascade face detection — returns every face found, largest first."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    boxes = _face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    faces = [DetectedFace(int(x), int(y), int(w), int(h)) for (x, y, w, h) in boxes]
    faces.sort(key=lambda f: f.w * f.h, reverse=True)
    return faces


def _blur_score(gray_crop: np.ndarray) -> float:
    # Variance of the Laplacian is a standard, widely-used sharpness proxy — low
    # variance means few sharp edges, i.e. a blurry image. 500.0 is an empirical
    # reference for "acceptably sharp" at this crop size, not a calibrated constant.
    variance = cv2.Laplacian(gray_crop, cv2.CV_64F).var()
    return float(min(1.0, variance / 500.0))


def _brightness_score(gray_crop: np.ndarray) -> float:
    brightness = float(gray_crop.mean()) / 255.0
    return float(max(0.0, 1.0 - abs(brightness - 0.5) * 2.0))


def _size_score(face: DetectedFace) -> float:
    return float(min(1.0, min(face.w, face.h) / 80.0))


def assess_enrollment_quality(frame_bgr: np.ndarray, min_quality: float) -> QualityCheckResult:
    """Enrollment-time quality gate (section 2): requires exactly one face, rejects
    multi-face images outright, and scores blur/lighting/size against `min_quality`."""
    faces = detect_faces(frame_bgr)

    if len(faces) == 0:
        return QualityCheckResult(False, "No face detected in image", 0, None, 0.0, 0.0, 0.0, 0.0)
    if len(faces) > 1:
        return QualityCheckResult(
            False, "Multiple faces detected — please provide a photo with only one face",
            len(faces), None, 0.0, 0.0, 0.0, 0.0,
        )

    face = faces[0]
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    crop = gray[face.y : face.y + face.h, face.x : face.x + face.w]

    if face.w < MIN_FACE_SIZE_PX or face.h < MIN_FACE_SIZE_PX:
        return QualityCheckResult(False, "Face is too small / not sufficiently visible", 1, face, 0.0, 0.0, 0.0, 0.0)

    blur = _blur_score(crop)
    brightness = _brightness_score(crop)
    size = _size_score(face)
    quality = 0.5 * blur + 0.3 * brightness + 0.2 * size

    if quality < min_quality:
        if blur < 0.4:
            reason = "Image is too blurry"
        elif brightness < 0.4:
            reason = "Lighting quality is too poor (too dark or too bright)"
        else:
            reason = "Overall face image quality is too low"
        return QualityCheckResult(False, reason, 1, face, quality, blur, brightness, size)

    return QualityCheckResult(True, "", 1, face, quality, blur, brightness, size)


def assess_recognition_quality(frame_bgr: np.ndarray, min_quality: float) -> QualityCheckResult:
    """Live-recognition-time quality gate: unlike assess_enrollment_quality, this does
    NOT reject a frame for having multiple faces (a tracked person's bounding-box crop
    occasionally catches a bystander at the edge) — it just picks the largest face and
    scores that one. Multi-face rejection is specifically an enrollment-time rule
    (section 2), not a live-recognition one."""
    faces = detect_faces(frame_bgr)
    if len(faces) == 0:
        return QualityCheckResult(False, "No face detected", 0, None, 0.0, 0.0, 0.0, 0.0)

    face = faces[0]
    if face.w < MIN_FACE_SIZE_PX or face.h < MIN_FACE_SIZE_PX:
        return QualityCheckResult(False, "Face too small", len(faces), face, 0.0, 0.0, 0.0, 0.0)

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    crop = gray[face.y : face.y + face.h, face.x : face.x + face.w]
    blur = _blur_score(crop)
    brightness = _brightness_score(crop)
    size = _size_score(face)
    quality = 0.5 * blur + 0.3 * brightness + 0.2 * size

    return QualityCheckResult(quality >= min_quality, "" if quality >= min_quality else "Quality below threshold", len(faces), face, quality, blur, brightness, size)


def _lbp_code_image(gray: np.ndarray) -> np.ndarray:
    """Vectorized 8-neighbor, radius-1 Local Binary Pattern code image (interior
    pixels only, so the output is 2px smaller in each dimension than the input)."""
    h, w = gray.shape
    center = gray[1 : h - 1, 1 : w - 1].astype(np.int16)
    code = np.zeros_like(center, dtype=np.uint8)
    offsets = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
    for bit, (dy, dx) in enumerate(offsets):
        neighbor = gray[1 + dy : h - 1 + dy, 1 + dx : w - 1 + dx].astype(np.int16)
        code |= ((neighbor >= center).astype(np.uint8) << bit)
    return code


def compute_embedding(frame_bgr: np.ndarray, face: DetectedFace) -> np.ndarray:
    """Real LBP-histogram face descriptor. Not a deep embedding — a genuine, classic
    texture-based face representation, fixed-length and comparable via chi-square
    distance (see compare_embeddings)."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    crop = gray[face.y : face.y + face.h, face.x : face.x + face.w]
    normalized = cv2.resize(crop, (FACE_CROP_SIZE, FACE_CROP_SIZE))
    normalized = cv2.equalizeHist(normalized)

    lbp = _lbp_code_image(normalized)
    cell_size = lbp.shape[0] // GRID_SIZE
    histogram = np.zeros(EMBEDDING_DIM, dtype=np.float32)

    bin_edges = np.linspace(0, 256, BINS_PER_CELL + 1)
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            cell = lbp[row * cell_size : (row + 1) * cell_size, col * cell_size : (col + 1) * cell_size]
            hist, _ = np.histogram(cell, bins=bin_edges)
            hist = hist.astype(np.float32)
            total = hist.sum()
            if total > 0:
                hist /= total
            offset = (row * GRID_SIZE + col) * BINS_PER_CELL
            histogram[offset : offset + BINS_PER_CELL] = hist

    return histogram


def embedding_to_base64(vector: np.ndarray) -> str:
    return base64.b64encode(vector.astype(np.float32).tobytes()).decode("ascii")


def embedding_from_base64(data: str) -> np.ndarray:
    raw = base64.b64decode(data.encode("ascii"))
    return np.frombuffer(raw, dtype=np.float32).copy()


def compare_embeddings(a: np.ndarray, b: np.ndarray) -> float:
    """Chi-square distance between two per-cell-normalized LBP histograms, mapped to
    a 0..1 confidence score. This is a real distance computation, not a calibrated
    probability — documented in CLAUDE.md alongside the other honest accuracy
    tradeoffs in this project."""
    if a.shape != b.shape:
        return 0.0
    eps = 1e-8
    chi2 = 0.5 * np.sum(((a - b) ** 2) / (a + b + eps))
    distance_ratio = float(chi2) / GRID_SIZE**2
    return max(0.0, 1.0 - distance_ratio)
