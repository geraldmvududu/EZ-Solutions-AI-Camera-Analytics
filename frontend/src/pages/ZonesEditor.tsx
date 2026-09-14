import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Layout } from "../components/layout/Layout";
import * as camerasApi from "../api/cameras";
import * as zonesApi from "../api/zones";
import { fetchSnapshotImage, listSnapshots } from "../api/misc";
import type { Tripwire, TripwireDirection, Zone, ZoneType } from "../api/zones";
import type { Camera } from "../types";

type DrawMode = "ZONE" | "TRIPWIRE";

// Professional VMS systems (Milestone, Genetec, Hikvision/Dahua's own config UIs)
// never make zone/tripwire drawing depend on a live stream staying available for the
// whole editing session — they freeze a single reference frame first, then draw over
// that static image. This is the permanent fix for "the video finishes/loops before I
// can finish drawing": once a frame is frozen client-side (canvas capture), drawing no
// longer cares whether the underlying camera is still running, looping, or has
// finished a single-pass VIDEO_FILE playback — the freeze happens automatically a
// couple seconds after the live feed starts, well within any short test clip's
// duration. A camera with no current live feed at all (offline, or a VIDEO_FILE
// camera that already completed its one-time pass) falls back to its most recent
// stored Snapshot instead of a dead "camera offline" placeholder — so the editor is
// always usable, not just while a camera happens to be actively streaming.
const AUTO_FREEZE_DELAY_MS = 1800;

function captureFrameToDataUrl(img: HTMLImageElement): string | null {
  try {
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth || img.width;
    canvas.height = img.naturalHeight || img.height;
    if (canvas.width === 0 || canvas.height === 0) return null;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.92);
  } catch {
    return null; // tainted canvas (cross-origin stream without CORS clearance) — caller falls back to live view
  }
}

export function ZonesEditorPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [cameraId, setCameraId] = useState<string>("");
  const [zones, setZones] = useState<Zone[]>([]);
  const [tripwires, setTripwires] = useState<Tripwire[]>([]);

  const [mode, setMode] = useState<DrawMode>("ZONE");
  const [zoneType, setZoneType] = useState<ZoneType>("INTRUSION");
  const [direction, setDirection] = useState<TripwireDirection>("BOTH");
  const [gateJumpEnabled, setGateJumpEnabled] = useState(false);
  const [tailgatingEnabled, setTailgatingEnabled] = useState(false);
  const [occupancyCountingEnabled, setOccupancyCountingEnabled] = useState(false);
  const [tailgatingWindow, setTailgatingWindow] = useState(5);
  const [name, setName] = useState("");
  const [points, setPoints] = useState<[number, number][]>([]);
  const [error, setError] = useState<string | null>(null);

  // Reference-frame state: `showingLive` is only true briefly while the raw stream is
  // being sampled for an auto-freeze, or while the user explicitly asked to see it.
  // Everything the user actually draws against is `frozenFrameUrl` — a static image,
  // by design, so drawing never races a finite/looping video.
  const [showingLive, setShowingLive] = useState(false);
  const [frozenFrameUrl, setFrozenFrameUrl] = useState<string | null>(null);
  const [referenceLabel, setReferenceLabel] = useState<string | null>(null);
  const [loadingReference, setLoadingReference] = useState(false);

  const imgRef = useRef<HTMLImageElement>(null);
  const freezeTimerRef = useRef<number | null>(null);

  useEffect(() => {
    camerasApi.listCameras().then((cams) => {
      setCameras(cams);
      if (cams.length > 0) setCameraId(cams[0].id);
    });
  }, []);

  function clearFreezeTimer() {
    if (freezeTimerRef.current !== null) {
      window.clearTimeout(freezeTimerRef.current);
      freezeTimerRef.current = null;
    }
  }

  async function loadReferenceFromLastSnapshot(camId: string, note: string) {
    setLoadingReference(true);
    try {
      const snaps = await listSnapshots({ camera_id: camId, limit: 1 });
      if (snaps.length === 0) {
        setFrozenFrameUrl(null);
        setReferenceLabel(null);
        return;
      }
      const url = await fetchSnapshotImage(snaps[0].id);
      if (url) {
        setFrozenFrameUrl(url);
        setReferenceLabel(`${note} (captured ${new Date(snaps[0].taken_at).toLocaleString()})`);
      }
    } finally {
      setLoadingReference(false);
    }
  }

  function captureLiveFrame() {
    if (!imgRef.current) return;
    const dataUrl = captureFrameToDataUrl(imgRef.current);
    clearFreezeTimer();
    if (dataUrl) {
      setFrozenFrameUrl(dataUrl);
      setReferenceLabel("Frozen frame — draw at your own pace, the camera can keep running");
      setShowingLive(false);
    } else if (cameraId) {
      // Cross-origin canvas tainting or a frame that hasn't decoded yet — fall back to
      // the last stored snapshot rather than leaving the user stuck on a live image
      // they can't freeze.
      loadReferenceFromLastSnapshot(cameraId, "Last known frame");
    }
  }

  function goLive() {
    setShowingLive(true);
    clearFreezeTimer();
    freezeTimerRef.current = window.setTimeout(captureLiveFrame, AUTO_FREEZE_DELAY_MS);
  }

  useEffect(() => {
    clearFreezeTimer();
    setFrozenFrameUrl(null);
    setReferenceLabel(null);
    setShowingLive(false);
    if (!cameraId) return;
    const camera = cameras.find((c) => c.id === cameraId);
    if (camera && camera.status === "ONLINE") {
      // Auto-freeze shortly after the live feed starts — by the time the user has
      // even looked at the screen, drawing no longer depends on the stream staying up.
      setShowingLive(true);
      freezeTimerRef.current = window.setTimeout(captureLiveFrame, AUTO_FREEZE_DELAY_MS);
    } else {
      loadReferenceFromLastSnapshot(cameraId, "Last known frame — camera is not currently live");
    }
    return clearFreezeTimer;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraId, cameras]);

  function loadZonesAndTripwires(camId: string) {
    zonesApi.listZones(camId).then(setZones).catch(() => {});
    zonesApi.listTripwires(camId).then(setTripwires).catch(() => {});
  }

  useEffect(() => {
    if (cameraId) {
      loadZonesAndTripwires(cameraId);
      setPoints([]);
    }
  }, [cameraId]);

  function handleImageClick(e: MouseEvent<HTMLImageElement>) {
    if (!imgRef.current) return;
    const rect = imgRef.current.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height));

    if (mode === "TRIPWIRE" && points.length >= 2) return; // a tripwire is exactly 2 points
    setPoints((prev) => [...prev, [x, y]]);
  }

  function undoLastPoint() {
    setPoints((prev) => prev.slice(0, -1));
  }

  function clearPoints() {
    setPoints([]);
  }

  async function handleSave() {
    setError(null);
    if (!name.trim()) {
      setError("Give this zone/tripwire a name first.");
      return;
    }
    try {
      if (mode === "ZONE") {
        if (points.length < 3) {
          setError("A zone needs at least 3 points.");
          return;
        }
        await zonesApi.createZone({ camera_id: cameraId, name, zone_type: zoneType, polygon: points });
      } else {
        if (points.length !== 2) {
          setError("A tripwire needs exactly 2 points.");
          return;
        }
        await zonesApi.createTripwire({
          camera_id: cameraId, name, line: points, direction,
          gate_jump_detection_enabled: gateJumpEnabled,
          tailgating_detection_enabled: tailgatingEnabled,
          tailgating_window_seconds: tailgatingWindow,
          occupancy_counting_enabled: occupancyCountingEnabled,
        });
      }
      setName("");
      setPoints([]);
      setGateJumpEnabled(false);
      setTailgatingEnabled(false);
      setTailgatingWindow(5);
      setOccupancyCountingEnabled(false);
      loadZonesAndTripwires(cameraId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    }
  }

  async function handleDeleteZone(id: string) {
    await zonesApi.deleteZone(id);
    loadZonesAndTripwires(cameraId);
  }

  async function handleDeleteTripwire(id: string) {
    await zonesApi.deleteTripwire(id);
    loadZonesAndTripwires(cameraId);
  }

  const selectedCamera = cameras.find((c) => c.id === cameraId);
  const pointsAttr = points.map(([x, y]) => `${x * 100},${y * 100}`).join(" ");

  return (
    <Layout title="Zones & Tripwires">
      <div className="flex flex-wrap gap-6">
        <div className="flex-1 min-w-[320px]">
          <div className="flex items-center gap-3 mb-3">
            <select
              value={cameraId}
              onChange={(e) => setCameraId(e.target.value)}
              className="rounded bg-base-800 border border-base-600 px-2 py-1.5 text-sm text-slate-100"
            >
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>

            <div className="flex rounded border border-base-600 overflow-hidden">
              {(["ZONE", "TRIPWIRE"] as DrawMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => {
                    setMode(m);
                    setPoints([]);
                  }}
                  className={`px-3 py-1.5 text-xs ${mode === m ? "bg-accent-600 text-white" : "text-slate-400 hover:bg-base-800"}`}
                >
                  {m === "ZONE" ? "Draw Zone" : "Draw Tripwire"}
                </button>
              ))}
            </div>

            {selectedCamera?.status === "ONLINE" && (
              <div className="flex rounded border border-base-600 overflow-hidden">
                <button
                  onClick={goLive}
                  disabled={showingLive}
                  className="px-3 py-1.5 text-xs text-slate-400 hover:bg-base-800 disabled:opacity-50"
                  title="Show the live feed again, then re-freeze a fresh reference frame"
                >
                  🔴 Live
                </button>
                <button
                  onClick={captureLiveFrame}
                  disabled={!showingLive}
                  className="px-3 py-1.5 text-xs text-slate-400 hover:bg-base-800 disabled:opacity-50"
                  title="Freeze the current frame right now"
                >
                  📷 Freeze
                </button>
              </div>
            )}
          </div>

          <div className="relative rounded-lg overflow-hidden border border-base-700 bg-black" style={{ aspectRatio: "16/9" }}>
            {showingLive && selectedCamera?.status === "ONLINE" ? (
              <img
                ref={imgRef}
                src={camerasApi.getStreamUrl(cameraId)}
                alt="camera feed"
                crossOrigin="anonymous"
                className="w-full h-full object-contain cursor-crosshair select-none"
                onClick={handleImageClick}
              />
            ) : frozenFrameUrl ? (
              <img
                ref={imgRef}
                src={frozenFrameUrl}
                alt="reference frame"
                className="w-full h-full object-contain cursor-crosshair select-none"
                onClick={handleImageClick}
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-slate-600 text-sm text-center px-6">
                {loadingReference
                  ? "Loading a reference frame…"
                  : "No frame available yet — bring the camera online, or wait for it to capture at least one snapshot."}
              </div>
            )}

            {showingLive && (
              <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-black/70 text-[10px] text-accent-400 uppercase tracking-wide">
                Live — freezing automatically…
              </div>
            )}

            <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 w-full h-full pointer-events-none">
              {mode === "ZONE" && points.length >= 2 && (
                <polygon points={pointsAttr} fill="rgba(20,184,166,0.25)" stroke="#14b8a6" strokeWidth="0.4" />
              )}
              {mode === "TRIPWIRE" && points.length === 2 && (
                <line
                  x1={points[0][0] * 100}
                  y1={points[0][1] * 100}
                  x2={points[1][0] * 100}
                  y2={points[1][1] * 100}
                  stroke="#f97316"
                  strokeWidth="0.6"
                />
              )}
              {points.map(([x, y], i) => (
                <circle key={i} cx={x * 100} cy={y * 100} r="0.8" fill="#fff" stroke="#14b8a6" strokeWidth="0.3" />
              ))}

              {/* Existing saved zones/tripwires, shown for reference */}
              {zones.map((z) => {
                const colors: Record<string, string> = {
                  PRIVACY: "#94a3b8",
                  FACE_DETECTION: "#3b82f6",
                  FACE_EXCLUSION: "#64748b",
                  RESTRICTED_AREA: "#a855f7",
                  ASSET_ZONE: "#22c55e",
                };
                const stroke = colors[z.zone_type] || "#ef4444";
                return (
                  <polygon
                    key={z.id}
                    points={z.polygon.map(([x, y]) => `${x * 100},${y * 100}`).join(" ")}
                    fill={`${stroke}33`}
                    stroke={stroke}
                    strokeWidth="0.3"
                    strokeDasharray="1,1"
                  />
                );
              })}
              {tripwires.map((t) => (
                <line
                  key={t.id}
                  x1={t.line[0][0] * 100}
                  y1={t.line[0][1] * 100}
                  x2={t.line[1][0] * 100}
                  y2={t.line[1][1] * 100}
                  stroke="#eab308"
                  strokeWidth="0.4"
                  strokeDasharray="1,1"
                />
              ))}
            </svg>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            Click to place points{mode === "ZONE" ? " (3+ for a polygon)" : " (exactly 2, for the line)"}. Dashed shapes are
            already-saved zones/tripwires for this camera.
            {!showingLive && referenceLabel && (
              <>
                {" "}
                <span className="text-accent-400">{referenceLabel}.</span>{" "}
                {selectedCamera?.status !== "ONLINE" && (
                  <button
                    onClick={() => loadReferenceFromLastSnapshot(cameraId, "Last known frame — camera is not currently live")}
                    className="underline text-slate-400 hover:text-slate-300"
                  >
                    Refresh
                  </button>
                )}
              </>
            )}
          </p>
        </div>

        <div className="w-72 shrink-0 space-y-4">
          <div className="rounded-lg border border-base-700 bg-base-900 p-4">
            <div className="font-semibold text-slate-200 text-sm mb-3">
              {mode === "ZONE" ? "New Zone" : "New Tripwire"}
            </div>

            {error && <div className="text-severity-critical text-xs mb-2">{error}</div>}

            <label className="block text-xs text-slate-400 mb-1">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded bg-base-800 border border-base-600 px-2 py-1.5 text-sm text-slate-100 mb-3"
            />

            {mode === "ZONE" ? (
              <>
                <label className="block text-xs text-slate-400 mb-1">Zone Type</label>
                <select
                  value={zoneType}
                  onChange={(e) => setZoneType(e.target.value as ZoneType)}
                  className="w-full rounded bg-base-800 border border-base-600 px-2 py-1.5 text-sm text-slate-100 mb-3"
                >
                  <option value="INTRUSION">Intrusion</option>
                  <option value="PRIVACY">Privacy (blurs this region)</option>
                  <option value="LOITERING">Loitering</option>
                  <option value="RESTRICTED_AREA">Restricted Area (AI Video Intelligence)</option>
                  <option value="ASSET_ZONE">Asset / Theft Monitoring Zone (AI Video Intelligence)</option>
                  <option value="FACE_DETECTION">Face Detection Zone (recognize only here)</option>
                  <option value="FACE_EXCLUSION">Face Exclusion Zone (never recognize here)</option>
                </select>
              </>
            ) : (
              <>
                <label className="block text-xs text-slate-400 mb-1">Direction</label>
                <select
                  value={direction}
                  onChange={(e) => setDirection(e.target.value as TripwireDirection)}
                  className="w-full rounded bg-base-800 border border-base-600 px-2 py-1.5 text-sm text-slate-100 mb-3"
                >
                  <option value="BOTH">Both directions</option>
                  <option value="ENTERING">Entering only</option>
                  <option value="EXITING">Exiting only</option>
                </select>

                <div className="text-xs text-slate-400 mb-1 mt-3">AI Video Intelligence</div>
                <label className="flex items-center gap-2 text-xs text-slate-300 mb-2">
                  <input type="checkbox" checked={gateJumpEnabled} onChange={(e) => setGateJumpEnabled(e.target.checked)} />
                  Gate jump / climbing detection
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-300 mb-2">
                  <input type="checkbox" checked={tailgatingEnabled} onChange={(e) => setTailgatingEnabled(e.target.checked)} />
                  Tailgating detection
                </label>
                {tailgatingEnabled && (
                  <div className="mb-3">
                    <label className="block text-xs text-slate-400 mb-1">Tailgating window (seconds)</label>
                    <input
                      type="number"
                      min={1}
                      value={tailgatingWindow}
                      onChange={(e) => setTailgatingWindow(Number(e.target.value))}
                      className="w-full rounded bg-base-800 border border-base-600 px-2 py-1.5 text-sm text-slate-100"
                    />
                  </div>
                )}

                <div className="text-xs text-slate-400 mb-1 mt-3">Crowd / Occupancy Analytics</div>
                <label className="flex items-center gap-2 text-xs text-slate-300 mb-2">
                  <input
                    type="checkbox"
                    checked={occupancyCountingEnabled}
                    onChange={(e) => setOccupancyCountingEnabled(e.target.checked)}
                  />
                  Count for occupancy
                </label>
                {occupancyCountingEnabled && (
                  <p className="text-xs text-slate-500 mb-3">
                    Every crossing counts, regardless of the Direction setting above — entering adds 1, exiting
                    subtracts 1. Set a Max Occupancy on the Cameras page to get an alert when it's exceeded.
                  </p>
                )}
              </>
            )}

            <div className="text-xs text-slate-500 mb-3">{points.length} point(s) placed</div>

            <div className="flex gap-2">
              <button onClick={undoLastPoint} className="flex-1 px-2 py-1.5 text-xs rounded border border-base-600 text-slate-300 hover:bg-base-800">
                Undo
              </button>
              <button onClick={clearPoints} className="flex-1 px-2 py-1.5 text-xs rounded border border-base-600 text-slate-300 hover:bg-base-800">
                Clear
              </button>
            </div>
            <button onClick={handleSave} className="w-full mt-2 px-2 py-1.5 text-xs rounded bg-accent-600 hover:bg-accent-500 text-white">
              Save
            </button>
          </div>

          <div className="rounded-lg border border-base-700 bg-base-900 p-4">
            <div className="font-semibold text-slate-200 text-sm mb-2">Zones</div>
            {zones.length === 0 && <div className="text-xs text-slate-500">None yet.</div>}
            {zones.map((z) => (
              <div key={z.id} className="flex items-center justify-between text-xs py-1 border-b border-base-800 last:border-0">
                <span className="text-slate-300">{z.name} <span className="text-slate-500">({z.zone_type})</span></span>
                <button onClick={() => handleDeleteZone(z.id)} className="text-severity-critical hover:underline">
                  Delete
                </button>
              </div>
            ))}
          </div>

          <div className="rounded-lg border border-base-700 bg-base-900 p-4">
            <div className="font-semibold text-slate-200 text-sm mb-2">Tripwires</div>
            {tripwires.length === 0 && <div className="text-xs text-slate-500">None yet.</div>}
            {tripwires.map((t) => (
              <div key={t.id} className="flex items-center justify-between text-xs py-1 border-b border-base-800 last:border-0">
                <span className="text-slate-300">
                  {t.name} <span className="text-slate-500">({t.direction})</span>
                  {t.gate_jump_detection_enabled && <span className="ml-1 text-accent-500">· gate-jump</span>}
                  {t.tailgating_detection_enabled && <span className="ml-1 text-accent-500">· tailgating</span>}
                  {t.occupancy_counting_enabled && <span className="ml-1 text-accent-500">· occupancy</span>}
                </span>
                <button onClick={() => handleDeleteTripwire(t.id)} className="text-severity-critical hover:underline">
                  Delete
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Layout>
  );
}
