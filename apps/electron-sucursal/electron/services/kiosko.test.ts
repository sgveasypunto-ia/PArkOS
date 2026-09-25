/**
 * Unit tests for `electron/services/kiosko.ts` (F2.3 — T4, DEC-UPD-08/09/10).
 *
 * RED → GREEN → REFACTOR coverage:
 *   K1: applyKiosko(true) → setKiosk(true) + Menu null + listeners wireados.
 *   K2: Ctrl+W bloqueado vía before-input-event.
 *   K3: Alt+F4 bloqueado vía before-input-event.
 *   K4: PIN correcto → success:true + reset counter.
 *   K5: PIN incorrecto → success:false + counter++ (PIN nunca logueado).
 *   K6: 3 intentos fallidos → lockout 5 min.
 *   K7: PIN hash null → invalid_pin + warning (PIN nunca logueado).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('bcryptjs', () => ({
  default: { compareSync: vi.fn() },
  compareSync: vi.fn(),
}));

import bcrypt from 'bcryptjs';

import {
  applyKiosko,
  tryUnlockKiosko,
  isKioskoLocked,
  MAX_FAILED_ATTEMPTS,
  LOCKOUT_SECONDS,
} from './kiosko';

interface BrowserWindowStub {
  setKiosk: ReturnType<typeof vi.fn>;
  on: ReturnType<typeof vi.fn>;
  webContents: {
    on: ReturnType<typeof vi.fn>;
    off: ReturnType<typeof vi.fn>;
  };
}

interface MenuStub {
  setApplicationMenu: ReturnType<typeof vi.fn>;
}

interface StoreStub {
  get: ReturnType<typeof vi.fn>;
  set: ReturnType<typeof vi.fn>;
}

interface LogStub {
  info: ReturnType<typeof vi.fn>;
  warn: ReturnType<typeof vi.fn>;
  error: ReturnType<typeof vi.fn>;
}

function makeBrowserWindow(): BrowserWindowStub {
  return {
    setKiosk: vi.fn(),
    on: vi.fn(),
    webContents: { on: vi.fn(), off: vi.fn() },
  };
}

function makeMenu(): MenuStub {
  return { setApplicationMenu: vi.fn() };
}

function makeStore(values: Record<string, unknown> = {}): StoreStub {
  return {
    get: vi.fn((key: string) => values[key] ?? null),
    set: vi.fn((key: string, value: unknown) => {
      values[key] = value;
    }),
  };
}

function makeLog(): LogStub {
  return { info: vi.fn(), warn: vi.fn(), error: vi.fn() };
}

describe('kiosko service', () => {
  let log: LogStub;
  let menu: MenuStub;
  let win: BrowserWindowStub;

  beforeEach(() => {
    log = makeLog();
    menu = makeMenu();
    win = makeBrowserWindow();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('applyKiosko', () => {
    it('K1: applyKiosko(win, true) → setKiosk(true) + Menu null + close + before-input-event listeners', () => {
      applyKiosko(win, menu, true, log);
      expect(win.setKiosk).toHaveBeenCalledWith(true);
      expect(menu.setApplicationMenu).toHaveBeenCalledWith(null);
      expect(win.on).toHaveBeenCalledWith('close', expect.any(Function));
      expect(win.webContents.on).toHaveBeenCalledWith('before-input-event', expect.any(Function));
    });

    it('K1b: applyKiosko(win, false) → setKiosk(false) + restores menu flag off (no null menu)', () => {
      applyKiosko(win, menu, false, log);
      expect(win.setKiosk).toHaveBeenCalledWith(false);
      expect(menu.setApplicationMenu).not.toHaveBeenCalled();
    });
  });

  describe('blockShortcuts via before-input-event', () => {
    it('K2: Ctrl+W es bloqueado con event.preventDefault()', () => {
      applyKiosko(win, menu, true, log);
      const handler = win.webContents.on.mock.calls.find(
        (c) => c[0] === 'before-input-event',
      )?.[1] as (e: { preventDefault: () => void }, input: { control: boolean; key: string }) => void;
      expect(handler).toBeTypeOf('function');
      const event = { preventDefault: vi.fn() };
      handler(event, { control: true, key: 'w' });
      expect(event.preventDefault).toHaveBeenCalled();
    });

    it('K3: Alt+F4 es bloqueado con event.preventDefault()', () => {
      applyKiosko(win, menu, true, log);
      const handler = win.webContents.on.mock.calls.find(
        (c) => c[0] === 'before-input-event',
      )?.[1] as (e: { preventDefault: () => void }, input: { alt: boolean; key: string }) => void;
      const event = { preventDefault: vi.fn() };
      handler(event, { alt: true, key: 'F4' });
      expect(event.preventDefault).toHaveBeenCalled();
    });
  });

  describe('tryUnlockKiosko', () => {
    it('K4: PIN correcto → success:true + counter reseteado', () => {
      const store = makeStore({
        'kiosk.pinHash': '$2b$12$validhash',
        'kiosk.failedAttempts': 2,
      });
      (bcrypt.compareSync as ReturnType<typeof vi.fn>).mockReturnValue(true);
      const result = tryUnlockKiosko('1234', store, log);
      expect(result.success).toBe(true);
      expect(store.set).toHaveBeenCalledWith('kiosk.failedAttempts', 0);
    });

    it('K5: PIN incorrecto → success:false + counter++ (PIN nunca logueado)', () => {
      const store = makeStore({ 'kiosk.pinHash': '$2b$12$validhash' });
      (bcrypt.compareSync as ReturnType<typeof vi.fn>).mockReturnValue(false);
      const result = tryUnlockKiosko('0000', store, log);
      expect(result.success).toBe(false);
      expect(store.set).toHaveBeenCalledWith('kiosk.failedAttempts', 1);
      // PIN never logged.
      const allLogCalls = JSON.stringify({
        info: log.info.mock.calls,
        warn: log.warn.mock.calls,
        error: log.error.mock.calls,
      });
      expect(allLogCalls).not.toContain('0000');
    });

    it('K6: 3 intentos fallidos → lockout 5 minutos', () => {
      const store = makeStore({
        'kiosk.pinHash': '$2b$12$validhash',
        'kiosk.failedAttempts': MAX_FAILED_ATTEMPTS,
      });
      (bcrypt.compareSync as ReturnType<typeof vi.fn>).mockReturnValue(false);
      const result = tryUnlockKiosko('9999', store, log);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.reason).toBe('lockout');
        if (result.reason === 'lockout') {
          expect(result.lockoutSecondsRemaining).toBe(LOCKOUT_SECONDS);
        }
      }
    });

    it('K7: PIN hash null → invalid_pin + warning log', () => {
      const store = makeStore({});
      const result = tryUnlockKiosko('1234', store, log);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.reason).toBe('invalid_pin');
      }
      expect(log.warn).toHaveBeenCalled();
      const allCalls = JSON.stringify({ warn: log.warn.mock.calls });
      expect(allCalls).not.toContain('1234');
    });
  });

  describe('isKioskoLocked', () => {
    it('false cuando failedAttempts < MAX_FAILED_ATTEMPTS', () => {
      const store = makeStore({ 'kiosk.failedAttempts': 1 });
      expect(isKioskoLocked(store)).toBe(false);
    });

    it('true cuando failedAttempts >= MAX_FAILED_ATTEMPTS', () => {
      const store = makeStore({ 'kiosk.failedAttempts': MAX_FAILED_ATTEMPTS });
      expect(isKioskoLocked(store)).toBe(true);
    });
  });
});