/**
 * Bridge IPC typed surface — exposed to the renderer via contextBridge.
 *
 * Stable contract (DEC-FETCH-08 + design.md §6.1):
 *   8 groups, 15 methods (post-installer-port-reconciliation 2026-09-27).
 *   - imprimir          (3)  → print ticket via escpos-usb  (F5.1 main)
 *                              + getQueue() poll status
 *                              + onStatus(handler) push events
 *   - usb               (1)  → list USB devices            (F5.1 consumer)
 *   - kiosk             (1)  → toggle kiosk mode           (F2.3 consumer)
 *   - app               (1)  → quit Electron app           (F2.3 consumer)
 *   - apiStatus         (1)  → backend health probe        (F11.x consumer)
 *   - config            (1)  → resolved API origin         (parkosFetch's
 *                              resolveRequestUrl.ts consumer - installer
 *                              port reconciliation, DEC-INST-03)
 *   - authStore         (3)  → electron-store get/set/del  (F2.2 authStore)
 *   - tarifasStore      (3)  → electron-store get/set/del  (F4.2 cache)
 *
 * Implemented by `preload.ts` via whitelist (no spread) so the renderer
 * never sees the raw `ipcRenderer` handle — the only legitimate channel
 * for cross-process communication.
 */
import type { PrintPayload, PrintResult, PrintStatusEvent, QueueStatus } from './types/print';

export type { PrintPayload, PrintResult, QueueStatus, PrintStatusEvent } from './types/print';

export interface PrintLine {
  text: string;
  bold?: boolean;
  align?: 'left' | 'center' | 'right';
}

export interface USBDevice {
  vendorId: number;
  productId: number;
  productName: string | null;
  serialNumber: string | null;
  /** USB-IF class code; F5.1 sets `0x07` for printers. */
  class: number;
}

export interface ApiStatus {
  /** `true` solo si el backend respondió 2xx (independiente del latency). */
  ok: boolean;
  /** Latencia del ping en milisegundos. `-1` si no hay medición (cache inicial). */
  latency_ms: number;
  /** HTTP status code si la respuesta fue HTTP (4xx/5xx). Undefined para timeout/network error. */
  code?: number;
}

export interface BridgeSurface {
  /**
   * Print a thermal ticket.
   *
   * The function itself returns the immediate attempt result. The two
   * helpers attached to it support the renderer's async UX needs:
   *   - `getQueue()` polls the persisted queue status (banners).
   *   - `onStatus(handler)` subscribes to push events from the drain
   *     loop and returns an unsubscribe function.
   *
   * The pattern (`Object.assign(fn, { … })`) preserves the original
   * call signature so the F2.2 call site (`bridge.imprimir(payload)`)
   * keeps working unchanged.
   */
  imprimir: {
    (payload: PrintPayload): Promise<PrintResult>;
    getQueue(): Promise<QueueStatus>;
    onStatus(handler: (event: PrintStatusEvent) => void): () => void;
  };

  usb: {
    /** Lista dispositivos USB conectados (Printer class `0x07`). F5.1+ consumer. */
    list(): Promise<USBDevice[]>;
  };

  kiosk: {
    /** Habilita/deshabilita kiosko mode. F2.3 consumer. */
    toggle(on: boolean): void;
  };

  app: {
    /** Cierra la app. F2.3 consumer (logout cleanup). */
    quit(): void;
  };

  apiStatus: {
    /** Health check del backend (ping /health). F11.x consumer. */
    get(): Promise<ApiStatus>;
  };

  config: {
    /**
     * Origin resuelto por el main process (`PARKOS_API_ORIGIN`, default
     * `http://127.0.0.1:8000`) para que el renderer arme URLs absolutas
     * bajo `file://` sin un puerto hardcodeado en el bundle compilado.
     * Consumer: `apps/ui-kit/src/fetch/resolveRequestUrl.ts`.
     */
    getApiOrigin(): Promise<string>;
  };

  authStore: {
    /** electron-store read. F2.2 authStore consumer. */
    get(key: string): Promise<string | null>;
    /** electron-store write. F2.2 authStore consumer. */
    set(key: string, value: string): Promise<void>;
    /** electron-store delete. F2.2 authStore consumer. */
    delete(key: string): Promise<void>;
  };

  tarifasStore: {
    /** electron-store read. F4.2 useTarifasVigentes cache consumer. */
    get(key: string): Promise<string | null>;
    /** electron-store write. F4.2 useTarifasVigentes cache consumer. */
    set(key: string, value: string): Promise<void>;
    /** electron-store delete. F4.2 useTarifasVigentes cache consumer. */
    delete(key: string): Promise<void>;
  };
}

declare global {
  interface Window {
    bridge: BridgeSurface;
  }
}

export {};