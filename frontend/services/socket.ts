import type { WSEnvelope } from "../types/network";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws";

export type SocketHandlers = {
  onMessage: (message: WSEnvelope) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
};

export function connectSocket(handlers: SocketHandlers) {
  const socket = new WebSocket(WS_URL);

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
  };

  return {
    close: () => socket.close(),
  };
}