/** Number formatting for dense terminal tables. */

export function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v >= 1000 ? v.toLocaleString("en-US", { maximumFractionDigits: 0 }) : v.toFixed(2);
}

export function fmtPct(v: number | null | undefined, signed = true): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const sign = signed && v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

export function fmtVol(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return v.toFixed(0);
}

export function fmtX(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v.toFixed(1)}x`;
}

/** Score → heat color (ink → amber → green). */
export function scoreColor(score: number): string {
  if (score >= 80) return "var(--color-gain-500)";
  if (score >= 65) return "#8ee06c";
  if (score >= 50) return "var(--color-amber-flag)";
  if (score >= 35) return "#c98b3d";
  return "var(--color-ink-400)";
}

export function changeColor(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return "var(--color-ink-200)";
  return v > 0 ? "var(--color-gain-500)" : "var(--color-loss-500)";
}

export function trendColor(trend: string): string {
  if (trend.includes("Strong")) return "var(--color-gain-500)";
  if (trend === "Uptrend") return "#8ee06c";
  if (trend === "Downtrend") return "var(--color-loss-500)";
  return "var(--color-ink-300)";
}
