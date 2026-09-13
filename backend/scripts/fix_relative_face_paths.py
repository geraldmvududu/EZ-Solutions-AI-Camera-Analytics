"""One-time repair for a real bug: FaceProfile.image_reference used to be stored as
whatever relative path settings.face_path happened to be (default "./data/faces"),
which gets silently re-resolved against the CURRENT process's working directory every
time it's read — so a photo enrolled while the backend ran from one working directory
stops resolving the moment the backend is next started from a different one (see the
fix in app/api/routes/faces.py::enroll_person, which now always stores an absolute
path for new enrollments). This script finds any already-stored relative paths and
rewrites them to absolute ones, trying every working directory this project's own
documented dev/deploy commands could plausibly have been run from, and only writing
back a candidate that actually exists on disk. Safe to run repeatedly — a row already
storing an absolute path, or whose file can't be found under any candidate, is left
untouched (and reported) rather than guessed at.

Usage: python -m scripts.fix_relative_face_paths
"""

import os
import sys

from app.config import get_settings
from app.database import SessionLocal
from app.models.face_profile import FaceProfile

settings = get_settings()

# Every directory this project's own documented commands could run the backend from:
# repo root (this ai-engine/frontend/backend monorepo's own directory), the backend/
# package directory itself (`cd backend && uvicorn ...`, the README's own instruction),
# and Docker's WORKDIR (/app, where FACE_PATH is already absolute so this never
# actually applies there — included anyway for completeness).
_CANDIDATE_CWDS = [
    os.getcwd(),
    os.path.abspath(os.path.join(os.getcwd(), "..")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    "/app",
]


def _resolve(relative_path: str) -> str | None:
    for cwd in _CANDIDATE_CWDS:
        candidate = os.path.normpath(os.path.join(cwd, relative_path))
        if os.path.exists(candidate):
            return candidate
    return None


def run() -> None:
    db = SessionLocal()
    fixed, already_absolute, unresolved = 0, 0, 0
    try:
        for profile in db.query(FaceProfile).all():
            if not profile.image_reference:
                continue
            if os.path.isabs(profile.image_reference):
                already_absolute += 1
                continue
            resolved = _resolve(profile.image_reference)
            if resolved is None:
                unresolved += 1
                print(f"UNRESOLVED: {profile.id} -> {profile.image_reference!r} (file not found under any candidate cwd)")
                continue
            print(f"FIXED: {profile.id}: {profile.image_reference!r} -> {resolved!r}")
            profile.image_reference = resolved
            fixed += 1
        db.commit()
    finally:
        db.close()

    print(f"\n{fixed} fixed, {already_absolute} already absolute, {unresolved} unresolved.")
    if unresolved:
        print("Unresolved rows keep their stored path unchanged — their photo will keep")
        print("404ing until the underlying file is located and image_reference is set")
        print("manually, or the person is re-enrolled with a fresh photo.")
        sys.exit(1)


if __name__ == "__main__":
    run()
