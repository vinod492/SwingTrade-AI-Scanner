/** WebSocket connection + alert toast surface. Reconnects with backoff,
 * invalidates queries on worker pushes, and raises toasts for alerts. */
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { WsEvent } from "../api/types";

interface Toast {
  id: number;
  ticker: string;
  message: string;
  rule_type: string;
}

interface LiveState {
  connected: boolean;
  toasts: Toast[];
  dismiss: (id: number) => void;
}

const LiveContext = createContext<LiveState>({ connected: false, toasts: [], dismiss: () => {} });
let toastSeq = 1;

export function LiveProvider({ children }: { children: React.ReactNode }) {
  const [connected, setConnected] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const qc = useQueryClient();
  const retryRef = useRef(1000);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let timer: number | undefined;

    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/ws`);
      ws.onopen = () => {
        setConnected(true);
        retryRef.current = 1000;
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) {
          timer = window.setTimeout(connect, retryRef.current);
          retryRef.current = Math.min(retryRef.current * 2, 15000);
        }
      };
      ws.onmessage = (msg) => {
        let event: WsEvent;
        try {
          event = JSON.parse(msg.data as string) as WsEvent;
        } catch {
          return;
        }
        if (event.type === "scanner") {
          qc.invalidateQueries({ queryKey: ["scanner"] });
          qc.invalidateQueries({ queryKey: ["ideas"] });
        } else if (event.type === "alert") {
          qc.invalidateQueries({ queryKey: ["alert-events"] });
          const toast: Toast = {
            id: toastSeq++,
            ticker: event.payload.ticker,
            message: event.payload.message,
            rule_type: event.payload.rule_type,
          };
          setToasts((prev) => [...prev.slice(-3), toast]);
          window.setTimeout(
            () => setToasts((prev) => prev.filter((t) => t.id !== toast.id)),
            8000,
          );
        } else if (event.type === "backtest_done") {
          qc.invalidateQueries({ queryKey: ["backtests"] });
          qc.invalidateQueries({ queryKey: ["backtest"] });
        }
      };
    };

    connect();
    return () => {
      closed = true;
      if (timer) window.clearTimeout(timer);
      ws?.close();
    };
  }, [qc]);

  const dismiss = (id: number) => setToasts((prev) => prev.filter((t) => t.id !== id));

  return (
    <LiveContext.Provider value={{ connected, toasts, dismiss }}>
      {children}
    </LiveContext.Provider>
  );
}

export const useLive = () => useContext(LiveContext);
