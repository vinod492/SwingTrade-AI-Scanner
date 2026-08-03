import { Link } from "react-router-dom";

import { useCandles, useScanner } from "../api/hooks";
import ChartPanel from "../components/ChartPanel";
import { Change, Empty, ScoreBadge, Spinner, TrendPill } from "../components/bits";
import type { ScannerRow } from "../api/types";
import { fmtPrice } from "../lib/format";

function MiniChartCard({ row }: { row: ScannerRow }) {
  const candles = useCandles(row.ticker);

  return (
    <Link to={`/idea/${row.ticker}`}
      className="panel group flex flex-col gap-2 p-3 transition-colors hover:border-[var(--color-ink-400)]">
      <div className="flex items-start justify-between">
        <div>
          <div className="num text-base font-semibold text-[var(--color-ink-50)] group-hover:text-[var(--color-signal-500)]">
            {row.ticker}
          </div>
          <div className="max-w-40 truncate text-[11px] text-[var(--color-ink-300)]">{row.name}</div>
        </div>
        <ScoreBadge score={row.swing_score} />
      </div>

      <div className="num flex items-center gap-2 text-sm">
        <span className="text-[var(--color-ink-50)]">{fmtPrice(row.price)}</span>
        <Change value={row.day_change_pct} />
      </div>

      {candles.isLoading && <Spinner />}
      {candles.data && candles.data.length > 0 && (
        <ChartPanel candles={candles.data} row={row} height={180} compact />
      )}

      <TrendPill trend={row.trend} />
    </Link>
  );
}

export default function DashboardPage() {
  const { data, isLoading } = useScanner({
    trend: "Strong Uptrend", sort: "swing_score", order: "desc", limit: 24,
  });
  const rows = data?.rows ?? [];

  return (
    <div className="flex flex-col gap-4">
      <header className="rise rise-1">
        <h1 className="font-[var(--font-display)] text-2xl font-bold tracking-wide text-[var(--color-ink-50)]">
          BULLISH DASHBOARD
        </h1>
        <p className="mt-0.5 text-xs text-[var(--color-ink-300)]">
          Strong Uptrend names — EMA 20 &gt; EMA 50 &gt; EMA 200 and price above EMA 20,
          ranked by Swing Score
        </p>
      </header>

      {isLoading && <Spinner />}
      {!isLoading && rows.length === 0 && (
        <Empty>No tickers currently in a Strong Uptrend (EMA 20&gt;50&gt;200) alignment.</Empty>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {rows.map((row) => <MiniChartCard key={row.ticker} row={row} />)}
      </div>
    </div>
  );
}
