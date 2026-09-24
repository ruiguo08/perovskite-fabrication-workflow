import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type ToastTone = "info" | "success" | "error";

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

interface ToastContextValue {
  show: (message: string, tone?: ToastTone) => void;
}

const AUTO_DISMISS_MS = 5000;

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, number>());

  const clearTimer = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const dismiss = useCallback(
    (id: number) => {
      clearTimer(id);
      setItems((current) => current.filter((item) => item.id !== id));
    },
    [clearTimer],
  );

  const schedule = useCallback(
    (item: ToastItem) => {
      // Errors stay until the operator dismisses them; the rest auto-hide.
      if (item.tone === "error") {
        return;
      }
      const timer = window.setTimeout(() => dismiss(item.id), AUTO_DISMISS_MS);
      timers.current.set(item.id, timer);
    },
    [dismiss],
  );

  const show = useCallback(
    (message: string, tone: ToastTone = "info") => {
      const id = nextId.current++;
      const item = { id, message, tone };
      setItems((current) => [...current, item]);
      schedule(item);
    },
    [schedule],
  );

  const pause = useCallback((id: number) => clearTimer(id), [clearTimer]);

  const resume = useCallback((item: ToastItem) => schedule(item), [schedule]);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-atomic="false">
        {items.map((item) => (
          <div
            key={item.id}
            className={`toast toast--${item.tone}`}
            role={item.tone === "error" ? "alert" : "status"}
            onMouseEnter={() => pause(item.id)}
            onMouseLeave={() => resume(item)}
          >
            {item.message}
            <button
              type="button"
              className="toast__dismiss"
              aria-label="Dismiss notification"
              onClick={() => dismiss(item.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (context === null) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
