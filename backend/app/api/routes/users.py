import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.deps import get_current_user, require_permission, tenant_filter_value
from app.core.permissions import Permissions, ROLE_PERMISSION_MAP
from app.core.security import hash_password
from app.database import get_db
from app.models.user import Role, User
from app.schemas.user import UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.MANAGE_USERS)),
) -> list[User]:
    query = db.query(User)
    tenant_id = tenant_filter_value(current_user)
    if tenant_id:
        query = query.filter(User.tenant_id == tenant_id)
    return query.order_by(User.created_at.desc()).all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.MANAGE_USERS)),
) -> User:
    if payload.role not in ROLE_PERMISSION_MAP:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown role: {payload.role}")

    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    role = db.query(Role).filter(Role.name == payload.role).first()
    if role is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role not found — has the DB been seeded?")

    user = User(
        tenant_id=current_user.tenant_id,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role_id=role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(
        db,
        action="USER_CREATED",
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=request.client.host if request.client else "",
        details={"email": user.email, "role": payload.role},
    )
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.MANAGE_USERS)),
) -> User:
    user = db.get(User, user_id)
    tenant_id = tenant_filter_value(current_user)
    if user is None or (tenant_id and user.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.role is not None:
        if payload.role not in ROLE_PERMISSION_MAP:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown role: {payload.role}")
        role = db.query(Role).filter(Role.name == payload.role).first()
        user.role_id = role.id

    db.commit()
    db.refresh(user)

    log_action(
        db,
        action="USER_UPDATED",
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=request.client.host if request.client else "",
        details=payload.model_dump(exclude_unset=True, exclude={"password"}),
    )
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.MANAGE_USERS)),
) -> None:
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")

    user = db.get(User, user_id)
    tenant_id = tenant_filter_value(current_user)
    if user is None or (tenant_id and user.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    db.delete(user)
    db.commit()

    log_action(
        db,
        action="USER_DELETED",
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(user_id),
        ip_address=request.client.host if request.client else "",
    )
