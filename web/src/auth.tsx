import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, kin } from "./api";
import { Mark } from "./brand";
import type { AuthInfo } from "./types";
import { Spinner } from "./ui";

interface AuthApi {
  info: AuthInfo | null;
  /** the person is signed in (or the server needs no sign-in) */
  ok: boolean;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthApi>({ info: null, ok: true, refresh: async () => {}, signOut: async () => {} });

export function useAuth(): AuthApi {
  return useContext(Ctx);
}

/**
 * The gate in front of the app. `KIN_AUTH=none`: invisible. `token`: asks for the shared access code once and keeps
 * the cookie the server sets. `easyauth`: the platform signs people in; if a request still comes back 401 the gate
 * shows the platform's sign-in link. A 401 from any API call re-opens the gate.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<AuthInfo | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const i = await kin.authMe();
      setInfo(i);
      setFailed(null);
    } catch (e) {
      setFailed(e instanceof ApiError && e.status === 0 ? "The server is not reachable." : (e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
    const onUnauth = () => refresh();
    window.addEventListener("kin:unauthorized", onUnauth);
    return () => window.removeEventListener("kin:unauthorized", onUnauth);
  }, [refresh]);

  const signOut = useCallback(async () => {
    if (!info) return;
    if (info.mode === "easyauth" && info.logout_url) {
      window.location.href = info.logout_url;
      return;
    }
    await kin.logout();
    await refresh();
  }, [info, refresh]);

  const ok = !!info && (info.mode === "none" || !!info.user);
  const value = useMemo<AuthApi>(() => ({ info, ok, refresh, signOut }), [info, ok, refresh, signOut]);

  if (failed && !info)
    return (
      <Ctx.Provider value={value}>
        <Gate title="Kintsugi is not answering">
          <p className="dim">{failed}</p>
          <button className="btn btn-primary" onClick={refresh}>
            Try again
          </button>
        </Gate>
      </Ctx.Provider>
    );
  if (!info)
    return (
      <Ctx.Provider value={value}>
        <Gate>
          <Spinner label="Opening…" />
        </Gate>
      </Ctx.Provider>
    );
  if (!ok)
    return (
      <Ctx.Provider value={value}>
        {info.mode === "token" ? <TokenLogin onDone={refresh} /> : <PlatformLogin info={info} />}
      </Ctx.Provider>
    );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

function Gate({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="gate">
      <div className="gate-card">
        <div className="brand" style={{ marginBottom: 14 }}>
          <span className="brand-mark">
            <Mark />
          </span>
          <span className="brand-name">Kintsugi</span>
        </div>
        {title && <h1 className="gate-title">{title}</h1>}
        {children}
      </div>
    </div>
  );
}

function TokenLogin({ onDone }: { onDone: () => Promise<void> }) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      await kin.login(token.trim());
      await onDone();
    } catch (ex) {
      setErr(ex instanceof ApiError && ex.status === 401 ? "That access code is not right." : (ex as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Gate title="Enter the access code">
      <p className="dim">This Kintsugi is shared with a small group. The code stays in a cookie on this device for 30 days.</p>
      <form className="stack" onSubmit={submit}>
        <input
          className="input input-mono"
          type="password"
          autoFocus
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="access code"
          aria-label="Access code"
          aria-invalid={!!err}
          autoComplete="current-password"
        />
        {err && <div className="banner banner-fail">{err}</div>}
        <button className="btn btn-primary" type="submit" disabled={busy || !token.trim()}>
          {busy ? <Spinner size={12} /> : null} Open Kintsugi
        </button>
      </form>
    </Gate>
  );
}

function PlatformLogin({ info }: { info: AuthInfo }) {
  return (
    <Gate title="Sign in to continue">
      <p className="dim">Your parts, photos and exports belong to your account on this server.</p>
      {info.login_url ? (
        <a className="btn btn-primary" href={info.login_url}>
          Sign in
        </a>
      ) : (
        <div className="banner banner-warn">The server expects platform sign-in but no login URL is configured (KIN_EASYAUTH_PROVIDER).</div>
      )}
    </Gate>
  );
}

/** Header chip: who is signed in, and the way out. Renders nothing when the server needs no sign-in. */
export function UserChip() {
  const a = useAuth();
  if (!a.info || a.info.mode === "none" || !a.info.user) return null;
  const u = a.info.user;
  return (
    <span className="user-chip" title={`${u.name} (${u.provider})${u.admin ? " · admin" : ""}`}>
      <span className="user-name">{a.info.mode === "token" ? "shared access" : u.name}</span>
      <button className="btn btn-xs btn-ghost" onClick={a.signOut}>
        Sign out
      </button>
    </span>
  );
}
