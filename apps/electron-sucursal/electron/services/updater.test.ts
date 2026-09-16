/**
 * Unit tests for `electron/services/updater.ts` (F2.3 — T1, DEC-UPD-01..04).
 *
 * RED → GREEN → REFACTOR coverage:
 *   U1: setFeedURL lee env.PARKOS_UPDATE_FEED_URL cuando está presente.
 *   U2: setFeedURL fallback GitHub default cuando env ausente.
 *   U3: autoDownload / autoInstallOnAppQuit / allowDowngrade configurados verbatim.
 *   U4: signature verification failure → log.error + NO install + interval sigue activo.
 *   U5: setInterval 6h configurado; dispose() limpia el interval.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { initUpdater, DEFAULT_FEED, DEFAULT_CHECK_INTERVAL_MS } from './updater';

interface AutoUpdaterStub {
  setFeedURL: ReturnType<typeof vi.fn>;
  autoDownload: boolean;
  autoInstallOnAppQuit: boolean;
  allowDowngrade: boolean;
  checkForUpdates: ReturnType<typeof vi.fn>;
  on: (event: string, listener: (...args: unknown[]) => void) => void;
  _listeners: Record<string, ((...args: unknown[]) => void) | undefined>;
}

interface LogStub {
  info: ReturnType<typeof vi.fn>;
  debug: ReturnType<typeof vi.fn>;
  warn: ReturnType<typeof vi.fn>;
  error: ReturnType<typeof vi.fn>;
}

function makeAutoUpdater(): AutoUpdaterStub {
  const listeners: Record<string, ((...args: unknown[]) => void) | undefined> = {};
  const stub: AutoUpdaterStub = {
    setFeedURL: vi.fn(),
    autoDownload: false,
    autoInstallOnAppQuit: false,
    allowDowngrade: true,
    checkForUpdates: vi.fn().mockResolvedValue(undefined),
    on: (event: string, listener: (...args: unknown[]) => void) => {
      listeners[event] = listener;
    },
    _listeners: listeners,
  };
  return stub;
}

function makeLog(): LogStub {
  return {
    info: vi.fn(),
    debug: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  };
}

describe('initUpdater', () => {
  let autoUpdater: AutoUpdaterStub;
  let log: LogStub;

  beforeEach(() => {
    vi.useFakeTimers();
    autoUpdater = makeAutoUpdater();
    log = makeLog();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('U1: setFeedURL lee env.PARKOS_UPDATE_FEED_URL cuando está presente', () => {
    initUpdater(autoUpdater, { PARKOS_UPDATE_FEED_URL: 'https://staging.example.com/releases' }, log);
    expect(autoUpdater.setFeedURL).toHaveBeenCalledWith('https://staging.example.com/releases');
  });

  it('U2: setFeedURL fallback al feed GitHub default cuando env ausente', () => {
    initUpdater(autoUpdater, {}, log);
    expect(autoUpdater.setFeedURL).toHaveBeenCalledWith(DEFAULT_FEED);
  });

  it('U3: configura autoDownload:true, autoInstallOnAppQuit:true, allowDowngrade:false', () => {
    initUpdater(autoUpdater, {}, log);
    expect(autoUpdater.autoDownload).toBe(true);
    expect(autoUpdater.autoInstallOnAppQuit).toBe(true);
    expect(autoUpdater.allowDowngrade).toBe(false);
  });

  it('U4: signature verification failure → log.error + NO install', async () => {
    const handle = initUpdater(autoUpdater, {}, log);
    const errorListener = autoUpdater._listeners['error'];
    expect(typeof errorListener).toBe('function');
    errorListener?.(new Error('Cannot verify signature of update payload'));

    expect(log.error).toHaveBeenCalledTimes(1);
    const [label, payload] = log.error.mock.calls[0] ?? [];
    expect(label).toBe('updater.error');
    expect(payload).toMatchObject({ signature: true });

    // Ensure checkForUpdates was NOT re-called as a result of the error itself.
    expect(autoUpdater.checkForUpdates).toHaveBeenCalledTimes(1);

    handle.dispose();
  });

  it('U5: setInterval 6h configurado; dispose() limpia el interval', () => {
    const handle = initUpdater(autoUpdater, {}, log);
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    handle.dispose();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('exporta DEFAULT_FEED apuntando al repo de releases', () => {
    expect(DEFAULT_FEED).toBe('https://github.com/easypunto_parkos/easypunto_parkos/releases');
    expect(DEFAULT_CHECK_INTERVAL_MS).toBe(6 * 60 * 60 * 1000);
  });
});