import { useState } from "react";

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Delete",
  pendingLabel = "Working...",
  danger = true,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  confirmLabel?: string;
  pendingLabel?: string;
  danger?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
}) {
  // Real bug this fixes: a delete against a camera/rule/person with a lot of real
  // dependent data (found live — one camera had 137,927 detections and 26,067
  // alerts) can genuinely take a while. Without any pending feedback the dialog
  // looked identical whether nothing had happened yet or the browser had already
  // given up waiting (nginx logs showed real 499s — the client closing the
  // connection) — indistinguishable from "the button doesn't work" to a user.
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    setPending(true);
    setError(null);
    try {
      await onConfirm();
    } catch (err) {
      // Caught here (in addition to whatever the caller's own onConfirm does with
      // it) so the failure is visible right on the dialog the user is already
      // looking at, not just a banner on the page behind this modal's backdrop.
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-base-900 border border-base-700 rounded-lg w-full max-w-sm p-5 space-y-4">
        <h3 className="font-semibold text-slate-100">{title}</h3>
        <p className="text-sm text-slate-400">{message}</p>
        {error && <p className="text-sm text-severity-critical">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onCancel} disabled={pending} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300 disabled:opacity-50">
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={pending}
            className={`px-3 py-1.5 text-sm rounded text-white disabled:opacity-50 ${danger ? "bg-severity-critical hover:opacity-90" : "bg-accent-600 hover:bg-accent-500"}`}
          >
            {pending ? pendingLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
