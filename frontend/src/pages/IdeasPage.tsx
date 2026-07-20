import { Link } from "react-router-dom";

import { useIdeas } from "../api/hooks";
import { Empty, ScoreBadge, Spinner, TrendPill } from "../components/bits";
import { fmtPct, fmtPrice } from "../lib/format";

export default function IdeasPage() {
  const { data, isLoading } = useIdeas(0);

  return (
    <div className="flex flex-col gap-4">
      <header className="rise rise-1">
        <h1 className="font-[var(--font-display)] text-2xl font-bold tracking-wide text-[var(--color-ink-50)]">
          TRADE IDEAS
        </h1>
        <p className="mt-0.5 text-xs text-[var(--color-ink-300)]">
          Top-ranked long setups with full trade plans — 2 day to 4 week horizon
        </p>
      </header>

      {isLoading && <Spinner />}
      {data && data.length === 0 && <Empty>No scored ideas yet — give the worker one scan cycle.</Empty>}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(data ?? []).map((r, i) => (
          <Link key={r.ticker} to={`/idea/${r.ticker}`}
            className={`rise panel group p-4 transition-colors hover:border-[var(--color-ink-400)] rise-${Math.min(i % 4 + 1, 4)}`}>
            <div className="flex items-start justify-between">
              <div>
                <div className="num text-lg font-semibold text-[var(--color-ink-50)] group-hover:text-[var(--color-signal-500)]">
                  {r.ticker}
                </div>
                <div className="max-w-44 truncate text-[11px] text-[var(--color-ink-300)]">{r.name}</div>
              </div>
              <ScoreBadge score={r.swing_score} size="lg" />
            </div>

            <div className="mt-3 flex items-center gap-2">
              <TrendPill trend={r.trend} />
              <span className="text-[11px] text-[var(--color-signal-500)]">{r.setup_label}</span>
            </div>

            <dl className="num mt-4 grid grid-cols-3 gap-x-3 gap-y-2 text-sm">
              <div>
                <dt className="label-caps !text-[10px]">Entry</dt>
                <dd className="text-[var(--color-signal-500)]">
                  {fmtPrice(r.entry)}{r.entry_high ? `–${fmtPrice(r.entry_high)}` : ""}
                </dd>
              </div>
              <div>
                <dt className="label-caps !text-[10px]">Stop</dt>
                <dd className="text-[var(--color-loss-500)]">{fmtPrice(r.stop)}</dd>
              </div>
              <div>
                <dt className="label-caps !text-[10px]">Target</dt>
                <dd className="text-[var(--color-gain-500)]">{fmtPrice(r.target)}</dd>
              </div>
              <div>
                <dt className="label-caps !text-[10px]">Risk</dt>
                <dd className="text-[var(--color-ink-100)]">{fmtPct(r.risk_pct, false)}</dd>
              </div>
              <div>
                <dt className="label-caps !text-[10px]">Reward</dt>
                <dd className="text-[var(--color-ink-100)]">{fmtPct(r.reward_pct, false)}</dd>
              </div>
              <div>
                <dt className="label-caps !text-[10px]">R / R</dt>
                <dd className="font-semibold text-[var(--color-ink-50)]">
                  {r.rr_ratio ? `${r.rr_ratio.toFixed(1)}:1` : "—"}
                </dd>
              </div>
            </dl>
          </Link>
        ))}
      </div>
    </div>
  );
}
