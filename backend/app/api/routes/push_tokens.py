from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.push_token import PushToken
from app.models.user import User
from app.schemas.push_token import PushTokenRegister, PushTokenUnregister

router = APIRouter(prefix="/push-tokens", tags=["push"])


@router.post("", status_code=status.HTTP_201_CREATED)
def register_push_token(
    payload: PushTokenRegister,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    existing = db.query(PushToken).filter(PushToken.user_id == user.id, PushToken.token == payload.token).first()
    if existing:
        return {"detail": "Already registered"}

    db.add(PushToken(tenant_id=user.tenant_id, user_id=user.id, token=payload.token, platform=payload.platform))
    db.commit()
    return {"detail": "Registered"}


@router.delete("")
def unregister_push_token(
    payload: PushTokenUnregister,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    db.query(PushToken).filter(PushToken.user_id == user.id, PushToken.token == payload.token).delete()
    db.commit()
    return {"detail": "Unregistered"}
