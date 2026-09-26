import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, kin } from "../api";
import { REFRESH_KINDS, useEvents } from "../events";
import CenterPane from "../panes/CenterPane";
import LeftPane from "../panes/LeftPane";
import RightPane from "../panes/RightPane";
import StageBar from "../panes/StageBar";
import TopBar from "../panes/TopBar";
import { useToast } from "../toast";
import type { KinEvent, SessionDetail } from "../types";
import { Empty, Spinner } from "../ui";
import { SessionCtx, type RunBody, type SessionState } from "./session-context";

export default function Session() {
  const { id = "" } = useParams();
  const { toast, error } = useToast();
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [runFlag, setRunFlag] = useState<boolean | null>(null);
  const refreshTimer = useRef<number | undefined>(undefined);
  const alive = useRef(true);
  const detailRef = useRef<SessionDetail | null>(null);
  detailRef.current = detail;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    try {
      const d = await kin.session(id);
      if (!alive.current) return;
      setDetail(d);
      setLoadErr(null);
      setRunFlag(null); // the server is authoritative once we have a fresh detail
    } catch (e) {
      if (!alive.current) return;
      if (e instanceof ApiError && e.status === 404) setLoadErr("Session not found.");
      else if (!detailRef.current) setLoadErr((e as Error).message);
      else toast(`Refresh failed: ${(e as Error).message}`, "warn");
    }
  }, [id, toast]);

  const scheduleRefresh = useCallback(
    (delay = 250) => {
      window.clearTimeout(refreshTimer.current);
      refreshTimer.current = window.setTimeout(() => refresh(), delay);
    },
    [refresh],
  );

  useEffect(() => {
    setDetail(null);
    setSelected(null);
    setRunFlag(null);
    refresh();
    return () => window.clearTimeout(refreshTimer.current);
  }, [id, refresh]);

  const onEvent = useCallback(
    (ev: KinEvent) => {
      if (ev.kind === "run_start") setRunFlag(true);
      if (ev.kind === "run_end" || ev.kind === "error") {
        setRunFlag(false);
        scheduleRefresh(1200); // the background task finishes just after run_end is written
      }
      if (REFRESH_KINDS.has(ev.kind)) scheduleRefresh();
    },
    [scheduleRefresh],
  );
  const { events, connected } = useEvents(id, onEvent);

  // Fallback polling while a run is active (covers a dropped SSE connection).
  const running = runFlag !== null ? runFlag : !!detail?.running;
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => refresh(), 6000);
    return () => window.clearInterval(t);
  }, [running, refresh]);

  const runBusy = useCallback(
    async <T,>(label: string, fn: () => Promise<T>): Promise<T | undefined> => {
      setBusy(label);
      try {
        return await fn();
      } finally {
        if (alive.current) setBusy(null);
      }
    },
    [],
  );

  const startRun = useCallback(
    async (body: RunBody): Promise<boolean> => {
      try {
        await kin.run(id, { budget: 8, critic_rounds: 2, ...body });
        setRunFlag(true);
        toast(body.answer ? "Answer sent — designer resuming" : "Designer started", "info");
        scheduleRefresh(400);
        return true;
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) toast("A run is already in progress", "warn");
        else if (e instanceof ApiError && e.status === 412) toast("Add your OpenAI API key in Settings to run the designer", "warn");
        else error(e, "Could not start the designer");
        return false;
      }
    },
    [id, toast, error, scheduleRefresh],
  );

  const stopRun = useCallback(async () => {
    try {
      const r = await kin.stop(id);
      toast(r.stopped ? "Run stopped" : "No run was in progress", r.stopped ? "warn" : "info");
      setRunFlag(false);
      scheduleRefresh(600);
    } catch (e) {
      error(e, "Could not stop");
    }
  }, [id, toast, error, scheduleRefresh]);

  const latestIter = useMemo(() => (detail && detail.iterations.length ? detail.iterations[detail.iterations.length - 1] : null), [detail]);
  const selectedIter = useMemo(() => {
    if (!detail) return null;
    if (selected === null) return latestIter;
    return detail.iterations.find((it) => it.iteration === selected) || latestIter;
  }, [detail, selected, latestIter]);

  const stlVersion = `${detail?.meta.iteration ?? 0}`;

  const state: SessionState = useMemo(
    () => ({
      sid: id,
      detail,
      refresh,
      events,
      connected,
      running,
      busy,
      runBusy,
      selected,
      setSelected,
      latestIter,
      selectedIter,
      startRun,
      stopRun,
      stlVersion,
    }),
    [id, detail, refresh, events, connected, running, busy, runBusy, selected, latestIter, selectedIter, startRun, stopRun, stlVersion],
  );

  useEffect(() => {
    document.title = detail ? `${detail.meta.name} — Kintsugi` : "Kintsugi";
    return () => {
      document.title = "Kintsugi";
    };
  }, [detail]);

  if (loadErr) {
    return (
      <div className="home">
        <Empty title="Could not open session">
          <div>{loadErr}</div>
          <div className="mt">
            <Link to="/" className="btn btn-sm">
              ← All sessions
            </Link>
          </div>
        </Empty>
      </div>
    );
  }
  if (!detail) {
    return (
      <div className="home">
        <Spinner label="Opening session…" />
      </div>
    );
  }

  return (
    <SessionCtx.Provider value={state}>
      <div className="ws">
        <div className="ws-top">
          <TopBar />
          <StageBar />
        </div>
        <div className="ws-left">
          <LeftPane />
        </div>
        <div className="ws-center">
          <CenterPane />
        </div>
        <div className="ws-right">
          <RightPane />
        </div>
      </div>
    </SessionCtx.Provider>
  );
}
