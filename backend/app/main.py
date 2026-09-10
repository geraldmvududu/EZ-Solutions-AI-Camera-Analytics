import os

from anyio import to_thread
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import get_settings
from app.core import rate_limit

settings = get_settings()

for path in (settings.recording_path, settings.snapshot_path, settings.upload_path, settings.ai_model_path):
    os.makedirs(path, exist_ok=True)

app = FastAPI(
    title="EZ Solutions AI Camera Analytics Platform API",
    description="AI-powered video surveillance, camera analytics, and security-event management.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Security headers (section 46) ----
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.environment != "development":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


# ---- Redis-backed rate limiter (per client IP) — see app/core/rate_limit.py ----
# Shared across every backend replica via Redis, unlike a process-local counter, and
# fails open to a per-process in-memory fallback if Redis itself is unreachable.
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    limited = await to_thread.run_sync(rate_limit.is_rate_limited, client_ip)
    if limited:
        return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content={"detail": "Rate limit exceeded"})
    return await call_next(request)


app.include_router(api_router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {"service": "EZ Solutions AI Camera Analytics Platform", "status": "running"}
