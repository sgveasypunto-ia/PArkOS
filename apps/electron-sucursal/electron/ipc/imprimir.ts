/**
 * IPC handlers for `bridge.imprimir` (HU-F5.1 T2.3, design.md §3).
 *
 * Three IPC channels:
 *   - `print:ticket`               → handler entry; Zod-validates, then
 *                                   either delegates to the printer or
 *                                   enqueues + emits `print_failed`.
 *   - `print:queue:get`            → returns `QueueStatus` for the renderer
 *                                   banner / manual refresh.
 *   - `print:queue:clear-failed`   → marks `fallido_permanente` items for a
 *                                   given `ticketId` as display-cleared.
 *
 * Status events flow one-way via `mainWindow.webContents.send('print:status', ...)`.
 * The renderer subscribes via `bridge.imprimir.onStatus(handler)` (preload).
 */
import { randomUUID } from 'node:crypto';

import {
  printPayloadSchema,
  type PrintPayload,
  type PrintResult,
  type QueueStatus,
} from '../types/print';
import { print, PrinterError } from '../services/printer';
import type { PrintQueue } from '../services/printQueue';
import type { LogLike } from '../services/printer';

/** `ipcMain.handle` channel signature — we accept the real `IpcMain` from Electron. */
export interface IpcMainLike {
  handle: (channel: string, handler: (event: unknown, ...args: unknown[]) => unknown) => void;
}

/** `BrowserWindow.webContents` subset we need (`send` for push events). */
export interface WebContentsLike {
  send: (channel: string, payload: unknown) => void;
}

/** Optional — when null the handler skips `print:status` pushes (used in unit tests). */
export type MainWindowLike = {
  webContents: WebContentsLike;
} | null;

export interface RegisterImprimirHandlersDeps {
  ipcMain: IpcMainLike;
  queue: PrintQueue;
  mainWindow: MainWindowLike;
  log: LogLike;
}

/**
 * Validate a payload against `printPayloadSchema`. Returns either the
 * parsed payload or a `PrintResult` carrying the typed error + Zod issues.
 */
function validate(payload: unknown): { ok: true; payload: PrintPayload } | { ok: false; result: PrintResult } {
  const parsed = printPayloadSchema.safeParse(payload);
  if (parsed.success) return { ok: true, payload: parsed.data };
  const issues = parsed.error.issues.map((issue) => ({
    path: issue.path.map((p) => (typeof p === 'number' ? p : String(p))),
    message: issue.message,
  }));
  return {
    ok: false,
    result: { ok: false, error: 'bridge_imprimir_invalid_payload', queueId: null, issues },
  };
}

function broadcast(deps: RegisterImprimirHandlersDeps, payload: unknown): void {
  deps.mainWindow?.webContents.send('print:status', payload);
}

/**
 * Resolve `(vid, pid)` either from the payload or by enumerating
 * `escpos-usb.findPrinter()`. Falls back to `0x0000 / 0x0000` when no
 * device is present so the printer service still produces a typed error
 * path the renderer can recognise.
 */
async function resolveVidPid(payload: PrintPayload): Promise<{ vid: number; pid: number }> {
  if (payload.vid !== undefined && payload.pid !== undefined) {
    return { vid: payload.vid, pid: payload.pid };
  }
  const { listDevices } = await import('../services/printer');
  const devices = listDevices();
  const first = devices[0];
  if (!first) return { vid: 0, pid: 0 };
  return { vid: first.vendorId, pid: first.productId };
}

/**
 * The actual `print:ticket` handler body. Extracted as a named function
 * so tests can exercise the validation/queue path without going through
 * the full Electron IPC plumbing.
 */
export async function handlePrintTicket(
  payload: unknown,
  deps: RegisterImprimirHandlersDeps,
): Promise<PrintResult> {
  const validation = validate(payload);
  if (!validation.ok) {
    deps.log.warn('imprimir.invalid_payload', { issues: validation.result.issues });
    broadcast(deps, {
      type: 'print_failed',
      queueId: randomUUID(), // synthetic — never persisted, only logged
      ticketId: 'invalid',
      error: 'bridge_imprimir_invalid_payload',
      attempts: 0,
    });
    return validation.result;
  }

  const parsed = validation.payload;
  const buf = Buffer.from(parsed.buffer, 'base64');
  const { vid, pid } = await resolveVidPid(parsed);

  try {
    await print(buf, vid, pid, deps.log);
    broadcast(deps, { type: 'print_succeeded', queueId: null, ticketId: parsed.ticketId });
    return { ok: true, error: undefined, queueId: null };
  } catch (err) {
    if (err instanceof PrinterError) {
      if (err.code === 'printer_offline') {
        const queueId = deps.queue.enqueue(
          { buffer: parsed.buffer, ticketId: parsed.ticketId, uuidRegistro: parsed.uuidRegistro },
          vid,
          pid,
        );
        deps.log.warn('imprimir.queued_offline', { queueId, ticketId: parsed.ticketId });
        return { ok: false, error: 'printer_offline', queueId };
      }
      return { ok: false, error: err.code, queueId: null };
    }
    deps.log.error('imprimir.unexpected_error', { err: String(err) });
    return { ok: false, error: 'printer_offline', queueId: null };
  }
}

/** Register all three IPC channels against `ipcMain`. */
export function registerImprimirHandlers(deps: RegisterImprimirHandlersDeps): void {
  deps.ipcMain.handle('print:ticket', (_event: unknown, payload: unknown) =>
    handlePrintTicket(payload, deps),
  );

  deps.ipcMain.handle('print:queue:get', (): QueueStatus => deps.queue.getQueue());

  deps.ipcMain.handle('print:queue:clear-failed', (_event: unknown, ticketId: unknown) => {
    if (typeof ticketId !== 'string') return false;
    deps.queue.clearFailed(ticketId);
    return true;
  });
}