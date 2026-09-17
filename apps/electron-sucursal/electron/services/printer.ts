/**
 * Hardware wrapper around `escpos-usb` (HU-F5.1 T2.1, design.md §1).
 *
 * Responsibilities:
 *   - USB enumeration filtered to Printer class `0x07`.
 *   - Lifecycle watch (`startWatcher`) polling every 5 s for hot-plug
 *     diff events — `node-usb`'s native `attach`/`detach` events are
 *     platform-flaky, so the design mandates a Set-diff fallback.
 *   - `print(buf, vid, pid)` — opens the device, writes the buffer,
 *     closes. Translates every `escpos-usb`/`libusb` error into a
 *     `PrinterErrorCode` and re-raises it.
 *
 * This module NEVER touches `electron-store` — persistence is the
 * queue's job (`printQueue.ts`). Hardware concerns stay pure so the
 * queue can swap the printer out under test via `vi.mock('escpos-usb')`.
 */
import EscposUsb from 'escpos-usb';

import type { USBDevice } from '../types/print';

/** Minimal logger interface — accepts electron-log's default export. */
export interface LogLike {
  info: (...args: unknown[]) => void;
  warn: (...args: unknown[]) => void;
  error: (...args: unknown[]) => void;
  debug?: (...args: unknown[]) => void;
}

/** Catalog of typed errors raised by `print()`. The IPC handler maps them onto `PrintResult`. */
export class PrinterError extends Error {
  public override readonly name = 'PrinterError';
  public readonly code: PrinterErrorCode;

  public constructor(code: PrinterErrorCode, message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.code = code;
  }
}

export type PrinterErrorCode =
  | 'printer_offline' // recoverable — queue will retry
  | 'printer_disconnected'; // terminal for this attempt — caller decides

/** Shape of the underlying `escpos-usb` device we need from a write perspective. */
export interface PrinterLike {
  open: (cb: (err: Error | null) => void) => unknown;
  write: (data: Buffer, cb?: (err: Error | null) => void) => unknown;
  close: (cb?: (err: Error | null) => void) => unknown;
}

export interface EscposUsbLike {
  findPrinter(): Array<{
    vendorId: number;
    productId: number;
    bDeviceClass?: number;
  }>;
}

/** Polling cadence for the watcher. 5 s per design.md §Data Flow. */
export const WATCHER_INTERVAL_MS = 5_000;

/**
 * Enumerate USB devices and filter to Printer class (`0x07`).
 *
 * `escpos-usb.findPrinter()` already filters to `bInterfaceClass === 0x07`
 * inside each interface, but on composite devices the **device-level**
 * `bDeviceClass` can be `0x00` while one of the interfaces is the
 * Printer class. We accept either signal to stay robust.
 */
export function listDevices(usb?: EscposUsbLike): USBDevice[] {
  const module: EscposUsbLike = usb ?? EscposUsb;
  const devices = module.findPrinter();
  return devices.map((d) => ({
    vendorId: d.vendorId,
    productId: d.productId,
    productName: null,
    serialNumber: null,
    class: 0x07,
  }));
}

/**
 * Translate a low-level `escpos-usb`/`libusb` error into a `PrinterErrorCode`.
 *
 * `LIBUSB_ERROR_NO_DEVICE` / `LIBUSB_ERROR_PIPE` / `LIBUSB_ERROR_IO` are
 * recoverable (the queue will retry). Anything else (permission,
 * access) becomes `printer_disconnected` so the caller stops trying for
 * this attempt and can show the "Impresora desconectada" banner.
 */
export function mapEscposError(err: unknown): PrinterErrorCode {
  const message =
    err instanceof Error
      ? err.message
      : typeof err === 'string'
        ? err
        : (() => {
            try {
              return JSON.stringify(err);
            } catch {
              return String(err);
            }
          })();
  const code = (err as { code?: string } | null)?.code ?? '';

  if (
    code === 'LIBUSB_ERROR_NO_DEVICE' ||
    code === 'LIBUSB_ERROR_PIPE' ||
    code === 'LIBUSB_ERROR_IO' ||
    /device not found|not found|cannot find printer/i.test(message)
  ) {
    return 'printer_offline';
  }
  if (
    code === 'LIBUSB_ERROR_ACCESS' ||
    code === 'LIBUSB_ERROR_BUSY' ||
    code === 'EPERM' ||
    code === 'EBUSY' ||
    /permission|busy|access/i.test(message)
  ) {
    return 'printer_disconnected';
  }
  return 'printer_offline';
}

/**
 * Print a buffer on the printer identified by `(vid, pid)`.
 *
 * Opens the device via `escpos-usb`, writes the buffer, closes, and
 * resolves once the OS acknowledges the transfer. Re-raises as a
 * `PrinterError` so the IPC handler can map it onto a `PrintResult`
 * and the queue can decide whether to retry.
 */
export function print(
  buf: Buffer,
  vid: number,
  pid: number,
  log: LogLike,
  usbCtor?: { new (v: number, p: number): PrinterLike },
): Promise<void> {
  const Ctor: { new (v: number, p: number): PrinterLike } = usbCtor
    ? usbCtor
    : (EscposUsb as unknown as { new (v: number, p: number): PrinterLike });
  return new Promise<void>((resolve, reject) => {
    let device: PrinterLike;
    try {
      device = new Ctor(vid, pid);
    } catch (err) {
      log.warn('printer.construct_failed', { vid, pid, err: String(err) });
      reject(new PrinterError(mapEscposError(err), `Cannot construct device ${vid}:${pid}`, { cause: err }));
      return;
    }

    device.open((openErr) => {
      if (openErr) {
        log.warn('printer.open_failed', { vid, pid, err: String(openErr) });
        reject(
          new PrinterError(mapEscposError(openErr), `Cannot open ${vid}:${pid}`, { cause: openErr }),
        );
        return;
      }
      try {
        device.write(buf, (writeErr) => {
          // Always close, even on write error, to free the USB handle.
          device.close(() => {
            if (writeErr) {
              log.warn('printer.write_failed', {
                vid,
                pid,
                bytes: buf.length,
                err: String(writeErr),
              });
              reject(
                new PrinterError(
                  mapEscposError(writeErr),
                  `Cannot write ${buf.length} bytes to ${vid}:${pid}`,
                  { cause: writeErr },
                ),
              );
              return;
            }
            log.info('printer.print_ok', { vid, pid, bytes: buf.length });
            resolve();
          });
        });
      } catch (syncErr) {
        log.warn('printer.write_threw_sync', { vid, pid, err: String(syncErr) });
        device.close(() => {
          reject(
            new PrinterError(
              mapEscposError(syncErr),
              `Synchronous write failure on ${vid}:${pid}`,
              { cause: syncErr },
            ),
          );
        });
      }
    });
  });
}

/**
 * Poll `escpos-usb.findPrinter()` every `intervalMs` and emit the diff
 * via `onChange`. Returns a disposer that stops the timer.
 *
 * `startWatcher` is intentionally a polling loop rather than a listener
 * on `usb.on('attach'|'detach')` because libusb hot-plug notifications
 * are flaky on Windows and macOS (see design.md §Risks).
 */
export function startWatcher(
  intervalMs: number,
  onChange: (devices: USBDevice[]) => void,
  log: LogLike,
  usb?: EscposUsbLike,
): () => void {
  let previous = new Set<string>(listDevices(usb).map(deviceKey));
  const tick = (): void => {
    try {
      const current = listDevices(usb);
      const currentKeys = new Set(current.map(deviceKey));
      const changed =
        currentKeys.size !== previous.size ||
        [...currentKeys].some((k) => !previous.has(k)) ||
        [...previous].some((k) => !currentKeys.has(k));
      if (changed) {
        log.info('printer.watcher.diff', {
          previous: previous.size,
          current: currentKeys.size,
        });
        previous = currentKeys;
        onChange(current);
      }
    } catch (err) {
      log.warn('printer.watcher.error', { err: String(err) });
    }
  };
  const handle = setInterval(tick, intervalMs);
  return () => clearInterval(handle);
}

function deviceKey(d: USBDevice): string {
  return `${d.vendorId.toString(16).padStart(4, '0')}:${d.productId.toString(16).padStart(4, '0')}`;
}