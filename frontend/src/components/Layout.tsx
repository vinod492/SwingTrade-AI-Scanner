import { Link, NavLink, Outlet } from "react-router-dom";

import { useScanner } from "../api/hooks";
import { changeColor, fmtPct, fmtPrice } from "../lib/format";
import { useAuth } from "../state/auth";
import { useLive } from "../state/live";

const NAV = [
  { to: "/", label: "Scanner", exact: true },
  { to: "/ideas", label: "Trade Ideas" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/alerts", label: "Alerts" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/backtest", label: "Backtest" },
  { to: "/settings", label: "Settings" },
];

function TickerTape() {
  const { data } = useScanner({ sort: "swing_score", order: "desc", limit: 30 });
  const rows = data?.rows ?? [];
  if (!rows.length) return <div className="h-8" />;
  const cells = [...rows, ...rows]; // duplicated for the seamless loop
  return (
    <div className="hairline-b overflow-hidden whitespace-nowrap bg-[var(--color-ink-900)]">
      <div className="tape inline-flex items-center gap-6 py-1.5 pl-6">
        {cells.map((r, i) => (
          <Link key={`${r.ticker}-${i}`} to={`/idea/${r.ticker}`}
            className="num inline-flex items-center gap-2 text-xs hover:opacity-75">
            <span className="font-semibold text-[var(--color-ink-100)]">{r.ticker}</span>
            <span className="text-[var(--color-ink-300)]">{fmtPrice(r.price)}</span>
            <span style={{ color: changeColor(r.day_change_pct) }}>{fmtPct(r.day_change_pct)}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function Toasts() {
  const { toasts, dismiss } = useLive();
  return (
    <div className="fixed right-4 top-4 z-50 flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <button key={t.id} onClick={() => dismiss(t.id)}
          className="toast-in panel cursor-pointer border-l-2 border-l-[var(--color-amber-flag)] p-3 text-left shadow-xl shadow-black/40">
          <div className="flex items-center justify-between">
            <span className="num text-sm font-semibold text-[var(--color-ink-50)]">{t.ticker}</span>
            <span className="label-caps !text-[var(--color-amber-flag)]">{t.rule_type.replace(/_/g, " ")}</span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-[var(--color-ink-200)]">{t.message}</p>
        </button>
      ))}
    </div>
  );
}

export default function Layout() {
  const { connected } = useLive();
  const { loggedIn, logout } = useAuth();

  return (
    <div className="flex min-h-screen">
      <aside className="hairline-b sticky top-0 flex h-screen w-52 shrink-0 flex-col border-r border-[var(--color-ink-600)] bg-[var(--color-ink-900)] max-md:hidden">
        <Link to="/" className="flex items-center gap-2.5 px-5 pb-5 pt-6">
          <svg viewBox="0 0 32 32" className="h-7 w-7 shrink-0">
            <rect width="32" height="32" rx="6" fill="var(--color-ink-700)" />
            <path d="M5 22 L11 14 L15 18 L21 8 L27 12" stroke="var(--color-gain-500)"
              strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div className="leading-tight">
            <div className="font-[var(--font-display)] text-sm font-bold tracking-wide text-[var(--color-ink-50)]">
              SWINGTRADE
            </div>
            <div className="label-caps !text-[10px] !tracking-[0.2em] text-[var(--color-gain-500)]">
              AI Scanner
            </div>
          </div>
        </Link>
        <nav className="flex flex-1 flex-col gap-0.5 px-3">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.exact}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-[13px] font-medium transition-colors ${
                  isActive
                    ? "bg-[var(--color-ink-700)] text-[var(--color-ink-50)] shadow-[inset_2px_0_0_var(--color-gain-500)]"
                    : "text-[var(--color-ink-300)] hover:bg-[var(--color-ink-800)] hover:text-[var(--color-ink-100)]"
                }`
              }>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-[var(--color-ink-600)] p-4">
          <div className="flex items-center gap-2 text-[11px] text-[var(--color-ink-300)]">
            <span className={`h-1.5 w-1.5 rounded-full ${connected ? "live-dot bg-[var(--color-gain-500)]" : "bg-[var(--color-loss-500)]"}`} />
            {connected ? "live feed" : "reconnecting…"}
          </div>
          {loggedIn ? (
            <button onClick={logout}
              className="mt-3 w-full rounded-md border border-[var(--color-ink-600)] px-3 py-1.5 text-xs text-[var(--color-ink-200)] hover:border-[var(--color-ink-400)]">
              Sign out
            </button>
          ) : (
            <Link to="/login"
              className="mt-3 block w-full rounded-md bg-[var(--color-gain-600)] px-3 py-1.5 text-center text-xs font-semibold text-[var(--color-ink-950)] hover:bg-[var(--color-gain-500)]">
              Sign in
            </Link>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <TickerTape />
        {/* mobile nav */}
        <nav className="hairline-b flex gap-1 overflow-x-auto bg-[var(--color-ink-900)] px-3 py-2 md:hidden">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.exact}
              className={({ isActive }) =>
                `whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium ${
                  isActive ? "bg-[var(--color-ink-700)] text-[var(--color-ink-50)]"
                           : "text-[var(--color-ink-300)]"}`
              }>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <main className="min-w-0 flex-1 p-4 lg:p-6">
          <Outlet />
        </main>
        <footer className="px-6 pb-4 text-[11px] text-[var(--color-ink-400)]">
          Research tool — not financial advice. Data may be delayed or synthetic (sample mode).
        </footer>
      </div>
      <Toasts />
    </div>
  );
}
