export function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent?: "default" | "critical" | "warning" | "success";
}) {
  const accentClass =
    accent === "critical"
      ? "text-severity-critical"
      : accent === "warning"
        ? "text-severity-medium"
        : accent === "success"
          ? "text-accent-500"
          : "text-slate-100";

  return (
    <div className="rounded-lg border border-base-700 bg-base-900 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${accentClass}`}>{value}</div>
    </div>
  );
}
