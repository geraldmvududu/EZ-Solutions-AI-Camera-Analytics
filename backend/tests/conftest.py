import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["INTERNAL_SERVICE_TOKEN"] = "test-internal-token"
# Face enrollment writes the uploaded photo to disk for real (app/api/routes/faces.py)
# — route it to a temp dir instead of the default ./data/faces, or running the test
# suite locally (outside Docker, where FACE_PATH isn't set to /data/faces) litters the
# repo's backend/ directory with real JPEGs on every run.
os.environ["FACE_PATH"] = os.path.join(tempfile.gettempdir(), "ez_test_faces")

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


@pytest.fixture
def one_face(monkeypatch):
    """Shared across all face-recognition tests: Haar detection is monkeypatched to a
    fixed bounding box (synthetic test images don't reliably trigger real Haar
    detection — that's not what these tests verify), and compute_embedding is
    monkeypatched to a deterministic, well-separated one-hot-per-cell vector derived
    from the image's own pixel content, so "same image -> same embedding" and
    "different image -> clearly different embedding" hold reliably for test fixtures,
    independent of the real LBP algorithm's actual (documented, modest) discriminative
    power against synthetic imagery. The real algorithm is exercised directly, without
    mocking, in test_face_embedding.py."""
    import numpy as np

    from app.services import face_embedding

    face = face_embedding.DetectedFace(40, 30, 100, 100)
    monkeypatch.setattr(face_embedding, "detect_faces", lambda frame: [face])

    def fake_embedding(frame, face):
        bin_index = int(np.sum(frame[:10, :10, 0])) % face_embedding.BINS_PER_CELL
        vec = np.zeros(face_embedding.EMBEDDING_DIM, dtype=np.float32)
        for cell in range(face_embedding.GRID_SIZE**2):
            vec[cell * face_embedding.BINS_PER_CELL + bin_index] = 1.0
        return vec

    monkeypatch.setattr(face_embedding, "compute_embedding", fake_embedding)
    return face
