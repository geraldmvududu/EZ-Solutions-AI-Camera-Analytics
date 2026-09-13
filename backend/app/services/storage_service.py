"""Event-First Cloud Storage Phase 1 (section 18): the storage-usage dashboard's
real SUM(file_size_bytes) aggregates, following analytics_service.py's own GROUP BY
convention — nothing here is sampled or precomputed.

Honest caveat, stated plainly rather than glossed over: `event_metadata_bytes` is the
ONE figure that is NOT a real sum of a recorded size — Event rows have no
file_size_bytes column (they're pure metadata, not a stored file), so it's a flat
per-row estimate (`_ESTIMATED_BYTES_PER_EVENT_ROW`, documented below) multiplied by a
real row count. Every other figure (snapshots, evidence clips, cloud/continuous
recordings) is a genuine SUM over real recorded file sizes — see
StorageUsageResponse.is_estimate, always True, since even those miss any AWS-side
overhead (e.g. S3 request/storage-class pricing) this environment has no billing API
access to query."""

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.incident import Incident
from app.models.recording import Recording
from app.models.snapshot import Snapshot
from app.schemas.storage import StorageUsageResponse

# A rough, disclosed average for one Event row's real footprint (JSON metadata +
# indexed columns + row/index overhead) — not measured per-row, since there's no
# stored-file size to sum for a pure-metadata table. Tune this constant, don't treat
# it as precise.
_ESTIMATED_BYTES_PER_EVENT_ROW = 512


def get_storage_usage(db: Session, tenant_id: uuid.UUID | None) -> StorageUsageResponse:
    def scope(query, model):
        return query.filter(model.tenant_id == tenant_id) if tenant_id else query

    event_count = scope(db.query(func.count(Event.id)), Event).scalar() or 0
    event_metadata_bytes = event_count * _ESTIMATED_BYTES_PER_EVENT_ROW

    snapshot_bytes = scope(db.query(func.coalesce(func.sum(Snapshot.file_size_bytes), 0)), Snapshot).scalar() or 0
    evidence_clip_bytes = scope(
        db.query(func.coalesce(func.sum(Incident.evidence_clip_size_bytes), 0)), Incident
    ).scalar() or 0

    cloud_recording_bytes = (
        scope(db.query(func.coalesce(func.sum(Recording.file_size_bytes), 0)), Recording)
        .filter(Recording.storage_key.isnot(None))
        .scalar()
        or 0
    )
    continuous_recording_bytes = (
        scope(db.query(func.coalesce(func.sum(Recording.file_size_bytes), 0)), Recording)
        .filter(Recording.storage_key.is_(None))
        .scalar()
        or 0
    )

    total_bytes = event_metadata_bytes + snapshot_bytes + evidence_clip_bytes + cloud_recording_bytes + continuous_recording_bytes

    return StorageUsageResponse(
        event_metadata_bytes=event_metadata_bytes,
        snapshot_bytes=snapshot_bytes,
        evidence_clip_bytes=evidence_clip_bytes,
        cloud_recording_bytes=cloud_recording_bytes,
        continuous_recording_bytes=continuous_recording_bytes,
        total_bytes=total_bytes,
    )
