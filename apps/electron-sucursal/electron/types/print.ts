/**
 * Printer IPC payload types — single source of truth for HU-F5.1.
 *
 * Every type is `z.infer<typeof schema>` so the runtime Zod validator
 * (used by the IPC handler before touching hardware) and the
 * compile-time TypeScript shape can never drift apart (design.md §6
 * Decision 1).
 *
 * Re-exported by `electron/bridge.d.ts` (renderer-facing) and consumed by
 * `electron/services/printQueue.ts` + `electron/ipc/imprimir.ts`.
 */
import { z } from 'zod';

/**
 * `printPayloadSchema` — the IPC payload accepted by `print:ticket`.
 *
 * Constraints (HU-F5.1 + DEC-SUC-08):
 *   - `buffer` is a base64-encoded `Buffer` of pre-serialised ESC/POS
 *     bytes. Serialisation itself is HU-F5.2 (`escposBuilder`); F5.1
 *     intentionally accepts ONLY this shape.
 *   - `ticketId` is operator-supplied; max 64 chars to keep logs tame.
 *   - `vid` / `pid` are optional — when absent the service picks the
 *     first printer reported by `escpos-usb.findPrinter()`.
 *   - `uuidRegistro`, when present, links the print to an
 *     `ingresos.uuid` / `salidas.uuid` / `facturas.uuid` so F6+ can
 *     later write `log_transaccional.accion='impreso'` (A-05).
 */
export const printPayloadSchema = z.object({
  buffer: z.string().min(1, 'buffer must be non-empty base64'),
  ticketId: z.string().min(1).max(64),
  cut: z.boolean().default(false),
  cashDrawer: z.boolean().optional(),
  vid: z.number().int().min(0).max(0xffff).optional(),
  pid: z.number().int().min(0).max(0xffff).optional(),
  uuidRegistro: z.string().uuid().optional(),
});
export type PrintPayload = z.infer<typeof printPayloadSchema>;

/** Catalog of typed error codes the F5.1 surface may emit (spec §Error Catalog). */
export const printerErrorSchema = z.enum([
  'bridge_imprimir_invalid_payload',
  'printer_offline',
  'printer_disconnected',
  'print_failed_terminal',
]);
export type PrinterErrorCode = z.infer<typeof printerErrorSchema>;

/** IPC reply shape — `{ok:true}` on success, `{ok:false, error, queueId?}` on failure. */
export const printResultSchema = z.object({
  ok: z.boolean(),
  error: printerErrorSchema.optional(),
  queueId: z.string().uuid().nullable(),
  issues: z
    .array(
      z.object({
        path: z.array(z.union([z.string(), z.number()])),
        message: z.string(),
      }),
    )
    .optional(),
});
export type PrintResult = z.infer<typeof printResultSchema>;

/** Persistent queue item — never physically deleted (spec §5 attempts). */
export const queueItemSchema = z.object({
  id: z.string().uuid(),
  buffer: z.string(), // base64
  vid: z.number().int(),
  pid: z.number().int(),
  ticketId: z.string(),
  uuidRegistro: z.string().uuid().optional(),
  attempts: z.number().int().min(0).max(5),
  nextRetryAt: z.number().int(), // epoch ms
  addedAt: z.number().int(),
  estado: z.enum(['pending', 'retrying', 'fallido_permanente']),
  lastError: printerErrorSchema.optional(),
});
export type QueueItem = z.infer<typeof queueItemSchema>;

/** Summary the renderer polls via `bridge.imprimir.getQueue()`. */
export const queueStatusSchema = z.object({
  pending: z.number().int().min(0),
  retrying: z.number().int().min(0),
  fallido_permanente: z.number().int().min(0),
  lastSuccessAt: z.number().int().nullable(),
  lastError: printerErrorSchema.nullable(),
});
export type QueueStatus = z.infer<typeof queueStatusSchema>;

/** Push event types emitted via `print:status` (spec §R3). */
export type PrintStatusEvent =
  | {
      type: 'print_succeeded';
      queueId: string | null;
      ticketId: string;
    }
  | {
      type: 'print_failed';
      queueId: string;
      ticketId: string;
      error: PrinterErrorCode;
      attempts: number;
    }
  | {
      type: 'print_failed_terminal';
      queueId: string;
      ticketId: string;
      error: PrinterErrorCode;
    }
  | {
      type: 'queue_grew';
      queueId: string;
      ticketId: string;
    };

/** Extend the bridge-surface USB device shape with `bDeviceClass` (USB-IF Printer = `0x07`). */
export interface USBDevice {
  vendorId: number;
  productId: number;
  productName: string | null;
  serialNumber: string | null;
  /** USB device class; `0x07` = Printer. */
  class: number;
}

/**
 * Backoff schedule (ms) per attempt number (DEC-SUC-08).
 *
 * Index 0 corresponds to the schedule AFTER attempt 1 (i.e. before
 * attempt 2). Stored as `[5000, 15000, 60000, 60000, 60000]` so attempt
 * `N` (1 ≤ N ≤ 5) consults `BACKOFF_MS[N - 1]`. After attempt 5 fails
 * the item is marked `fallido_permanente`.
 */
export const BACKOFF_MS: readonly number[] = [5_000, 15_000, 60_000, 60_000, 60_000] as const;

/** Maximum attempts before an item is considered permanently failed. */
export const MAX_ATTEMPTS = 5;

/** electron-store key holding the queue as a JSON array. */
export const QUEUE_STORE_KEY = 'parkos.print.queue.v1';