import { Link } from "react-router-dom";

import { useAlertEvents, useAlertRules, useMarkAllSeen, useToggleRule } from "../api/hooks";
import { Empty, PanelTitle, Spinner } from "../components/bits";
import { useAuth } from "../state/auth";
import LoginGate from "./LoginGate";

const RULE_META: Record<string, { label: string; desc: string }> = {
  top20_entry: { label: "Top-20 entry", desc: "Symbol newly enters the top 20 ranked list" },
  relvol_3x: { label: "Relative volume 3x", desc: "Relative volume exceeds 3x its 20-day average" },
  breakout: { label: "Breakout", desc: "Price crosses above tracked resistance" },
  rsi_cross_50: { label: "RSI crosses 50", desc: "Momentum flips as RSI crosses up through 50" },
  unusual_options: { label: "Unusual options", desc: "Call volume spikes above 2.5x its norm" },
};

export default function AlertsPage() {
  const { loggedIn } = useAuth();
  if (!loggedIn) return <LoginGate feature="alert rules and your alert feed" />;
  return <AlertsInner />;
}

function AlertsInner() {
  const rules = useAlertRules();
  const events = useAlertEvents();
  const toggle = useToggleRule();
  const markAll = useMarkAllSeen();

  return (
    <div className="flex flex-col gap-4">
      <header className="rise rise-1">
        <h1 className="font-[var(--font-display)] text-2xl font-bold tracking-wide text-[var(--color-ink-50)]">
          ALERTS
        </h1>
        <p className="mt-0.5 text-xs text-[var(--color-ink-300)]">
          Fired by the scan cycle — also pushed live as toasts while you're here
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <section className="rise rise-2 panel h-fit">
          <PanelTitle>Rules</PanelTitle>
          {rules.isLoading && <Spinner />}
          <ul className="flex flex-col">
            {(rules.data ?? []).map((rule) => {
              const meta = RULE_META[rule.rule_type] ?? { label: rule.rule_type, desc: "" };
              return (
                <li key={rule.id} className="hairline-b flex items-center justify-between gap-3 px-4 py-3 last:border-b-0">
                  <div>
                    <div className="text-[13px] font-medium text-[var(--color-ink-100)]">{meta.label}</div>
                    <div className="text-[11px] text-[var(--color-ink-300)]">{meta.desc}</div>
                  </div>
                  <button
                    role="switch"
                    aria-checked={rule.enabled}
                    onClick={() => toggle.mutate({ id: rule.id, enabled: !rule.enabled })}
                    className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
                      rule.enabled ? "bg-[var(--color-gain-600)]" : "bg-[var(--color-ink-500)]"}`}>
                    <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-[var(--color-ink-50)] transition-all ${
                      rule.enabled ? "left-[18px]" : "left-0.5"}`} />
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <section className="rise rise-3 panel lg:col-span-2">
          <PanelTitle
            right={
              (events.data ?? []).some((e) => !e.seen) && (
                <button onClick={() => markAll.mutate()}
                  className="text-xs text-[var(--color-signal-500)] hover:underline">
                  mark all seen
                </button>
              )
            }>
            Event Feed
          </PanelTitle>
          {events.isLoading && <Spinner />}
          {events.data && events.data.length === 0 && (
            <Empty>No alerts fired yet. They'll appear here (and as live toasts) when rules trigger.</Empty>
          )}
          <ul className="flex flex-col">
            {(events.data ?? []).map((event) => (
              <li key={event.id}
                className={`hairline-b flex items-start gap-3 px-4 py-3 last:border-b-0 ${event.seen ? "opacity-55" : ""}`}>
                <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                  event.seen ? "bg-[var(--color-ink-400)]" : "bg-[var(--color-amber-flag)]"}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <Link to={`/idea/${event.ticker}`}
                      className="num text-sm font-semibold text-[var(--color-ink-50)] hover:text-[var(--color-signal-500)]">
                      {event.ticker}
                    </Link>
                    <span className="label-caps !text-[10px] !text-[var(--color-amber-flag)]">
                      {(RULE_META[event.rule_type] ?? { label: event.rule_type }).label}
                    </span>
                    <span className="num ml-auto text-[11px] text-[var(--color-ink-400)]">
                      {new Date(event.triggered_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-[var(--color-ink-200)]">{event.message}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
