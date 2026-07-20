import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { ApiKeyStatus } from "../api/types";
import { PanelTitle, Spinner } from "../components/bits";
import { useAuth } from "../state/auth";
import LoginGate from "./LoginGate";

const PROVIDER_META: Record<string, { label: string; hint: string; hasSecret: boolean }> = {
  polygon: { label: "Massive (Polygon.io)", hint: "Market data — aggregates, snapshots, options, news", hasSecret: false },
  alpaca: { label: "Alpaca Market Data", hint: "Free IEX real-time quotes & bars", hasSecret: true },
  openai: { label: "OpenAI", hint: "Powers the AI trade analysis", hasSecret: false },
};

export default function SettingsPage() {
  const { loggedIn } = useAuth();
  if (!loggedIn) return <LoginGate feature="personal API keys" />;
  return <SettingsInner />;
}

function KeyRow({ status }: { status: ApiKeyStatus }) {
  const meta = PROVIDER_META[status.provider] ?? { label: status.provider, hint: "", hasSecret: false };
  const [key, setKey] = useState("");
  const [secret, setSecret] = useState("");
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => api<ApiKeyStatus>("/settings/api-keys", {
      method: "PUT", body: { provider: status.provider, key, secret },
    }),
    onSuccess: () => { setKey(""); setSecret(""); qc.invalidateQueries({ queryKey: ["api-keys"] }); },
  });
  const remove = useMutation({
    mutationFn: () => api<void>(`/settings/api-keys/${status.provider}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }),
  });

  const inputCls =
    "num flex-1 rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-900)] px-3 py-1.5 text-xs outline-none placeholder:text-[var(--color-ink-400)] focus:border-[var(--color-signal-500)]";

  return (
    <li className="hairline-b px-4 py-4 last:border-b-0">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-sm font-medium text-[var(--color-ink-100)]">{meta.label}</span>
          <span className="ml-2 text-[11px] text-[var(--color-ink-400)]">{meta.hint}</span>
        </div>
        {status.configured ? (
          <span className="flex items-center gap-2 text-[11px] text-[var(--color-gain-500)]">
            ● saved
            <button onClick={() => remove.mutate()}
              className="text-[var(--color-ink-400)] hover:text-[var(--color-loss-500)]">remove</button>
          </span>
        ) : (
          <span className="text-[11px] text-[var(--color-ink-400)]">not set</span>
        )}
      </div>
      <form className="mt-2 flex gap-2"
        onSubmit={(e) => { e.preventDefault(); if (key.trim()) save.mutate(); }}>
        <input className={inputCls} type="password" placeholder="API key" value={key}
          onChange={(e) => setKey(e.target.value)} />
        {meta.hasSecret && (
          <input className={inputCls} type="password" placeholder="API secret" value={secret}
            onChange={(e) => setSecret(e.target.value)} />
        )}
        <button type="submit" disabled={!key.trim() || save.isPending}
          className="rounded-md border border-[var(--color-ink-500)] px-3 py-1.5 text-xs text-[var(--color-ink-100)] hover:border-[var(--color-gain-500)] disabled:opacity-40">
          Save
        </button>
      </form>
      {save.isError && <p className="mt-1 text-xs text-[var(--color-loss-500)]">{(save.error as Error).message}</p>}
    </li>
  );
}

function SettingsInner() {
  const { data, isLoading } = useQuery({
    queryKey: ["api-keys"],
    queryFn: () => api<ApiKeyStatus[]>("/settings/api-keys"),
  });

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <header className="rise rise-1">
        <h1 className="font-[var(--font-display)] text-2xl font-bold tracking-wide text-[var(--color-ink-50)]">
          SETTINGS
        </h1>
        <p className="mt-0.5 text-xs text-[var(--color-ink-300)]">
          Personal API keys are encrypted at rest (Fernet) and never returned by the API
        </p>
      </header>
      <section className="rise rise-2 panel">
        <PanelTitle>API Keys</PanelTitle>
        {isLoading && <Spinner />}
        <ul>{(data ?? []).map((s) => <KeyRow key={s.provider} status={s} />)}</ul>
      </section>
      <p className="rise rise-3 text-[11px] leading-relaxed text-[var(--color-ink-400)]">
        The server's own provider selection is configured via environment variables
        (DATA_PROVIDER / AI_PROVIDER). A personal OpenAI key here overrides the server's
        for your AI analyses.
      </p>
    </div>
  );
}
