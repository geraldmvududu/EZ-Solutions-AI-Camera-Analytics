import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.event import EventSeverity


class AIRuleCreate(BaseModel):
    name: str
    description: str = ""
    is_enabled: bool = True
    conditions: dict
    action_severity: EventSeverity = EventSeverity.MEDIUM
    action_alert_type: str = "RULE_MATCH"
    camera_id: uuid.UUID | None = None


class AIRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_enabled: bool | None = None
    conditions: dict | None = None
    action_severity: EventSeverity | None = None
    action_alert_type: str | None = None
    camera_id: uuid.UUID | None = None


class AIRuleResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str
    is_enabled: bool
    conditions: dict
    action_severity: EventSeverity
    action_alert_type: str
    camera_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
