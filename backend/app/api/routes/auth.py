from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import log_action
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_token,
    verify_password,
)
from app.database import get_db
from app.models.base import ensure_aware
from app.models.session import UserSession
from app.models.user import User
from app.schemas.auth import CurrentUserResponse, LoginRequest, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _issue_tokens(db: Session, user: User, request: Request) -> TokenResponse:
    access_token = create_access_token(user.id, user.tenant_id, user.role.name)
    refresh_token = create_refresh_token(user.id)

    session = UserSession(
        user_id=user.id,
        refresh_token_hash=hash_token(refresh_token),
        device_label=request.headers.get("User-Agent", "")[:255],
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent", "")[:500],
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days),
    )
    db.add(session)
    db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email.lower()).first()

    if user is None or not verify_password(payload.password, user.password_hash):
        log_action(
            db,
            action="LOGIN_FAILED",
            resource_type="user",
            resource_id=payload.email,
            ip_address=_client_ip(request),
            result="FAILURE",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    tokens = _issue_tokens(db, user, request)

    log_action(
        db,
        action="LOGIN_SUCCESS",
        tenant_id=user.tenant_id,
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=_client_ip(request),
    )
    return tokens


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        token_payload = decode_refresh_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    token_hash = hash_token(payload.refresh_token)
    session = db.query(UserSession).filter(UserSession.refresh_token_hash == token_hash).first()

    if session is None or session.revoked or ensure_aware(session.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked")

    import uuid as uuid_module

    user = db.get(User, uuid_module.UUID(token_payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    session.revoked = True
    db.commit()

    return _issue_tokens(db, user, request)


@router.post("/logout")
def logout(payload: RefreshRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    token_hash = hash_token(payload.refresh_token)
    session = db.query(UserSession).filter(
        UserSession.refresh_token_hash == token_hash, UserSession.user_id == user.id
    ).first()
    if session:
        session.revoked = True
        db.commit()
    log_action(db, action="LOGOUT", tenant_id=user.tenant_id, user_id=user.id, resource_type="user", resource_id=str(user.id))
    return {"detail": "Logged out"}


@router.get("/me", response_model=CurrentUserResponse)
def me(user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.name,
        permissions=[p.code for p in user.role.permissions],
    )
