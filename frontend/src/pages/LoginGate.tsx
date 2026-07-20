import { Link } from "react-router-dom";

export default function LoginGate({ feature }: { feature: string }) {
  return (
    <div className="rise panel mx-auto mt-16 max-w-md p-8 text-center">
      <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-ink-700)] text-lg">
        🔒
      </div>
      <h2 className="font-[var(--font-display)] text-lg font-bold text-[var(--color-ink-50)]">
        SIGN IN REQUIRED
      </h2>
      <p className="mt-2 text-sm text-[var(--color-ink-300)]">
        Create a free account to use {feature}.
      </p>
      <Link to="/login"
        className="mt-5 inline-block rounded-md bg-[var(--color-gain-600)] px-5 py-2 text-sm font-semibold text-[var(--color-ink-950)] hover:bg-[var(--color-gain-500)]">
        Sign in / Register
      </Link>
    </div>
  );
}
