import uuid

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def log_action(
    db: Session,
    *,
    action: str,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    resource_type: str = "",
    resource_id: str = "",
    ip_address: str = "",
    result: str = "SUCCESS",
    details: dict | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        result=result,
        details=details or {},
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry
