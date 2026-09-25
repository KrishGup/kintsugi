import { useEffect, useRef, useState } from "react";
import type { KinEvent } from "./types";

// Event names the backend emits (the SSE event name equals the `kind` field of the events.jsonl line).
export const EVENT_KINDS = [
  "run_start",
  "assistant",
  "tool_use",
  "iteration",
  "critic_start",
  "critic",
  "critic_followup",
  "narration",
  "question",
  "answer",
  "run_end",
  "error",
  "photo",
  "estimate",
  "dim_confirmed",
  "spec_updated",
  "coupon",
  "coupon_result",
  "export",
  "intake",
  "branch",
  "event",
];

// Events after which the detail model (GET /api/sessions/{id}) should be refetched.
export const REFRESH_KINDS = new Set([
  "iteration",
  "critic",
  "run_start",
  "run_end",
  "export",
  "photo",
  "spec_updated",
  "estimate",
  "dim_confirmed",
  "coupon",
  "coupon_result",
  "intake",
  "branch",
  "question",
  "answer",
  "error",
  "narration",
]);

export interface EventStream {
  events: KinEvent[];
  connected: boolean;
}

/** Tails GET /api/sessions/{id}/events over SSE, replaying history from the start and reconnecting with `since`. */
export function useEvents(sid: string | undefined, onEvent?: (ev: KinEvent) => void): EventStream {
  const [events, setEvents] = useState<KinEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (!sid) return;
    let es: EventSource | null = null;
    let closed = false;
    let lastId = 0;
    let retry: number | undefined;
    const seen = new Set<number>();
    setEvents([]);

    const open = () => {
      if (closed) return;
      es = new EventSource(`/api/sessions/${encodeURIComponent(sid)}/events?since=${lastId}`);
      const onMsg = (e: MessageEvent) => {
        if (e.type === "ping") return;
        let data: Record<string, unknown> = {};
        try {
          data = JSON.parse(e.data || "{}");
        } catch {
          return;
        }
        const id = Number(e.lastEventId || lastId + 1);
        if (Number.isFinite(id)) lastId = Math.max(lastId, id);
        if (seen.has(id)) return;
        seen.add(id);
        const ev: KinEvent = { ...(data as object), id, t: Number(data.t) || Date.now() / 1000, kind: String(data.kind || e.type) };
        setEvents((prev) => [...prev, ev]);
        handler.current?.(ev);
      };
      for (const k of EVENT_KINDS) es.addEventListener(k, onMsg as EventListener);
      es.addEventListener("ping", () => setConnected(true));
      es.onmessage = onMsg;
      es.onopen = () => setConnected(true);
      es.onerror = () => {
        setConnected(false);
        // EventSource would auto-reconnect with the same URL (since=0) and replay everything; do it ourselves.
        es?.close();
        es = null;
        if (!closed) retry = window.setTimeout(open, 2000);
      };
    };
    open();
    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
      es?.close();
      setConnected(false);
    };
  }, [sid]);

  return { events, connected };
}
