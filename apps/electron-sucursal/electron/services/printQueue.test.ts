/**
 * Unit tests for `electron/services/printQueue.ts` (HU-F5.1 T4.3).
 *
 * Coverage:
 *   - `enqueue` persists JSON to `electron-store` under `parkos.print.queue.v1`.
 *   - Backoff schedule is `[5000, 15000, 60000, 60000, 60000]` for attempts 1..5.
 *   - `nextRetryAt = failedAt + BACKOFF_MS[attempts - 1]`.
 *   - 5 attempts → `fallido_permanente` + terminal `print_failed_terminal` event.
 *   - `clearFailed(ticketId)` only updates the cleared display set, never deletes from store.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BACKOFF_MS, QUEUE_STORE_KEY, type QueueItem } from '../types/print';
import { PrintQueue, type QueueStoreLike, type StatusEmitter } from './printQueue';
import { PrinterError } from './printer';

interface StoreMock extends QueueStoreLike {
  storage: Record<string, unknown>;
}

function makeStore(): StoreMock {
  const storage: Record<string, unknown> = {};
  return {
    storage,
    get: vi.fn((key: string): unknown => storage[key]),
    set: vi.fn((key: string, value: unknown): void => {
      storage[key] = value;
    }),
    delete: vi.fn((key: string): void => {
      delete storage[key];
    }),
  };
}

function makeLog() {
  return { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() };
}

function makeQueue(opts: {
  print?: (item: QueueItem) => Promise<void>;
  onEvent?: StatusEmitter;
} = {}): {
  queue: PrintQueue;
  events: Parameters<StatusEmitter>[0][];
  printImpl: ReturnType<typeof vi.fn>;
} {
  const events: Parameters<StatusEmitter>[0][] = [];
  const printImpl = vi.fn(async (): Promise<void> => undefined);
  const log = makeLog();
  const queue = new PrintQueue(
    makeStore(),
    log,
    opts.print ?? printImpl,
    opts.onEvent ?? ((event) => events.push(event)),
  );
  return { queue, events, printImpl };
}

describe('PrintQueue.enqueue', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-16T12:00:00Z'));
  });

  it('persists the new item under parkos.print.queue.v1 with backoff schedule applied', () => {
    const { queue, events } = makeQueue();
    const queueId = queue.enqueue({ buffer: 'AA==', ticketId: 't-1' }, 0x04b8, 0x0202);
    expect(typeof queueId).toBe('string');
    expect(events.some((e) => e.type === 'queue_grew')).toBe(true);

    const stored = (queue as unknown as { store: QueueStoreLike }).store.get(QUEUE_STORE_KEY);
    expect(Array.isArray(stored)).toBe(true);
    const items = stored as QueueItem[];
    expect(items).toHaveLength(1);
    const item = items[0]!;
    expect(item.attempts).toBe(0);
    expect(item.estado).toBe('pending');
    expect(item.nextRetryAt).toBe(Date.now() + BACKOFF_MS[0]!);
  });
});

describe('PrintQueue.backoff schedule', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-16T12:00:00Z'));
  });

  it('after N failures, nextRetryAt = failedAt + BACKOFF_MS[N-1] for N=1..5', async () => {
    // First attempt always fails. Then we read the queue after each
    // bumpAttempts call to confirm the schedule.
    const { queue } = makeQueue({
      print: vi.fn(async () => {
        throw new PrinterError('printer_offline', 'gone');
      }),
    });
    queue.enqueue({ buffer: 'AA==', ticketId: 't-1' }, 0x04b8, 0x0202);

    const readItems = (): QueueItem[] => {
      const stored = (queue as unknown as { store: QueueStoreLike }).store.get(QUEUE_STORE_KEY);
      return (stored as QueueItem[]) ?? [];
    };

    for (let attempt = 1; attempt <= 5; attempt += 1) {
      // Drive the drain synchronously: jump to nextRetryAt + 1 ms.
      const item = readItems()[0]!;
      vi.setSystemTime(new Date(item.nextRetryAt + 1));
      await queue.drain();
      const updated = readItems()[0]!;
      expect(updated.attempts).toBe(attempt);
      if (attempt < 5) {
        expect(updated.estado).toBe('retrying');
        // nextRetryAt is `Date.now() + BACKOFF_MS[attempt - 1]` (computed at the moment of the bump).
        const expected = Date.now() + BACKOFF_MS[attempt - 1]!;
        // Allow 2 ms drift from the FakeTimers `setSystemTime` resolution.
        expect(Math.abs(updated.nextRetryAt - expected)).toBeLessThanOrEqual(2);
      } else {
        expect(updated.estado).toBe('fallido_permanente');
      }
    }
  });

  it('emits `print_failed_terminal` after 5 failed attempts and keeps the item on disk', async () => {
    const { queue, events } = makeQueue({
      print: vi.fn(async () => {
        throw new PrinterError('printer_offline', 'gone');
      }),
    });
    queue.enqueue({ buffer: 'AA==', ticketId: 't-1' }, 0x04b8, 0x0202);
    for (let i = 0; i < 5; i += 1) {
      const items = (queue as unknown as { store: QueueStoreLike }).store.get(QUEUE_STORE_KEY) as QueueItem[];
      vi.setSystemTime(new Date(items[0]!.nextRetryAt + 1));
      await queue.drain();
    }
    const terminal = events.find((e) => e.type === 'print_failed_terminal');
    expect(terminal).toBeDefined();
    const itemsAfter = (queue as unknown as { store: QueueStoreLike }).store.get(QUEUE_STORE_KEY) as QueueItem[];
    expect(itemsAfter).toHaveLength(1);
    expect(itemsAfter[0]!.estado).toBe('fallido_permanente');
  });

  it('removes the item from disk on `print_succeeded`', async () => {
    const { queue, events } = makeQueue({
      print: vi.fn(async () => undefined),
    });
    queue.enqueue({ buffer: 'AA==', ticketId: 't-2' }, 0x04b8, 0x0202);
    const items = (queue as unknown as { store: QueueStoreLike }).store.get(QUEUE_STORE_KEY) as QueueItem[];
    vi.setSystemTime(new Date(items[0]!.nextRetryAt + 1));
    await queue.drain();
    const itemsAfter = (queue as unknown as { store: QueueStoreLike }).store.get(QUEUE_STORE_KEY) as QueueItem[];
    expect(itemsAfter).toHaveLength(0);
    expect(events.some((e) => e.type === 'print_succeeded')).toBe(true);
  });
});

describe('PrintQueue.clearFailed', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-16T12:00:00Z'));
  });

  it('marks the item as display-cleared without deleting from electron-store', () => {
    const { queue } = makeQueue();
    const id = queue.enqueue({ buffer: 'AA==', ticketId: 't-1' }, 0x04b8, 0x0202);

    const store = (queue as unknown as { store: StoreMock }).store;
    // Force the item into fallido_permanente so clearFailed has something to clear.
    const items = store.get(QUEUE_STORE_KEY) as QueueItem[];
    items[0] = { ...items[0]!, estado: 'fallido_permanente', attempts: 5 };
    store.set(QUEUE_STORE_KEY, items);

    queue.clearFailed('t-1');
    const cleared = store.get('parkos.print.queue.cleared.v1') as string[];
    expect(cleared).toContain(id);
    // The item is still on disk.
    const after = store.get(QUEUE_STORE_KEY) as QueueItem[];
    expect(after).toHaveLength(1);
  });
});

describe('PrintQueue.getQueue', () => {
  it('returns zero counters when the store is empty', () => {
    const { queue } = makeQueue();
    expect(queue.getQueue()).toEqual({
      pending: 0,
      retrying: 0,
      fallido_permanente: 0,
      lastSuccessAt: null,
      lastError: null,
    });
  });

  it('counts items per estado', () => {
    const { queue } = makeQueue();
    queue.enqueue({ buffer: 'AA==', ticketId: 't-1' }, 0, 0);
    queue.enqueue({ buffer: 'AA==', ticketId: 't-2' }, 0, 0);
    const store = (queue as unknown as { store: QueueStoreLike }).store;
    const items = store.get(QUEUE_STORE_KEY) as QueueItem[];
    items[1] = { ...items[1]!, estado: 'fallido_permanente' };
    store.set(QUEUE_STORE_KEY, items);
    const status = queue.getQueue();
    expect(status.pending).toBe(1);
    expect(status.fallido_permanente).toBe(1);
  });
});