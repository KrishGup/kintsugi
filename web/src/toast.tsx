import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { Close } from "./icons";

export type ToastKind = "info" | "pass" | "fail" | "warn";

interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
}

interface ToastApi {
  toast: (text: string, kind?: ToastKind) => void;
  error: (e: unknown, prefix?: string) => void;
}

const Ctx = createContext<ToastApi>({ toast: () => {}, error: () => {} });

export function useToast(): ToastApi {
  return useContext(Ctx);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((t) => t.id !== id)), []);

  const toast = useCallback(
    (text: string, kind: ToastKind = "info") => {
      const id = ++seq.current;
      setItems((xs) => [...xs.slice(-4), { id, kind, text }]);
      window.setTimeout(() => dismiss(id), kind === "fail" ? 8000 : 4500);
    },
    [dismiss],
  );

  const error = useCallback(
    (e: unknown, prefix?: string) => {
      const msg = e instanceof Error ? e.message : String(e);
      toast(prefix ? `${prefix}: ${msg}` : msg, "fail");
    },
    [toast],
  );

  const value = useMemo(() => ({ toast, error }), [toast, error]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            <span className="toast-text">{t.text}</span>
            <button className="toast-x" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              <Close size={13} />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
