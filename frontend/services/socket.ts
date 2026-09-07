import type { WSEnvelope } from "../types/network";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws";
const RECONNECT_DELAY_MS = 2000;

export type SocketHandlers = {
  onMessage: (message: WSEnvelope) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
};

export function connectSocket(handlers: SocketHandlers) {
  let socket: WebSocket | null = null;
  let closedByClient = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

  const open = () => {
    socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      handlers.onOpen?.();
    };

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as WSEnvelope;
        handlers.onMessage(message);
      } catch (error) {
        console.error("Failed to parse WebSocket message:", error);
      }
    };

    socket.onerror = (error) => {
      handlers.onError?.(error);
    };

    socket.onclose = () => {
      handlers.onClose?.();
      // Reconnect on an unexpected drop; stop once the client closed on purpose
      // (component unmount). One socket at a time — `open` reassigns `socket`.
      if (!closedByClient) {
        reconnectTimer = setTimeout(open, RECONNECT_DELAY_MS);
      }
    };
  };

  open();

  return {
    close: () => {
      closedByClient = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    },
  };
}
