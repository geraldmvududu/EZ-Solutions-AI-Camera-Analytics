"""Generates a short synthetic MP4 test pattern (moving shape + timestamp) into
videos/sample_test_pattern.mp4, so a VIDEO_FILE camera can be configured and the full
pipeline (capture -> motion detection -> recording -> snapshots) exercised immediately,
without needing internet access or a real camera.

This is NOT a substitute for testing real person/vehicle AI detection (section 8's
primary recommended method) — the shape is synthetic, so the HOG person detector will
correctly find nothing in it, same as app/sources/simulated_source.py in the ai-engine.
For a real person-detection demo, supply your own MP4 of pedestrian footage and point a
VIDEO_FILE camera at it instead.

Usage (from the project root, with the ai-engine's opencv/numpy available):
    python scripts/generate_sample_video.py
"""

import os

import cv2
import numpy as np

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "videos", "sample_test_pattern.mp4")
WIDTH, HEIGHT, FPS, DURATION_SECONDS = 1280, 720, 15, 30


def main() -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(OUTPUT_PATH, fourcc, FPS, (WIDTH, HEIGHT))

    total_frames = FPS * DURATION_SECONDS
    for i in range(total_frames):
        frame = np.full((HEIGHT, WIDTH, 3), (24, 24, 20), dtype=np.uint8)
        t = i / FPS
        x = int((np.sin(t / 4) * 0.4 + 0.5) * (WIDTH - 120))
        cv2.rectangle(frame, (x, 300), (x + 120, 500), (60, 140, 60), -1)
        cv2.putText(frame, f"SAMPLE TEST PATTERN  frame {i}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
        writer.write(frame)

    writer.release()
    print(f"Wrote {total_frames} frames ({DURATION_SECONDS}s) to {os.path.abspath(OUTPUT_PATH)}")


if __name__ == "__main__":
    main()
