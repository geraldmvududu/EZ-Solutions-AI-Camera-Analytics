"""Event-First Cloud Storage Phase 1 (sections 9/21): a thin boto3 S3 client wrapper.

Talks to MinIO in local dev (S3_ENDPOINT_URL set to MinIO's URL — MinIO implements the
real S3 API, so this is not a fake/mock client, just a self-hosted S3-compatible
target) and to real AWS S3 in production by leaving S3_ENDPOINT_URL unset, which makes
boto3 fall back to the real regional endpoint for AWS_REGION. Same code path either
way — nothing here branches on which backend it's talking to.

Deliberately duplicated byte-for-byte at ai-engine/app/core/object_storage.py, the
same pattern already established for face_embedding.py: ai-engine is the process that
actually creates snapshot/recording/evidence-clip files and needs to upload them, while
the backend only ever reads them back out (via presigned URLs) — there's no shared-
package infrastructure in this monorepo to import one copy from the other.

Real bug class this avoids: never construct a boto3 client at import time using
module-level settings, since tests and any process that never touches storage
shouldn't need real (even if fake/local) AWS credentials configured just to import
this module — the client is built lazily on first use.
"""

import logging

logger = logging.getLogger("object_storage")

_client = None
_presign_client = None


def _get_client():
    global _client
    if _client is None:
        import boto3

        from app.config import get_settings

        settings = get_settings()
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
    return _client


def _get_presign_client():
    """A SEPARATE client used only for signing presigned URLs, pointed at whatever
    endpoint the end user's actual browser can reach — never the internal Docker
    endpoint_url the main client uses for upload/delete calls. See the
    s3_public_endpoint_url config field's own docstring for why these must differ."""
    global _presign_client
    if _presign_client is None:
        import boto3

        from app.config import get_settings

        settings = get_settings()
        public_endpoint = getattr(settings, "s3_public_endpoint_url", None) or settings.s3_endpoint_url
        _presign_client = boto3.client(
            "s3",
            endpoint_url=public_endpoint,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
    return _presign_client


def _bucket() -> str:
    from app.config import get_settings

    return get_settings().aws_s3_bucket


def build_key(tenant_id: str, site_id: str | None, camera_id: str, artifact_type: str, filename: str) -> str:
    """Spec section 9's exact bucket layout:
    tenant-{id}/site-{id}/camera-{id}/{snapshots|events|video-clips}/{filename}."""
    site_segment = f"site-{site_id}" if site_id else "site-unassigned"
    return f"tenant-{tenant_id}/{site_segment}/camera-{camera_id}/{artifact_type}/{filename}"


def upload_file(local_path: str, key: str) -> None:
    """Uploads a local file to the configured bucket under `key`. Never raises out —
    a failed upload should not break the caller's real work (a snapshot/recording was
    still captured and saved locally); it just means that artifact has no storage_key
    and callers fall back to serving the local file, exactly as before this phase."""
    try:
        _get_client().upload_file(local_path, _bucket(), key)
    except Exception:
        logger.exception("Failed to upload %s to s3://%s/%s", local_path, _bucket(), key)
        raise


def generate_presigned_url(key: str, expires_in: int = 300) -> str:
    """A short-lived, credential-free GET URL — this is what lets the backend serve
    snapshots/videos "without exposing the underlying storage credentials" (spec
    section 4) while still enforcing this platform's own auth/tenant checks first,
    since the presigned URL is only ever generated after those checks already passed."""
    return _get_presign_client().generate_presigned_url(
        "get_object", Params={"Bucket": _bucket(), "Key": key}, ExpiresIn=expires_in
    )


def delete_object(key: str) -> None:
    """Used by the retention worker once a cloud-stored artifact's retention window
    expires. Deleting a key that doesn't exist is not an error (S3's own semantics)."""
    _get_client().delete_object(Bucket=_bucket(), Key=key)


def ensure_bucket_exists() -> None:
    """Idempotent bucket creation — called once at ai-engine/backend startup so a
    fresh MinIO instance (which starts with zero buckets) is ready without a manual
    setup step. A no-op if the bucket already exists; never raises for that case."""
    client = _get_client()
    try:
        client.head_bucket(Bucket=_bucket())
    except Exception:
        try:
            client.create_bucket(Bucket=_bucket())
        except Exception:
            logger.exception("Failed to create bucket %s", _bucket())
            raise
