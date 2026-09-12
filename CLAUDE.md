# CLAUDE.md — EZ Solutions AI Camera Analytics Platform

Project memory for Claude Code. Read this before making changes — it records what is
actually implemented (verified, not assumed) vs. what's planned.

## Architecture

```
backend/     FastAPI + PostgreSQL + SQLAlchemy + Alembic — REST API, auth/RBAC,
             rule engine, WebSocket broadcast, audit logging
ai-engine/   OpenCV-based video capture, privacy-zone masking (applied first, before
             anything else sees the frame), motion detection, AI object detection
             (HOG person detector, pluggable), centroid tracking, zone/tripwire/
             loitering geometry, recording, snapshots — reports everything to backend
             over HTTP with a shared internal-service token. Also runs a small internal
             MJPEG server (app/streaming.py, port 8090) publishing each camera's live
             annotated frames for the live-view feature. main.py's discovery loop
             restarts a camera's worker when its config/zones/tripwires change, so
             editing a zone takes effect within one discovery cycle, not a full
             ai-engine restart.
worker/      Standalone retention-policy cleanup (deletes expired, non-evidence-locked
             recordings/snapshots) — plain SQL against the same Postgres DB
frontend/    React + TypeScript + Vite + Tailwind SPA
nginx/       Reverse proxy + TLS termination (self-signed cert generated on first run)
mobile/      Not started — see "Known limitations"
```

Data flow: camera source → ai-engine (real inference) → backend (`POST /api/detections`,
`/api/events`) → rule engine (`app/services/rule_engine.py`) evaluates the event against
enabled `AIRule` rows → matching rules create `Alert` rows → both are broadcast over
`/ws/live` to that tenant's connected dashboards.

Every "trusted server-to-server" backend endpoint (ai-engine → backend) requires the
`X-Internal-Token` header (`app/core/deps.py::require_internal_service`) — never a user
JWT. These are `include_in_schema=False` and live at `/api/{resource}/internal/...` or
as plain internal POST endpoints (`/api/detections`, `/api/events`, `/api/snapshots`,
`/api/recordings`, `/api/cameras/{id}/heartbeat`).

**Push notifications** (section 39/40): the mobile app registers an Expo push token
with `POST /api/push-tokens` after login. When `app/api/routes/events.py::create_event`
creates a HIGH/CRITICAL alert, `app/services/notification_service.py` writes a real
`Notification` row for every user in that tenant with `manage_alerts` (operators/
admins — not viewers), and sends a real push via `app/services/push_service.py`, which
calls **Expo's** push API (`https://exp.host/--/api/v2/push/send`) rather than Firebase
Cloud Messaging or APNs directly. This is the key point: Expo's push service is
available to any Expo-built app without the deploying organization provisioning its
own Firebase project or Apple Developer account, which is what makes this feature
real and testable in this environment rather than blocked on external credentials.

**Live video** (`GET /api/cameras/{id}/stream`): the browser/mobile client hits this
JWT-authenticated (token as a query param, since `<img>`/WebView can't set headers)
backend route, which checks tenant + `view_live_video` permission, then proxies
(`httpx` streaming) the ai-engine's MJPEG output for that camera straight through. The
ai-engine's stream port (8090) is never exposed to the frontend directly — the backend
is the only access-control boundary. Web renders it with a plain `<img src="...">`;
mobile wraps the same URL in a `react-native-webview` `<WebView>` because React
Native's native `<Image>` component can't decode `multipart/x-mixed-replace`, but a
WebView's underlying browser engine can.

**Facial Recognition & Identity Analytics** (`app/api/routes/faces.py`,
`app/services/face_embedding.py`): a real, self-contained biometric pipeline — no
downloaded model weights, matching the same offline-build constraint that already
shaped the HOG person detector (limitation 3). Face detection is OpenCV's bundled
Haar cascade; the "embedding" is a genuine classic Local Binary Patterns histogram
descriptor computed directly (not a deep-learning embedding) — real inference, modest
accuracy, fully reproducible without internet access at build or run time.
`app/services/face_embedding.py` is intentionally duplicated byte-for-byte at
`ai-engine/app/core/face_embedding.py`: enrollment-time embedding generation is a
synchronous backend upload-request concern, while live-recognition-time embedding
generation happens per-frame in the ai-engine — there's no shared-package
infrastructure in this monorepo to unify them without a bigger architectural change
than this feature warranted. `FACE_MODEL_VERSION` exists specifically to detect drift
between the two copies.

The module deliberately reuses almost the entire existing event/alert pipeline rather
than building a parallel one: `ai-engine/app/core/face_recognizer.py` runs on already-
tracked PERSON detections (never every frame), applies a cooldown + FACE_DETECTION/
FACE_EXCLUSION zones (two new `ZoneType` values on the existing `Zone` model/geometry)
+ per-camera operating hours, then POSTs the live candidate embedding to the internal
`POST /api/faces/recognize` endpoint. That endpoint does the actual decrypt+compare
against every enrolled `FaceProfile` in the camera's tenant, creates a real `Event`
(two new `EventType` values, `FACE_RECOGNIZED`/`UNKNOWN_FACE_DETECTED`) plus a
`FaceRecognitionEvent` detail row, and calls the exact same
`rule_engine.evaluate_event()` / WebSocket broadcast / `notify_users_of_alert()` path
that every other event type already uses — so face-triggered `Alert` rows, real-time
dashboard updates, and mobile push notifications work with zero new plumbing. Two new
`_rule_matches()` condition keys, `person_category` and `person_status`, are what make
"Suspended Person"/"Watchlist Match"/etc. rules possible; `zone_id`/`min_confidence`/
`time_start`/`time_end` conditions already worked unchanged. Embeddings are Fernet-
encrypted at rest with a **separate** key from camera-credential encryption
(`FACE_EMBEDDING_ENCRYPTION_KEY`) and are never returned by any list/detail API
response — only a dedicated, permission-gated `/faces/{id}/photo` endpoint serves the
enrolled image itself. Biometric-specific audit actions (`FACE_ENROLL`, `FACE_VIEW`,
`FACE_MODIFY`, `FACE_DELETE`) reuse the existing generic `AuditLog`/`log_action` —
there is no separate biometric audit table.

**Identified-person violations** (`app/services/violation_service.py`): a genuine
"Person + Behaviour" correlation (spec section 9), not a new detection capability —
`FaceRecognizer.identity_for(track_id)` (ai-engine) remembers the most recent
RECOGNIZED result for a still-tracked person for `IDENTITY_FRESHNESS_SECONDS` (5 min),
and `worker.py::_identity_metadata` attaches that identity to a `TRIPWIRE_VIOLATION`/
`INTRUSION_DETECTED` event's `event_metadata` when one fires for the same track_id —
two independent signals (who they are, and that they crossed a boundary) correlated by
camera+tracking, not claimed to be the same thing. When `create_event` sees a
violation event carrying a `person_id`, it automatically opens a real `Incident`
(reusing the existing incident model/API/page — section 5 — rather than a new
"violations" table), linked to whatever `Alert`(s) the rule engine created from the
same event, with a description that explicitly tells the reviewer to check the
evidence rather than treat the correlation as confirmed proof. This is the literal
answer to "flag an enrolled person doing something like jumping a gate and keep it on
a file I can open" — open **Incidents** and click a row to see the full description,
linked alert/evidence, and set a status/resolution.

## Development commands

```bash
# Backend
cd backend
.venv/Scripts/python -m uvicorn app.main:app --reload   # Windows
.venv/bin/uvicorn app.main:app --reload                  # Linux/macOS
.venv/*/python -m alembic revision --autogenerate -m "message"
.venv/*/python -m alembic upgrade head
.venv/*/python -m scripts.bootstrap     # idempotent: seeds roles/permissions/tenant/admin

# Frontend
cd frontend && npm run dev      # http://localhost:3000
cd frontend && npm run build    # tsc -b && vite build (type-checks)

# ai-engine
cd ai-engine && python -m app.main
```

## Testing commands

```bash
cd backend && pytest -q      # 86 tests: auth, RBAC, tenant isolation, camera CRUD
                              # (including the delete cascade covering every dependent
                              # table), credential encryption, rule engine, analytics
                              # aggregates, report export, the Redis-backed rate limiter
                              # (fakeredis, including the internal-service-token
                              # exemption), push notifications (Expo API call mocked),
                              # facial recognition (enrollment quality gates/duplicate
                              # detection, the real LBP algorithm unmocked, recognition
                              # matching, person_category/status rule conditions, tenant
                              # isolation of biometric data, audit logging), and the
                              # identified-person violation -> auto-Incident correlation
                              # — all against a real in-memory SQLite DB through the
                              # actual FastAPI app
cd ai-engine && pytest -q    # 36 tests: centroid tracker, zone/tripwire geometry,
                              # loitering timer, motion detection (real MOG2 background
                              # subtraction against synthetic frames), privacy-zone
                              # blurring, the discovery-loop config fingerprint, and the
                              # FaceRecognizer pipeline (cooldown, zone filtering,
                              # identity tracking/expiry for the violation correlation,
                              # exception-safety — a recognition bug must never stop
                              # the capture loop)
cd frontend && npm run build # TypeScript strict-mode compile + production bundle
```

No test mocks the security boundary it's testing — e.g. `test_tenant_isolation.py`
creates two real tenants and asserts a 404 (not empty data) when tenant B requests
tenant A's camera by ID, which is what actually happens against the live route code.

## Docker commands

```bash
docker compose up -d --build
docker compose logs -f backend|ai-engine|worker|nginx|frontend
docker compose exec backend python -m scripts.bootstrap
docker compose exec postgres psql -U ezsolutions -d ez_camera_analytics
docker compose restart backend
docker compose down          # keeps ./data volumes
```

## Environment variables

See `.env.example` (root, shared by backend/ai-engine via `env_file: .env` in
docker-compose.yml) and `frontend/.env.example`. Key ones: `DATABASE_URL`,
`JWT_SECRET`/`JWT_REFRESH_SECRET`, `CREDENTIAL_ENCRYPTION_KEY` (Fernet-derived, encrypts
camera passwords at rest), `INTERNAL_SERVICE_TOKEN` (must match between backend and
ai-engine), `AI_DEVICE` (cpu — GPU is an optional future path, never required).
Facial-recognition-specific: `FACE_EMBEDDING_ENCRYPTION_KEY` (must differ from
`CREDENTIAL_ENCRYPTION_KEY`), `FACE_MATCH_THRESHOLD`/`FACE_MIN_QUALITY`/
`FACE_EVENT_COOLDOWN` (seed a new tenant's `FaceRecognitionSettings` row on first use —
the tenant's own admin-configured values in Settings take over after that; only
`FACE_EVENT_COOLDOWN`/`FACE_MIN_QUALITY` are still read live by ai-engine, see
limitation 13), `FACE_PATH` (`/data/faces`, enrolled-photo storage).

## Coding standards

- Backend: FastAPI route → Pydantic schema → SQLAlchemy model, tenant-scoped via
  `app/core/deps.py::tenant_filter_value` on every list/get/update/delete. New
  tenant-owned tables must inherit `TenantScopedMixin` (`app/models/base.py`).
  Object-level authorization: always look up by ID through a `_get_owned_*` helper
  that 404s on tenant mismatch — never trust a client-supplied ID alone.
- New permission-gated endpoints use `Depends(require_permission(Permissions.X))` from
  `app/core/permissions.py` — don't hand-roll role checks.
  Log side-effecting actions with `app/core/audit.py::log_action`.
- ai-engine: `Detector`/`FrameSource` are the two swap points (`app/detectors/base.py`,
  `app/sources/base.py`). Don't couple `worker.py` to a specific model or source type.
- Frontend: all API calls go through `src/api/client.ts::apiRequest` (handles the
  access/refresh token dance) — don't call `fetch` directly from a page component.

## Security requirements (already implemented — don't regress these)

- Passwords: bcrypt via `app/core/security.py`, never logged/stored in plaintext.
- Camera credentials: Fernet-encrypted at rest (`password_encrypted` column); the
  `CameraResponse` schema deliberately omits `stream_url`/`username`/`password` — the
  frontend never receives them. The one exception is the internal
  `/cameras/{id}/internal/stream-info` endpoint, reachable only with the internal
  service token, because the ai-engine's capture process needs real credentials to
  connect to RTSP/IP cameras.
- JWT access tokens expire in 15 min; refresh tokens are rotated and hashed at rest
  (`sessions.refresh_token_hash`), never stored raw.
- CORS is allow-listed via `CORS_ORIGINS`; security headers + a per-IP rate limiter are
  applied in `app/main.py` middleware (the rate limiter is in-process — see "Known
  limitations" before scaling to multiple backend replicas).
- SQL injection: 100% SQLAlchemy ORM/parameterized queries — the retention worker's raw
  SQL uses `text()` with bound parameters, not string interpolation.
- Face embeddings: Fernet-encrypted at rest (`face_profiles.embedding_encrypted`) with
  a key separate from camera-credential encryption; never returned by any list/detail
  API response (`schemas/person.py::FaceProfileResponse` omits it entirely). Biometric
  enrollment/management requires the dedicated `manage_biometrics` permission
  (admin/super-admin only); viewing recognition events requires `view_biometric_events`
  (also granted to operators, for the human-review workflow).

## Known limitations (real, documented — not silently faked)

1. **Mobile app**: login, camera list, live view (via WebView), alerts (with
   acknowledge), recorded-video playback (via `expo-av`), push notifications (via
   Expo's push service — see below), and an in-app notification feed are implemented
   and hit the real API — not a placeholder UI. Full incident/event browsing is not
   built yet.
2. **RTSP/HTTP_MJPEG/IP_CAMERA sources**: wired end-to-end (credential decryption,
   OpenCV capture) but only smoke-tested against synthetic/file sources in this
   environment — no physical camera was available to verify against real hardware.
3. **Default AI detector** (`app/detectors/hog_detector.py` in ai-engine) is OpenCV's
   built-in HOG person detector: real inference, ships with no external model
   download, but PERSON-only and lower accuracy than a modern CNN. The `Detector`
   interface (`app/detectors/base.py`) is the intended swap point for a YOLOv8/ONNX
   multi-class detector — not implemented, since that requires downloading model
   weights this environment can't fetch and verify.
4. **Recording pre-roll**: MOTION/AI_EVENT-triggered recordings start writing from the
   moment the trigger fires — there is no ring-buffer capturing the few seconds
   *before* the trigger yet (`ai-engine/app/core/recorder.py`).
5. **Rate limiting** (`app/core/rate_limit.py`) is now Redis-backed (fixed-window
   INCR+EXPIRE, shared correctly across replicas), with a circuit-breaker fallback to
   a per-process in-memory counter if Redis is unreachable — see "Verified end-to-end"
   below for a real latency bug this caught and fixed, and for a real self-DoS bug
   (ai-engine 429-ing its own traffic) found deploying the Facial Recognition module.
   `app/main.py::rate_limit_middleware` now exempts any request carrying a valid
   `X-Internal-Token` from the per-IP limit entirely — internal server-to-server calls
   already pass a separate, stronger auth check
   (`app/core/deps.py::require_internal_service`) than the abuse protection this
   limiter exists for.
6. Analytics/reports (section 36) are done, with one honest caveat: "camera status
   summary" reflects each camera's *current* status, not a historical uptime
   percentage — there's no periodic status-history table yet, only point-in-time
   heartbeats.
7. **Facial recognition**: implemented (see the Architecture section above and
   limitations 12/13 below) — **ANPR/license-plate recognition is not** (out of scope
   for this pass).
8. **Push notification delivery** was verified up to the point of a real HTTP call to
   Expo's push API with a correctly-shaped payload (mocked in tests, since there's no
   real device/token in this environment to receive an actual push) — see
   `tests/test_push_notifications.py`. The registration flow, DB writes (Notification
   rows), RBAC filtering (viewers excluded), and the push payload itself are all real
   and tested; actual delivery to a physical device has not been observed firsthand.
9. **Config-change hot-reload** (`ai-engine/app/main.py::_config_fingerprint`) restarts
   a camera's entire worker on any zone/tripwire/camera-settings change — simple and
   correct, but it also resets that camera's object tracker and loitering timers, and
   truncates any recording in progress. Fine for a lab deployment where zones are
   configured occasionally; a production system with frequent edits should diff and
   apply changes without a full restart.
10. **MJPEG stream server** (`ai-engine/app/streaming.py`) uses Python's stdlib
   `ThreadingHTTPServer` — one thread per connected viewer, polling a shared frame
   buffer. Fine for a handful of concurrent viewers per camera at lab scale; a
   production/100+-camera deployment (section 77) should move this to an async
   server (e.g. `aiohttp`) or a proper media server (e.g. MediaMTX/go2rtc) rather than
   scaling thread count.
11. **Backend port 8000 is published to the host** in `docker-compose.yml` (a
   deliberate exception to "not published to the host" — every other internal service
   stays unpublished). This exists only so the mobile app can reach the backend over
   plain HTTP: Expo Go is a published app using a bare `fetch()` with no
   click-through-the-warning flow for nginx's self-signed HTTPS cert, so mobile can't
   use the same TLS path the web dashboard does. This is a real, unresolved gap, not a
   workaround to remove later — it stays until a CA-trusted cert (`scripts/setup-letsencrypt.sh`,
   needs a real domain) is in place, at which point port 8000 should be closed again.
12. **Facial Recognition, Phase 1 scope** (deliberately phased — see the Phase 2
   backlog items below, not silently dropped): the LBP-histogram
   matcher is a real, classic algorithm but has genuinely lower discriminative accuracy
   than a modern CNN face embedding — expect more false positives/negatives at the
   default 85% threshold than a commercial system, especially across lighting/angle
   variation; tune `face_recognition_threshold` per camera if needed. Liveness/anti-
   spoofing is **not implemented** (real spoof detection needs a depth/IR sensor a lab
   webcam pipeline doesn't have — the `liveness_detection_enabled` setting exists in
   the schema for Phase 2 but currently does nothing). No automated retention/deletion
   background job yet for `face_recognition_events`/snapshots (the `FaceRecognitionSettings`
   retention-day fields are stored and configurable but not yet enforced — manual
   deletion via the Enrolled People page works today). No PDF/CSV/Excel reports for
   face data yet (the existing `reports.py`/reportlab pattern is the intended
   follow-up). Person-to-camera/zone authorization is by **category/status**
   (`person_category`/`person_status` rule conditions), not a fine-grained per-person-
   per-camera ACL — the spec's own schema didn't define one either. No written AWS
   deployment guide yet.
13. **Per-tenant face settings partially synced to ai-engine**: `POST /api/faces/recognize`
   reads a tenant's `FaceRecognitionSettings.default_match_threshold` live (admin
   changes to the match threshold in Settings take effect on the very next
   recognition), but `recognition_cooldown_seconds`/`multi_frame_confirmation_enabled`
   are **not** — ai-engine's `FaceRecognizer` reads its own static `FACE_EVENT_COOLDOWN`
   env var instead, the same way zones/tripwires are periodically re-fetched but this
   particular setting isn't (yet). Wiring this up would mean ai-engine periodically
   fetching `FaceRecognitionSettings` per tenant, similar to its existing zone/tripwire
   discovery poll in `app/main.py`.
14. **Sidebar navigation is flat, not nested**: the four new Face pages are added as
   flat sibling nav items (matching every other item in `Sidebar.tsx`, which has no
   nested-submenu support anywhere) rather than the nested "Facial Recognition ▸
   Dashboard/Enrolled People/..." tree sketched in the original spec — introducing
   nested-menu UI infrastructure used nowhere else in the app was judged out of scope
   for "don't redesign the existing application."

## Current implementation status

| Phase | Status |
|---|---|
| 1. Foundation (Docker/Ubuntu, Postgres schema, auth, RBAC, dashboard shell) | Done, tested |
| 2. Video (simulated/file cameras, capture, recording, live view, playback) | Capture/recording/live streaming done; recorded-video playback UI is list-only, no in-browser player yet |
| 3. AI (detection, tracking, snapshots) | Done with the HOG detector (see limitation 3) |
| 4. Security analytics (motion, tripwire, intrusion, loitering, rules, privacy zones) | Done, tested — includes a click-to-draw `/zones` editor over the live feed |
| 5. Alerting (real-time WebSocket, ack workflow, incidents, evidence lock) | Done |
| 6. Analytics/reporting (charts, exports) | Done — `/api/analytics/summary` + `/analytics` dashboard (SVG bar charts, date-range filter), CSV export for events/alerts, PDF security report (reportlab) |
| 7. Mobile | Login, camera list, live view, alerts, recording playback, push notifications, and an in-app notification feed are done |
| 8. Multi-tenancy | Data model + isolation enforced and tested; no tenant self-signup UI |
| 9. Production hardening (real TLS, Redis rate limit, perf) | Redis-backed rate limiting done; real-TLS automation done (`scripts/setup-letsencrypt.sh`, needs the user's own domain to run) |
| 10. Facial Recognition & Identity Analytics | Phase 1 done, tested, verified in a real browser — enroll/manage people, real detect→embed→match pipeline, recognition events feeding the existing event/alert/rule/notification/WebSocket pipeline, camera + zone config, human review. Reports, retention jobs, liveness, and full rules-builder UI are Phase 2 (see limitation 12) |

## Verified end-to-end (not just "should work")

- **Real deployment to a real Ubuntu Server VM + real Postgres**, not just local
  SQLite testing. This surfaced a genuine bug SQLite testing couldn't have caught:
  `events`/`detections`/`snapshots`/`recordings` form a circular FK reference
  (Snapshot -> Event -> Detection -> Snapshot). SQLite never enforces FK targets at
  CREATE TABLE time, so `alembic upgrade head` "worked" in every local test run; a real
  Postgres correctly rejected it (`relation "recordings" does not exist`) partway
  through the initial migration. Fixed by moving the six cyclic FK columns to separate
  `ALTER TABLE` statements issued after every table exists (`op.create_foreign_key`,
  skipped on SQLite since it can't ALTER in a constraint outside of Alembic's batch
  mode, and never needed it enforced anyway). Also found and fixed along the way: a
  `.gitkeep` placeholder in `data/postgres/` that broke Postgres's `initdb` (it refuses
  to initialize a non-empty directory), and undocumented URL-breaking behavior when
  `POSTGRES_PASSWORD` contains `@` (it's interpolated unescaped into `DATABASE_URL`,
  so a password like `Ellah@0712` made the backend try to resolve a garbled hostname
  instead of `postgres` — confusing because a literal `getent hosts postgres` always
  resolved fine, since the app was never actually asking for that literal string). Also
  found: `docker-compose.yml`'s `ai-engine` service was missing a mount for
  `./data/uploads` (the backend had it; ai-engine — the service that actually needs to
  *read* an uploaded VIDEO_FILE camera's video — didn't), so every VIDEO_FILE camera
  pointed at `/data/uploads/...` failed with "Could not open video source" and the
  camera stayed OFFLINE forever. Fixed by adding the mount (read-only, since ai-engine
  never writes there).
- **Deleting a camera with real activity against it** (found live, via the user
  reporting "the Delete button is not working") was another instance of the same
  SQLite-vs-Postgres gap as the circular-FK bug above: `delete_camera` did a naive
  `db.delete(camera); db.commit()`, which "worked" in every local test (SQLite never
  enforced the foreign keys pointing at `cameras.id`) but silently failed on Postgres
  once the camera had any real events/detections/zones/alerts/etc. — an unhandled
  `IntegrityError` the frontend's `handleDelete` had no try/catch around, so the
  button visibly did nothing. Fixed by explicitly cleaning up every dependent table in
  FK-safe order (nulling the circular Event/Detection/Snapshot cross-references first,
  same technique as the migration fix), removing the now-orphaned snapshot/recording
  files from disk, and unscoping (not deleting) any `AIRule` that targeted the camera.
  Also added error handling to the frontend's delete button so a future failure shows
  a message instead of silently doing nothing. Covered by
  `tests/test_camera_delete_cascade.py`, which builds real dependent rows for every
  affected table (not just an empty camera) and asserts they're actually gone
  afterward — not merely that the request didn't crash.
- Full auth flow (login/refresh/logout) against a real backend + real frontend in a
  browser.
- RBAC enforcement: VIEWER blocked (403) from camera/user management; ADMIN allowed.
- Tenant isolation: cross-tenant camera access returns 404, not another tenant's data.
- A SIMULATED camera run through the actual ai-engine produced real MOTION_DETECTED
  events (via MOG2 background subtraction) that landed in Postgres/SQLite, updated the
  camera's heartbeat/ONLINE status, and appeared in real dashboard stat aggregates.
- `SegmentRecorder` wrote a real playable MP4 to disk and reported its real file size/
  duration to the backend as a `Recording` row.
- A VIDEO_FILE camera pointed at a nonexistent path correctly stayed OFFLINE and logged
  an error — no fake "success" status.
- Live view end-to-end in a real browser: the Live Cameras page's grid tile and its
  expand-to-fullscreen modal both rendered the ai-engine's actual MJPEG output — a
  moving shape and a live-updating timestamp overlay confirmed frame-by-frame via two
  screenshots taken seconds apart, proxied through the backend's authenticated
  `/api/cameras/{id}/stream` route.
- Analytics end-to-end in a real browser: seeded real events/alerts/detections via the
  API, then confirmed the `/analytics` page's stat cards and every chart (hourly
  histogram, most-active-cameras, alerts-by-severity, detections-by-type) matched the
  seeded numbers exactly, and that the CSV/PDF export buttons fired real authenticated
  requests. Caught and fixed a real bug in the process: `total_alerts`/
  `total_detections` were built from an already-aggregated query object, which
  collapses to a `.count()` of 1 regardless of the real row count — covered now by
  `tests/test_analytics.py::test_total_counts_are_not_collapsed_by_aggregate_subquery`.
- Privacy zones + the zone/tripwire editor, live in a real browser: drew a PRIVACY
  polygon over the live MJPEG feed on the new `/zones` page, saved it, and watched the
  live stream's moving shape genuinely blur (real `cv2.GaussianBlur`, not a CSS
  filter) — then deleted the zone and watched the blur disappear, both without
  restarting the ai-engine process by hand. Caught and fixed a real bug in the process:
  the first version of the hot-reload fingerprint included `last_heartbeat_at`/
  `status`, which change every heartbeat, causing every camera's worker to restart on
  every single discovery cycle forever. Fixed by excluding volatile fields, verified by
  log inspection (exactly one restart for one real zone change, none over the next 85s)
  and covered by `tests/test_main_fingerprint.py`.
- Redis-backed rate limiting: ran a live backend with no Redis available and measured
  real request latency with a stopwatch, not just unit tests. The first version added
  ~2 seconds to *every single request* while Redis was down (a fresh connect-timeout
  paid every time) — unit tests never caught this because fakeredis never exercises
  the real timeout path. Fixed with a circuit breaker (skip Redis entirely for 10s
  after one failure); re-measured: first request ~2.1s, every request after that
  8-10ms. Covered by `tests/test_rate_limit.py::test_does_not_retry_redis_on_every_call_during_cooldown`.
- Real deployment of the Facial Recognition module to the VM surfaced a second,
  unrelated real bug in the same rate limiter: `docker compose logs backend` showed
  ai-engine's own `POST /api/detections`/`/api/events`/`/api/snapshots`/`/api/recordings`
  and even its `GET /api/cameras/internal/active` discovery polling all returning 429
  — the per-IP limiter (300 req/60s, sized for one browser/user) was blocking
  ai-engine's own aggregate traffic, which shares one container IP across every camera
  worker it runs. This was already possible before Facial Recognition existed
  (multiple active cameras alone can exceed 300 req/min from one ai-engine instance)
  but wasn't yet observed until this deployment's traffic pattern crossed the
  threshold. Fixed by exempting valid-`X-Internal-Token` requests from the limiter
  entirely (`app/main.py::rate_limit_middleware`) — confirmed no exemption existed
  previously (the middleware only ever checked `client_ip`). Covered by
  `tests/test_rate_limit.py::test_internal_service_calls_are_exempt_from_rate_limiting`
  and `::test_regular_authenticated_requests_are_still_rate_limited` (regression guard
  that the exemption doesn't accidentally disable rate limiting for real users).
- Facial Recognition, end-to-end in a real browser against a real (unmocked) backend:
  submitted a real multipart upload through the actual `/faces/enroll` UI with a
  synthetic (non-face) test image — the real, un-mocked OpenCV Haar cascade correctly
  found no face and the API returned "No face detected in image", which the frontend
  rendered cleanly with no crash. Created a real camera with `face_recognition_enabled`
  and a recognition threshold/operating-hours window through the Cameras page and
  confirmed the new "Face Rec." column reflected it. Confirmed the two new
  `FACE_DETECTION`/`FACE_EXCLUSION` zone-type options render correctly in the existing
  `/zones` polygon editor. Also ran the real (not the auto-generated `create_all`)
  Alembic migration against a fresh SQLite dev DB — `alembic upgrade head` applied both
  the initial schema and the face-recognition migration cleanly in sequence, and
  `scripts.bootstrap` correctly seeded the two new permissions
  (`manage_biometrics`/`view_biometric_events`) into the ADMIN/SUPER_ADMIN roles.
  Separately, unit-level tests confirmed the real LBP algorithm itself: identical
  images produce confidence 1.0, a perturbed image produces meaningfully lower
  confidence, and the base64 embedding serialization round-trips exactly.
- Identified-person violation → auto-Incident, end-to-end against a real backend +
  real frontend in a browser: created a real Person/Camera, posted a real
  `TRIPWIRE_VIOLATION` event (internal token, as ai-engine would) carrying a
  `person_id`, and confirmed a real `Incident` was created — visited **Incidents** in
  the browser, opened it, and saw the correct title, CRITICAL severity, resolved
  camera name, the full auto-generated description (including the "review the
  evidence before treating this as confirmed" caveat), and the linked `Alert` the same
  event's rule match produced. Changed its status to INVESTIGATING and added
  resolution notes through the new detail modal, saved, reopened it, and confirmed
  both persisted — including that a UTF-8 em dash in the generated title/resolution
  text round-tripped correctly through the API and rendered correctly in the browser
  (a `python -m json.tool`-piped terminal check of the same data had shown mojibake —
  that turned out to be a Windows console/pipe encoding artifact, not a real bug, and
  the browser check is what actually settled it).
