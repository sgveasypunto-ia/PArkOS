/**
 * Persistent print retry queue (HU-F5.1 T2.2, design.md §2).
 *
 * FIFO queue backed by `electron-store` under key `parkos.print.queue.v1`.
 * Each item carries `attempts`, `nextRetryAt`, and a typed `lastError`.
 * When `escpos-usb` raises, the IPC handler calls `enqueue(payload)`
 * and a background drain loop picks items up when `nextRetryAt <= now`.
 *
 * Backoff schedule (DEC-SUC-08):
 *   attempt 1 → wait 5 s
 *   attempt 2 → wait 15 s
 *   attempt 3 → wait 60 s
 *   attempt 4 → wait 60 s
 *   attempt 5 → wait 60 s
 *   after 5 failed attempts → `estado='fallido_permanente'` + terminal
 *   `print_failed_terminal` event; the item NEVER gets deleted from
 *   `electron-store` (audit-first compliance — `reclamos` workflow can
 *   still inspect history).
 *
 * The drain timer uses `setTimeout` recursively so we never overlap
 * retries and we honour the per-item `nextRetryAt` exactly.
 */
import { randomUUID } from 'node:crypto';

import {
  BACKOFF_MS,
  MAX_ATTEMPTS,
  QUEUE_STORE_KEY,
  type PrintPayload,
  type PrinterErrorCode,
  type PrintStatusEvent,
  type QueueItem,
  type QueueStatus,
} from '../types/print';
import type { LogLike } from './printer';

/** Minimal `electron-store` shape used by `PrintQueue`. */
export interface QueueStoreLike {
  get(key: string): unknown;
  set(key: string, value: unknown): void;
  delete(key: string): void;
}

/** Emitter interface used to broadcast `print:status` to the renderer. */
export type StatusEmitter = (event: PrintStatusEvent) => void;

/** Callback that performs the actual print; the queue owns retry scheduling. */
export type PrintFn = (
  item: QueueItem,
) => Promise<void>;

/**
 * `class PrintQueue` — singleton-scoped per Electron main process.
 * The single-instance lock (DEC-UPD-07 / DEC-SUC-19) guarantees there
 * is only one queue per machine.
 */
export class PrintQueue {
  private readonly store: QueueStoreLike;
  private readonly log: LogLike;
  private readonly emitStatus: StatusEmitter;
  private readonly performPrint: PrintFn;
  private timer: NodeJS.Timeout | null = null;
  private draining = false;
  private lastSuccessAt: number | null = null;
  private lastError: PrinterErrorCode | null = null;

  public constructor(
    store: QueueStoreLike,
    log: LogLike,
    performPrint: PrintFn,
    emitStatus: StatusEmitter = () => undefined,
  ) {
    this.store = store;
    this.log = log;
    this.performPrint = performPrint;
    this.emitStatus = emitStatus;
  }

  /** Read the queue from `electron-store`. Always returns an array (never undefined). */
  private readAll(): QueueItem[] {
    const raw = this.store.get(QUEUE_STORE_KEY);
    if (!Array.isArray(raw)) return [];
    return raw as QueueItem[];
  }

  /** Persist the queue verbatim — append-only, never physically delete. */
  private writeAll(items: QueueItem[]): void {
    this.store.set(QUEUE_STORE_KEY, items);
  }

  /** Append a payload to the queue and return its UUID. */
  public enqueue(payload: Pick<PrintPayload, 'buffer' | 'ticketId' | 'uuidRegistro'>, vid: number, pid: number): string {
    const items = this.readAll();
    const item: QueueItem = {
      id: randomUUID(),
      buffer: payload.buffer,
      vid,
      pid,
      ticketId: payload.ticketId,
      uuidRegistro: payload.uuidRegistro,
      attempts: 0,
      nextRetryAt: Date.now() + BACKOFF_MS[0]!,
      addedAt: Date.now(),
      estado: 'pending',
    };
    items.push(item);
    this.writeAll(items);
    this.emitStatus({ type: 'queue_grew', queueId: item.id, ticketId: item.ticketId });
    this.scheduleNextDrain();
    return item.id;
  }

  /** Summary used by `bridge.imprimir.getQueue()`. */
  public getQueue(): QueueStatus {
    const items = this.readAll();
    return {
      pending: items.filter((i) => i.estado === 'pending').length,
      retrying: items.filter((i) => i.estado === 'retrying').length,
      fallido_permanente: items.filter((i) => i.estado === 'fallido_permanente').length,
      lastSuccessAt: this.lastSuccessAt,
      lastError: this.lastError,
    };
  }

  /**
   * Mark `fallido_permanente` items for a given `ticketId` as cleared
   * for display purposes only. The items stay in `electron-store`
   * forever — the audit-first principle for an append-only log.
   */
  public clearFailed(ticketId: string): void {
    const items = this.readAll();
    const touched = items.filter((i) => i.ticketId === ticketId && i.estado === 'fallido_permanente');
    // We can't mutate `estado` (that field is reserved for `pending`/`retrying`/`fallido_permanente`).
    // Display-only clearing means: leave items in place but the renderer will no longer render them
    // once `clearFailed` has been called for that `ticketId`. We track cleared IDs separately.
    const clearedRaw = this.store.get('parkos.print.queue.cleared.v1');
    const cleared = (Array.isArray(clearedRaw) ? clearedRaw : []) as string[];
    const clearedSet = new Set(cleared);
    for (const item of touched) clearedSet.add(item.id);
    this.store.set('parkos.print.queue.cleared.v1', [...clearedSet]);
  }

  /**
   * Process one item at a time. Returns when the item has either been
   * printed, rescheduled, or marked terminal.
   */
  private async processItem(item: QueueItem): Promise<void> {
    let buf: Buffer;
    try {
      buf = Buffer.from(item.buffer, 'base64');
    } catch (err) {
      this.log.warn('printQueue.decode_failed', {
        queueId: item.id,
        ticketId: item.ticketId,
        err: String(err),
      });
      this.markTerminal(item, 'printer_offline');
      return;
    }

    try {
      await this.performPrint({ ...item, buffer: buf.toString('base64') });
      this.lastSuccessAt = Date.now();
      this.lastError = null;
      this.removeItem(item.id);
      this.emitStatus({
        type: 'print_succeeded',
        queueId: item.id,
        ticketId: item.ticketId,
      });
    } catch (err) {
      const code =
        err && typeof err === 'object' && 'code' in err
          ? (err as { code: PrinterErrorCode }).code
          : 'printer_offline';
      this.lastError = code;
      this.bumpAttempts(item, code);
    }
  }

  private bumpAttempts(item: QueueItem, code: PrinterErrorCode): void {
    const items = this.readAll();
    const idx = items.findIndex((i) => i.id === item.id);
    if (idx < 0) return;
    const next = items[idx]!;
    const newAttempts = next.attempts + 1;
    if (newAttempts >= MAX_ATTEMPTS) {
      const updated: QueueItem = { ...next, attempts: newAttempts, estado: 'fallido_permanente', lastError: code };
      items[idx] = updated;
      this.writeAll(items);
      this.emitStatus({
        type: 'print_failed_terminal',
        queueId: updated.id,
        ticketId: updated.ticketId,
        error: code,
      });
      this.log.error('printQueue.terminal', {
        queueId: updated.id,
        ticketId: updated.ticketId,
        attempts: newAttempts,
        error: code,
      });
      return;
    }
    const scheduleIdx = Math.min(newAttempts - 1, BACKOFF_MS.length - 1);
    const waitMs = BACKOFF_MS[scheduleIdx]!;
    const updated: QueueItem = {
      ...next,
      attempts: newAttempts,
      nextRetryAt: Date.now() + waitMs,
      estado: 'retrying',
      lastError: code,
    };
    items[idx] = updated;
    this.writeAll(items);
    this.emitStatus({
      type: 'print_failed',
      queueId: updated.id,
      ticketId: updated.ticketId,
      error: code,
      attempts: newAttempts,
    });
    this.log.warn('printQueue.retry_scheduled', {
      queueId: updated.id,
      ticketId: updated.ticketId,
      attempts: newAttempts,
      nextRetryAt: updated.nextRetryAt,
    });
  }

  private markTerminal(item: QueueItem, code: PrinterErrorCode): void {
    const items = this.readAll();
    const idx = items.findIndex((i) => i.id === item.id);
    if (idx < 0) return;
    const updated: QueueItem = {
      ...items[idx]!,
      estado: 'fallido_permanente',
      lastError: code,
      attempts: MAX_ATTEMPTS,
    };
    items[idx] = updated;
    this.writeAll(items);
    this.emitStatus({
      type: 'print_failed_terminal',
      queueId: updated.id,
      ticketId: updated.ticketId,
      error: code,
    });
  }

  /** Remove a single item (only ever called on `print_succeeded`). */
  private removeItem(id: string): void {
    const items = this.readAll();
    this.writeAll(items.filter((i) => i.id !== id));
  }

  /**
   * Drain loop — process every item whose `nextRetryAt <= now` once,
   * then schedule the next tick from the smallest remaining `nextRetryAt`.
   *
   * Single-flight via `this.draining` flag so two ticks never overlap.
   */
  public async drain(): Promise<void> {
    if (this.draining) return;
    this.draining = true;
    try {
      const items = this.readAll();
      const now = Date.now();
      const due = items.filter((i) => i.estado !== 'fallido_permanente' && i.nextRetryAt <= now);
      for (const item of due) {
        await this.processItem(item);
      }
    } finally {
      this.draining = false;
      this.scheduleNextDrain();
    }
  }

  /**
   * (Re)compute the next `setTimeout` based on the earliest
   * `nextRetryAt` among pending/retrying items. Past-due items trigger
   * `drain()` immediately.
   *
   * Called after `enqueue`, after `processItem`, and once on boot via
   * `start()` so app restart resumes the schedule.
   */
  public scheduleNextDrain(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    const items = this.readAll().filter((i) => i.estado !== 'fallido_permanente');
    if (items.length === 0) return;
    const next = items.reduce((min, item) => Math.min(min, item.nextRetryAt), Number.POSITIVE_INFINITY);
    if (!Number.isFinite(next)) return;
    const waitMs = Math.max(0, next - Date.now());
    this.timer = setTimeout(() => {
      void this.drain();
    }, waitMs);
  }

  /**
   * Resume the queue after app boot — kick a `drain()` so past-due
   * items retry immediately, then arm the timer for future-dated ones.
   */
  public start(): void {
    this.log.info('printQueue.start', {
      size: this.readAll().length,
      status: this.getQueue(),
    });
    void this.drain();
  }

  /** Cancel the timer. Called on `app.before-quit` to avoid leaks. */
  public stop(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
}