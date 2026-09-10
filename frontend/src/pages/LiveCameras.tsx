import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { StatusBadge } from "../components/ui/Badge";
import * as camerasApi from "../api/cameras";
import type { Camera } from "../types";

type LayoutSize = 1 | 4 | 9 | 16;

const LAYOUT_COLS: Record<LayoutSize, string> = {
  1: "grid-cols-1",
  4: "grid-cols-1 sm:grid-cols-2",
  9: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
  16: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4",
};

function CameraTile({ camera, onExpand }: { camera: Camera; onExpand: () => void }) {
  const [errored, setErrored] = useState(false);
  const canStream = camera.status === "ONLINE";

  return (
    <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
      <button className="w-full aspect-video bg-black flex items-center justify-center relative" onClick={onExpand}>
        {canStream && !errored ? (
          <img
            src={camerasApi.getStreamUrl(camera.id)}
            alt={camera.name}
            className="w-full h-full object-contain"
            onError={() => setErrored(true)}
          />
        ) : (
          <span className="text-slate-600 text-sm">{canStream ? "Stream unavailable" : "Camera offline"}</span>
        )}
        <div className="absolute top-1.5 left-1.5 flex gap-1">
          {camera.ai_enabled && <span className="text-[10px] bg-black/60 text-accent-500 px-1.5 py-0.5 rounded">AI</span>}
          {camera.recording_enabled && <span className="text-[10px] bg-black/60 text-severity-critical px-1.5 py-0.5 rounded">REC</span>}
        </div>
      </button>
      <div className="p-3">
        <div className="flex items-center justify-between mb-1">
          <div className="font-medium text-slate-100 text-sm truncate">{camera.name}</div>
          <StatusBadge status={camera.status} />
        </div>
        <div className="text-xs text-slate-500 flex gap-3">
          <span>{camera.capture_fps} FPS</span>
          <span>{camera.resolution_width}x{camera.resolution_height}</span>
        </div>
      </div>
    </div>
  );
}

function ExpandedCameraModal({ camera, onClose }: { camera: Camera; onClose: () => void }) {
  const [errored, setErrored] = useState(false);
  const canStream = camera.status === "ONLINE";

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="max-w-4xl w-full" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-2">
          <div className="text-slate-100 font-semibold">{camera.name}</div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-100 text-sm">
            Close ✕
          </button>
        </div>
        <div className="aspect-video bg-black rounded-lg overflow-hidden flex items-center justify-center">
          {canStream && !errored ? (
            <img
              src={camerasApi.getStreamUrl(camera.id)}
              alt={camera.name}
              className="w-full h-full object-contain"
              onError={() => setErrored(true)}
            />
          ) : (
            <span className="text-slate-600 text-sm">{canStream ? "Stream unavailable" : "Camera offline"}</span>
          )}
        </div>
      </div>
    </div>
  );
}

export function LiveCamerasPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [layout, setLayout] = useState<LayoutSize>(4);
  const [expanded, setExpanded] = useState<Camera | null>(null);

  useEffect(() => {
    camerasApi.listCameras().then(setCameras).catch(() => {});
  }, []);

  return (
    <Layout title="Live Cameras">
      <div className="flex justify-between items-center mb-4">
        <div className="text-sm text-slate-400">{cameras.length} camera(s)</div>
        <div className="flex gap-1">
          {([1, 4, 9, 16] as LayoutSize[]).map((size) => (
            <button
              key={size}
              onClick={() => setLayout(size)}
              className={`px-3 py-1 text-xs rounded border ${
                layout === size ? "bg-accent-600 border-accent-600 text-white" : "border-base-600 text-slate-400 hover:text-slate-100"
              }`}
            >
              {size}
            </button>
          ))}
        </div>
      </div>

      <div className={`grid ${LAYOUT_COLS[layout]} gap-4`}>
        {cameras.slice(0, layout).map((cam) => (
          <CameraTile key={cam.id} camera={cam} onExpand={() => setExpanded(cam)} />
        ))}
        {cameras.length === 0 && <div className="text-slate-500 text-sm">No cameras configured yet.</div>}
      </div>

      {expanded && <ExpandedCameraModal camera={expanded} onClose={() => setExpanded(null)} />}
    </Layout>
  );
}
