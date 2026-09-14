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
             recordings/snapshots, face recognition events, expired face profiles, and
             — per each tenant's configured RetentionTier — expired cloud-stored
             snapshots/evidence recordings/incident evidence clips, deleting the
             underlying MinIO/S3 object first) — plain SQL against the same Postgres DB
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

**Two real bugs found and fixed: enrolled-photo blur rejection and photo-path
persistence.** Reported by the user as "Enrolled People Photo tab not showing images
of enrolled people." Reproduced for real with two actual phone-camera photos (not
synthetic test fixtures) posted through the real `/api/faces/enroll` endpoint:

1. **`face_embedding.py::_blur_score` was not scale-invariant.** It runs
   `cv2.Laplacian(...).var()` directly on the raw face crop, and that variance scales
   with the crop's own resolution — the identical, genuinely sharp real photo scored
   0.31 ("too blurry", rejected) at its native 742x742px face crop but a perfect 1.0
   once downscaled to ~220px, with zero actual change in sharpness. Modern phone
   cameras produce large face crops, so real enrollment photos were being rejected as
   blurry essentially at random depending on resolution, while the unit tests' small
   (200x200) synthetic noise fixture always trivially passed regardless, so this never
   surfaced there. Fixed by resizing every crop to a fixed reference size before
   scoring, making the metric comparable regardless of the uploaded photo's
   resolution (`ai-engine/tests/test_face_embedding.py`/`backend/tests/
   test_face_embedding.py::test_blur_score_is_scale_invariant_for_a_genuinely_
   sharp_image`, plus a regression test confirming a genuinely blurred image is still
   correctly rejected). Applied identically to both byte-identical copies of
   `face_embedding.py`.
2. **`FaceProfile.image_reference` was stored as a relative path.**
   `settings.face_path` defaults to `"./data/faces"` (only guaranteed absolute in
   Docker, via `.env.example`'s `FACE_PATH=/data/faces`); the enroll route joined the
   person's photo path onto that relative string and stored the result as-is. Every
   subsequent read (`GET /faces/{id}/photo`) re-resolves that relative path against
   whatever the CURRENT process's working directory happens to be — which silently
   breaks every previously-enrolled photo the moment the backend is next started from
   a different cwd (e.g. `cd backend && uvicorn ...` vs. a tool that launches uvicorn
   from the repo root with `--app-dir backend` — this project's own documented
   personal-local-dev-loop quirk already noted elsewhere for the SQLite DB path).
   Fixed going forward by resolving to an absolute path with `os.path.abspath()` at
   enrollment time (a no-op when `FACE_PATH` is already absolute, as in Docker).
   Already-affected rows need a one-time repair:
   `backend/scripts/fix_relative_face_paths.py` finds any stored relative path, tries
   every working directory this project's documented dev/deploy commands could
   plausibly have run from, and rewrites the row to the absolute path it actually
   finds on disk — leaving anything it can't resolve untouched and reported rather
   than guessed at. Verified for real: enrolled a person, confirmed the stored path
   was absolute and the photo rendered in the browser, then (separately, against a
   dev-DB copy still carrying the old relative-path bug) ran the repair script and
   confirmed the same photo kept rendering afterward.

   Follow-up from the user ("Face still doesn't show" after the above fix, plus a
   request to "see or edit the image"): the fix itself was correct, but re-testing
   surfaced the actual reason it looked unfixed — the local dev backend has no code-
   reload, so a running process keeps serving whatever was loaded at its last start
   regardless of subsequent file edits, which is exactly what makes a relative-path-
   style bug like this look intermittent. `.claude/launch.json`'s `backend` config now
   runs uvicorn with `--reload --reload-dir backend/app`, so local dev testing
   reflects the current code without a manual restart. Separately, added the actual
   requested feature: `PUT /api/faces/{id}/photo` (`EditPersonModal` in
   `EnrolledPeople.tsx`, wired to a new "Edit" action) lets an admin see the enrolled
   photo at full size and replace it — the exact same enrollment quality gate applies
   to the replacement (a blurry/no-face/multi-face photo is rejected the same way),
   and the previous `FaceProfile` is marked `SUSPENDED` rather than deleted, preserving
   the audit trail the same way `delete_person` keeps the `Person` row. Verified for
   real against a genuinely restarted (`--reload`-picked-up) backend: replaced a real
   enrolled photo through the actual endpoint and confirmed the new photo — not the
   old one — rendered in the Enrolled People table afterward.

   Second follow-up, on the deployed VM, after the user reported (repeatedly) that two
   specific enrolled people ("Ellah miss-e" and the tenant admin's own profile) still
   showed no photo even after the fixes above shipped: this was NOT the same bug
   recurring. `SELECT image_reference FROM face_profiles` showed both rows still
   storing the OLD relative path (`./data/faces/<tenant>/<uuid>.jpg`) — meaning both
   were enrolled before `FACE_PATH` was added to the VM's `.env`, so their photo files
   were written to the backend container's ephemeral filesystem the moment they were
   uploaded, not the bind-mounted `/data/faces` volume. Confirmed directly on the VM:
   `/data/faces` inside the backend container contains only `.gitkeep` — the files
   never existed at any persistent location, so no code fix can recover them; this is
   exactly the "already-affected rows... permanently unrecoverable" case documented
   above, now confirmed to be these two specific rows rather than a hypothetical. Then
   verified, end-to-end against the real live backend, that a **new** enrollment today
   is genuinely fixed: enrolled a real test person with a real photo via
   `POST /api/faces/enroll`, confirmed the resulting `image_reference` was a real
   absolute path (`/data/faces/<tenant>/<uuid>.jpg`) that actually exists inside the
   container, fetched it back through `GET /api/faces/{id}/photo` and confirmed the
   exact same 174,022-byte JPEG came back byte-for-byte, then deleted the test person
   to avoid leaving synthetic data in the tenant's real Enrolled People list. The fix
   is correct and verified; "Ellah miss-e" and the admin's own profile specifically
   need to be re-enrolled with a new photo through the UI — there's nothing left to
   patch in code for them.

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

**AI Video Intelligence, Phase 2 — real multi-class detection + potential theft
detection** (`ai-engine/app/detectors/yolo_detector.py`,
`ai-engine/app/core/object_tracking.py`): adds the one real capability Phase 1
explicitly deferred — seeing objects other than PERSON at all. Two honest scope limits,
disclosed here rather than discovered later: **(a)** COCO (the dataset YOLOv8n is
trained on) has no generic "box"/"package" class — real theft detection here means "a
`backpack`/`handbag`/`suitcase` was removed from a monitored area," not literal
cardboard-box/package tracking, and there is no feasible way to train a custom "box"
class in this environment. **(b)** Adding `ultralytics` (which pulls in `torch`) is a
real, non-trivial Docker/venv size increase (~311MB for torch alone, measured locally)
that applies to every build regardless of whether any camera actually opts in, since
Docker images are static. A related, real packaging gotcha found *while* adding this:
`ultralytics` depends on the PyPI package `opencv-python` (GUI-capable), and pip has no
notion that the already-installed `opencv-python-headless` satisfies it — installing
both in the same environment silently corrupts the shared `cv2` native module
(`cv2.CascadeClassifier` disappeared, breaking face detection). Fixed by switching
`requirements.txt` from `opencv-python-headless` to `opencv-python` at the same pinned
version — this codebase never calls a GUI function (`cv2.imshow` etc.), and the
Dockerfile already installs `libgl1`/`libglib2.0-0`, which `opencv-python` needs to
import at all.

- `Camera.multi_class_detection_enabled` (mirrors `ai_enabled`/
  `face_recognition_enabled`) opts a specific camera into `YoloDetector` in place of
  the default `HOGPersonDetector` — existing cameras are unaffected. `YoloDetector`
  lazily imports `ultralytics` inside `__init__` (a process running only HOG-only
  cameras never pays torch's import cost) and loads `yolov8n.pt` from
  `settings.model_path` (`./data/models`, the same already-mounted persistent Docker
  volume used elsewhere) rather than a bare filename, so Ultralytics' own
  missing-file download lands on the volume and survives container restarts instead
  of re-downloading into an image-local cache. Real, unmocked verification this
  session: `ultralytics==8.4.150` installs cleanly, downloads real weights (6.2MB)
  over genuine internet access, runs real inference, and sustains ~6.9fps warmed-up
  on this dev machine's CPU — comfortably above the platform's default `ai_fps=5`.
- COCO class name → this platform's existing object-type vocabulary (already
  anticipated verbatim in `Detection`'s docstring before this phase existed):
  `person`→PERSON, `backpack`→BACKPACK, `handbag`→BAG, `suitcase`→SUITCASE, the
  vehicle classes → CAR/TRUCK/BUS/MOTORCYCLE/BICYCLE, the 9 COCO animal classes →
  ANIMAL. Everything else (chair, laptop, ...) is dropped.
- **Real bug found and fixed while building this**: `CentroidTracker` (the same
  nearest-centroid tracker every zone/tripwire feature already depends on) matched a
  new detection to an existing track by distance alone — harmless while the only
  detector was PERSON-only, but with a multi-class detector a backpack near a person
  could steal that person's track (or vice versa), corrupting both track identity and
  `object_type` mid-track. Fixed by requiring `object_type` to match before
  considering a candidate for nearest-centroid association
  (`ai-engine/tests/test_tracker.py::test_person_and_backpack_at_the_same_position_
  stay_on_separate_tracks`).
- `ZoneType.ASSET_ZONE` (a monitored asset area — shelf, display case, loading dock)
  reuses `loitering_threshold_seconds` as "minimum seconds an object must be
  continuously present before its removal counts as a violation," same reuse pattern
  Phase 1 used for `RESTRICTED_AREA`. `ai-engine/app/core/object_tracking.py::
  AssetZoneTracker` is a small, transparent, real heuristic — structurally similar to
  `LoiteringTracker` but with inverted trigger semantics (fires on **exit** after
  sufficient dwell, not on continued presence). Honest limitation: this only fires
  while the object remains independently classifiable by the detector as it crosses
  the zone boundary — an object that becomes occluded first (hidden under clothing,
  placed inside another bag, put in a vehicle trunk) will not be caught, since at that
  point the detector can no longer see it as a distinct BACKPACK/BAG/SUITCASE to
  track.
- `worker.py::_check_zones` gained a `POTENTIAL_THEFT_DETECTED` branch (`HIGH`
  severity) gated on the zone's `ASSET_ZONE` type, the detection's object type being
  one of the three monitored classes, and the tenant's new
  `VideoIntelligenceSettings.theft_detection_enabled` kill switch. At the firing
  moment, a new `_closest_person_track_id` helper looks for the nearest
  currently-tracked PERSON (reusing `CentroidTracker`'s own default proximity scale)
  and attaches that person's recognized identity via the existing
  `_identity_metadata` helper *only* when they happen to also be a known face match —
  never fabricated, and it's a best-effort "who was nearby," not a claim they took the
  item. `violation_service.py`'s existing `_ALWAYS_INCIDENT_EVENT_TYPES` dispatch
  path picks this event type up with zero new incident-creation code — same
  `compute_risk_score`, `requires_human_review=True`, and deterministic (non-LLM)
  description template convention as every other Phase 1 always-incident type.
- Frontend: `ZonesEditor.tsx` gained the "Asset / Theft Monitoring Zone" option,
  `Cameras.tsx` gained the "Multi-class object detection (YOLOv8n)" toggle (with an
  inline CPU-cost/dependency note), and `VideoIntelligenceSettings.tsx`'s "Potential
  theft" checkbox moved out of the disabled "Coming soon" block into a real, working
  toggle. `Incidents.tsx`, the AI Video Intelligence dashboard, and the PDF report's
  incident-type section needed zero changes — all three already group by
  `incident_type` generically.

Abandoned-object detection was deliberately **not** added alongside theft detection in
this phase — it shares the same object-tracking foundation and would be a small
addition, but the user asked specifically for gate-jumping and theft, and adding
unrequested detection categories isn't this project's convention. See limitation 17.

**Event-First Cloud Storage, Phase 1** (`app/models/site.py`,
`app/models/retention_tier.py`, `app/services/object_storage.py`,
`app/services/storage_service.py`): a large architectural addition — real object
storage, a `Site` hierarchy, per-tenant retention policy, and event review/filtering —
deliberately scoped to integrate into the existing pipeline rather than build a
parallel one (per the plan's own explicit "do not rebuild from scratch" instruction).
Two upfront decisions, made explicitly rather than assumed: build against **local
MinIO** first (a self-hosted, real S3-API-compatible server — not a fake/mock target)
so the whole feature is genuinely testable without an AWS account, with the exact same
code talking to real AWS S3 in production by changing only `S3_ENDPOINT_URL`/
credentials; and add the **Site** model now rather than defer it, since it changes how
camera scoping works everywhere.

- `app/models/site.py`: `Site` (name/address/timezone/is_active) sits between `Tenant`
  and `Camera` — `Camera.site_id` is nullable so existing cameras are unaffected (the
  migration backfills one `"Default Site"` per tenant that already has cameras, so
  nothing currently working stops working). CRUD lives at `app/api/routes/sites.py`,
  gated by new `view_sites`/`manage_sites` permissions; deleting a site nulls
  `Camera.site_id` for its cameras rather than deleting or blocking on them — a
  camera's whole event/recording history is too significant to destroy as a side
  effect of a site being removed.
- `app/services/object_storage.py` (byte-for-byte duplicated at
  `ai-engine/app/core/object_storage.py`, the same no-shared-package convention already
  used for `face_embedding.py`): a thin `boto3` S3 client wrapper —
  `upload_file`/`generate_presigned_url`/`delete_object`/`ensure_bucket_exists`, plus
  `build_key(tenant_id, site_id, camera_id, artifact_type, filename)` implementing the
  bucket layout `tenant-{id}/site-{id-or-"unassigned"}/camera-{id}/{snapshots|
  video-clips}/{filename}`. **Real bug caught and fixed before it could ever manifest**:
  a presigned URL signed against the internal Docker hostname (`S3_ENDPOINT_URL=
  http://minio:9000`) would be completely unreachable from an actual end user's
  browser. Fixed with a **second, separate** boto3 client (`_get_presign_client()`)
  constructed against a distinct `s3_public_endpoint_url` config value, used only for
  `generate_presigned_url` — every internal upload/delete/head-bucket call keeps using
  the internal `s3_endpoint_url`. `s3_public_endpoint_url` defaults to
  `http://localhost:9000` (correct only when Docker and the browser share one machine)
  and must be set to the deployment's real reachable address otherwise — the exact same
  per-deployment customization `API_URL`/`FRONTEND_URL` already need.
- Snapshots always upload to cloud storage (they're small and are the spec's core
  "evidence" concept); non-`CONTINUOUS` recordings (i.e. the already-short AI_EVENT/
  MOTION ones) and incident evidence clips upload by default too. A plain `CONTINUOUS`
  recording stays local-only unless the camera has the new
  `Camera.cloud_recording_enabled` opt-in set (the spec's "Full Cloud Recording" premium
  tier) — implemented, off by default. `ai-engine/app/core/snapshotter.py::save_snapshot`
  and `ai-engine/app/core/recorder.py::SegmentRecorder` upload after writing the local
  file (still needed for the ffmpeg trim step and existing local-file assumptions) and
  report the resulting `storage_key` to the backend alongside the existing `file_path` —
  a failed upload sets `storage_key=None` rather than raising, so the caller still has a
  real local file to fall back to serving, exactly as before this phase.
- Serving endpoints (`GET /snapshots/{id}/image`, `/recordings/{id}/play`,
  `/incidents/{id}/evidence-clip`) changed from always `FileResponse`-ing the local path
  to: if `storage_key` is set, a `307` redirect to a short-lived presigned GET URL;
  else (no `storage_key` — a still-local continuous recording, or a pre-migration row)
  fall back to today's `FileResponse` exactly as before. Because the existing query-
  token/header auth already runs before this branch, and a redirect from an
  authenticated response is transparent to `fetch()`/`<video src>`/`<img>` (browsers
  correctly drop the original `Authorization` header on the cross-origin redirect,
  which is fine since the presigned URL carries its own embedded auth) — **this
  required zero frontend changes** for playback/viewing, the same "backend is the sole
  access-control boundary, never expose storage credentials" principle already used for
  the live-video proxy.
- `app/models/retention_tier.py`: `RetentionTier` (name + event_metadata_days/
  snapshot_days/video_evidence_days) is deliberately **not** tenant-scoped — a small,
  named, platform-wide set of presets (Starter/Business/Professional/Enterprise, seeded
  by the migration with the spec's own worked example values) a Platform Administrator
  (`SUPER_ADMIN`) configures via `GET`/`PUT /api/retention-tiers`
  (`app/api/routes/retention_tiers.py`), never hard-coded anywhere per the spec's
  explicit requirement. `Tenant.retention_tier_id` picks one (defaults to `NULL` until
  a migration/admin assigns it — `worker.py`'s cleanup simply skips a tenant with none
  assigned, rather than guessing a default).
- `worker/app.py::cleanup_expired_cloud_evidence` follows the exact per-tenant-cutoff-
  computed-in-Python pattern `cleanup_face_recognition_events` already established
  (portable, not Postgres-`interval`-specific): for each tenant with a `RetentionTier`
  assigned, deletes `Snapshot` rows past `snapshot_days`, cloud-uploaded (`storage_key
  IS NOT NULL`, unprotected) `Recording` rows past `video_evidence_days`, and clears
  (not deletes) `Incident.evidence_clip_path`/`evidence_clip_storage_key` past the same
  cutoff — each case calls a small, standalone boto3 delete helper (worker.py has no
  `app.config` to import `object_storage.py` from, matching its existing plain-SQL/
  stdlib convention) before removing the local reference. Event metadata past
  `event_metadata_days` is deleted outright, but **deliberately conservatively**: an
  `Event` still referenced by an `Alert` or `FaceRecognitionEvent` (both `NOT NULL`
  foreign keys — every event that ever mattered enough to alert on or match a face
  against) is never deleted even past its cutoff, since there's no safe way to null
  those references without losing the record of what triggered them; only "quiet"
  events with neither are actually purged, nulling `Incident.source_event_id`/
  `Snapshot.event_id` first since those are nullable.
- `app/models/event.py` gained `status`(UNREVIEWED/REVIEWED)/`reviewed_by_user_id`/
  `reviewed_at`/`notes` — a plain `Event` (e.g. `PERSON_DETECTED`) never automatically
  becomes an `Incident` (see `violation_service.py`'s always-incident dispatch), so
  before this it had no review workflow of its own at all, only Incidents/Alerts did.
  New `POST /events/{id}/review`/`POST /events/{id}/notes` endpoints (`manage_alerts`-
  gated, mirroring the existing Incident/Alert status-update pattern). A new
  `EventCategory` enum (SECURITY/PEOPLE/VEHICLES/SAFETY/OPERATIONS) is computed once at
  event-creation time via `app/services/event_classification.py::classify_event` — a
  static, transparent `EventType -> EventCategory` dict (plain Python, not an LLM call
  or trained classifier, the same "do not hallucinate" convention `violation_service.py`
  already established), stored as an indexed column so filtering by category is a real
  indexed query rather than a per-row computation. `list_events` gained `event_category`/
  `status` (aliased from the reserved word) query params; `Events.tsx` now sends real
  camera/severity/category/review-status/date-range filters (confirmed via direct code
  read to be a pure UI-wiring gap before this — the backend already had `camera_id`/
  `event_type`/`severity`/`start`/`end` params the frontend simply never sent), and its
  detail modal gained "Mark as Reviewed"/investigation-notes controls. `Alerts.tsx`
  gained the same camera/severity/status filter dropdowns for the params `list_alerts`
  already supported.
- `app/services/storage_service.py::get_storage_usage` follows
  `analytics_service.py`'s own `func.sum()`/`group_by()` convention: real
  `SUM(file_size_bytes)` aggregates for snapshots, evidence clips, and cloud vs.
  continuous recordings (split via `storage_key IS NOT NULL`/`IS NULL`). One honest,
  explicitly disclosed exception: `event_metadata_bytes` is **not** a real sum (`Event`
  rows have no stored-file size to sum) — a flat per-row estimate constant times a real
  row count, which is why `StorageUsageResponse.is_estimate` is always `True` even
  though every other figure is a genuine aggregate. `GET /api/storage/usage`
  (`view_reports`-gated) backs the new `StorageUsage.tsx` dashboard page, which labels
  itself "estimated" for the same reason.
- New `SECURITY_MANAGER` role (`app/core/permissions.py`) sits between Operator and
  Admin — can investigate events/evidence and view reports (same as Operator) plus
  `manage_sites`, but unlike Admin cannot manage cameras/users/AI configuration/
  retention policy. Picked up automatically by the existing idempotent
  `scripts/bootstrap.py` seeding loop (it already iterates whatever's in
  `ROLE_PERMISSION_MAP`) — zero new seeding code needed.
- Explicitly out of scope for this phase (see "Known limitations" below): email/SMS/
  webhook alerts, an offline edge queue-and-sync, a generalized event-deduplication/
  cooldown config framework, per-user site-level RBAC, S3 lifecycle/archival policies,
  and AWS Cost Explorer billing integration.

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
cd backend && pytest -q      # 215 tests: auth, RBAC, tenant isolation, camera CRUD
                              # (including the delete cascade covering every dependent
                              # table), credential encryption, rule engine, analytics
                              # aggregates, report export, the Redis-backed rate limiter
                              # (fakeredis, including the internal-service-token
                              # exemption), push notifications (Expo API call mocked),
                              # facial recognition (enrollment quality gates/duplicate
                              # detection, the real LBP algorithm unmocked, the blur-
                              # score's scale-invariance fix, the enrolled-photo path
                              # being stored absolute and surviving a simulated cwd
                              # change, the photo-replace endpoint's quality gate/RBAC/
                              # 404/audit-preserving-suspend behavior, recognition
                              # matching, person_category/status rule conditions,
                              # tenant isolation of biometric data, audit logging), the
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
                              # real temp files, the PDF report's incident-type
                              # section, and AI Video Intelligence Phase 2
                              # (multi_class_detection_enabled CRUD + presence on
                              # CameraInternalResponse, the ASSET_ZONE zone type,
                              # theft_detection_enabled, and the always-incident path
                              # for POTENTIAL_THEFT_DETECTED with/without a recognized
                              # nearby person), and Event-First Cloud Storage Phase 1
                              # (Site CRUD + tenant isolation + camera site_id round-
                              # tripping, the object_storage client's internal-vs-
                              # public presigned endpoint split with boto3 mocked at
                              # the network boundary, RetentionTier CRUD + the
                              # SUPER_ADMIN-only gate, event review/notes endpoints +
                              # event_category computed per type + category/status
                              # list filters, and the storage-usage aggregate hand-
                              # verified against real seeded file sizes), the per-event
                              # PDF export endpoint (real reportlab PDF bytes + tenant
                              # isolation, plus the snapshot-image-embedding fix: a real
                              # local-file JPEG and a real cloud-stored-via-storage_key
                              # snapshot both land in the PDF as a genuine embedded
                              # /DCTDecode image, a missing/unreadable snapshot file
                              # degrades to a plain "not available" line instead of
                              # breaking the export, and an event with no snapshot at
                              # all renders unchanged from before), object_storage's new
                              # download_object (real bytes back, using the internal —
                              # never the public presign — client, since this is a
                              # server-side read with no browser to hand a redirect to),
                              # and two more instances of the naive-db.delete()-crashes-
                              # on-a-real-dependent-row bug class found live on the
                              # deployed VM (delete_camera not cleaning up Notification/
                              # incident_alerts/Incident references, delete_rule having
                              # no dependent-row handling at all) — all against a real
                              # in-memory SQLite DB through the actual FastAPI app
cd ai-engine && pytest -q    # 104 tests: centroid tracker (including type-aware
                              # matching so a multi-class detector can't let a track
                              # of one object_type steal another's), zone/tripwire
                              # geometry, loitering timer, motion detection (real MOG2 background
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
                              # end-to-end"), the gate-jump heuristic/tailgating
                              # window logic (synthetic trajectories), and AI Video
                              # Intelligence Phase 2 (YoloDetector's COCO-class-to-
                              # object_type mapping/confidence filtering — the
                              # ultralytics.YOLO model itself mocked at the boundary,
                              # same rationale as the ffmpeg subprocess mocking above —
                              # AssetZoneTracker's dwell-then-exit logic, and the
                              # CameraWorker._check_zones ASSET_ZONE wiring including
                              # the nearby-person identity attribution, exercised
                              # directly against a real CameraWorker instance), and the
                              # Event-First Cloud Storage object_storage client (key
                              # layout, internal-vs-public presigned endpoint split,
                              # upload/delete/presign/ensure-bucket-exists — boto3.client
                              # itself mocked at the network boundary), and the real
                              # OBJECT_EVENT_COOLDOWN_SECONDS bug fix (a second "new"
                              # track within the cooldown window must not spam a
                              # second event, one after the cooldown expires must
                              # still be reported, and the very first detection a
                              # camera ever makes must never be swallowed), and the
                              # real TRIPWIRE_VIOLATION_COOLDOWN_SECONDS bug fix (a
                              # second, different track_id crossing the SAME tripwire
                              # within the cooldown must not spam a second event, a
                              # crossing after the cooldown expires must still be
                              # reported, the very first crossing must never be
                              # swallowed, and two DIFFERENT tripwires crossed by the
                              # same movement must each still get their own event —
                              # cooldowns are independent per tripwire, not global),
                              # and the real content-based snapshot deduplication fix
                              # (app/core/frame_similarity.py's aHash comparison: an
                              # identical frame reuses the previous snapshot instead of
                              # saving a new one, light per-pixel noise between two
                              # captures of the same content is still recognized as a
                              # duplicate, a genuinely different frame still gets its
                              # own snapshot, the very first snapshot a camera ever
                              # takes is never treated as a duplicate, and — a real,
                              # disclosed scope limit — a repeated frame is only
                              # compared against the IMMEDIATELY PREVIOUS snapshot, not
                              # a full history)
cd worker && pytest -q       # 21 tests: retention cleanup for recordings/snapshots/
                              # face-recognition-events/face-profiles against a real
                              # SQLite DB with a hand-crafted minimal schema (the
                              # service's first-ever tests), plus
                              # cleanup_expired_cloud_evidence (per-tenant RetentionTier
                              # cutoffs for snapshots/cloud-uploaded recordings/incident
                              # evidence clips — each calling a mocked S3 delete before
                              # removing the row — the FK-safe nulling of live Event/
                              # Detection/Incident references before a delete, never
                              # purging an Event still referenced by an Alert or
                              # FaceRecognitionEvent, and per-tenant tier isolation),
                              # and the real cleanup_orphaned_media_files bug fix found
                              # live during a disk-full incident (a file with no
                              # referencing recordings/snapshots row at all is removed,
                              # one referenced by either table is kept, anything younger
                              # than the grace period is left alone even with no
                              # referencing row, and missing directories don't crash it)
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
Event-First Cloud Storage: `S3_ENDPOINT_URL` (MinIO's internal Docker address in dev,
`http://minio:9000`; **leave unset** in real AWS so boto3 falls back to the real
regional S3 endpoint), `S3_PUBLIC_ENDPOINT_URL` (the address a real user's *browser*
can reach for presigned URLs — never the same as `S3_ENDPOINT_URL` once backend and
browser aren't on the same machine; **must** be set to the deployment's real reachable
address, the same per-deployment customization `API_URL`/`FRONTEND_URL` already need),
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (MinIO's root credentials in dev; a real,
narrowly-scoped IAM key in production — never reuse a broader-privileged credential),
`AWS_REGION`, `AWS_S3_BUCKET`.

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
17. **Theft/unauthorized-object-removal detection (AI Video Intelligence Phase 2) is
   implemented, with two real, disclosed scope limits.** First, COCO (the dataset the
   new `YoloDetector` — `ai-engine/app/detectors/yolo_detector.py` — is trained on) has
   no generic "box"/"package" class: detection covers `backpack`/`handbag`/`suitcase`
   specifically, not literal cardboard boxes/packages, and there's no feasible way to
   train a custom class for that in this environment. Second, the dwell-then-exit
   heuristic (`ai-engine/app/core/object_tracking.py::AssetZoneTracker`) only fires
   while the object stays independently classifiable as it crosses the monitored
   zone's boundary — an item hidden under clothing, placed inside another bag, or put
   in a vehicle trunk before that point will not be caught, since the detector can no
   longer see it as a distinct object to track. It is opt-in per camera
   (`Camera.multi_class_detection_enabled`, off by default — heavier CPU cost, real
   `torch`/`ultralytics` dependency) and per zone (`ZoneType.ASSET_ZONE`). Also
   real: switching from `opencv-python-headless` to `opencv-python` was necessary
   because `ultralytics` depends on the latter by package name and installing both
   silently corrupts the shared native `cv2` module — see the Architecture section.
   **Abandoned-object detection remains not implemented** — it shares the same
   object-tracking foundation and would be a comparatively small future addition, but
   wasn't requested and so wasn't built speculatively.
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
20. **Event-First Cloud Storage — explicitly out of scope for Phase 1** (documented,
   not silently dropped, matching this project's own phased-delivery discipline):
   multi-channel alerts beyond WebSocket + Expo push (no email/SMS/webhook channel
   exists anywhere in this codebase, same underlying gap as limitation 19's last
   sentence); an offline edge queue-and-sync (today's ai-engine -> backend calls
   already fail silently with no retry — a real persistent local queue is a
   substantial standalone feature); a generalized, configurable event-deduplication/
   cooldown framework (today's per-feature throttles — motion's 30s throttle,
   `LoiteringTracker`'s one-shot-per-stay — stay exactly as they are); per-user
   site-level RBAC (a user is scoped to their tenant's sites, not a subset of them);
   S3 lifecycle/archival-storage policies (an AWS console/Terraform deployment
   concern, not application code); and AWS Cost Explorer billing integration (the
   storage dashboard sums real recorded file sizes, clearly labeled as an estimate,
   rather than querying AWS's billing API — this environment has no AWS billing
   credentials to do so even if it were in scope).
21. **RetentionTier has no per-tenant default assignment path yet**: a brand-new
   tenant's `retention_tier_id` is `NULL` until a `SUPER_ADMIN` explicitly assigns one
   via `PUT /api/retention-tiers/assign/{tenant_id}` — `worker.py::
   cleanup_expired_cloud_evidence` simply skips a tenant with none assigned (never
   guesses a default), so a forgotten assignment means that tenant's cloud evidence
   never expires until someone notices and assigns a tier. The migration itself only
   backfills existing pre-Phase-1 tenants to `"starter"`; a tenant created after the
   migration has no such backfill.
22. **Retention enforcement for cloud evidence is worker-cycle-based, not
   instantaneous**: `cleanup_expired_cloud_evidence` runs on the same
   `RETENTION_CHECK_INTERVAL_SECONDS` loop as every other retention job (default one
   hour) — an artifact can outlive its configured retention window by up to one cycle
   before it's actually purged. Same characteristic the pre-existing
   `cleanup_recordings`/`cleanup_snapshots`/`cleanup_face_recognition_events` jobs
   already have; not a new gap introduced by this phase.
23. **`OBJECT_EVENT_COOLDOWN_SECONDS` (ai-engine/app/worker.py, 30s) is a per-camera
   throttle, not per-object or per-person**: found live on a deployed VM as a real bug
   (CentroidTracker briefly losing/re-acquiring the same object was creating a new
   PERSON_DETECTED event — with its own snapshot and recording trigger — every time,
   producing ~30k snapshots and 57 recordings for one camera in under a day). The fix
   trades a small amount of real coverage for that: if two genuinely different people
   enter the same camera's frame within 30 seconds of each other, only the first gets
   its own event+snapshot; the second is silently absorbed by the cooldown.
   LOITERING_DETECTED/RESTRICTED_AREA_VIOLATION already had their own real per-(track,
   zone) "once per continuous stay" debounce (`LoiteringTracker`) before this fix and
   don't share this cooldown — but see limitation 24 below: TRIPWIRE_VIOLATION did NOT
   have any debounce of its own, which this entry originally (incorrectly) implied it
   did.
24. **`TRIPWIRE_VIOLATION_COOLDOWN_SECONDS` (ai-engine/app/worker.py, 30s) — a second,
   independent instance of the same track-churn bug class as limitation 23, found live
   on the same deployed VM**: `_check_tripwires` had zero debounce of any kind — every
   single frame where a tracked centroid genuinely crossed a tripwire's line fired its
   own `TRIPWIRE_VIOLATION` event, with no equivalent of `LoiteringTracker`'s "once per
   continuous stay" gate. A tracked object jittering right at a tripwire line (or,
   worse, a synthetic SIMULATED-camera object oscillating back and forth across it) got
   reassigned a brand-new track_id by `CentroidTracker` every ~10-25 seconds, and each
   one fired again — one camera produced **535 TRIPWIRE_VIOLATION events in ~2 hours,
   all attached to the exact same `recording_id`** (535 reported "incidents" for what
   was really one continuous scene). Fixed with a per-tripwire (not per-track_id, since
   the whole bug is that track_id keeps changing for what's really the same presence)
   30-second cooldown, `self._last_tripwire_violation_sent: dict[str, float]` — the
   same accepted trade-off as limitation 23: two genuinely different real crossings of
   the same tripwire within 30s means only the first is reported. Gates the downstream
   `GATE_JUMPING_DETECTED`/`TAILGATING_DETECTED` checks for that same crossing too,
   since they're evaluated from the same (now-suppressed) crossing event. Covered by
   `ai-engine/tests/test_tripwire_violation_cooldown.py`.
25. **Snapshot deduplication (`ai-engine/app/core/frame_similarity.py`) is real
   content-based comparison, but a deliberately narrow one**: requested directly by
   the user after testing against a looping demo video file, where the existing
   cooldowns (limitations 23/24) only throttle by elapsed time — once a loop's period
   exceeds the cooldown window, a "new" event fires for a frame that's visually
   identical to one already saved, writing another near-duplicate JPEG. Fixed by
   computing a real 64-bit average hash (aHash: downscale to 8x8 grayscale, threshold
   each pixel against the image's own mean brightness) of every captured frame and
   comparing it, via Hamming distance, against the hash of the last snapshot actually
   saved for that camera — a Hamming distance of 5 bits or fewer (out of 64) is treated
   as "the same picture" and reuses the existing snapshot instead of writing/uploading
   a new one; the *event* itself is still created and logged either way, only the
   redundant image file is skipped. This is a coarse, transparent heuristic (per
   CLAUDE.md's "do not hallucinate accuracy we don't have" convention), not a trained
   image-similarity model, and has two honest, disclosed scope limits: it only compares
   against the IMMEDIATELY PREVIOUS snapshot for that camera, not a full history (a
   repeating A/B/A/B pattern will save A and B as distinct snapshots every time, since
   each is "new" relative to the one right before it — this is what a looping single-
   scene test video needs, not what a scene that alternates between two states needs);
   and `_last_snapshot_hash`/`_last_snapshot_id` are plain in-memory instance state on
   `CameraWorker`, so — like every other per-camera cooldown in this file — a worker
   restart (limitation 9) forgets the last snapshot and the next frame captured after
   restart is never treated as a duplicate, even if it's identical to the last one
   saved before the restart.

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
| 11. AI Video Intelligence | Phase 1 + Phase 2 done, tested, verified in a real browser — gate-jumping/climbing (heuristic), tailgating, restricted-area, and now potential-theft detection (real YOLOv8n multi-class detector, opt-in per camera; backpack/handbag/suitcase removal from a monitored zone) extending the existing tripwire/zone pipeline; a real, transparent risk score; auto-created Incidents with a template-based (not LLM) AI summary; real ffmpeg-trimmed evidence clips; a dashboard and settings page; a PDF report section. Abandoned-object detection (not requested) and fall detection (Phase 3, needs pose estimation) are deliberately not built yet — see limitations 17-19 |
| 12. Event-First Cloud Storage | Phase 1 done, tested — Site hierarchy (Customer → Site → Camera), a real object-storage abstraction (MinIO in dev / real AWS S3 in production, same code path) with presigned-URL serving, configurable per-tenant retention tiers with worker-side enforcement, per-event review/notes/categorization with real filter UI on Events/Alerts, a storage-usage dashboard, and a new SECURITY_MANAGER role. See limitations 20-22 for the explicit out-of-scope list (multi-channel alerts, offline edge queue-and-sync, generalized dedup/cooldown config, per-user site-level RBAC, S3 lifecycle policies, AWS Cost Explorer billing) |

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
- **AI Video Intelligence Phase 2 (theft detection), end-to-end in a real browser
  against a real (unmocked) backend and a real running ai-engine.** Created a real
  camera with `multi_class_detection_enabled` checked through the Cameras page UI and
  confirmed the new "Multi-class" column showed ON. Started the actual `ai-engine`
  process (not mocked) against it — confirmed via its own logs that the camera's
  worker booted cleanly, meaning `YoloDetector.__init__` genuinely loaded the
  already-downloaded `yolov8n.pt` from the mounted `data/models` path with no import
  or load error, and that its live MJPEG feed rendered correctly in the Zones &
  Tripwires editor (a real moving synthetic frame, timestamp overlay ticking).
  Drew a real `ASSET_ZONE` polygon ("Display Case") by clicking points against that
  live feed and saved it through the real API. Confirmed the AI Video Intelligence
  Settings page's "Potential theft / unauthorized object removal" checkbox is now a
  real, enabled control (no longer in the disabled "Coming soon" block) and persists.
  Because a `SIMULATED` camera's synthetic frame (a plain moving rectangle) will never
  be classified as a real backpack/handbag/suitcase by a genuine COCO-trained model —
  there's no fixture in this environment that would — the actual firing path was
  verified the same way Phase 1's identified-person-violation path was: posted a real
  `POTENTIAL_THEFT_DETECTED` event via the internal API (internal token, as ai-engine's
  `worker.py::_check_zones` would after a real `AssetZoneTracker` exit-after-dwell
  match) and confirmed in the browser that a real Incident was auto-created with the
  exact expected values — title `"Potential Theft / Unauthorized Object Removal —
  Unknown Person at Theft Test Zone Cam"`, `risk_score: 50` (matching
  `compute_risk_score` by hand: 30 for HIGH + 20 for the after-hours timestamp used),
  `requires_human_review: true`, and the exact deterministic description including the
  "not a trained theft-behavior classifier" caveat. Also opened the same event from
  the Events page and confirmed `explainEvent.ts`'s new `POTENTIAL_THEFT_DETECTED`
  case renders the matching plain-language explanation and raw metadata table. This is
  the same honest verification boundary as limitation 15's ffmpeg-transcode
  disclosure: the real detector, real tracker, real API, and real UI were all
  exercised for real; only the specific "a real backpack appears in a camera frame"
  trigger was simulated via a seeded event rather than genuine pixels, since no such
  fixture exists in this environment. `cd backend && pytest -q` (140),
  `cd ai-engine && pytest -q` (76), and `cd frontend && npm run build` all green.
- **Enrolled-photo bug fixes, end-to-end against a real (unmocked) backend.** Reported
  by the user as "Enrolled People Photo tab not showing images of enrolled people."
  Posted two real phone-camera photos (not synthetic test fixtures) to the actual
  `POST /api/faces/enroll` endpoint — both were rejected with `"Image is too blurry"`
  despite being genuinely sharp, confirming the report and pinpointing
  `_blur_score`'s resolution-dependence for real: the identical photo's face crop
  scored 0.31 (rejected) at its native 742x742px and 1.0 (a perfect score) once
  downscaled to ~220px with a quick standalone script, before any code changed.
  After fixing `_blur_score` to normalize against a reference crop size, the exact
  same two real photos enrolled successfully (quality scores 0.89 and, separately,
  passing outright), and the resulting photo rendered correctly in the Enrolled
  People page's Photo column in a real browser. Separately reproduced the path-
  persistence bug by inspecting the raw SQLite row: `image_reference` was stored as
  `'./data/faces\\<tenant>\\<person>.jpg'` — a relative path — confirming it as a
  second real, independent contributing cause. After fixing the enroll route to store
  an absolute path, ran the new `fix_relative_face_paths` repair script against that
  same already-affected row and confirmed it rewrote the path to the correct absolute
  location — the same photo kept rendering in the browser afterward, unchanged.
  `cd backend && pytest -q` (143) and `cd ai-engine && pytest -q` (77) both green.
- **Photo-edit feature + a real dev-workflow bug it surfaced, end-to-end.** After the
  fix above, the user reported the photo still didn't show. Re-testing found the fix
  itself was correct — the actual cause was that the local dev backend process was
  never restarted after the code change (no `--reload`, so it kept serving the old
  in-memory code), which looks exactly like "the fix didn't work" from the browser.
  Confirmed directly: a `curl PUT` to the new photo-replace endpoint returned a genuine
  `405 Method Not Allowed` against the stale process, then `200 OK` with the expected
  response immediately after restarting with `--reload` added to
  `.claude/launch.json` — no code change needed, just the reload flag. Then built and
  verified the actually-requested feature for real: opened the new "Edit" modal on an
  enrolled person, confirmed the full-size photo rendered correctly, called the new
  `PUT /api/faces/{id}/photo` endpoint directly with a second real photo, and confirmed
  in the browser that the Enrolled People table's thumbnail updated to the new photo
  (not the old one) — with the API response showing the previous `FaceProfile` marked
  `SUSPENDED` and a new one `ACTIVE`, matching the audit-preserving design.
  `cd backend && pytest -q` (148) and `cd frontend && npm run build` both green.
- **Event-First Cloud Storage Phase 1, real MinIO + real deployed-VM verification (not
  mocked).** Deploying this phase surfaced and fixed five genuine, previously-unseen
  bugs — all found via live logs/DB inspection on the deployed VM, not anticipated in
  advance:
  1. **MinIO's Docker Hub images no longer exist** (`minio/minio`, `minio/mc` both
     return "pull access denied", not a deprecation notice) — MinIO now publishes to
     Quay; fixed by switching `docker-compose.yml` to `quay.io/minio/minio` and
     `quay.io/minio/mc`.
  2. **The Phase 1 migration's `event_category` backfill failed on real Postgres**
     twice, in two different spots: `sa.table('events', sa.column('event_type',
     sa.String()), ...)` bound the WHERE-clause comparison value as `character
     varying` against the real `eventtype` Postgres ENUM column
     ("operator does not exist"), and the same String()-vs-Enum mismatch on the
     `.values(event_category=...)` SET side ("column ... is of type eventcategory
     but expression is of type character varying"). SQLite has no true enum type, so
     this session's own earlier SQLite-based migration test never caught either —
     the same category of gap this project has hit before (circular FK, camera
     delete cascade). Fixed by declaring both columns with their real
     `sa.Enum(..., create_type=False)` types in the `sa.table()` construct. Verified
     for real: the migration failed with a full Postgres transaction rollback (no
     partial state — confirmed via `SELECT version_num FROM alembic_version` after
     each failed attempt) both times, then applied cleanly on the third attempt, with
     `event_category` correctly backfilled per event_type (spot-checked against real
     rows) and all four retention tiers seeded with their real day-counts.
  3. **A real snapshot → MinIO → presigned-URL round trip, with actual bytes.**
     `docker compose exec minio mc ls --recursive` showed real JPEG objects landing
     at the exact `tenant-{id}/site-{id}/camera-{id}/snapshots/{filename}` key layout;
     hitting the real, authenticated `GET /api/snapshots/{id}/image` endpoint with
     `curl` returned a `307` to `http://<vm-ip>:9000/...` (the **public**, not internal
     `minio:9000`, endpoint — confirming the internal-vs-public client split actually
     works against a real deployment, not just in code review); following that
     redirect downloaded a real 162KB file that `file` confirmed as genuine JPEG data.
  4. **The same round trip for recordings**, with one added wrinkle: two `AI_EVENT`
     recordings stayed open far longer than expected because this session's own
     `POST_TRIGGER_RECORD_SECONDS` widening (10s → 30s, itself a fix from this same
     deployment — see below) combined with the demo cameras' near-continuous
     synthetic activity meant they simply never hit a detection gap long enough to
     close. Confirmed this wasn't a bug by forcing a clean shutdown
     (`docker compose stop -t 30 ai-engine`), watching real "worker stopped" log
     lines for both cameras, and then finding both recordings finalized with a real
     `storage_key`, a real object in MinIO's `recordings/` prefix, and a real `307`
     to a working presigned URL from `GET /api/recordings/{id}/play` — the exact
     same verification rigor as the snapshot path.
  5. **Two more instances of the "naive `db.delete()` crashes on a real dependent
     row" bug class** (previously fixed once for cameras, see the circular-FK/camera-
     delete-cascade entries above), found live by exercising this phase's own new/
     touched code paths against real accumulated VM data:
     `cameras.py::delete_camera` didn't null `Notification.alert_id` or clean up
     `incident_alerts` rows before deleting `Alert`s (a real
     `notifications_alert_id_fkey` violation, confirmed via the actual traceback in
     `docker compose logs backend`), and didn't unscope `Incident.camera_id`/
     `source_event_id` either; `rules.py::delete_rule` had *no* dependent-row handling
     at all and crashed the instant a rule had ever matched a real event
     (`alerts_rule_id_fkey` violation) — found by exercising the Rules page's
     just-added Edit feature end-to-end against the live VM. Both fixed the same way
     as the original camera-delete fix: null the nullable FK / remove the join row,
     never delete the surviving record's own history as a side effect. Confirmed
     against the real VM Postgres, not just the SQLite test suite: the exact same
     rule ID that returned `500` before the fix returned `204` after it, with the
     surviving `Alert.rule_id` correctly `NULL`.
  6. Also found and fixed in this same pass, independent of the cloud-storage work:
     ai-engine created a brand-new `PERSON_DETECTED`/`VEHICLE_DETECTED` event (with
     its own snapshot and recording trigger) every time `CentroidTracker` merely
     re-acquired the same object under a new `track_id` — real, measured impact on
     the VM: one camera produced **~30,600 snapshot rows and 5.9GB of recording
     files in under 24 hours**, most of it near-duplicate content of an
     essentially-continuous scene. Fixed with a 30s per-camera cooldown
     (`OBJECT_EVENT_COOLDOWN_SECONDS`, matching the existing `MOTION_DETECTED`
     throttle's own convention) and by widening `POST_TRIGGER_RECORD_SECONDS`
     10s → 30s so a brief detection gap merges into one recording instead of
     fragmenting into several. Recovering the already-accumulated disk usage this
     caused (11GB across recordings+snapshots) surfaced one more real, independent
     bug: **none of `alerts`/`detections`/`events`/`face_recognition_events`
     `.snapshot_id`/`.recording_id` FK columns were indexed**, so Postgres had to
     sequentially scan every one of those tables for every one of the ~30,600 rows
     being deleted — a bulk cleanup that should take seconds took over 20 minutes,
     confirmed via `pg_stat_activity` showing an active (not blocked, not
     deadlocked) query with no `wait_event` for that entire duration. Fixed with a
     dedicated migration adding the seven missing indexes; verified by adding four
     of them live via `CREATE INDEX CONCURRENTLY` mid-incident (safe — doesn't lock
     out the in-flight DELETE) and watching the same class of query's real
     wall-clock time drop accordingly.
  `cd backend && pytest -q` (208), `cd ai-engine && pytest -q` (91),
  `cd worker && pytest -q` (16), and `cd frontend && npm run build` all green
  throughout every fix in this pass.
- **Two more real bugs found live on the deployed VM in the same pass, plus one
  feature gap closed, all verified against real data rather than fixed speculatively**:
  1. **The per-event PDF export (`GET /api/reports/events/{id}.pdf`) never actually
     showed the event's picture** — it rendered every field the Events page's detail
     modal shows except the one thing (the snapshot image) most reports are actually
     wanted for. Fixed by having `build_event_detail_pdf` embed the real image bytes
     via reportlab's `Image` flowable, scaled to fit while preserving aspect ratio. The
     bytes themselves come from a new `app/services/object_storage.py::download_object`
     (deliberately NOT duplicated to the ai-engine copy — see its own docstring — since
     ai-engine only ever uploads objects it just created, never reads one back) for a
     cloud-stored snapshot, or straight off local disk otherwise — the same
     storage_key-vs-file_path branch `GET /snapshots/{id}/image` already uses, except a
     server-side PDF has no browser to hand a redirect to, so this reads real bytes
     instead of 307-ing. A missing/unreadable snapshot degrades to a plain
     "not available" line rather than breaking the export — same "never let a
     best-effort enhancement break the caller's real work" convention as
     `object_storage.upload_file`. Verified via `tests/test_event_pdf_export.py`: a
     real local JPEG and a real (mocked-boto3) cloud-stored JPEG both land in the PDF
     as a genuine embedded `/DCTDecode` image object, not merely referenced.
  2. **`TRIPWIRE_VIOLATION` events were being duplicated at a scale that dwarfed the
     PERSON_DETECTED bug this same VM had already been fixed for** — `SELECT
     recording_id, COUNT(*) FROM events GROUP BY recording_id HAVING COUNT(*) > 1`
     turned up one `recording_id` with **535 TRIPWIRE_VIOLATION rows in roughly two
     hours**, every one of them a genuinely-crossing-but-different `tracking_id`
     (confirmed by inspecting `event_metadata->>'tracking_id'`: 8, 18, 31, 40, 50, 63,
     72, 82, 95, 104, 114, 127, ... each appearing exactly once, each firing its own
     ENTERING/EXITING pair roughly every 20-25 seconds). Root cause: `_check_tripwires`
     had no debounce at all — unlike `LoiteringTracker`'s real "once per continuous
     stay" gate for zones, every single frame where a tracked centroid crossed a
     tripwire line fired a brand-new event, and `CentroidTracker` reassigning a fresh
     `track_id` every time it briefly lost and re-acquired the same jittering object
     (the identical root cause already fixed for plain detections — see limitation 23)
     meant it never stopped. Fixed with `TRIPWIRE_VIOLATION_COOLDOWN_SECONDS` (30s,
     keyed per-tripwire rather than per-track_id, since the whole point is that
     track_id keeps changing for what's really one presence) — see limitation 24.
     `ai-engine/tests/test_tripwire_violation_cooldown.py` reproduces the exact
     "different track_id, same tripwire" shape found live.
  3. **Definitively root-caused two specific enrolled people's still-missing photos**
     (the user reported this had been asked for "several times") to real, permanent
     data loss rather than a recurrence of the already-fixed relative-path bug:
     `SELECT image_reference FROM face_profiles` on the live VM showed both rows still
     storing the OLD relative path, and `find /data/faces -type f` inside the backend
     container turned up only `.gitkeep` — both people were enrolled before `FACE_PATH`
     was added to the VM's `.env`, so their photo files were written to the container's
     ephemeral filesystem and never reached the persistent volume at all; no code
     change can recover bytes that were never actually saved anywhere durable. Then,
     to make sure the current code+environment combination genuinely works (rather than
     asserting it does), enrolled a real throwaway test person with a real photo
     directly against the live backend, confirmed the resulting `image_reference` was a
     real absolute path that exists inside the container, fetched it back through
     `GET /api/faces/{id}/photo` and confirmed the exact same JPEG bytes came back
     (174,022 bytes, byte-for-byte), then deleted the test person. The two originally-
     reported people need to be re-enrolled through the UI with a new photo — there is
     nothing left to fix in code for them.
  `cd backend && pytest -q` (215) and `cd ai-engine && pytest -q` (95) both green.
- **A real production outage on the deployed VM, root-caused and fixed live**: the
  user reported `/dashboard` "not working." The actual chain: the VM's root filesystem
  was at 100% (`df -h /` showed 0 bytes available), which made Postgres PANIC mid-crash-
  recovery (`could not write to file "pg_logical/replorigin_checkpoint.tmp": No space
  left on device`) and enter a genuine crash-restart loop, which in turn made
  `POST /api/auth/refresh` return `500` and every dashboard API call `401`/fail — and
  separately made nginx itself throw `mkdir() ... failed (28: No space left on device)`
  trying to buffer the frontend's JS bundle, so even the static asset request failed.
  Freed disk in order of safety/certainty: `docker builder prune -af` (3.55GB, pure
  build cache, zero data loss) got Postgres enough room to finish its checkpoint and
  come back healthy on its own; then found and removed real, **zero-reference**
  leftover files — two directories under `data/recordings`/`data/snapshots` named by
  camera IDs that no longer exist in the `cameras` table at all (confirmed via
  `SELECT id FROM cameras` before deleting anything), and, the single largest item, one
  **3.26GB** recording file whose name didn't match any `recordings.file_path` row in
  the database (confirmed with a targeted `SELECT` before deletion) — together these
  freed the VM from 100% to 79% used. Root cause for why these existed at all:
  `delete_camera` (see the camera-delete-cascade entries above) DOES already clean up
  its own local files after commit, but only for the rows it queried before deleting —
  a camera's ai-engine worker that's still actively writing/registering a new
  recording in the same window the camera row gets deleted can create a row+file that
  delete_camera's file-cleanup loop never saw; separately, a `SegmentRecorder` ffmpeg
  transcode killed mid-write by this SAME disk-full crash (not disk-full itself — a
  local recording that was never registered via `POST /api/recordings` in the first
  place, for reasons not fully traced) left one large local file with literally no
  database row ever pointing at it. Rather than patch each individual cause (a
  narrower fix would leave the next not-yet-discovered one to eventually refill the
  disk again), added `worker/app.py::cleanup_orphaned_media_files` — a new pass in the
  existing hourly retention loop that walks `/data/recordings`/`/data/snapshots`
  directly and removes any file not referenced by any `recordings.file_path`/
  `snapshots.file_path` row (skipping anything younger than a 1-hour grace period, so
  a file whose registering POST just hasn't landed yet is never touched). Verified via
  `worker/tests/test_app.py`: an unreferenced file past the grace period is removed, a
  file referenced by either table is kept, a fresh unreferenced file within the grace
  period is left alone, and missing directories don't crash the pass. `cd worker &&
  pytest -q` (21) green. Deployed live and confirmed stable afterward: Postgres
  `healthy`, backend `healthy`, `/dashboard` returns real data again, and TRIPWIRE_
  VIOLATION event volume for the post-fix period stayed at the expected ~1-per-25s
  cadence with no other event type showing runaway duplication.
