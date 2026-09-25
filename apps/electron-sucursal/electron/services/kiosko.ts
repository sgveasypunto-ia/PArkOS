/**
 * Kiosko mode service (F2.3 — T4, DEC-UPD-08/09/10).
 *
 * Enables unattended Electron kiosko mode with a bcrypt-protected PIN:
 *   - `applyKiosko(win, on)` toggles `setKiosk`, application menu, close
 *     handler, and Ctrl+W / Alt+F4 blocking via `before-input-event`.
 *   - `tryUnlockKiosko(pin, store)` uses bcrypt constant-time compare
 *     to validate the PIN against a pre-shared hash stored in
 *     electron-store. Three failed attempts trigger a 5-minute lockout
 *     that persists across restarts.
 *
 * The PIN NEVER appears in any log call. Only the attempt UUID, ISO
 * timestamp, and success boolean are emitted.
 */
import { randomUUID } from 'node:crypto';
import bcrypt from 'bcryptjs';

/** Maximum failed unlock attempts before lockout (DEC-UPD-09). */
export const MAX_FAILED_ATTEMPTS = 3;

/** Lockout duration in seconds (5 minutes — DEC-UPD-09). */
export const LOCKOUT_SECONDS = 300;

/** Minimal logger interface — accepts electron-log's default export. */
export interface LogLike {
  info: (...args: unknown[]) => void;
  warn: (...args: unknown[]) => void;
  error: (...args: unknown[]) => void;
}

/**
 * BrowserWindow subset required by applyKiosko.
 *
 * `on`/`webContents.on`/`webContents.off` are narrowed to the literal event
 * names this module actually wires up (`'close'`, `'before-input-event'`)
 * instead of a generic `event: string`. Electron's real `BrowserWindow.on`
 * is a large overload set keyed by string-literal event names, which a
 * plain `(event: string, …) => void` property can never structurally match
 * (TS2345 "string is not assignable to '<literal event>'"). Narrowing to
 * the literals actually used keeps this interface satisfied by the real
 * `BrowserWindow` without widening to `unknown`/`any`, and a plain object
 * stub still satisfies it in tests.
 */
export interface BrowserWindowLike {
  setKiosk: (on: boolean) => void;
  on(event: 'close', listener: (...args: unknown[]) => void): void;
  webContents: {
    on(event: 'before-input-event', listener: (...args: unknown[]) => void): void;
    off(event: 'before-input-event', listener: (...args: unknown[]) => void): void;
  };
}

/**
 * Menu subset — only setApplicationMenu is required.
 *
 * Narrowed to `null` (the only value this module ever passes — it always
 * clears the menu, never sets one) instead of `unknown`. Electron's real
 * `Menu.setApplicationMenu(menu: Menu | null): void` is not assignable to
 * a `(menu: unknown) => void` slot (a real `Menu | null` parameter can't
 * safely accept an arbitrary `unknown` value), so `unknown` silently broke
 * that assignability; `null` is both accurate to actual usage and a valid
 * subtype of `Menu | null`.
 */
export interface MenuLike {
  setApplicationMenu: (menu: null) => void;
}

/** Minimal electron-store shape used by tryUnlockKiosko. */
export interface StoreLike {
  get: (key: string) => unknown;
  set: (key: string, value: unknown) => void;
}

/**
 * Discriminated union describing the outcome of `tryUnlockKiosko`.
 *
 *  - `success:true`                  → kiosko unlocked.
 *  - `success:false, reason:'invalid_pin'` → PIN wrong; remaining
 *    attempts before lockout.
 *  - `success:false, reason:'lockout'` → 5-minute lockout active.
 */
export type KioskoUnlockResult =
  | { success: true; attemptId: string }
  | { success: false; reason: 'invalid_pin'; remainingAttempts: number }
  | { success: false; reason: 'lockout'; lockoutSecondsRemaining: number };

/** Shape of the `before-input-event` input — Electron 30 typing. */
interface BeforeInputEventInput {
  type?: string;
  key: string;
  code?: string;
  control?: boolean;
  alt?: boolean;
  shift?: boolean;
  meta?: boolean;
}

/**
 * Block Ctrl+W and Alt+F4 to prevent accidental closure of the kiosko
 * window. Other shortcuts remain operational (e.g., Tab navigation).
 */
function blockShortcuts(event: { preventDefault: () => void }, input: BeforeInputEventInput): void {
  if (input.control && input.key.toLowerCase() === 'w') {
    event.preventDefault();
    return;
  }
  if (input.alt && input.key === 'F4') {
    event.preventDefault();
  }
}

/**
 * Toggle kiosko mode on or off. When enabling, this:
 *   - Calls `mainWindow.setKiosk(true)` (full-screen, no chrome).
 *   - Removes the application menu (`Menu.setApplicationMenu(null)`).
 *   - Prevents accidental window close (`mainWindow.on('close', …)`).
 *   - Blocks `Ctrl+W` and `Alt+F4` via `before-input-event`.
 */
export function applyKiosko(
  win: BrowserWindowLike,
  menu: MenuLike,
  on: boolean,
  log: LogLike,
): void {
  win.setKiosk(on);
  if (on) {
    menu.setApplicationMenu(null);
    // BrowserWindowLike.on/webContents.on declare a generic `(...args:
    // unknown[]) => void` listener (see interface doc above) so tests can
    // pass simple mocks. Real Electron listeners receive typed arguments,
    // so the wrapper narrows `args` back to the shape this module expects
    // before delegating — same runtime behavior, satisfies both types.
    win.on('close', (...args: unknown[]) => {
      const [e] = args as [{ preventDefault: () => void }];
      e.preventDefault();
    });
    win.webContents.on('before-input-event', (...args: unknown[]) => {
      const [event, input] = args as [{ preventDefault: () => void }, BeforeInputEventInput];
      blockShortcuts(event, input);
    });
    log.info('kiosko.applied');
  } else {
    log.info('kiosko.removed');
  }
}

/**
 * Validate a PIN against the bcrypt hash stored in electron-store.
 *
 * Lockout semantics:
 *   - If `kiosk.failedAttempts >= MAX_FAILED_ATTEMPTS` the call short
 *     circuits to `{success:false, reason:'lockout'}` without
 *     performing the bcrypt comparison.
 *   - A successful call resets the counter to 0.
 *   - A failed call increments the counter; if the new count reaches
 *     `MAX_FAILED_ATTEMPTS` the response carries `{reason:'lockout'}`.
 */
export function tryUnlockKiosko(
  pin: string,
  store: StoreLike,
  log: LogLike,
): KioskoUnlockResult {
  const attemptId = randomUUID();
  const timestamp = new Date().toISOString();

  const pinHash = store.get('kiosk.pinHash');
  if (typeof pinHash !== 'string' || pinHash.length === 0) {
    log.warn('kiosko.unlock_attempt', {
      attemptId,
      timestamp,
      success: false,
      reason: 'pin_missing',
    });
    return { success: false, reason: 'invalid_pin', remainingAttempts: 0 };
  }

  const failedAttempts = (store.get('kiosk.failedAttempts') as number | null) ?? 0;
  if (failedAttempts >= MAX_FAILED_ATTEMPTS) {
    log.warn('kiosko.unlock_attempt', {
      attemptId,
      timestamp,
      success: false,
      reason: 'lockout',
    });
    return { success: false, reason: 'lockout', lockoutSecondsRemaining: LOCKOUT_SECONDS };
  }

  const isValid = bcrypt.compareSync(pin, pinHash);

  if (isValid) {
    store.set('kiosk.failedAttempts', 0);
    log.info('kiosko.unlock_attempt', { attemptId, timestamp, success: true });
    return { success: true, attemptId };
  }

  const next = failedAttempts + 1;
  store.set('kiosk.failedAttempts', next);
  log.warn('kiosko.unlock_attempt', {
    attemptId,
    timestamp,
    success: false,
    reason: 'invalid_pin',
  });

  if (next >= MAX_FAILED_ATTEMPTS) {
    return { success: false, reason: 'lockout', lockoutSecondsRemaining: LOCKOUT_SECONDS };
  }
  return {
    success: false,
    reason: 'invalid_pin',
    remainingAttempts: MAX_FAILED_ATTEMPTS - next,
  };
}

/** Convenience helper — true if the store currently reflects a lockout. */
export function isKioskoLocked(store: StoreLike): boolean {
  const failed = (store.get('kiosk.failedAttempts') as number | null) ?? 0;
  return failed >= MAX_FAILED_ATTEMPTS;
}