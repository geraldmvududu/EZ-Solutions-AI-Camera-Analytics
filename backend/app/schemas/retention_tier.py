import uuid

from pydantic import BaseModel


class RetentionTierResponse(BaseModel):
    id: uuid.UUID
    name: str
    event_metadata_days: int
    snapshot_days: int
    video_evidence_days: int

    model_config = {"from_attributes": True}


class RetentionTierUpdate(BaseModel):
    """Platform Administrator only (spec section 10: "must be configurable by the
    platform administrator. Do not hard-code retention periods.") — every field is
    optional so a PUT can adjust just one day-count without resending the others."""

    event_metadata_days: int | None = None
    snapshot_days: int | None = None
    video_evidence_days: int | None = None


class TenantRetentionTierAssign(BaseModel):
    retention_tier_id: uuid.UUID
