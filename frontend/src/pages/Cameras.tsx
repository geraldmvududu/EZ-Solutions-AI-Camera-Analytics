import { useEffect, useState, type FormEvent } from "react";
import { Layout } from "../components/layout/Layout";
import { StatusBadge } from "../components/ui/Badge";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import * as camerasApi from "../api/cameras";
import * as sitesApi from "../api/sites";
import type { Camera, CameraSourceType, Site } from "../types";
import { ApiError } from "../api/client";

const SOURCE_TYPES: CameraSourceType[] = ["VIDEO_FILE", "SIMULATED", "WEBCAM", "RTSP", "HTTP_MJPEG", "IP_CAMERA"];

function CameraFormModal({
  sites,
  camera,
  onClose,
  onSaved,
}: {
  sites: Site[];
  camera?: Camera | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!camera;
  const [name, setName] = useState(camera?.name ?? "");
  const [location, setLocation] = useState(camera?.location ?? "");
  const [sourceType, setSourceType] = useState<CameraSourceType>(camera?.source_type ?? "SIMULATED");
  const [videoFilePath, setVideoFilePath] = useState(camera?.video_file_path ?? "");
  const [loopVideo, setLoopVideo] = useState(camera?.loop_video ?? true);
  const [streamUrl, setStreamUrl] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [siteId, setSiteId] = useState(camera?.site_id ?? "");
  const [cloudRecordingEnabled, setCloudRecordingEnabled] = useState(camera?.cloud_recording_enabled ?? false);
  const [maxOccupancy, setMaxOccupancy] = useState<string>(camera?.max_occupancy != null ? String(camera.max_occupancy) : "");
  const [faceRecognitionEnabled, setFaceRecognitionEnabled] = useState(camera?.face_recognition_enabled ?? false);
  const [faceThreshold, setFaceThreshold] = useState(camera?.face_recognition_threshold?.toString() ?? "");
  const [faceHoursStart, setFaceHoursStart] = useState(camera?.face_operating_hours_start ?? "");
  const [faceHoursEnd, setFaceHoursEnd] = useState(camera?.face_operating_hours_end ?? "");
  const [multiClassDetectionEnabled, setMultiClassDetectionEnabled] = useState(camera?.multi_class_detection_enabled ?? false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);

  async function handleFileUpload(file: File) {
    setUploading(true);
    setError(null);
    try {
      const result = await camerasApi.uploadCameraVideo(file);
      setVideoFilePath(result.video_file_path);
      setUploadedFileName(file.name);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to upload video file");
    } finally {
      setUploading(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        name,
        location,
        video_file_path: sourceType === "VIDEO_FILE" ? videoFilePath : undefined,
        loop_video: sourceType === "VIDEO_FILE" ? loopVideo : undefined,
        stream_url: ["RTSP", "HTTP_MJPEG", "IP_CAMERA"].includes(sourceType) ? streamUrl || undefined : undefined,
        username: username || undefined,
        password: password || undefined,
        site_id: siteId || null,
        cloud_recording_enabled: cloudRecordingEnabled,
        max_occupancy: maxOccupancy.trim() === "" ? null : Number(maxOccupancy),
        face_recognition_enabled: faceRecognitionEnabled,
        face_recognition_threshold: faceThreshold ? Number(faceThreshold) : undefined,
        face_operating_hours_start: faceHoursStart || undefined,
        face_operating_hours_end: faceHoursEnd || undefined,
        multi_class_detection_enabled: multiClassDetectionEnabled,
      };
      if (isEdit && camera) {
        await camerasApi.updateCamera(camera.id, payload);
      } else {
        await camerasApi.createCamera({ ...payload, source_type: sourceType });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Failed to ${isEdit ? "save" : "create"} camera`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <form onSubmit={handleSubmit} className="bg-base-900 border border-base-700 rounded-lg w-full max-w-md p-5 space-y-3">
        <h3 className="font-semibold text-slate-100 mb-2">{isEdit ? `Edit Camera — ${camera?.name}` : "Add Camera"}</h3>
        {error && <div className="text-sm text-severity-critical">{error}</div>}

        <div>
          <label className="block text-xs text-slate-400 mb-1">Name</label>
          <input required value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Location</label>
          <input value={location} onChange={(e) => setLocation(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Source Type{isEdit && " (cannot be changed after creation)"}</label>
          {isEdit ? (
            <div className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-400">{sourceType.replace(/_/g, " ")}</div>
          ) : (
            <select value={sourceType} onChange={(e) => setSourceType(e.target.value as CameraSourceType)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
              {SOURCE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          )}
        </div>

        {sourceType === "VIDEO_FILE" && (
          <div className="space-y-2">
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Upload a video file (e.g. footage copied from an external hard drive)
              </label>
              <input
                type="file"
                accept="video/*,.mp4,.avi,.mov,.mkv,.webm"
                disabled={uploading}
                onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
                className="w-full text-sm text-slate-300 file:mr-3 file:rounded file:border-0 file:bg-accent-600 file:px-3 file:py-1.5 file:text-sm file:text-white hover:file:bg-accent-500"
              />
              {uploading && <p className="text-xs text-slate-500 mt-1">Uploading...</p>}
              {!uploading && uploadedFileName && <p className="text-xs text-accent-500 mt-1">Uploaded: {uploadedFileName}</p>}
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Or enter a path already on the server (e.g. /data/uploads/front_gate.mp4)</label>
              <input value={videoFilePath} onChange={(e) => setVideoFilePath(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
            </div>
            <div>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={loopVideo} onChange={(e) => setLoopVideo(e.target.checked)} />
                Loop this video continuously
              </label>
              <p className="text-xs text-slate-500 mt-1">
                {loopVideo
                  ? "Replays forever, as if this were a live camera — good for ongoing testing, but the same footage gets re-analyzed and can produce repeated events for the same content every loop."
                  : "Plays through once, then stops and marks the camera inactive — no more analysis, no more events from this footage. Right for reviewing a fixed clip (e.g. external-drive footage) exactly once."}
              </p>
              {isEdit && camera?.video_processed_at && (
                <p className="text-xs text-accent-500 mt-1">
                  Already processed on {new Date(camera.video_processed_at).toLocaleString()} — this camera is now inactive.
                </p>
              )}
            </div>
          </div>
        )}

        {["RTSP", "HTTP_MJPEG", "IP_CAMERA"].includes(sourceType) && (
          <>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Stream URL{isEdit && " (leave blank to keep current)"}</label>
              <input value={streamUrl} onChange={(e) => setStreamUrl(e.target.value)} placeholder={isEdit ? "unchanged" : "rtsp://host:554/stream"} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Username{isEdit && " (blank = unchanged)"}</label>
                <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder={isEdit ? "unchanged" : ""} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Password{isEdit && " (blank = unchanged)"}</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={isEdit ? "unchanged" : ""} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
              </div>
            </div>
          </>
        )}

        <div>
          <label className="block text-xs text-slate-400 mb-1">Site</label>
          <select value={siteId} onChange={(e) => setSiteId(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
            <option value="">Unassigned</option>
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>

        <div className="border-t border-base-700 pt-3">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={cloudRecordingEnabled} onChange={(e) => setCloudRecordingEnabled(e.target.checked)} />
            Cloud Recording (upload continuous footage too)
          </label>
          <p className="text-xs text-slate-500 mt-1">
            Off by default — only AI-event recordings/snapshots/evidence clips upload to cloud storage. Turn this on
            to also upload this camera's continuous recordings.
          </p>
        </div>

        <div className="border-t border-base-700 pt-3">
          <label className="block text-sm text-slate-300 mb-1">Max Occupancy (crowd/occupancy counting)</label>
          <input
            type="number"
            min={0}
            value={maxOccupancy}
            onChange={(e) => setMaxOccupancy(e.target.value)}
            placeholder="No limit"
            className="w-full rounded bg-base-800 border border-base-600 px-2 py-1.5 text-sm text-slate-100"
          />
          <p className="text-xs text-slate-500 mt-1">
            Requires at least one tripwire on this camera with "Count for occupancy" enabled (Zones & Tripwires page).
            Leave blank for no limit — occupancy is still tracked and shown, just never triggers an alert.
          </p>
        </div>

        <div className="border-t border-base-700 pt-3">
          <label className="flex items-center gap-2 text-sm text-slate-300 mb-2">
            <input type="checkbox" checked={faceRecognitionEnabled} onChange={(e) => setFaceRecognitionEnabled(e.target.checked)} />
            Facial Recognition
          </label>
          {faceRecognitionEnabled && (
            <div className="space-y-2">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Recognition threshold (0-1, blank = tenant default)</label>
                <input
                  type="number" min={0} max={1} step={0.01} value={faceThreshold}
                  onChange={(e) => setFaceThreshold(e.target.value)}
                  className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Operating hours start</label>
                  <input type="time" value={faceHoursStart} onChange={(e) => setFaceHoursStart(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Operating hours end</label>
                  <input type="time" value={faceHoursEnd} onChange={(e) => setFaceHoursEnd(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-base-700 pt-3">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={multiClassDetectionEnabled} onChange={(e) => setMultiClassDetectionEnabled(e.target.checked)} />
            Multi-class object detection (YOLOv8n)
          </label>
          <p className="text-xs text-slate-500 mt-1">
            Detects backpacks/bags/suitcases/vehicles/animals, not just people — higher CPU usage. Required for
            Asset/Theft Monitoring zones (Zones &amp; Tripwires page) to see anything.
          </p>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
            Cancel
          </button>
          <button type="submit" disabled={submitting || uploading} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50">
            {submitting ? "Saving..." : isEdit ? "Save Changes" : "Create Camera"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function CamerasPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [editTarget, setEditTarget] = useState<Camera | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Camera | null>(null);

  async function load() {
    try {
      setCameras(await camerasApi.listCameras());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load cameras");
    }
  }

  useEffect(() => {
    load();
    sitesApi.listSites().then(setSites).catch(() => {
      /* Sites is a permission-gated feature (view_sites) — a user without it simply
      sees no site dropdown/column, not an error, since it's non-essential here. */
    });
  }, []);

  function siteName(siteId: string | null): string {
    if (!siteId) return "—";
    return sites.find((s) => s.id === siteId)?.name ?? "—";
  }

  async function handleTest(id: string) {
    setTestResults((prev) => ({ ...prev, [id]: "Testing..." }));
    try {
      const result = await camerasApi.testCameraConnection(id);
      setTestResults((prev) => ({ ...prev, [id]: result.detail }));
    } catch (err) {
      setTestResults((prev) => ({ ...prev, [id]: err instanceof Error ? err.message : "Test failed" }));
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setError(null);
    try {
      await camerasApi.deleteCamera(deleteTarget.id);
      setDeleteTarget(null);
      load();
    } catch (err) {
      // Dialog stays open (deleteTarget untouched) so the user can see the error and
      // decide to retry or cancel, instead of it silently vanishing on failure.
      setError(err instanceof ApiError ? err.message : "Failed to delete camera");
    }
  }

  return (
    <Layout title="Cameras">
      <div className="flex justify-between items-center mb-4">
        <div className="text-sm text-slate-400">{cameras.length} camera(s) configured</div>
        <button onClick={() => setShowModal(true)} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white">
          + Add Camera
        </button>
      </div>

      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Code</th>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-left px-4 py-2">Site</th>
              <th className="text-left px-4 py-2">Location</th>
              <th className="text-left px-4 py-2">Source</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">AI</th>
              <th className="text-left px-4 py-2">Recording</th>
              <th className="text-left px-4 py-2">Face Rec.</th>
              <th className="text-left px-4 py-2">Multi-class</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {cameras.map((cam) => (
              <tr key={cam.id}>
                <td className="px-4 py-2 text-slate-400">{cam.camera_code}</td>
                <td className="px-4 py-2 text-slate-100">{cam.name}</td>
                <td className="px-4 py-2 text-slate-400">{siteName(cam.site_id)}</td>
                <td className="px-4 py-2 text-slate-400">{cam.location || "—"}</td>
                <td className="px-4 py-2 text-slate-400">{cam.source_type.replace(/_/g, " ")}</td>
                <td className="px-4 py-2">
                  <StatusBadge status={cam.status} />
                  {cam.video_processed_at && <div className="text-xs text-accent-500 mt-0.5">Processed</div>}
                </td>
                <td className="px-4 py-2 text-slate-400">{cam.ai_enabled ? "ON" : "OFF"}</td>
                <td className="px-4 py-2 text-slate-400">{cam.recording_enabled ? "ON" : "OFF"}</td>
                <td className="px-4 py-2 text-slate-400">{cam.face_recognition_enabled ? "ON" : "OFF"}</td>
                <td className="px-4 py-2 text-slate-400">{cam.multi_class_detection_enabled ? "ON" : "OFF"}</td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-3">
                    <button onClick={() => handleTest(cam.id)} className="text-accent-500 hover:underline text-xs">
                      Test
                    </button>
                    <button onClick={() => setEditTarget(cam)} className="text-accent-500 hover:underline text-xs">
                      Edit
                    </button>
                    <button onClick={() => setDeleteTarget(cam)} className="text-severity-critical hover:underline text-xs">
                      Delete
                    </button>
                  </div>
                  {testResults[cam.id] && <div className="text-xs text-slate-500 mt-1">{testResults[cam.id]}</div>}
                </td>
              </tr>
            ))}
            {cameras.length === 0 && (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-slate-500">
                  No cameras yet. Add one to get started.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showModal && <CameraFormModal sites={sites} onClose={() => setShowModal(false)} onSaved={load} />}

      {editTarget && (
        <CameraFormModal sites={sites} camera={editTarget} onClose={() => setEditTarget(null)} onSaved={load} />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title="Delete camera"
          message={`Delete "${deleteTarget.name}"? This permanently removes its events, detections, snapshots, recordings, zones, and tripwires. This cannot be undone.`}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </Layout>
  );
}
