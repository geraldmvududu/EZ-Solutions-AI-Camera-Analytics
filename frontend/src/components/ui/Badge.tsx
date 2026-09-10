const SEVERITY_CLASSES: Record<string, string> = {
  INFO: "bg-severity-info/15 text-severity-info",
  LOW: "bg-severity-low/15 text-severity-low",
  MEDIUM: "bg-severity-medium/15 text-severity-medium",
  HIGH: "bg-severity-high/15 text-severity-high",
  CRITICAL: "bg-severity-critical/15 text-severity-critical",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded ${SEVERITY_CLASSES[severity] || "bg-base-700 text-slate-300"}`}>
      {severity}
    </span>
  );
}

const STATUS_CLASSES: Record<string, string> = {
  ONLINE: "bg-accent-500/15 text-accent-500",
  OFFLINE: "bg-base-600 text-slate-400",
  ERROR: "bg-severity-critical/15 text-severity-critical",
  DISABLED: "bg-base-700 text-slate-500",
  NEW: "bg-severity-info/15 text-severity-info",
  ACKNOWLEDGED: "bg-severity-medium/15 text-severity-medium",
  INVESTIGATING: "bg-severity-high/15 text-severity-high",
  RESOLVED: "bg-accent-500/15 text-accent-500",
  FALSE_POSITIVE: "bg-base-600 text-slate-400",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded ${STATUS_CLASSES[status] || "bg-base-700 text-slate-300"}`}>
      {status}
    </span>
  );
}
