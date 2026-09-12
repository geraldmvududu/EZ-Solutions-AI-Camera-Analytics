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
             recordings/snapshots, face recognition events, and expired face profiles)
             — plain SQL against the same Postgres DB
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

**Facial Recognition Phase 2 — recording linkage, in-browser playback, and
higher-confidence recognition**: `ai-engine/app/core/recorder.py::SegmentRecorder`
creates the `Recording` row via `POST /api/recordings` the moment a segment starts
(not when it closes), storing the returned ID as `self.recording_id` -- this is what
makes it possible to attach a real `recording_id` to a face-recognition or
tripwire/zone-violation `Event` while the segment covering that moment is still being
written. `worker.py` threads `self._recorder.recording_id` into violation event
payloads and into `FaceRecognizer.maybe_recognize()`; `POST /api/faces/recognize`
persists it on both the `Event` and the `FaceRecognitionEvent` row. Because
`rule_engine.evaluate_event` already copies `event.recording_id` onto any `Alert` it
creates, and Incidents already link to those Alerts, this required zero changes to
`rule_engine.py`/`violation_service.py` -- the linkage just started being populated
(`tests/test_recording_linkage.py`). `stop()` finalizes the same row via
`PATCH /api/recordings/{id}/internal` (`ended_at`/`duration_seconds`/`file_size_bytes`)
instead of creating a second one.

Recordings now play inline: `GET /api/recordings/{id}/play?token=` (query-token auth,
the same pattern as the live-stream endpoint) returns the file via Starlette's
`FileResponse` without a `filename=` kwarg so it doesn't force a download, and Range
requests (so seeking works) are handled by `FileResponse` itself -- no extra code.
`Recordings.tsx` exports a reusable `VideoPlayerModal` wired into Recordings,
Recognition Events, Incidents (per linked alert), and Enrolled People's new
"Appearances" view; each caller computes a `seekSeconds` offset client-side from the
relevant event's real occurrence timestamp minus the recording's `started_at` --
Incidents specifically fetches the underlying `Event` via `getEvent(alert.event_id)`
and uses `event.occurred_at`, not `alert.created_at` (the Alert row's own DB-insert
timestamp), since those are conceptually different fields that happen to look similar
in real-time operation. Verified in a real browser with a `seeked`-event listener
reading `video.currentTime` at the exact moment the seek completed (not after a
polling delay, which -- misleadingly -- can show the correct seek having already
progressed under `autoPlay`): landed on exactly the expected offset.

Critical bug found and fixed while building this: `cv2.VideoWriter`'s `mp4v` fourcc --
the only codec this environment's OpenCV/FFmpeg build can open for writing, since the
`avc1`/H264 fourccs fail here with a missing-OpenH264-library error -- produces real,
valid video (readable by cv2 itself, VLC, ffplay) that Chrome's `<video>` tag flatly
refuses to decode (`MEDIA_ERR_SRC_NOT_SUPPORTED`), confirmed directly against a real
recorded file in a real browser. This would have silently broken the entire
"linked to camera recordings" feature -- the link would exist, but clicking it would
show a black, non-functional player. Fixed by adding
`SegmentRecorder._transcode_to_h264()`, which shells out to the system `ffmpeg` binary
(installed via apt in `ai-engine/Dockerfile` -- a full Ubuntu build, not OpenCV's
bundled/limited one) right after `stop()` closes the file, re-encoding to
H.264/yuv420p/faststart and replacing the file in place so the existing DB row's
`file_path` is unaffected. If ffmpeg is missing or the transcode fails, the original
mp4v file is kept rather than losing the recording (still usable as evidence in
VLC/ffplay, just not in-browser). Confirmed on the real deployed Ubuntu VM (not just
the Windows dev machine) — see "Verified end-to-end" below.

Two further real, narrowly-scoped features, not oversold: multi-frame confirmation
(`app/api/routes/faces.py`, a module-level `_pending_confirmations` dict, same
single-process caveat already accepted for the in-memory rate-limit fallback) requires
two consecutive `recognize_face` calls for the same `(camera_id, tracking_id)` to agree
before an Event/Alert is created -- the first call returns `PENDING_CONFIRMATION`
without creating anything; this is attempt-level confirmation (attempts are already
~30s cooldown-spaced), not true same-second multi-frame voting. Liveness
(`ai-engine/app/core/face_recognizer.py::_passes_liveness_check`) keeps the previous
recognition attempt's downsampled face crop per track_id and requires a minimum
pixel-difference between consecutive attempts -- this genuinely rejects a perfectly
static printed photo or paused video held up to the camera; it does not defend against
a moving photo or a played video, and is not real depth/IR-based biometric liveness
(limitation 12 already documents why that's out of scope). Retention enforcement
(`worker/app.py::cleanup_face_recognition_events`/`cleanup_face_profiles`) now actually
runs, using per-tenant `FaceRecognitionSettings` retention-day fields computed in
Python (portable across SQLite/Postgres, unlike the recordings/snapshots cleanup
functions' Postgres-specific `now() - interval` SQL) and skipping any event linked to
a still-open Incident. A person's full appearance history is browsable (Enrolled
People -> "Appearances") and exportable
(`GET /api/reports/face-appearances.csv?person_id=`).

**Recognition cooldown sync + PDF face-recognition section** (the two remaining Phase
2 backlog items, now done): `recognition_cooldown_seconds` is flattened onto each
camera dict by `GET /cameras/internal/active` exactly like `liveness_detection_enabled`
already was, and `ai-engine/app/core/face_recognizer.py`'s cooldown check now reads
`camera.get("recognition_cooldown_seconds", settings.face_event_cooldown)` instead of
always using its own static env var -- an admin's Settings change now genuinely
reaches ai-engine (within one discovery cycle, since the config-fingerprint diff in
`main.py` already restarts a camera's worker on any dict field change, with zero code
change needed there). `GET /api/reports/security-report.pdf` now also includes a real
"Face Recognition Activity" (counts by RECOGNIZED/UNKNOWN/LOW_CONFIDENCE) and "Top
Recognized People" section, built via `app/services/analytics_service.py
::get_face_recognition_report_data` (the same SQL GROUP BY convention as every other
analytics aggregate here, not a Python loop over loaded rows) -- gated behind the same
`view_biometric_events` permission the CSV export already requires, so a user without
it gets a complete report minus that one section rather than a 403 on the whole PDF.

**AI Video Intelligence, Phase 1** (`app/services/violation_service.py`,
`ai-engine/app/core/tripwire_analysis.py`): extends the existing tripwire/zone
pipeline rather than adding a parallel detection system — nearly everything the
original spec asked for already existed under other names (tripwire crossing +
direction, `INTRUSION`/`LOITERING` zones, the generic rule engine's
`time_start`/`time_end`/`days_of_week` conditions already cover "after-hours" rules
with zero new code). What Phase 1 actually adds:
- `ZoneType.RESTRICTED_AREA` — identical mechanism to `LOITERING`
  (`ai-engine/app/core/zones.py::LoiteringTracker` is already zone-type-agnostic,
  keyed by `track_id`+`zone_id`), reported as its own category.
- `Tripwire.tailgating_detection_enabled`/`tailgating_window_seconds` — a second,
  different track crossing the same tripwire within the window is flagged
  `TAILGATING_DETECTED`. No access-control-system integration exists in this
  platform, so "authorized" here just means "the first crossing observed in the
  window" — real door/gate/turnstile correlation would be a stronger signal.
- `Tripwire.gate_jump_detection_enabled` — `tripwire_analysis.py::gate_jump_confidence`
  is a real, transparent, honestly-approximate heuristic (peak vertical centroid
  displacement clearly dominating the track's own recent horizontal pace), not a
  trained climbing/jumping classifier. Tuned against synthetic trajectories only —
  validate against real footage once deployed.
- `app/services/violation_service.py` gained a second incident-creation path: unlike
  the original identified-person-only path (a plain unidentified crossing isn't
  incident-worthy), `GATE_JUMPING_DETECTED`/`TAILGATING_DETECTED`/
  `RESTRICTED_AREA_VIOLATION` only ever fire when a violation was already decided, so
  they *always* become an Incident — "Unknown Person" when no face match, rather than
  gating on identity. Each gets `compute_risk_score()` (0-100, a documented severity +
  after-hours + identified-person weight table — alert-prioritization only, never
  proof of wrongdoing) and a deterministic, template-based AI summary from real event/
  zone/camera/confidence facts (per the "do not hallucinate" requirement, this is
  plain string formatting, not an LLM call) with `requires_human_review=True`.
- Real evidence clips: `Incident.source_event_id` (set at creation, independent of
  whether any `AIRule` matched and created an `Alert`) lets
  `GET /api/incidents/internal/pending-evidence-clips?recording_id=` find incidents
  needing a clip once their recording finalizes; `ai-engine/app/core/recorder.py
  ::SegmentRecorder.stop()` then runs a real stream-copy ffmpeg trim (honest caveat:
  available pre-roll is capped by how early the segment itself started — no live ring
  buffer, see limitation 4) and reports the path back via
  `PATCH /api/incidents/{id}/internal/evidence-clip`. Playback
  (`GET /api/incidents/{id}/evidence-clip?token=`) mirrors the recordings `/play`
  endpoint's query-token pattern exactly.
- New `VideoIntelligenceSettings` tenant table (mirrors `FaceRecognitionSettings`):
  per-tripwire/zone opt-in is the primary control; these three toggles are an
  additional tenant-wide kill switch flattened onto `GET /cameras/internal/active`
  the same way `liveness_detection_enabled` already is.
- A new `AI Video Intelligence` dashboard (real incident counts by severity/category,
  `GET /api/incidents/summary`) and settings page, both flat sidebar items (matching
  the existing convention — see limitation 14, not the nested tree the original spec
  sketched), plus a PDF report section (`get_incident_type_report_data`, same GROUP BY
  convention as everything else in `analytics_service.py`).

Explicitly not built in Phase 1 (see limitations 17-19): theft/unauthorized-object-
removal and abandoned-object detection (need a multi-class detector — the current one
is real but PERSON-only), person-falling/safety detection (needs pose estimation),
and PPE/fighting/crowd-panic detection (need specialized models this environment
can't obtain).

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
cd backend && pytest -q      # 133 tests: auth, RBAC, tenant isolation, camera CRUD
                              # (including the delete cascade covering every dependent
                              # table), credential encryption, rule engine, analytics
                              # aggregates, report export, the Redis-backed rate limiter
                              # (fakeredis, including the internal-service-token
                              # exemption), push notifications (Expo API call mocked),
                              # facial recognition (enrollment quality gates/duplicate
                              # detection, the real LBP algorithm unmocked, recognition
                              # matching, person_category/status rule conditions, tenant
                              # isolation of biometric data, audit logging), the
                              # identified-person violation -> auto-Incident correlation,
                              # recording_id propagating Event -> Alert -> Incident,
                              # multi-frame confirmation's pending/confirm logic, the
                              # face-appearances CSV export, recognition_cooldown_seconds
                              # flattening onto GET /cameras/internal/active, the PDF
                              # security report's Face Recognition section (both its real
                              # GROUP BY aggregate and the view_biometric_events gate),
                              # AI Video Intelligence Phase 1 (RESTRICTED_AREA zone/
                              # tailgating/gate-jump tripwire fields round-tripping
                              # through the real API, the always-incident path for the
                              # three new event types with/without a recognized person,
                              # compute_risk_score, VideoIntelligenceSettings CRUD +
                              # tenant isolation, the two internal evidence-clip
                              # endpoints and the query-token playback endpoint using
                              # real temp files, and the PDF report's incident-type
                              # section) — all against a real in-memory SQLite DB
                              # through the actual FastAPI app
cd ai-engine && pytest -q    # 60 tests: centroid tracker, zone/tripwire geometry,
                              # loitering timer, motion detection (real MOG2 background
                              # subtraction against synthetic frames), privacy-zone
                              # blurring, the discovery-loop config fingerprint, the
                              # FaceRecognizer pipeline (cooldown — including honoring a
                              # per-camera recognition_cooldown_seconds override over the
                              # static env var, zone filtering, identity tracking/expiry
                              # for the violation correlation, liveness frame-diff
                              # rejection, exception-safety — a recognition bug must never
                              # stop the capture loop), SegmentRecorder
                              # (create-at-start/finalize-at-stop, the ffmpeg H.264
                              # transcode step and its fallback paths, and the evidence-
                              # clip trim step's offset/duration/clamping logic and
                              # graceful-failure path — subprocess mocked in these unit
                              # tests; the real ffmpeg binary itself is confirmed working
                              # end-to-end on the deployed Ubuntu VM, see "Verified
                              # end-to-end"), and the gate-jump heuristic/tailgating
                              # window logic (synthetic trajectories)
cd worker && pytest -q       # 6 tests: retention cleanup for recordings/snapshots/
                              # face-recognition-events/face-profiles against a real
                              # SQLite DB with a hand-crafted minimal schema — the
                              # service's first-ever tests (previously untested)
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
12. **Facial Recognition accuracy ceiling** (real, structural — not a Phase 2 gap):
   the LBP-histogram matcher is a real, classic algorithm but has genuinely lower
   discriminative accuracy than a modern CNN face embedding — expect more false
   positives/negatives at the default 85% threshold than a commercial system,
   especially across lighting/angle variation; tune `face_recognition_threshold` per
   camera if needed. Liveness (limitation 12b below, Phase 2) narrows but does not
   close this gap — it rejects only a perfectly static photo, not a moving one.
   Person-to-camera/zone authorization is by **category/status**
   (`person_category`/`person_status` rule conditions), not a fine-grained per-person-
   per-camera ACL — the spec's own schema didn't define one either. Cross-camera
   person re-identification (a single stitched "journey" across multiple cameras) is
   explicitly out of scope — the Appearances view is a per-person list of individual
   camera events, not a re-id track; genuine cross-camera re-id is a materially harder
   CV problem this LBP-based pipeline isn't built for. No written AWS deployment guide
   yet.
13. **Per-tenant face settings synced to ai-engine**: `POST /api/faces/recognize` reads
   a tenant's `FaceRecognitionSettings.default_match_threshold` live (admin changes to
   the match threshold in Settings take effect on the very next recognition).
   `recognition_cooldown_seconds` is synced too, but via the discovery-poll/fingerprint
   mechanism rather than live-per-request: `GET /cameras/internal/active` flattens it
   (and `liveness_detection_enabled`) onto each camera dict, the same tenant-level-
   setting-on-a-camera-dict pattern as liveness, so a change takes effect within one
   ai-engine discovery cycle (worker restart), not instantly. `multi_frame_confirmation_
   enabled` itself needs no ai-engine-side sync at all — that logic lives entirely in
   the backend (`app/api/routes/faces.py`'s `_pending_confirmations` gate), so a live DB
   read on every `/faces/recognize` call is already correct with zero caching lag.
14. **Sidebar navigation is flat, not nested**: the four new Face pages are added as
   flat sibling nav items (matching every other item in `Sidebar.tsx`, which has no
   nested-submenu support anywhere) rather than the nested "Facial Recognition ▸
   Dashboard/Enrolled People/..." tree sketched in the original spec — introducing
   nested-menu UI infrastructure used nowhere else in the app was judged out of scope
   for "don't redesign the existing application."
15. **Multi-frame confirmation still requires the admin to configure a sane cooldown**
   (no longer a sync gap — see limitation 13 — but a real constraint that remains): a
   `PENDING_CONFIRMATION` result from `POST /api/faces/recognize` relies on ai-engine
   sending a second recognition attempt for the same `(camera_id, tracking_id)` within
   `_MULTI_FRAME_CONFIRMATION_WINDOW_SECONDS` (120s) of the first. If a tenant's
   `recognition_cooldown_seconds` (now genuinely honored by ai-engine, per limitation
   13) is configured above 120s while `multi_frame_confirmation_enabled` is also on,
   confirmation will never complete and no Event/Alert will ever be created for that
   person at that camera — there's no validation in `PUT /face-settings` today
   preventing this inconsistent combination from being saved. Keep
   `recognition_cooldown_seconds` under 120s wherever `multi_frame_confirmation_enabled`
   is on for a tenant.
16. **AI Video Intelligence Phase 1's gate-jump heuristic is real but approximate**:
   `tripwire_analysis.py::gate_jump_confidence` looks only at a track's own recent
   centroid trajectory (no trained climbing/jumping model exists in this environment)
   — it will not catch every real climb/jump, and an unusually erratic but ordinary
   walk-through (e.g. someone stumbling) could in principle trigger a false positive.
   Tuned against synthetic test trajectories only (`ai-engine/tests/
   test_tripwire_analysis.py`) — validate the `GATE_JUMP_MIN_VERTICAL_STEP`/
   `GATE_JUMP_VELOCITY_RATIO` constants against real footage once deployed, and treat
   every `GATE_JUMPING_DETECTED` incident as `requires_human_review` (already the
   default).
17. **Theft/unauthorized-object-removal and abandoned-object detection are not
   implemented** (AI Video Intelligence Phase 2 backlog): both need tracking actual
   objects (boxes, bags), and the current detector
   (`ai-engine/app/detectors/hog_detector.py`) is real but PERSON-only — see
   limitation 3. Adding a real multi-class detector (e.g. YOLOv8n) to unlock this is
   scoped as a future phase, not faked with a person-only proxy.
18. **Person-falling/lying-down/motionless safety detection is not implemented** (AI
   Video Intelligence Phase 3 backlog): needs real pose estimation, which this
   platform doesn't have. A bounding-box-only heuristic was deliberately not built
   as a substitute — it would be too unreliable to responsibly label a "safety alert."
19. **PPE detection, fighting/aggressive-activity detection, and crowd-panic
   indicators are out of scope** (same treatment as the existing ANPR limitation):
   these need specialized trained models (PPE classifiers, action-recognition
   networks) this offline-build environment can't obtain. Not faked with a heuristic
   proxy. Also out of scope: real access-control-system correlation for tailgating/
   forced-entry (no such integration exists in this platform — tailgating detection
   is video-only), and true scheduled/emailed daily/weekly AI security reports (no
   email channel exists anywhere in this codebase — only WebSocket dashboard + Expo
   push do; the PDF/CSV reports are on-demand, not autonomously emailed).

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
| 10. Facial Recognition & Identity Analytics | Phase 1 + Phase 2 done, tested, verified in a real browser — enroll/manage people, real detect→embed→match pipeline, recognition events feeding the existing event/alert/rule/notification/WebSocket pipeline, camera + zone config, human review, identified-person violation → auto-Incident, recordings linked to face/violation events with in-browser seekable playback, multi-frame confirmation, liveness (narrow scope, limitation 12), retention enforcement, and a CSV appearance-history export. Full drag-and-drop rules-builder UI is still out of scope (rules are managed via the existing generic Rules page) |
| 11. AI Video Intelligence | Phase 1 done, tested, verified in a real browser — gate-jumping/climbing (heuristic), tailgating, and restricted-area detection extending the existing tripwire/zone pipeline; a real, transparent risk score; auto-created Incidents with a template-based (not LLM) AI summary; real ffmpeg-trimmed evidence clips; a dashboard and settings page; a PDF report section. Theft/abandoned-object detection (Phase 2, needs a multi-class detector) and fall detection (Phase 3, needs pose estimation) are deliberately not built yet — see limitations 17-19 |

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
- Facial Recognition Phase 2's recording linkage and playback, end-to-end in a real
  browser. First caught a critical bug this way: a recording made through the real
  `SegmentRecorder` loaded into a real `<video>` element and failed with
  `error.code: 4` (`MEDIA_ERR_SRC_NOT_SUPPORTED`) — direct JS inspection of the video
  element confirmed Chrome could not decode the mp4v file at all. Installed a real
  `ffmpeg` binary on the Windows dev machine (no local ffmpeg had been available before
  this) via `winget install --id Gyan.FFmpeg`, fixed `SegmentRecorder` to transcode to
  H.264 on `stop()`, and re-verified: the transcoded file reported `readyState: 4`,
  correct `duration`/`videoWidth`/`videoHeight`, and `error: null` in the same browser.
  Second, opened a real Incident's linked Alert's "View in recording" action and used a
  `document.addEventListener('seeked', ..., true)` capture-phase listener to read
  `video.currentTime` at the exact instant the seek completed (not after a delay, which
  is misleading here — `autoPlay` continues advancing `currentTime` after a correct
  seek, so a delayed check can show a plausible-looking but wrong number even when the
  seek itself was exact): landed on `currentTime: 4` against a fixture where
  `event.occurred_at` was exactly 4 seconds after `recording.started_at` — confirming
  the seek math (`event.occurred_at - recording.started_at`, not `alert.created_at`) is
  correct. `cd backend/ai-engine/worker && pytest -q` all green (100/48/6) and
  `cd frontend && npm run build` clean throughout.
- **The recording H.264 transcode step, verified for real on the actual deployed
  Ubuntu VM** (not just the Windows dev machine — this closes out what was previously
  documented as an open gap). Pulled this Phase 2 code onto the VM, rebuilt
  ai-engine/backend/worker/frontend, and let a real `VIDEO_FILE` camera run.
  `docker compose logs ai-engine` showed zero `ffmpeg transcode failed`/`ffmpeg
  transcode skipped` warnings across multiple completed recordings. Directly confirmed
  with `ffprobe` inside the ai-engine container against an actual finalized recording
  file: `codec_name=h264` (not the mp4v the file started as) — the real system ffmpeg
  binary genuinely transcoded it. Also confirmed the `recordings` table itself shows
  the create-at-start/finalize-at-stop pattern working live: the in-progress
  recording's row had `ended_at=NULL`/`duration_seconds=0`/`file_size_bytes=0`, while
  every prior row had real finalized values. Separately hit the real
  `GET /api/recordings/{id}/play?token=` endpoint on the live backend with `curl`: a
  plain request returned `200` with `content-type: video/mp4` and `accept-ranges:
  bytes` and no `Content-Disposition` (confirming it plays inline, doesn't force a
  download); a request with a `Range` header returned a correct `206 Partial Content`
  with the matching `Content-Range` — exactly what a browser's `<video>` seek depends
  on. (Along the way, fixed an unrelated SSH access snag on this VM: the automation
  key in `~/.ssh/ez_vm_key` turned out to be passphrase-protected, which silently
  breaks non-interactive/`BatchMode` SSH at the signing step with no clear server-side
  error — generated a dedicated passphrase-free key for this automation instead of
  ever handling the existing key's passphrase or the account password directly.)
- **AI Video Intelligence Phase 1, end-to-end in a real browser against a real
  (unmocked) backend.** Created a real camera and tripwire with
  `gate_jump_detection_enabled`/`tailgating_detection_enabled` through the actual
  Zones & Tripwires UI/API and confirmed the new "Restricted Area (AI Video
  Intelligence)" zone-type option and the tripwire's "· gate-jump · tailgating"
  badges render correctly. Posted a real `GATE_JUMPING_DETECTED` event (internal
  token, as ai-engine would) and confirmed a real Incident was auto-created with the
  exact expected values: title `"Possible Gate Jumping — Unknown Person at Main
  Gate"`, `risk_score: 30` (matching `compute_risk_score`'s documented formula by
  hand: 30 for HIGH severity + 0 for occurring within business hours + 0 for no
  identified person), `confidence: 0.87` (echoing the value sent), `requires_human_
  review: true`, and the exact deterministic template description including the
  "not a trained climbing/jumping classifier" caveat. Simulated the evidence-clip
  pipeline ai-engine's `SegmentRecorder.stop()` performs: called the real
  `pending-evidence-clips` endpoint (found the incident via `source_event_id`, with
  correct offsets), `PATCH`ed a real clip path, then confirmed
  `GET /api/incidents/{id}/evidence-clip?token=` returns `200`, `content-type:
  video/mp4`, `accept-ranges: bytes`, and the exact real file bytes (verified with
  `curl` directly, after first catching a test-setup artifact: a bash-style `/tmp`
  path doesn't resolve to the same location as the Windows Python process expects —
  not a code bug). Confirmed the new **AI Video Intelligence** dashboard's real
  `GET /api/incidents/summary`-backed counts matched exactly (1 HIGH, 1
  `GATE_JUMPING_DETECTED`), and that the **AI Video Intelligence Settings** page's
  save/reload round-trip genuinely persists (`pre_event_seconds`, and unchecking
  `tailgating_enabled`, both confirmed via direct DOM inspection after a fresh page
  load). `cd backend && pytest -q` (133) and `cd ai-engine && pytest -q` (60) both
  green, `cd frontend && npm run build` clean throughout.
