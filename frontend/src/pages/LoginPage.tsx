import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../state/auth";

export default function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await (mode === "login" ? login(email, password) : register(email, password));
      navigate("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const inputCls =
    "w-full rounded-md border border-[var(--color-ink-600)] bg-[var(--color-ink-900)] px-3 py-2 text-sm outline-none placeholder:text-[var(--color-ink-400)] focus:border-[var(--color-signal-500)]";

  return (
    <div className="rise mx-auto mt-14 w-full max-w-sm">
      <div className="panel p-6">
        <div className="mb-5 flex rounded-md bg-[var(--color-ink-900)] p-1">
          {(["login", "register"] as const).map((m) => (
            <button key={m} onClick={() => { setMode(m); setError(""); }}
              className={`flex-1 rounded px-3 py-1.5 text-xs font-semibold uppercase tracking-wider ${
                mode === m ? "bg-[var(--color-ink-700)] text-[var(--color-ink-50)]"
                           : "text-[var(--color-ink-400)]"}`}>
              {m === "login" ? "Sign in" : "Register"}
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="label-caps !text-[10px]">Email</span>
            <input className={inputCls} type="email" required value={email}
              placeholder="you@example.com" onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="label-caps !text-[10px]">Password</span>
            <input className={inputCls} type="password" required minLength={8} value={password}
              placeholder={mode === "register" ? "at least 8 characters" : "••••••••"}
              onChange={(e) => setPassword(e.target.value)} />
          </label>
          {error && <p className="text-xs text-[var(--color-loss-500)]">{error}</p>}
          <button type="submit" disabled={busy}
            className="mt-1 rounded-md bg-[var(--color-gain-600)] px-4 py-2 text-sm font-semibold text-[var(--color-ink-950)] hover:bg-[var(--color-gain-500)] disabled:opacity-50">
            {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
        <p className="mt-4 text-center text-[11px] leading-relaxed text-[var(--color-ink-400)]">
          Accounts unlock alerts, watchlists, backtesting and personal API keys.
        </p>
      </div>
    </div>
  );
}
