import { useParams } from "react-router-dom";

import { useAnalyze, useCandles, useSymbol, useWatchlistMutations } from "../api/hooks";
import ChartPanel from "../components/ChartPanel";
import { Change, Empty, PanelTitle, ScoreBadge, Spinner, TrendPill } from "../components/bits";
import { fmtPct, fmtPrice, fmtVol, fmtX } from "../lib/format";
import { useAuth } from "../state/auth";

const COMPONENTS: { key: "momentum_pts" | "volatility_pts" | "volume_pts" | "breakout_pts" | "options_pts" | "catalyst_pts"; label: string; max: number }[] = [
  { key: "momentum_pts", label: "Momentum", max: 20 },
  { key: "volatility_pts", label: "Volatility", max: 20 },
  { key: "volume_pts", label: "Volume", max: 15 },
  { key: "breakout_pts", label: "Breakout", max: 20 },
  { key: "options_pts", label: "Options", max: 15 },
  { key: "catalyst_pts", label: "Catalyst", max: 10 },
];

const AI_SECTIONS: { key: "why_moving" | "bull_case" | "bear_case" | "technical" | "trade_plan" | "risk_factors"; label: string }[] = [
  { key: "why_moving", label: "Why it's moving" },
  { key: "bull_case", label: "Bull case" },
  { key: "bear_case", label: "Bear case" },
  { key: "technical", label: "Technical read" },
  { key: "trade_plan", label: "Trade plan" },
  { key: "risk_factors", label: "Risk factors" },
];

export default function IdeaDetailPage() {
  const { ticker = "" } = useParams();
  const symbol = useSymbol(ticker.toUpperCase());
  const candles = useCandles(ticker.toUpperCase());
  const analyze = useAnalyze(ticker.toUpperCase());
  const { loggedIn } = useAuth();
  const { add } = useWatchlistMutations();

  if (symbol.isLoading) return <Spinner />;
  if (symbol.isError || !symbol.data) return <Empty>Unknown ticker {ticker.toUpperCase()}</Empty>;

  const detail = symbol.data;
  const row = detail.row;

  return (
    <div className="flex flex-col gap-4">
      <header className="rise rise-1 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-baseline gap-3">
            <h1 className="num text-3xl font-semibold text-[var(--color-ink-50)]">{detail.ticker}</h1>
            {row && <span className="num text-2xl text-[var(--color-ink-100)]">{fmtPrice(row.price)}</span>}
            {row && <span className="text-lg"><Change value={row.day_change_pct} /></span>}
          </div>
          <p className="mt-1 text-sm text-[var(--color-ink-300)]">
            {detail.name} · {detail.sector}
            {detail.market_cap ? ` · ${fmtVol(detail.market_cap)} mkt cap` : ""}
          </p>
          {row && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <TrendPill trend={row.trend} />
              <span className="text-xs text-[var(--color-signal-500)]">{row.setup_label}</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-4">
          {row && <ScoreBadge score={row.swing_score} size="lg" />}
          {loggedIn && row && (
            <button
              onClick={() => add.mutate({ ticker: detail.ticker, entry_price: row.price })}
              disabled={add.isPending}
              className="rounded-md border border-[var(--color-ink-500)] px-3 py-2 text-xs font-medium text-[var(--color-ink-100)] hover:border-[var(--color-gain-500)] hover:text-[var(--color-gain-500)] disabled:opacity-50">
              {add.isSuccess ? "✓ Watching" : "+ Watchlist"}
            </button>
          )}
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <section className="rise rise-2 panel xl:col-span-2">
          <PanelTitle>Price · Daily</PanelTitle>
          <div className="p-3">
            {candles.isLoading && <Spinner />}
            {candles.data && candles.data.length > 0 && (
              <ChartPanel candles={candles.data} row={row} />
            )}
            {candles.data && candles.data.length === 0 && (
              <Empty>No candles stored yet for {detail.ticker}.</Empty>
            )}
          </div>
        </section>

        <div className="flex flex-col gap-4">
          {row && (
            <section className="rise rise-2 panel">
              <PanelTitle>Trade Plan</PanelTitle>
              <dl className="num grid grid-cols-2 gap-x-4 gap-y-3 p-4 text-sm">
                <div>
                  <dt className="label-caps !text-[10px]">Entry zone</dt>
                  <dd className="text-[var(--color-signal-500)]">
                    {fmtPrice(row.entry)}{row.entry_high ? ` – ${fmtPrice(row.entry_high)}` : ""}
                  </dd>
                </div>
                <div>
                  <dt className="label-caps !text-[10px]">Stop loss</dt>
                  <dd className="text-[var(--color-loss-500)]">{fmtPrice(row.stop)}</dd>
                </div>
                <div>
                  <dt className="label-caps !text-[10px]">Target</dt>
                  <dd className="text-[var(--color-gain-500)]">{fmtPrice(row.target)}</dd>
                </div>
                <div>
                  <dt className="label-caps !text-[10px]">R / R</dt>
                  <dd className="font-semibold">{row.rr_ratio ? `${row.rr_ratio.toFixed(1)}:1` : "—"}</dd>
                </div>
                <div>
                  <dt className="label-caps !text-[10px]">Risk</dt>
                  <dd>{fmtPct(row.risk_pct, false)}</dd>
                </div>
                <div>
                  <dt className="label-caps !text-[10px]">Reward</dt>
                  <dd>{fmtPct(row.reward_pct, false)}</dd>
                </div>
                <div>
                  <dt className="label-caps !text-[10px]">Support</dt>
                  <dd>{fmtPrice(row.support)}</dd>
                </div>
                <div>
                  <dt className="label-caps !text-[10px]">Resistance</dt>
                  <dd>{fmtPrice(row.resistance)}</dd>
                </div>
                <div>
                  <dt className="label-caps !text-[10px]">RelVol</dt>
                  <dd>{fmtX(row.rel_volume)}</dd>
                </div>
                <div>
                  <dt className="label-caps !text-[10px]">ATR</dt>
                  <dd>{fmtPct(row.atr_pct, false)}</dd>
                </div>
              </dl>
            </section>
          )}

          {row && (
            <section className="rise rise-3 panel">
              <PanelTitle>Score Breakdown</PanelTitle>
              <div className="flex flex-col gap-2.5 p-4">
                {COMPONENTS.map(({ key, label, max }) => {
                  const val = row[key];
                  return (
                    <div key={key}>
                      <div className="mb-1 flex justify-between text-[11px]">
                        <span className="text-[var(--color-ink-200)]">{label}</span>
                        <span className="num text-[var(--color-ink-300)]">{val.toFixed(0)}/{max}</span>
                      </div>
                      <div className="scorebar">
                        <span style={{
                          width: `${(val / max) * 100}%`,
                          background: val / max > 0.65 ? "var(--color-gain-500)" :
                                      val / max > 0.3 ? "var(--color-amber-flag)" : "var(--color-ink-400)",
                        }} />
                      </div>
                    </div>
                  );
                })}
                {row.reasons.length > 0 && (
                  <ul className="mt-2 flex flex-col gap-1 border-t border-[var(--color-ink-600)] pt-3">
                    {row.reasons.map((reason) => (
                      <li key={reason} className="text-[11px] text-[var(--color-ink-200)]">
                        <span className="mr-1.5 text-[var(--color-gain-500)]">▸</span>{reason}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>
          )}

          {detail.catalysts.length > 0 && (
            <section className="rise rise-4 panel">
              <PanelTitle>Catalysts</PanelTitle>
              <ul className="flex flex-col gap-2 p-4">
                {detail.catalysts.map((c, i) => (
                  <li key={i} className="text-xs leading-relaxed">
                    <span className="label-caps mr-2 !text-[10px] !text-[var(--color-amber-flag)]">{c.kind}</span>
                    <span className="text-[var(--color-ink-200)]">{c.headline}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>

      <section className="rise rise-3 panel">
        <PanelTitle
          right={
            <button
              onClick={() => analyze.mutate(false)}
              disabled={analyze.isPending}
              className="rounded-md bg-[var(--color-ink-700)] px-3 py-1 text-xs font-medium text-[var(--color-signal-500)] hover:bg-[var(--color-ink-600)] disabled:opacity-50">
              {analyze.isPending ? "Analyzing…" : analyze.data ? "Regenerate" : "⚡ Generate AI analysis"}
            </button>
          }>
          AI Analysis
        </PanelTitle>
        {!analyze.data && !analyze.isPending && (
          <Empty>
            Generate a structured read: why it's moving, bull/bear case, technicals, trade plan, risks.
          </Empty>
        )}
        {analyze.isPending && <Spinner />}
        {analyze.data && (
          <div className="grid grid-cols-1 gap-x-6 gap-y-4 p-4 md:grid-cols-2 xl:grid-cols-3">
            {AI_SECTIONS.map(({ key, label }) => (
              <div key={key}>
                <h3 className="label-caps mb-1.5 !text-[var(--color-signal-500)]">{label}</h3>
                <p className="text-[13px] leading-relaxed text-[var(--color-ink-100)]">
                  {analyze.data[key]}
                </p>
              </div>
            ))}
            <p className="text-[10px] text-[var(--color-ink-400)] md:col-span-2 xl:col-span-3">
              provider: {analyze.data.provider}{analyze.data.cached ? " · cached" : ""} · generated{" "}
              {new Date(analyze.data.generated_at).toLocaleTimeString()}
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
