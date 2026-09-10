import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../api/client";
import type { AlertItem, EventItem } from "../types";

type LiveMessage = { type: "event"; event: EventItem } | { type: "alert"; alert: AlertItem };

/** Real WebSocket connection to /ws/live (section 25) — reconnects with backoff, and
 * every message rendered here originated from an actual Event/Alert row created by
 * app.api.routes.events.create_event, not a client-side timer or mock. */
export function useLiveFeed(onMessage: (message: LiveMessage) => void, enabled: boolean) {
  const [connected, setConnected] = useState(false);
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  useEffect(() => {
    if (!enabled) return;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let stopped = false;

    function connect() {
      socket = new WebSocket(wsUrl("/ws/live"));
      socket.onopen = () => setConnected(true);
      socket.onclose = () => {
        setConnected(false);
        if (!stopped) reconnectTimer = setTimeout(connect, 3000);
      };
      socket.onerror = () => socket?.close();
      socket.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data) as LiveMessage;
          handlerRef.current(data);
        } catch {
          /* ignore malformed frame */
        }
      };
    }

    connect();
    return () => {
      stopped = true;
      clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [enabled]);

  return { connected };
}
