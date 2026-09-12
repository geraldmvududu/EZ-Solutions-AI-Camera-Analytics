import { useEffect, useState, type FormEvent } from "react";
import { Layout } from "../components/layout/Layout";
import { StatusBadge } from "../components/ui/Badge";
import * as camerasApi from "../api/cameras";
import type { Camera, CameraSourceType } from "../types";
import { ApiError } from "../api/client";

const SOURCE_TYPES: CameraSourceType[] = ["VIDEO_FILE", "SIMULATED", "WEBCAM", "RTSP", "HTTP_MJPEG", "IP_CAMERA"];

function CameraFormModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [sourceType, setSourceType] = useState<CameraSourceType>("SIMULATED");
  const [videoFilePath, setVideoFilePath] = useState("");
  const [streamUrl, setStreamUrl] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [faceRecognitionEnabled, setFaceRecognitionEnabled] = useState(false);
  const [faceThreshold, setFaceThreshold] = useState("");
  const [faceHoursStart, setFaceHoursStart] = useState("");
  const [faceHoursEnd, setFaceHoursEnd] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await camerasApi.createCamera({
        name,
        location,
        source_type: sourceType,
        video_file_path: sourceType === "VIDEO_FILE" ? videoFilePath : undefined,
        stream_url: ["RTSP", "HTTP_MJPEG", "IP_CAMERA"].includes(sourceType) ? streamUrl : undefined,
        username: username || undefined,
        password: password || undefined,
        face_recognition_enabled: faceRecognitionEnabled,
        face_recognition_threshold: faceThreshold ? Number(faceThreshold) : undefined,
        face_operating_hours_start: faceHoursStart || undefined,
        face_operating_hours_end: faceHoursEnd || undefined,
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create camera");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <form onSubmit={handleSubmit} className="bg-base-900 border border-base-700 rounded-lg w-full max-w-md p-5 space-y-3">
        <h3 className="font-semibold text-slate-100 mb-2">Add Camera</h3>
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
          <label className="block text-xs text-slate-400 mb-1">Source Type</label>
          <select value={sourceType} onChange={(e) => setSourceType(e.target.value as CameraSourceType)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
            {SOURCE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>

        {sourceType === "VIDEO_FILE" && (
          <div>
            <label className="block text-xs text-slate-400 mb-1">Video file path (on server, e.g. /data/uploads/front_gate.mp4)</label>
            <input value={videoFilePath} onChange={(e) => setVideoFilePath(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
          </div>
        )}

        {["RTSP", "HTTP_MJPEG", "IP_CAMERA"].includes(sourceType) && (
          <>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Stream URL</label>
              <input value={streamUrl} onChange={(e) => setStreamUrl(e.target.value)} placeholder="rtsp://host:554/stream" className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Username</label>
                <input value={username} onChange={(e) => setUsername(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Password</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
              </div>
            </div>
          </>
        )}

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

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
            Cancel
          </button>
          <button type="submit" disabled={submitting} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50">
            {submitting ? "Creating..." : "Create Camera"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function CamerasPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setCameras(await camerasApi.listCameras());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load cameras");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleTest(id: string) {
    setTestResults((prev) => ({ ...prev, [id]: "Testing..." }));
    try {
      const result = await camerasApi.testCameraConnection(id);
      setTestResults((prev) => ({ ...prev, [id]: result.detail }));
    } catch (err) {
      setTestResults((prev) => ({ ...prev, [id]: err instanceof Error ? err.message : "Test failed" }));
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this camera? This cannot be undone.")) return;
    setError(null);
    try {
      await camerasApi.deleteCamera(id);
      load();
    } catch (err) {
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
              <th className="text-left px-4 py-2">Location</th>
              <th className="text-left px-4 py-2">Source</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">AI</th>
              <th className="text-left px-4 py-2">Recording</th>
              <th className="text-left px-4 py-2">Face Rec.</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {cameras.map((cam) => (
              <tr key={cam.id}>
                <td className="px-4 py-2 text-slate-400">{cam.camera_code}</td>
                <td className="px-4 py-2 text-slate-100">{cam.name}</td>
                <td className="px-4 py-2 text-slate-400">{cam.location || "—"}</td>
                <td className="px-4 py-2 text-slate-400">{cam.source_type.replace(/_/g, " ")}</td>
                <td className="px-4 py-2">
                  <StatusBadge status={cam.status} />
                </td>
                <td className="px-4 py-2 text-slate-400">{cam.ai_enabled ? "ON" : "OFF"}</td>
                <td className="px-4 py-2 text-slate-400">{cam.recording_enabled ? "ON" : "OFF"}</td>
                <td className="px-4 py-2 text-slate-400">{cam.face_recognition_enabled ? "ON" : "OFF"}</td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-3">
                    <button onClick={() => handleTest(cam.id)} className="text-accent-500 hover:underline text-xs">
                      Test
                    </button>
                    <button onClick={() => handleDelete(cam.id)} className="text-severity-critical hover:underline text-xs">
                      Delete
                    </button>
                  </div>
                  {testResults[cam.id] && <div className="text-xs text-slate-500 mt-1">{testResults[cam.id]}</div>}
                </td>
              </tr>
            ))}
            {cameras.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-slate-500">
                  No cameras yet. Add one to get started.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showModal && <CameraFormModal onClose={() => setShowModal(false)} onCreated={load} />}
    </Layout>
  );
}
