"""Shared test fixtures for the whole ai-engine test suite.

Real bug avoided: without this, every test that exercises save_snapshot/
SegmentRecorder (most of the worker/theft-detection/face-recognizer suites) would
make a REAL network call to AWS's default S3 endpoint via boto3 — object_storage's
client has no endpoint_url configured in the test environment, so it falls back to
real AWS, which is slow (a real TLS handshake + a 403 from invalid test credentials)
and makes test runtime depend on network access this sandbox may not reliably have.
Mocking object_storage at the boundary for every test by default matches this
project's own established convention for other slow/external dependencies (e.g. the
ffmpeg subprocess mocking in test_recorder.py) — a real MinIO integration is verified
manually in the browser walkthrough, not on every test run.
"""

import pytest

from app.core import object_storage


@pytest.fixture(autouse=True)
def _mock_object_storage(monkeypatch):
    monkeypatch.setattr(object_storage, "upload_file", lambda local_path, key: None)
    monkeypatch.setattr(object_storage, "delete_object", lambda key: None)
    monkeypatch.setattr(object_storage, "generate_presigned_url", lambda key, expires_in=300: f"https://fake-presigned/{key}")
