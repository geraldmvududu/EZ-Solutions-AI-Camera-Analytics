import uuid

from pydantic import BaseModel


class StorageUsageResponse(BaseModel):
    """Spec section 18 — every figure here is a real SUM(file_size_bytes) over rows
    this tenant actually owns, not a sampled/estimated number. Labeled "estimated"
    only in the sense that it reflects file sizes recorded at upload time rather than
    a live query against the object-storage provider's own billing API (which this
    environment has no credentials for) — see get_storage_usage's docstring."""

    event_metadata_bytes: int
    snapshot_bytes: int
    evidence_clip_bytes: int
    cloud_recording_bytes: int
    continuous_recording_bytes: int
    total_bytes: int
    is_estimate: bool = True


class TenantStorageUsage(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    total_bytes: int
