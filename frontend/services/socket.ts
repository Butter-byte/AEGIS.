import type { WSEnvelope } from "../types/network";

const WS_URL = import.meta.env.VITE_WS_URL
  ? import.meta.env.VITE_WS_URL
  : "ws://localhost:8000/ws";
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
    console.log("AEGIS: opening websocket", WS_URL)
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

      if (!closedByClient) {
        reconnectTimer = setTimeout(open, RECONNECT_DELAY_MS);
      }
    };
  };

  open();

  return {
    close: () => {
      closedByClient = true;

      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }

      if (socket) {
        if (socket.readyState === WebSocket.CONNECTING) {
          socket.onopen = () => {
            socket?.close();
          };
        } else if (socket.readyState === WebSocket.OPEN) {
          socket.close();
        }
      }
    },
  };
}
