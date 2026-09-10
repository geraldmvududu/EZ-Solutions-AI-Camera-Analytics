"""Idempotent bootstrap: seeds permissions, the four system roles, the initial tenant,
and the first Super Admin account. Safe to run repeatedly (used at container startup
and documented in the README as `python -m scripts.bootstrap`)."""

import re
import sys

from app.config import get_settings
from app.core.permissions import Permissions, ROLE_PERMISSION_MAP
from app.core.security import hash_password
from app.database import SessionLocal
from app.models.tenant import Tenant
from app.models.user import Permission, Role, User

settings = get_settings()


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def run() -> None:
    db = SessionLocal()
    try:
        permission_rows: dict[str, Permission] = {}
        for code in Permissions.all():
            perm = db.query(Permission).filter(Permission.code == code).first()
            if perm is None:
                perm = Permission(code=code, description=code.replace("_", " ").title())
                db.add(perm)
                db.flush()
            permission_rows[code] = perm

        role_rows: dict[str, Role] = {}
        for role_name, codes in ROLE_PERMISSION_MAP.items():
            role = db.query(Role).filter(Role.name == role_name).first()
            if role is None:
                role = Role(name=role_name, is_system=True)
                db.add(role)
                db.flush()
            role.permissions = [permission_rows[c] for c in codes]
            role_rows[role_name] = role
        db.commit()
        print(f"Seeded {len(permission_rows)} permissions and {len(role_rows)} roles.")

        tenant = db.query(Tenant).filter(Tenant.name == settings.initial_tenant_name).first()
        if tenant is None:
            tenant = Tenant(name=settings.initial_tenant_name, slug=slugify(settings.initial_tenant_name))
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            print(f"Created tenant '{tenant.name}' ({tenant.id}).")
        else:
            print(f"Tenant '{tenant.name}' already exists.")

        admin = db.query(User).filter(User.email == settings.bootstrap_admin_email.lower()).first()
        if admin is None:
            admin_role = role_rows["SUPER_ADMIN"]
            admin = User(
                tenant_id=tenant.id,
                email=settings.bootstrap_admin_email.lower(),
                password_hash=hash_password(settings.bootstrap_admin_password),
                full_name="System Administrator",
                role_id=admin_role.id,
            )
            db.add(admin)
            db.commit()
            print(f"Created bootstrap Super Admin: {admin.email}")
            print("IMPORTANT: change this password immediately after first login.")
        else:
            print(f"Admin user '{admin.email}' already exists — skipping.")

    finally:
        db.close()


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # pragma: no cover
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        raise
