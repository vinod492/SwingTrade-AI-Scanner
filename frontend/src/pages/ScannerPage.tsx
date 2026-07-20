import { useState } from "react";
import { Link } from "react-router-dom";

import { useScanner, useSectors, type ScannerFilters } from "../api/hooks";
import { Change, Empty, ScoreBadge, Spinner, TrendPill } from "../components/bits";
import { fmtPct, fmtPrice, fmtVol, fmtX } from "../lib/format";

const COLUMNS: { key: string; label: string; align?: "right" }[] = [
  { key: "rank", label: "#" },
  { key: "ticker", label: "Ticker" },
  { key: "price", label: "Price", align: "right" },
  { key: "day_change_pct", label: "Day %", align: "right" },
  { key: "volume", label: "Volume", align: "right" },
  { key: "rel_volume", label: "RelVol", align: "right" },
  { key: "atr_pct", label: "ATR %", align: "right" },
  { key: "rsi", label: "RSI", align: "right" },
  { key: "trend", label: "Trend" },
  { key: "swing_score", label: "Score" },
  { key: "entry", label: "Entry", align: "right" },
  { key: "stop", label: "Stop", align: "right" },
  { key: "target", label: "Target", align: "right" },
  { key: "rr_ratio", label: "R/R", align: "right" },
];

export default function ScannerPage() {
  const [filters, setFilters] = useState<ScannerFilters>({ sort: "swing_score", order: "desc", limit: 100 });
  const { data, isLoading, isError, error } = useScanner(filters);
  const { data: sectors } = useSectors();

  const set = (patch: Partial<ScannerFilters>) => setFilters((f) => ({ ...f, ...patch }));
  const sortBy = (key: string) =>
    set(filters.sort === key ? { order: filters.order === "desc" ? "asc" : "desc" } : { sort: key, order: "desc" });

  return (
    <div className="flex flex-col gap-4">
      <header className="rise rise-1 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-[var(--font-display)] text-2xl font-bold tracking-wide text-[var(--color-ink-50)]">
            MARKET SCANNER
          </h1>
          <p className="mt-0.5 text-xs text-[var(--color-ink-300)]">
            {data ? `${data.total} symbols ranked by Swing Score` : "ranking swing setups 2d–4w"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            placeholder="Search ticker or name…"
            className="w-44 rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-800)] px-3 py-1.5 text-xs outline-none placeholder:text-[var(--color-ink-400)] focus:border-[var(--color-signal-500)]"
            value={filters.q ?? ""}
            onChange={(e) => set({ q: e.target.value })}
          />
          <select
            className="rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-800)] px-2 py-1.5 text-xs"
            value={filters.sector ?? ""}
            onChange={(e) => set({ sector: e.target.value || undefined })}
          >
            <option value="">All sectors</option>
            {(sectors ?? []).map((s) => <option key={s}>{s}</option>)}
          </select>
          <select
            className="rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-800)] px-2 py-1.5 text-xs"
            value={filters.min_score ?? ""}
            onChange={(e) => set({ min_score: e.target.value ? Number(e.target.value) : "" })}
          >
            <option value="">Any score</option>
            <option value="80">Score ≥ 80</option>
            <option value="65">Score ≥ 65</option>
            <option value="50">Score ≥ 50</option>
          </select>
          <select
            className="rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-800)] px-2 py-1.5 text-xs"
            value={filters.min_rel_volume ?? ""}
            onChange={(e) => set({ min_rel_volume: e.target.value ? Number(e.target.value) : "" })}
          >
            <option value="">Any RelVol</option>
            <option value="2">RelVol ≥ 2x</option>
            <option value="3">RelVol ≥ 3x</option>
          </select>
        </div>
      </header>

      <div className="rise rise-2 panel overflow-x-auto">
        {isLoading && <Spinner />}
        {isError && <Empty>Scanner unavailable: {(error as Error).message}</Empty>}
        {data && data.rows.length === 0 && (
          <Empty>No rows yet — the worker may still be running its first scan cycle.</Empty>
        )}
        {data && data.rows.length > 0 && (
          <table className="w-full min-w-[1080px] border-collapse text-[13px]">
            <thead>
              <tr className="hairline-b">
                {COLUMNS.map((col) => (
                  <th key={col.key}
                    onClick={() => sortBy(col.key)}
                    className={`label-caps cursor-pointer select-none whitespace-nowrap px-3 py-2.5 hover:text-[var(--color-ink-100)] ${col.align === "right" ? "text-right" : "text-left"}`}>
                    {col.label}
                    {filters.sort === col.key && (filters.order === "desc" ? " ↓" : " ↑")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.ticker} className="row-hover hairline-b border-[var(--color-ink-700)]">
                  <td className="num px-3 py-2 text-[var(--color-ink-400)]">{r.rank}</td>
                  <td className="px-3 py-2">
                    <Link to={`/idea/${r.ticker}`} className="group block">
                      <span className="num font-semibold text-[var(--color-ink-50)] group-hover:text-[var(--color-signal-500)]">
                        {r.ticker}
                        {r.unusual_options && (
                          <span title="unusual options activity" className="ml-1 text-[var(--color-amber-flag)]">◆</span>
                        )}
                      </span>
                      <span className="block max-w-40 truncate text-[11px] text-[var(--color-ink-300)]">
                        {r.name}
                      </span>
                    </Link>
                  </td>
                  <td className="num px-3 py-2 text-right">{fmtPrice(r.price)}</td>
                  <td className="px-3 py-2 text-right"><Change value={r.day_change_pct} /></td>
                  <td className="num px-3 py-2 text-right text-[var(--color-ink-200)]">{fmtVol(r.volume)}</td>
                  <td className="num px-3 py-2 text-right"
                    style={{ color: (r.rel_volume ?? 0) >= 2 ? "var(--color-amber-flag)" : "var(--color-ink-200)" }}>
                    {fmtX(r.rel_volume)}
                  </td>
                  <td className="num px-3 py-2 text-right text-[var(--color-ink-200)]">{fmtPct(r.atr_pct, false)}</td>
                  <td className="num px-3 py-2 text-right text-[var(--color-ink-200)]">{r.rsi?.toFixed(0) ?? "—"}</td>
                  <td className="px-3 py-2"><TrendPill trend={r.trend} /></td>
                  <td className="px-3 py-2"><ScoreBadge score={r.swing_score} /></td>
                  <td className="num px-3 py-2 text-right text-[var(--color-signal-500)]">{fmtPrice(r.entry)}</td>
                  <td className="num px-3 py-2 text-right text-[var(--color-loss-500)]">{fmtPrice(r.stop)}</td>
                  <td className="num px-3 py-2 text-right text-[var(--color-gain-500)]">{fmtPrice(r.target)}</td>
                  <td className="num px-3 py-2 text-right font-medium text-[var(--color-ink-100)]">
                    {r.rr_ratio ? `${r.rr_ratio.toFixed(1)}:1` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
