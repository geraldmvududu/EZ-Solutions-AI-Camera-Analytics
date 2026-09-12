import { useEffect, useRef, useState, type FormEvent } from "react";
import { Layout } from "../../components/layout/Layout";
import * as facesApi from "../../api/faces";
import type { PersonCategory } from "../../types";
import { ApiError } from "../../api/client";

const CATEGORIES: PersonCategory[] = ["EMPLOYEE", "CONTRACTOR", "VISITOR", "AUTHORIZED_PERSON", "WATCHLIST"];

function WebcamCapture({ onCapture, onCancel }: { onCapture: (file: File) => void; onCancel: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function start() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        setReady(true);
      } catch {
        if (!cancelled) setError("Could not access the camera — check that this browser has camera permission and no other app is using it.");
      }
    }

    start();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  function handleCapture() {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (blob) onCapture(new File([blob], `webcam-${Date.now()}.jpg`, { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.92,
    );
  }

  return (
    <div className="rounded border border-base-600 bg-base-800 p-3 space-y-2">
      {error ? (
        <div className="text-sm text-severity-critical">{error}</div>
      ) : (
        <video ref={videoRef} muted playsInline className="w-full max-w-sm rounded border border-base-600 bg-black" />
      )}
      <div className="flex gap-2">
        <button
          type="button" onClick={handleCapture} disabled={!ready}
          className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50"
        >
          Capture Photo
        </button>
        <button type="button" onClick={onCancel} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
          Cancel
        </button>
      </div>
    </div>
  );
}

export function EnrollPersonPage() {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [category, setCategory] = useState<PersonCategory>("EMPLOYEE");
  const [externalReference, setExternalReference] = useState("");
  const [department, setDepartment] = useState("");
  const [notes, setNotes] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);

  function handlePhotoChange(file: File | null) {
    setPhoto(file);
    setPreview(file ? URL.createObjectURL(file) : null);
  }

  function handleCapture(file: File) {
    handlePhotoChange(file);
    setCameraOpen(false);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!photo) return;
    setSubmitting(true);
    setResult(null);
    try {
      const res = await facesApi.enrollFace({
        first_name: firstName,
        last_name: lastName,
        category,
        external_reference: externalReference,
        department,
        notes,
        photo,
      });
      setResult({ success: res.success, message: res.message });
      if (res.success) {
        setFirstName("");
        setLastName("");
        setExternalReference("");
        setDepartment("");
        setNotes("");
        handlePhotoChange(null);
      }
    } catch (err) {
      setResult({ success: false, message: err instanceof ApiError ? err.message : "Enrollment failed" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Layout title="Enroll Person">
      <form onSubmit={handleSubmit} className="max-w-2xl rounded-lg border border-base-700 bg-base-900 p-5 space-y-4">
        {result && (
          <div
            className={`text-sm rounded p-3 ${
              result.success ? "bg-accent-600/10 text-accent-500 border border-accent-600/30" : "bg-severity-critical/10 text-severity-critical border border-severity-critical/30"
            }`}
          >
            {result.success ? "Face successfully enrolled" : result.message}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">First name</label>
            <input required value={firstName} onChange={(e) => setFirstName(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Last name</label>
            <input required value={lastName} onChange={(e) => setLastName(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Category</label>
            <select value={category} onChange={(e) => setCategory(e.target.value as PersonCategory)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Employee/reference number</label>
            <input value={externalReference} onChange={(e) => setExternalReference(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
          </div>
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Department</label>
          <input value={department} onChange={(e) => setDepartment(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Notes</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Face photo</label>

          {cameraOpen ? (
            <WebcamCapture onCapture={handleCapture} onCancel={() => setCameraOpen(false)} />
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="file" accept="image/*"
                onChange={(e) => handlePhotoChange(e.target.files?.[0] || null)}
                className="text-sm text-slate-300 file:mr-3 file:rounded file:border-0 file:bg-accent-600 file:px-3 file:py-1.5 file:text-white file:text-sm"
              />
              <button
                type="button" onClick={() => setCameraOpen(true)}
                className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300 hover:text-slate-100 hover:border-accent-500"
              >
                Use Camera
              </button>
            </div>
          )}

          <p className="text-xs text-slate-500 mt-1">
            One clearly visible, well-lit face per photo — uploaded or captured live from this device's camera. Multi-face,
            blurry, or too-dark/too-bright images will be rejected automatically.
          </p>
          {preview && !cameraOpen && <img src={preview} alt="Preview" className="mt-2 h-32 w-32 object-cover rounded border border-base-600" />}
        </div>

        <div className="flex justify-end pt-2">
          <button type="submit" disabled={submitting || !photo} className="px-4 py-2 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50">
            {submitting ? "Enrolling..." : "Enroll Face"}
          </button>
        </div>
      </form>
    </Layout>
  );
}
