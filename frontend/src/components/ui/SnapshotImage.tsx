import { useEffect, useState } from "react";
import { fetchSnapshotImage } from "../../api/misc";

// Same authenticated-blob-fetch pattern as faces/EnrolledPeople.tsx's PersonPhoto —
// GET /snapshots/{id}/image needs a normal Authorization header, so this fetches it
// as a blob rather than using a plain <img src="..."> that can't send one.
export function SnapshotImage({ snapshotId, className }: { snapshotId: string; className?: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setUrl(null);
    setFailed(false);
    fetchSnapshotImage(snapshotId).then((u) => {
      if (cancelled) return;
      if (!u) {
        setFailed(true);
        return;
      }
      objectUrl = u;
      setUrl(u);
    });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [snapshotId]);

  if (failed) {
    return (
      <div className={`${className ?? ""} bg-base-800 border border-base-600 rounded flex items-center justify-center text-slate-500 text-xs p-4`}>
        Snapshot file no longer available (may have expired via retention).
      </div>
    );
  }

  if (!url) {
    return <div className={`${className ?? ""} bg-base-800 border border-base-600 rounded flex items-center justify-center text-slate-600 text-xs p-4`}>Loading…</div>;
  }

  return <img src={url} alt="Evidence snapshot" className={className} />;
}
