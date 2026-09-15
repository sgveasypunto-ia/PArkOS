/**
 * Bridge IPC typed surface — exposed to the renderer via contextBridge.
 *
 * Stable contract (DEC-FETCH-08 + design.md §6.1):
 *   6 groups, 8 methods.
 *   - imprimir          (1)  — print ticket via escpos-usb  (F5.1+ consumer)
 *   - usb               (1)  — list USB devices            (F5.1+ consumer)
 *   - kiosk             (1)  — toggle kiosk mode           (F2.3 consumer)
 *   - app               (1)  — quit Electron app           (F2.3 consumer)
 *   - apiStatus         (1)  — backend health probe        (F11.x consumer)
 *   - authStore         (3)  — electron-store get/set/del  (F2.2 authStore)
 *
 * Implemented by `preload.ts` via whitelist (no spread) so the renderer
 * never sees the raw `ipcRenderer` handle — the only legitimate channel
 * for cross-process communication.
 */

export interface PrintLine {
  text: string;
  bold?: boolean;
  align?: 'left' | 'center' | 'right';
}

export interface PrintPayload {
  ticketId: string;
  lines: PrintLine[];
  cut: boolean;
  cashDrawer?: boolean;
}

export interface PrintResult {
  ok: boolean;
}

export interface USBDevice {
  vendorId: number;
  productId: number;
  productName: string | null;
  serialNumber: string | null;
}

export interface ApiStatus {
  online: boolean;
  lastSync: string | null;
}

export interface BridgeSurface {
  /** Imprime ticket en impresora térmica USB. F5.1+ consumer. */
  imprimir(payload: PrintPayload): Promise<PrintResult>;

  usb: {
    /** Lista dispositivos USB conectados. F5.1+ consumer. */
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

  authStore: {
    /** electron-store read. F2.2 authStore consumer. */
    get(key: string): Promise<string | null>;
    /** electron-store write. F2.2 authStore consumer. */
    set(key: string, value: string): Promise<void>;
    /** electron-store delete. F2.2 authStore consumer. */
    delete(key: string): Promise<void>;
  };
}

declare global {
  interface Window {
    bridge: BridgeSurface;
  }
}

export {};
