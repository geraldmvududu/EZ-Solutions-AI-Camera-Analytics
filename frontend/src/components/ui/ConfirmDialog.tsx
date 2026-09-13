export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Delete",
  danger = true,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-base-900 border border-base-700 rounded-lg w-full max-w-sm p-5 space-y-4">
        <h3 className="font-semibold text-slate-100">{title}</h3>
        <p className="text-sm text-slate-400">{message}</p>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onCancel} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`px-3 py-1.5 text-sm rounded text-white ${danger ? "bg-severity-critical hover:opacity-90" : "bg-accent-600 hover:bg-accent-500"}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
