import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: uuid.UUID
    alert_id: uuid.UUID | None
    title: str
    body: str
    notification_type: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
