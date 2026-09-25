import { createContext, useContext } from "react";
import type { IterationEntry, KinEvent, SessionDetail } from "../types";

export interface RunBody {
  message?: string;
  strategy?: string;
  budget?: number;
  critic_rounds?: number;
  answer?: string;
}

export interface SessionState {
  sid: string;
  detail: SessionDetail | null;
  refresh: () => Promise<void>;
  events: KinEvent[];
  connected: boolean;
  /** the designer agent is running (server-side background task) */
  running: boolean;
  /** a synchronous UI-triggered operation (params / iterate / coupon / export) is in flight */
  busy: string | null;
  runBusy: <T>(label: string, fn: () => Promise<T>) => Promise<T | undefined>;
  selected: number | null;
  setSelected: (n: number | null) => void;
  latestIter: IterationEntry | null;
  selectedIter: IterationEntry | null;
  startRun: (body: RunBody) => Promise<boolean>;
  stopRun: () => Promise<void>;
  /** version token that changes whenever the latest mesh may have changed (cache-busting) */
  stlVersion: string;
}

export const SessionCtx = createContext<SessionState | null>(null);

export function useSession(): SessionState {
  const s = useContext(SessionCtx);
  if (!s) throw new Error("useSession outside SessionCtx");
  return s;
}

export function iterPath(n: number, rest: string): string {
  return `iterations/iter_${String(n).padStart(2, "0")}/${rest}`;
}
