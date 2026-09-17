/**
 * Unit tests for `electron/services/printer.ts` (HU-F5.1 T4.2).
 *
 * `escpos-usb` is mocked with `vi.mock` because it requires the native
 * `usb` binding that is unavailable in CI. The mock provides a
 * `PrinterLike` (constructor + open/write/close callbacks) so we can
 * drive both the happy path and the disconnect simulation.
 *
 * Coverage:
 *   - `listDevices()` filters / annotates with `class: 0x07`.
 *   - `print()` calls open/print/close exactly once on the happy path.
 *   - `print()` rejects with a typed `PrinterError` when the device
 *     disconnects mid-print.
 *   - `mapEscposError()` classifies the libusb error catalog.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { EscposUsbLike, PrinterLike } from './printer';

vi.mock('escpos-usb', () => {
  const escposUsbMock = {
    findPrinter: vi.fn(),
  };
  return { default: escposUsbMock };
});

function makeDevice(opts: {
  openFails?: Error;
  writeFails?: Error;
}): PrinterLike {
  return {
    open: (cb: (err: Error | null) => void): void => {
      setImmediate(() => cb(opts.openFails ?? null));
    },
    write: (_data: Buffer, cb?: (err: Error | null) => void): void => {
      setImmediate(() => cb?.(opts.writeFails ?? null));
    },
    close: (cb?: (err: Error | null) => void): void => {
      setImmediate(() => cb?.(null));
    },
  };
}

function makeCtor(device: PrinterLike): { new (v: number, p: number): PrinterLike } {
  return vi.fn().mockImplementation(() => device) as unknown as {
    new (v: number, p: number): PrinterLike;
  };
}

const log = {
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
  debug: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('mapEscposError', () => {
  it('LIBUSB_ERROR_NO_DEVICE → printer_offline', async () => {
    const { mapEscposError } = await import('./printer');
    expect(mapEscposError({ code: 'LIBUSB_ERROR_NO_DEVICE', message: 'gone' })).toBe(
      'printer_offline',
    );
  });

  it('LIBUSB_ERROR_ACCESS / EPERM / EBUSY → printer_disconnected', async () => {
    const { mapEscposError } = await import('./printer');
    expect(mapEscposError({ code: 'LIBUSB_ERROR_ACCESS' })).toBe('printer_disconnected');
    expect(mapEscposError({ code: 'EPERM' })).toBe('printer_disconnected');
    expect(mapEscposError({ code: 'EBUSY' })).toBe('printer_disconnected');
  });

  it('plain `Cannot find printer` message → printer_offline', async () => {
    const { mapEscposError } = await import('./printer');
    expect(mapEscposError(new Error('Cannot find printer'))).toBe('printer_offline');
  });
});

describe('listDevices', () => {
  it('annotates every entry with class = 0x07', async () => {
    const usb: EscposUsbLike = {
      findPrinter: vi.fn().mockReturnValue([
        { vendorId: 0x04b8, productId: 0x0202 },
        { vendorId: 0x04b8, productId: 0x0e15 },
      ]),
    };
    const { listDevices } = await import('./printer');
    const devices = listDevices(usb);
    expect(devices).toHaveLength(2);
    expect(devices.every((d) => d.class === 0x07)).toBe(true);
  });

  it('returns an empty list when no printers are connected', async () => {
    const usb: EscposUsbLike = { findPrinter: vi.fn().mockReturnValue([]) };
    const { listDevices } = await import('./printer');
    expect(listDevices(usb)).toEqual([]);
  });
});

describe('print', () => {
  it('calls open / write / close exactly once on the happy path', async () => {
    const device = makeDevice({});
    const openSpy = vi.spyOn(device, 'open');
    const writeSpy = vi.spyOn(device, 'write');
    const closeSpy = vi.spyOn(device, 'close');
    const Ctor = makeCtor(device);

    const { print } = await import('./printer');
    await print(Buffer.from('hello'), 0x04b8, 0x0202, log, Ctor);

    expect(openSpy).toHaveBeenCalledTimes(1);
    expect(writeSpy).toHaveBeenCalledTimes(1);
    expect(closeSpy).toHaveBeenCalledTimes(1);
    expect(writeSpy).toHaveBeenCalledWith(expect.any(Buffer), expect.any(Function));
  });

  it('rejects with typed PrinterError(printer_offline) when open fails (LIBUSB_ERROR_NO_DEVICE)', async () => {
    const device = makeDevice({ openFails: Object.assign(new Error('gone'), { code: 'LIBUSB_ERROR_NO_DEVICE' }) });
    const Ctor = makeCtor(device);
    const { print, PrinterError } = await import('./printer');

    await expect(print(Buffer.from('hello'), 0x04b8, 0x0202, log, Ctor)).rejects.toBeInstanceOf(
      PrinterError,
    );
    await expect(
      print(Buffer.from('hello'), 0x04b8, 0x0202, log, Ctor),
    ).rejects.toMatchObject({ code: 'printer_offline' });
  });

  it('rejects with typed PrinterError(printer_disconnected) on EBUSY during write', async () => {
    const device = makeDevice({
      writeFails: Object.assign(new Error('busy'), { code: 'EBUSY' }),
    });
    const closeSpy = vi.spyOn(device, 'close');
    const Ctor = makeCtor(device);
    const { print } = await import('./printer');

    await expect(print(Buffer.from('hello'), 0x04b8, 0x0202, log, Ctor)).rejects.toMatchObject({
      code: 'printer_disconnected',
    });
    // Close must still run even on write error so we do not leak the USB handle.
    expect(closeSpy).toHaveBeenCalledTimes(1);
  });

  it('rejects with typed PrinterError when the constructor throws (cable unplugged before open)', async () => {
    const Ctor = vi.fn().mockImplementation(() => {
      throw new Error('Can not find printer');
    }) as unknown as { new (v: number, p: number): PrinterLike };
    const { print, PrinterError } = await import('./printer');

    await expect(print(Buffer.from('hello'), 0, 0, log, Ctor)).rejects.toBeInstanceOf(PrinterError);
  });
});