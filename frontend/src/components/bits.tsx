/** Small shared display atoms for the terminal tables. */
import { changeColor, fmtPct, scoreColor, trendColor } from "../lib/format";

export function ScoreBadge({ score, size = "md" }: { score: number; size?: "md" | "lg" }) {
  const color = scoreColor(score);
  return (
    <div className={size === "lg" ? "w-24" : "w-16"}>
      <div className="flex items-baseline justify-between">
        <span
          className={`num font-semibold ${size === "lg" ? "text-3xl" : "text-sm"}`}
          style={{ color }}
        >
          {Math.round(score)}
        </span>
        {size === "lg" && <span className="text-xs text-[var(--color-ink-300)]">/100</span>}
      </div>
      <div className="scorebar mt-1">
        <span style={{ width: `${score}%`, background: color }} />
      </div>
    </div>
  );
}

export function Change({ value }: { value: number | null }) {
  return (
    <span className="num" style={{ color: changeColor(value) }}>
      {fmtPct(value)}
    </span>
  );
}

export function TrendPill({ trend }: { trend: string }) {
  const color = trendColor(trend);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-sm px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap"
      style={{ color, background: "color-mix(in srgb, currentColor 12%, transparent)" }}
    >
      <span className="inline-block h-1 w-1 rounded-full" style={{ background: color }} />
      {trend}
    </span>
  );
}

export function SetupTag({ label }: { label: string }) {
  const bearish = label.startsWith("Downtrend");
  return (
    <span
      className="text-[11px]"
      style={{ color: bearish ? "var(--color-ink-300)" : "var(--color-signal-500)" }}
    >
      {label}
    </span>
  );
}

export function PanelTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="hairline-b flex items-center justify-between px-4 py-2.5">
      <h2 className="label-caps">{children}</h2>
      {right}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center gap-2 p-6 text-sm text-[var(--color-ink-300)]">
      <span className="inline-block h-3 w-3 animate-spin rounded-full border border-[var(--color-ink-400)] border-t-[var(--color-gain-500)]" />
      loading…
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="p-8 text-center text-sm text-[var(--color-ink-300)]">{children}</div>;
}
