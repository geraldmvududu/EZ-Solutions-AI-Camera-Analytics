"""Real tests for app/services/object_storage.py (Event-First Cloud Storage Phase 1,
sections 9/21) — the boto3 S3 client wrapper. The real network call itself is mocked
at the boto3.client() boundary (same rationale as this project's existing ffmpeg-
subprocess mocking, and mirrors ai-engine/tests/test_object_storage.py exactly);
everything above that boundary (key construction, endpoint/credential selection,
bucket naming, and — the one thing genuinely unique to the backend's copy — the
internal-vs-public presigned-URL client split) is real and unmocked.

conftest.py's session-wide autouse `_mock_object_storage` fixture replaces
upload_file/delete_object/generate_presigned_url on the module for every OTHER test
file in this suite, so they never hit the network. This file needs the real
implementations, so it captures direct references to them at import time — before
that fixture's per-test monkeypatch.setattr call ever runs.
"""

import pytest

from app.services import object_storage

_real_upload_file = object_storage.upload_file
_real_delete_object = object_storage.delete_object
_real_generate_presigned_url = object_storage.generate_presigned_url


@pytest.fixture(autouse=True)
def _reset_clients():
    object_storage._client = None
    object_storage._presign_client = None
    yield
    object_storage._client = None
    object_storage._presign_client = None


class _FakeBotoClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []

    def upload_file(self, local_path, bucket, key):
        self.calls.append(("upload_file", local_path, bucket, key))

    def delete_object(self, Bucket, Key):
        self.calls.append(("delete_object", Bucket, Key))

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.calls.append(("generate_presigned_url", operation, Params, ExpiresIn))
        return f"https://fake-presigned.example/{Params['Bucket']}/{Params['Key']}?expires={ExpiresIn}"

    def head_bucket(self, Bucket):
        raise Exception("bucket does not exist")

    def create_bucket(self, Bucket):
        self.calls.append(("create_bucket", Bucket))


def _patch_boto_client(monkeypatch, capture: dict):
    import boto3

    def fake_client(service_name, **kwargs):
        capture["kwargs"] = kwargs
        client = _FakeBotoClient(**kwargs)
        capture.setdefault("clients", []).append(client)
        return client

    monkeypatch.setattr(boto3, "client", fake_client)


def test_build_key_matches_spec_layout():
    key = object_storage.build_key("t1", "s2", "c3", "snapshots", "photo.jpg")
    assert key == "tenant-t1/site-s2/camera-c3/snapshots/photo.jpg"


def test_build_key_uses_unassigned_when_no_site():
    key = object_storage.build_key("t1", None, "c3", "video-clips", "clip.mp4")
    assert key == "tenant-t1/site-unassigned/camera-c3/video-clips/clip.mp4"


def test_internal_client_uses_internal_endpoint(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testkey")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    capture: dict = {}
    _patch_boto_client(monkeypatch, capture)

    object_storage._get_client()

    assert capture["kwargs"]["endpoint_url"] == "http://minio:9000"
    assert capture["kwargs"]["aws_access_key_id"] == "testkey"
    assert capture["kwargs"]["region_name"] == "us-west-2"
    get_settings.cache_clear()


def test_presign_client_uses_public_endpoint_not_internal(monkeypatch):
    """The real architectural bug this session caught: a presigned URL signed against
    the internal Docker hostname would be unreachable from an end-user's browser. The
    presign client must use s3_public_endpoint_url, never s3_endpoint_url."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT_URL", "http://localhost:9000")
    capture: dict = {}
    _patch_boto_client(monkeypatch, capture)

    object_storage._get_presign_client()

    assert capture["kwargs"]["endpoint_url"] == "http://localhost:9000"
    get_settings.cache_clear()


def test_presign_client_falls_back_to_internal_endpoint_when_public_unset(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT_URL", raising=False)
    capture: dict = {}
    _patch_boto_client(monkeypatch, capture)

    object_storage._get_presign_client()

    assert capture["kwargs"]["endpoint_url"] == "http://minio:9000"
    get_settings.cache_clear()


def test_internal_and_presign_clients_are_independent(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT_URL", "http://localhost:9000")
    capture: dict = {}
    _patch_boto_client(monkeypatch, capture)

    internal = object_storage._get_client()
    presign = object_storage._get_presign_client()

    assert internal is not presign
    assert len(capture["clients"]) == 2
    get_settings.cache_clear()


def test_upload_file_calls_client_with_local_path_bucket_and_key(monkeypatch):
    capture: dict = {}
    _patch_boto_client(monkeypatch, capture)

    _real_upload_file("/tmp/snap.jpg", "tenant-1/site-1/camera-1/snapshots/snap.jpg")

    client = capture["clients"][0]
    assert client.calls == [("upload_file", "/tmp/snap.jpg", object_storage._bucket(), "tenant-1/site-1/camera-1/snapshots/snap.jpg")]


def test_upload_file_reraises_after_logging_so_caller_can_fall_back(monkeypatch):
    def failing_client(service_name, **kwargs):
        class _Failing:
            def upload_file(self, *a, **kw):
                raise ConnectionError("no route to host")

        return _Failing()

    import boto3

    monkeypatch.setattr(boto3, "client", failing_client)

    with pytest.raises(ConnectionError):
        _real_upload_file("/tmp/snap.jpg", "some/key.jpg")


def test_delete_object_targets_configured_bucket(monkeypatch):
    capture: dict = {}
    _patch_boto_client(monkeypatch, capture)

    _real_delete_object("tenant-1/site-1/camera-1/snapshots/old.jpg")

    client = capture["clients"][0]
    assert client.calls == [("delete_object", object_storage._bucket(), "tenant-1/site-1/camera-1/snapshots/old.jpg")]


def test_generate_presigned_url_uses_the_presign_client(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT_URL", "http://localhost:9000")
    capture: dict = {}
    _patch_boto_client(monkeypatch, capture)

    url = _real_generate_presigned_url("tenant-1/site-1/camera-1/snapshots/photo.jpg", expires_in=120)

    assert capture["kwargs"]["endpoint_url"] == "http://localhost:9000"
    assert "expires=120" in url
    get_settings.cache_clear()


def test_generate_presigned_url_passes_bucket_key_and_expiry(monkeypatch):
    capture: dict = {}
    _patch_boto_client(monkeypatch, capture)

    _real_generate_presigned_url("tenant-1/site-1/camera-1/snapshots/photo.jpg", expires_in=600)

    client = capture["clients"][0]
    assert client.calls == [
        ("generate_presigned_url", "get_object", {"Bucket": object_storage._bucket(), "Key": "tenant-1/site-1/camera-1/snapshots/photo.jpg"}, 600)
    ]


def test_ensure_bucket_exists_creates_bucket_when_missing(monkeypatch):
    capture: dict = {}
    _patch_boto_client(monkeypatch, capture)

    object_storage.ensure_bucket_exists()

    client = capture["clients"][0]
    assert ("create_bucket", object_storage._bucket()) in client.calls


def test_ensure_bucket_exists_is_a_noop_when_bucket_already_exists(monkeypatch):
    class _AlreadyExistsClient(_FakeBotoClient):
        def head_bucket(self, Bucket):
            self.calls.append(("head_bucket", Bucket))
            return {}

    captured_client = {}

    def fake_client(service_name, **kwargs):
        client = _AlreadyExistsClient(**kwargs)
        captured_client["client"] = client
        return client

    import boto3

    monkeypatch.setattr(boto3, "client", fake_client)

    object_storage.ensure_bucket_exists()

    assert ("head_bucket", object_storage._bucket()) in captured_client["client"].calls
    assert not any(call[0] == "create_bucket" for call in captured_client["client"].calls)
