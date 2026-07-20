import { useState } from "react";
import { Link } from "react-router-dom";

import { useWatchlist, useWatchlistMutations } from "../api/hooks";
import { Change, Empty, PanelTitle, Spinner } from "../components/bits";
import { changeColor, fmtPrice, scoreColor } from "../lib/format";
import { useAuth } from "../state/auth";
import LoginGate from "./LoginGate";

export default function WatchlistPage() {
  const { loggedIn } = useAuth();
  if (!loggedIn) return <LoginGate feature="watchlists and position tracking" />;
  return <WatchlistInner />;
}

function WatchlistInner() {
  const { data, isLoading } = useWatchlist();
  const { add, remove } = useWatchlistMutations();
  const [form, setForm] = useState({ ticker: "", entry_price: "", shares: "" });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.ticker.trim()) return;
    add.mutate(
      {
        ticker: form.ticker.trim().toUpperCase(),
        entry_price: form.entry_price ? Number(form.entry_price) : undefined,
        shares: form.shares ? Number(form.shares) : undefined,
      },
      { onSuccess: () => setForm({ ticker: "", entry_price: "", shares: "" }) },
    );
  };

  const totalPl = (data ?? []).reduce((acc, item) => acc + (item.pl_amount ?? 0), 0);

  return (
    <div className="flex flex-col gap-4">
      <header className="rise rise-1 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-[var(--font-display)] text-2xl font-bold tracking-wide text-[var(--color-ink-50)]">
            WATCHLIST
          </h1>
          <p className="mt-0.5 text-xs text-[var(--color-ink-300)]">
            Track tickers, entries and live P/L
          </p>
        </div>
        {data && data.some((i) => i.pl_amount !== null) && (
          <div className="panel px-4 py-2 text-right">
            <div className="label-caps !text-[10px]">Open P/L</div>
            <div className="num text-lg font-semibold" style={{ color: changeColor(totalPl) }}>
              {totalPl >= 0 ? "+" : "−"}${Math.abs(totalPl).toFixed(2)}
            </div>
          </div>
        )}
      </header>

      <form onSubmit={submit} className="rise rise-2 panel flex flex-wrap items-end gap-3 p-4">
        <label className="flex flex-col gap-1">
          <span className="label-caps !text-[10px]">Ticker</span>
          <input value={form.ticker} required placeholder="NVDA"
            onChange={(e) => setForm({ ...form, ticker: e.target.value })}
            className="num w-28 rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-900)] px-3 py-1.5 text-sm uppercase outline-none focus:border-[var(--color-signal-500)]" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label-caps !text-[10px]">Entry price</span>
          <input value={form.entry_price} type="number" step="0.01" min="0" placeholder="optional"
            onChange={(e) => setForm({ ...form, entry_price: e.target.value })}
            className="num w-32 rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-900)] px-3 py-1.5 text-sm outline-none focus:border-[var(--color-signal-500)]" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label-caps !text-[10px]">Shares</span>
          <input value={form.shares} type="number" step="any" min="0" placeholder="optional"
            onChange={(e) => setForm({ ...form, shares: e.target.value })}
            className="num w-28 rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-900)] px-3 py-1.5 text-sm outline-none focus:border-[var(--color-signal-500)]" />
        </label>
        <button type="submit" disabled={add.isPending}
          className="rounded-md bg-[var(--color-gain-600)] px-4 py-1.5 text-sm font-semibold text-[var(--color-ink-950)] hover:bg-[var(--color-gain-500)] disabled:opacity-50">
          Add
        </button>
        {add.isError && (
          <span className="text-xs text-[var(--color-loss-500)]">{(add.error as Error).message}</span>
        )}
      </form>

      <section className="rise rise-3 panel overflow-x-auto">
        <PanelTitle>Positions & Watches</PanelTitle>
        {isLoading && <Spinner />}
        {data && data.length === 0 && (
          <Empty>Nothing here yet — add a ticker above, or hit “+ Watchlist” on any idea page.</Empty>
        )}
        {data && data.length > 0 && (
          <table className="w-full min-w-[720px] text-[13px]">
            <thead>
              <tr className="hairline-b">
                {["Ticker", "Score", "Price", "Day %", "Entry", "Shares", "P/L $", "P/L %", ""].map((h, i) => (
                  <th key={h + i} className={`label-caps px-3 py-2.5 ${i >= 2 && i <= 7 ? "text-right" : "text-left"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((item) => (
                <tr key={item.id} className="row-hover hairline-b border-[var(--color-ink-700)]">
                  <td className="px-3 py-2.5">
                    <Link to={`/idea/${item.ticker}`} className="group">
                      <span className="num font-semibold text-[var(--color-ink-50)] group-hover:text-[var(--color-signal-500)]">{item.ticker}</span>
                      <span className="block max-w-44 truncate text-[11px] text-[var(--color-ink-300)]">{item.name}</span>
                    </Link>
                  </td>
                  <td className="num px-3 py-2.5" style={{ color: scoreColor(item.swing_score ?? 0) }}>
                    {item.swing_score !== null ? Math.round(item.swing_score) : "—"}
                  </td>
                  <td className="num px-3 py-2.5 text-right">{fmtPrice(item.price)}</td>
                  <td className="px-3 py-2.5 text-right"><Change value={item.day_change_pct} /></td>
                  <td className="num px-3 py-2.5 text-right text-[var(--color-ink-200)]">{fmtPrice(item.entry_price)}</td>
                  <td className="num px-3 py-2.5 text-right text-[var(--color-ink-200)]">{item.shares ?? "—"}</td>
                  <td className="num px-3 py-2.5 text-right" style={{ color: changeColor(item.pl_amount) }}>
                    {item.pl_amount !== null ? `${item.pl_amount >= 0 ? "+" : "−"}$${Math.abs(item.pl_amount).toFixed(2)}` : "—"}
                  </td>
                  <td className="num px-3 py-2.5 text-right" style={{ color: changeColor(item.pl_pct) }}>
                    {item.pl_pct !== null ? `${item.pl_pct >= 0 ? "+" : ""}${item.pl_pct.toFixed(2)}%` : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <button onClick={() => remove.mutate(item.id)}
                      title="remove"
                      className="text-[var(--color-ink-400)] hover:text-[var(--color-loss-500)]">✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
