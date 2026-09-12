import { useState, type FormEvent } from "react";
import { Layout } from "../../components/layout/Layout";
import * as facesApi from "../../api/faces";
import type { PersonCategory } from "../../types";
import { ApiError } from "../../api/client";

const CATEGORIES: PersonCategory[] = ["EMPLOYEE", "CONTRACTOR", "VISITOR", "AUTHORIZED_PERSON", "WATCHLIST"];

export function EnrollPersonPage() {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [category, setCategory] = useState<PersonCategory>("EMPLOYEE");
  const [externalReference, setExternalReference] = useState("");
  const [department, setDepartment] = useState("");
  const [notes, setNotes] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);

  function handlePhotoChange(file: File | null) {
    setPhoto(file);
    setPreview(file ? URL.createObjectURL(file) : null);
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
          <input
            required type="file" accept="image/*"
            onChange={(e) => handlePhotoChange(e.target.files?.[0] || null)}
            className="w-full text-sm text-slate-300 file:mr-3 file:rounded file:border-0 file:bg-accent-600 file:px-3 file:py-1.5 file:text-white file:text-sm"
          />
          <p className="text-xs text-slate-500 mt-1">
            One clearly visible, well-lit face per photo. Multi-face, blurry, or too-dark/too-bright images will be rejected automatically.
          </p>
          {preview && <img src={preview} alt="Preview" className="mt-2 h-32 w-32 object-cover rounded border border-base-600" />}
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
