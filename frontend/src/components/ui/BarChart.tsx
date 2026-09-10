interface BarDatum {
  label: string;
  count: number;
  color?: string;
}

export function HorizontalBarChart({ data, emptyLabel = "No data" }: { data: BarDatum[]; emptyLabel?: string }) {
  if (data.length === 0) {
    return <div className="text-sm text-slate-500 py-6 text-center">{emptyLabel}</div>;
  }
  const max = Math.max(...data.map((d) => d.count), 1);

  return (
    <div className="space-y-2">
      {data.map((d) => (
        <div key={d.label} className="flex items-center gap-2 text-xs">
          <div className="w-28 shrink-0 truncate text-slate-400" title={d.label}>
            {d.label}
          </div>
          <div className="flex-1 bg-base-800 rounded h-4 overflow-hidden">
            <div
              className="h-full rounded"
              style={{ width: `${(d.count / max) * 100}%`, backgroundColor: d.color || "#14b8a6" }}
            />
          </div>
          <div className="w-8 text-right text-slate-300 font-medium">{d.count}</div>
        </div>
      ))}
    </div>
  );
}

export function HourlyBarChart({ data }: { data: { hour: number; count: number }[] }) {
  const max = Math.max(...data.map((d) => d.count), 1);
  const width = 600;
  const height = 140;
  const barWidth = width / data.length;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-36" preserveAspectRatio="none">
      {data.map((d, i) => {
        const barHeight = (d.count / max) * (height - 20);
        return (
          <g key={d.hour}>
            <rect
              x={i * barWidth + 2}
              y={height - 20 - barHeight}
              width={barWidth - 4}
              height={barHeight}
              fill="#14b8a6"
              opacity={d.count === 0 ? 0.15 : 0.9}
            />
            {i % 3 === 0 && (
              <text x={i * barWidth + barWidth / 2} y={height - 4} fontSize="9" fill="#5a6472" textAnchor="middle">
                {d.hour}h
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
