import { useState } from "react";
import { Link } from "react-router-dom";

import { useExplosive, type ExplosiveFilters } from "../api/hooks";
import type { ExplosiveRow } from "../api/types";
import { Empty, Spinner } from "../components/bits";
import { fmtVol, fmtX, scoreColor } from "../lib/format";

const KIND_LABELS: Record<string, string> = {
  earnings: "Earnings",
  trial_readout: "Trial readout",
  fda_decision: "FDA decision",
};

function daysLabel(days: number | null): string {
  if (days === null) return "—";
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  return `in ${days}d`;
}

const COMPONENTS: { key: keyof ExplosiveRow; label: string; max: number }[] = [
  { key: "catalyst_pts", label: "Catalyst proximity", max: 30 },
  { key: "squeeze_pts", label: "Short squeeze setup", max: 25 },
  { key: "float_pts", label: "Float amplifier", max: 15 },
  { key: "iv_pts", label: "Options / IV positioning", max: 20 },
  { key: "volume_pts", label: "Pre-event volume", max: 10 },
];

function RadarCard({ row, expanded, onToggle }: {
  row: ExplosiveRow; expanded: boolean; onToggle: () => void;
}) {
  const color = scoreColor(row.explosive_score);
  return (
    <div className="rise panel overflow-hidden">
      <button onClick={onToggle} className="row-hover flex w-full items-center gap-4 p-4 text-left">
        <span className="w-8 shrink-0 text-center text-[11px] text-[var(--color-ink-400)]">
          #{row.rank}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-2">
            <Link to={`/idea/${row.ticker}`} onClick={(e) => e.stopPropagation()}
              className="num font-semibold text-[var(--color-ink-50)] hover:text-[var(--color-signal-500)]">
              {row.ticker}
            </Link>
            <span className="truncate text-[11px] text-[var(--color-ink-300)]">{row.name}</span>
            {row.catalyst_kind && (
              <span className="label-caps !text-[10px] !text-[var(--color-amber-flag)]">
                {KIND_LABELS[row.catalyst_kind] ?? row.catalyst_kind} · {daysLabel(row.days_to_catalyst)}
              </span>
            )}
          </div>
          <p className="mt-1 truncate text-xs text-[var(--color-ink-300)]">
            {row.catalyst_headline || "No dated catalyst — flagged on positioning alone"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-4 text-xs text-[var(--color-ink-200)]">
          {row.short_pct_float !== null && (
            <span title="short interest % of float">
              SI {row.short_pct_float.toFixed(0)}%
            </span>
          )}
          {row.rel_volume !== null && <span title="relative volume">{fmtX(row.rel_volume)}</span>}
          <div className="w-14 text-right">
            <span className="num text-lg font-semibold" style={{ color }}>
              {Math.round(row.explosive_score)}
            </span>
          </div>
        </div>
      </button>
      {expanded && (
        <div className="hairline-b border-t border-[var(--color-ink-600)] px-4 py-4">
          <div className="grid grid-cols-1 gap-x-8 gap-y-4 md:grid-cols-2">
            <div className="flex flex-col gap-2.5">
              {COMPONENTS.map(({ key, label, max }) => {
                const val = row[key] as number;
                return (
                  <div key={key}>
                    <div className="mb-1 flex justify-between text-[11px]">
                      <span className="text-[var(--color-ink-200)]">{label}</span>
                      <span className="num text-[var(--color-ink-300)]">{val.toFixed(0)}/{max}</span>
                    </div>
                    <div className="scorebar">
                      <span style={{ width: `${(val / max) * 100}%`, background: color }} />
                    </div>
                  </div>
                );
              })}
            </div>
            <dl className="num grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <div>
                <dt className="label-caps !text-[10px]">Days to cover</dt>
                <dd>{row.days_to_cover !== null ? `${row.days_to_cover.toFixed(1)}d` : "—"}</dd>
              </div>
              <div>
                <dt className="label-caps !text-[10px]">IV rank</dt>
                <dd>{row.iv_rank !== null ? row.iv_rank.toFixed(0) : "—"}</dd>
              </div>
              <div>
                <dt className="label-caps !text-[10px]">Float</dt>
                <dd>{row.float_shares !== null ? fmtVol(row.float_shares) : "—"}</dd>
              </div>
              <div>
                <dt className="label-caps !text-[10px]">Sector</dt>
                <dd className="truncate">{row.sector || "—"}</dd>
              </div>
            </dl>
          </div>
          {row.reasons.length > 0 && (
            <ul className="mt-4 flex flex-col gap-1 border-t border-[var(--color-ink-600)] pt-3">
              {row.reasons.map((reason) => (
                <li key={reason} className="text-[11px] text-[var(--color-ink-200)]">
                  <span className="mr-1.5 text-[var(--color-amber-flag)]">▸</span>{reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default function ExplosiveRadarPage() {
  const [filters, setFilters] = useState<ExplosiveFilters>({});
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const { data, isLoading, isError, error } = useExplosive(filters);
  const set = (patch: Partial<ExplosiveFilters>) => setFilters((f) => ({ ...f, ...patch }));

  return (
    <div className="flex flex-col gap-4">
      <header className="rise rise-1">
        <h1 className="font-[var(--font-display)] text-2xl font-bold tracking-wide text-[var(--color-ink-50)]">
          CATALYST RADAR
        </h1>
        <p className="mt-0.5 text-xs text-[var(--color-ink-300)]">
          Stocks with elevated move-<em className="not-italic text-[var(--color-ink-100)]">magnitude</em> potential
          {data ? ` · ${data.total} flagged` : ""}
        </p>
      </header>

      <div className="rise rise-1 panel border-l-2 border-l-[var(--color-amber-flag)] p-4 text-[13px] leading-relaxed text-[var(--color-ink-200)]">
        <strong className="text-[var(--color-ink-50)]">This is not a directional signal.</strong>{" "}
        It ranks how <em>big</em> a move could be — not which way it goes. A stock lands here because
        it has a pending, outcome-unknown event (earnings, an FDA decision, a trial readout) landing
        soon, combined with positioning that amplifies moves: heavy short interest, a thin float,
        options pricing in volatility, or volume already building. Real binary catalysts — the kind
        that produced Moderna's 90%+ single-day jump on its 2026-08-19 melanoma-trial results — can
        gap up <em>or</em> down on the news. Nothing here predicts the outcome.
      </div>

      <div className="rise rise-2 flex flex-wrap items-center gap-2">
        <select
          className="rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-800)] px-2 py-1.5 text-xs"
          value={filters.kind ?? ""}
          onChange={(e) => set({ kind: e.target.value || undefined })}
        >
          <option value="">Any catalyst type</option>
          <option value="earnings">Earnings</option>
          <option value="trial_readout">Trial readout</option>
          <option value="fda_decision">FDA decision</option>
        </select>
        <select
          className="rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-800)] px-2 py-1.5 text-xs"
          value={filters.max_days ?? ""}
          onChange={(e) => set({ max_days: e.target.value ? Number(e.target.value) : "" })}
        >
          <option value="">Any timeframe</option>
          <option value="3">Within 3 days</option>
          <option value="7">Within 1 week</option>
          <option value="14">Within 2 weeks</option>
        </select>
        <select
          className="rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-800)] px-2 py-1.5 text-xs"
          value={filters.min_score ?? ""}
          onChange={(e) => set({ min_score: e.target.value ? Number(e.target.value) : "" })}
        >
          <option value="">Any score</option>
          <option value="50">Score ≥ 50</option>
          <option value="30">Score ≥ 30</option>
        </select>
      </div>

      {isLoading && <Spinner />}
      {isError && <Empty>Catalyst radar unavailable: {(error as Error).message}</Empty>}
      {data && data.rows.length === 0 && (
        <Empty>Nothing flagged right now — no symbols combine a near-term catalyst with crowded positioning.</Empty>
      )}

      <div className="flex flex-col gap-2">
        {(data?.rows ?? []).map((row) => (
          <RadarCard
            key={row.ticker}
            row={row}
            expanded={expandedTicker === row.ticker}
            onToggle={() => setExpandedTicker((t) => (t === row.ticker ? null : row.ticker))}
          />
        ))}
      </div>
    </div>
  );
}
