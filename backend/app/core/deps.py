import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    user = db.get(User, uuid.UUID(user_id)) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    request.state.current_user = user
    return user


def require_permission(permission: str) -> Callable[[User], User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        role_permission_codes = {p.code for p in user.role.permissions}
        if permission not in role_permission_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )
        return user

    return checker


def require_role(*roles: str) -> Callable[[User], User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role.name not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return checker


def require_internal_service(request: Request) -> None:
    """Authenticates server-to-server calls from the ai-engine (or worker) using a
    shared static token — this is not a user identity, so it never touches JWTs."""
    from app.config import get_settings

    settings = get_settings()
    token = request.headers.get("X-Internal-Token")
    if token != settings.internal_service_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal service token")


def tenant_filter_value(user: User) -> uuid.UUID | None:
    """SUPER_ADMIN can see across tenants (returns None = no filter); every other role
    is confined to their own tenant_id. Every tenant-scoped query MUST use this."""
    if user.role.name == "SUPER_ADMIN":
        return None
    return user.tenant_id
