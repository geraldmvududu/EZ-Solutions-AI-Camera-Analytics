"""Turns a real Alert into real Notification rows (in-app feed) and a real push
notification (section 39) — sent to every active user in the alert's tenant who holds
the manage_alerts permission (operators/admins/super-admins), not viewers.
"""

from sqlalchemy.orm import Session

from app.core.permissions import Permissions
from app.models.alert import Alert
from app.models.camera import Camera
from app.models.event import EventSeverity
from app.models.notification import Notification
from app.models.push_token import PushToken
from app.models.user import Role, User
from app.services.push_service import send_push_notifications

_PUSH_WORTHY_SEVERITIES = {EventSeverity.HIGH, EventSeverity.CRITICAL}


def notify_users_of_alert(db: Session, alert: Alert, camera: Camera) -> None:
    recipients = (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(User.tenant_id == alert.tenant_id, User.is_active.is_(True))
        .all()
    )
    recipients = [u for u in recipients if Permissions.MANAGE_ALERTS in {p.code for p in u.role.permissions}]
    if not recipients:
        return

    title = f"{alert.severity.value} Alert: {alert.alert_type.replace('_', ' ').title()}"
    body = f"{camera.name} — {alert.severity.value.title()} severity"

    for user in recipients:
        db.add(Notification(
            tenant_id=alert.tenant_id,
            user_id=user.id,
            alert_id=alert.id,
            title=title,
            body=body,
            notification_type="ALERT",
        ))
    db.commit()

    if alert.severity not in _PUSH_WORTHY_SEVERITIES:
        return

    recipient_ids = [u.id for u in recipients]
    tokens = [
        row[0]
        for row in db.query(PushToken.token).filter(PushToken.user_id.in_(recipient_ids)).all()
    ]
    if tokens:
        send_push_notifications(tokens, title, body, data={"alert_id": str(alert.id), "camera_id": str(camera.id)})
