import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["INTERNAL_SERVICE_TOKEN"] = "test-internal-token"

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.core import rate_limit
from app.core.permissions import Permissions, ROLE_PERMISSION_MAP
from app.core.security import hash_password
from app.database import Base, get_db
from app.main import app
from app.models.tenant import Tenant
from app.models.user import Permission, Role, User

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

# Every request in these tests passes through the rate-limit middleware, which would
# otherwise try to reach a real Redis at localhost:6379 and either fail slowly (network
# timeout) or, on a dev machine that happens to run Redis, share state across test
# runs. Point it at an in-memory fake for the whole test session instead.
rate_limit._redis_client = fakeredis.FakeRedis()


@pytest.fixture(autouse=True)
def _fresh_database():
    Base.metadata.create_all(bind=engine)
    rate_limit._redis_client.flushall()  # each test starts with a clean rate-limit counter
    rate_limit._redis_down_until = 0.0
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


def _seed_rbac(db):
    perms = {}
    for code in Permissions.all():
        p = Permission(code=code, description=code)
        db.add(p)
        db.flush()
        perms[code] = p
    roles = {}
    for role_name, codes in ROLE_PERMISSION_MAP.items():
        role = Role(name=role_name, is_system=True)
        role.permissions = [perms[c] for c in codes]
        db.add(role)
        db.flush()
        roles[role_name] = role
    db.commit()
    return roles


@pytest.fixture
def tenant(db_session):
    t = Tenant(name="EZ Solutions", slug="ez-solutions")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture
def roles(db_session):
    return _seed_rbac(db_session)


def make_user(db_session, tenant, roles, email, role_name, password="Password123!"):
    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(password),
        full_name=email.split("@")[0],
        role_id=roles[role_name].id,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session, tenant, roles):
    return make_user(db_session, tenant, roles, "admin@ezsolutions.lan", "ADMIN")


@pytest.fixture
def viewer_user(db_session, tenant, roles):
    return make_user(db_session, tenant, roles, "viewer@ezsolutions.lan", "VIEWER")


def login(client, email, password="Password123!"):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
