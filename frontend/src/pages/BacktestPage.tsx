import { useState } from "react";

import { useBacktest, useBacktests, useCreateBacktest } from "../api/hooks";
import type { Backtest } from "../api/types";
import { Empty, PanelTitle, Spinner } from "../components/bits";
import { changeColor } from "../lib/format";
import { useAuth } from "../state/auth";
import LoginGate from "./LoginGate";

export default function BacktestPage() {
  const { loggedIn } = useAuth();
  if (!loggedIn) return <LoginGate feature="the strategy backtester" />;
  return <BacktestInner />;
}

const DEFAULTS = {
  name: "Score>80 breakout momo",
  min_swing_score: 80,
  min_rel_volume: 2,
  price_above_ema: 50 as number | 0,
  stop_loss_pct: 8,
  take_profit_pct: 15,
  max_hold_days: 20,
  lookback_days: 365,
};

function EquityCurve({ points }: { points: { date: string; equity: number }[] }) {
  if (points.length < 2) return null;
  const w = 640, h = 140, pad = 4;
  const values = points.map((p) => p.equity);
  const min = Math.min(...values, 1), max = Math.max(...values, 1);
  const x = (i: number) => pad + (i / (points.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - min) / (max - min || 1)) * (h - 2 * pad);
  const path = values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = values[values.length - 1];
  const base = y(1);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full">
      <line x1={pad} x2={w - pad} y1={base} y2={base} stroke="var(--color-ink-500)" strokeDasharray="3 4" strokeWidth="1" />
      <path d={path} fill="none" strokeWidth="1.5"
        stroke={last >= 1 ? "var(--color-gain-500)" : "var(--color-loss-500)"} />
      <path d={`${path} L${x(points.length - 1)},${h - pad} L${x(0)},${h - pad} Z`}
        fill={last >= 1 ? "rgba(56,224,125,0.08)" : "rgba(244,86,78,0.08)"} />
    </svg>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="panel px-4 py-3">
      <div className="label-caps !text-[10px]">{label}</div>
      <div className="num mt-1 text-xl font-semibold" style={{ color: color ?? "var(--color-ink-50)" }}>
        {value}
      </div>
    </div>
  );
}

function Results({ bt }: { bt: Backtest }) {
  const r = bt.results;
  if (bt.status === "error") return <Empty>Backtest failed: {bt.error}</Empty>;
  if (bt.status !== "done" || !r) return <Spinner />;
  if (!r.total_trades) return <Empty>{r.message ?? "No trades matched the rules."}</Empty>;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Win rate" value={`${r.win_rate_pct}%`}
          color={(r.win_rate_pct ?? 0) >= 50 ? "var(--color-gain-500)" : "var(--color-amber-flag)"} />
        <Metric label="Avg return / trade" value={`${(r.avg_return_pct ?? 0) > 0 ? "+" : ""}${r.avg_return_pct}%`}
          color={changeColor(r.avg_return_pct)} />
        <Metric label="Max drawdown" value={`${r.max_drawdown_pct}%`} color="var(--color-loss-500)" />
        <Metric label="Sharpe ratio" value={r.sharpe_ratio?.toFixed(2) ?? "n/a"} />
        <Metric label="Trades" value={String(r.total_trades)} />
        <Metric label="Wins / losses" value={`${r.wins} / ${r.losses}`} />
        <Metric label="Avg hold" value={`${r.avg_hold_days}d`} />
        <Metric label="Total return" value={`${(r.total_return_pct ?? 0) > 0 ? "+" : ""}${r.total_return_pct}%`}
          color={changeColor(r.total_return_pct)} />
      </div>

      {r.equity_curve && (
        <section className="panel">
          <PanelTitle
            right={<span className="num text-[11px] text-[var(--color-ink-300)]">
              exits — target: {r.exit_breakdown?.target ?? 0} · stop: {r.exit_breakdown?.stop ?? 0} · time: {r.exit_breakdown?.time ?? 0}
            </span>}>
            Equity Curve (1.0 = start)
          </PanelTitle>
          <div className="p-4"><EquityCurve points={r.equity_curve} /></div>
        </section>
      )}

      {bt.trades.length > 0 && (
        <section className="panel overflow-x-auto">
          <PanelTitle>Trades ({bt.trades.length}{bt.trades.length === 500 ? ", first 500" : ""})</PanelTitle>
          <table className="w-full min-w-[640px] text-xs">
            <thead>
              <tr className="hairline-b">
                {["Ticker", "Entry date", "Entry", "Exit date", "Exit", "Return", "Reason"].map((h) => (
                  <th key={h} className="label-caps px-3 py-2 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bt.trades.map((t, i) => (
                <tr key={i} className="hairline-b row-hover border-[var(--color-ink-700)]">
                  <td className="num px-3 py-1.5 font-medium text-[var(--color-ink-100)]">{t.ticker}</td>
                  <td className="num px-3 py-1.5 text-[var(--color-ink-300)]">{t.entry_date.slice(0, 10)}</td>
                  <td className="num px-3 py-1.5">{t.entry_price.toFixed(2)}</td>
                  <td className="num px-3 py-1.5 text-[var(--color-ink-300)]">{t.exit_date?.slice(0, 10) ?? "—"}</td>
                  <td className="num px-3 py-1.5">{t.exit_price?.toFixed(2) ?? "—"}</td>
                  <td className="num px-3 py-1.5" style={{ color: changeColor(t.return_pct) }}>
                    {t.return_pct !== null ? `${t.return_pct > 0 ? "+" : ""}${t.return_pct.toFixed(1)}%` : "—"}
                  </td>
                  <td className="px-3 py-1.5">
                    <span className="label-caps !text-[9px]"
                      style={{ color: t.exit_reason === "target" ? "var(--color-gain-500)" :
                               t.exit_reason === "stop" ? "var(--color-loss-500)" : "var(--color-ink-300)" }}>
                      {t.exit_reason}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="label-caps !text-[10px]">{label}</span>
      {children}
    </label>
  );
}

const inputCls =
  "num w-full rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-900)] px-3 py-1.5 text-sm outline-none focus:border-[var(--color-signal-500)]";

function BacktestInner() {
  const [form, setForm] = useState(DEFAULTS);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const create = useCreateBacktest();
  const list = useBacktests();
  const selected = useBacktest(selectedId);

  const run = (e: React.FormEvent) => {
    e.preventDefault();
    const { name, ...params } = form;
    create.mutate(
      { name, params: { ...params, price_above_ema: params.price_above_ema || null } },
      { onSuccess: (bt) => setSelectedId(bt.id) },
    );
  };

  const num = (key: keyof typeof DEFAULTS) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: Number(e.target.value) }));

  return (
    <div className="flex flex-col gap-4">
      <header className="rise rise-1">
        <h1 className="font-[var(--font-display)] text-2xl font-bold tracking-wide text-[var(--color-ink-50)]">
          STRATEGY BACKTEST
        </h1>
        <p className="mt-0.5 text-xs text-[var(--color-ink-300)]">
          Replay entry rules over stored daily history · next-day-open fills, stop checked before target
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
        <form onSubmit={run} className="rise rise-2 panel flex h-fit flex-col gap-3 p-4">
          <Field label="Name">
            <input className={inputCls} value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Min score">
              <input className={inputCls} type="number" min={0} max={100} value={form.min_swing_score}
                onChange={num("min_swing_score")} />
            </Field>
            <Field label="Min RelVol">
              <input className={inputCls} type="number" step="0.5" min={0} value={form.min_rel_volume}
                onChange={num("min_rel_volume")} />
            </Field>
            <Field label="Above EMA">
              <select className={inputCls} value={form.price_above_ema} onChange={num("price_above_ema")}>
                <option value={0}>—</option>
                <option value={20}>EMA 20</option>
                <option value={50}>EMA 50</option>
                <option value={200}>EMA 200</option>
              </select>
            </Field>
            <Field label="Lookback (days)">
              <input className={inputCls} type="number" min={90} max={730} value={form.lookback_days}
                onChange={num("lookback_days")} />
            </Field>
            <Field label="Stop loss %">
              <input className={inputCls} type="number" step="0.5" min={1} value={form.stop_loss_pct}
                onChange={num("stop_loss_pct")} />
            </Field>
            <Field label="Take profit %">
              <input className={inputCls} type="number" step="0.5" min={1} value={form.take_profit_pct}
                onChange={num("take_profit_pct")} />
            </Field>
            <Field label="Max hold days">
              <input className={inputCls} type="number" min={1} max={60} value={form.max_hold_days}
                onChange={num("max_hold_days")} />
            </Field>
          </div>
          <button type="submit" disabled={create.isPending}
            className="mt-1 rounded-md bg-[var(--color-gain-600)] px-4 py-2 text-sm font-semibold text-[var(--color-ink-950)] hover:bg-[var(--color-gain-500)] disabled:opacity-50">
            {create.isPending ? "Running…" : "▶ Run backtest"}
          </button>
          {create.isError && (
            <p className="text-xs text-[var(--color-loss-500)]">{(create.error as Error).message}</p>
          )}

          {list.data && list.data.length > 0 && (
            <div className="mt-2 border-t border-[var(--color-ink-600)] pt-3">
              <div className="label-caps mb-2 !text-[10px]">History</div>
              <ul className="flex max-h-56 flex-col gap-1 overflow-y-auto">
                {list.data.map((bt) => (
                  <li key={bt.id}>
                    <button type="button" onClick={() => setSelectedId(bt.id)}
                      className={`w-full rounded px-2 py-1.5 text-left text-xs ${
                        selectedId === bt.id ? "bg-[var(--color-ink-700)] text-[var(--color-ink-50)]"
                                             : "text-[var(--color-ink-300)] hover:bg-[var(--color-ink-800)]"}`}>
                      <span className="block truncate">{bt.name}</span>
                      <span className="num text-[10px] text-[var(--color-ink-400)]">
                        {bt.status} · {new Date(bt.created_at).toLocaleString()}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </form>

        <div className="rise rise-3 xl:col-span-3">
          {selectedId === null && (
            <Empty>Configure entry/exit rules and run — results, equity curve and every simulated trade land here.</Empty>
          )}
          {selected.data && <Results bt={selected.data} />}
        </div>
      </div>
    </div>
  );
}
