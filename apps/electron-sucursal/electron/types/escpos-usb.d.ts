/**
 * Minimal TypeScript shim for `escpos-usb@^3.0.0-alpha.4`.
 *
 * Rationale (HU-F5.1 T1.2, design.md §6 Decision 6 — Plan B):
 *   `escpos-usb@3.0.0-alpha.4` ships without a `.d.ts`, and DefinitelyTyped
 *   does not (currently) publish `@types/escpos-usb` for the alpha line.
 *   We declare only the surface our F5.1 wrapper actually consumes; the
 *   package's runtime API is `module.exports = USB` (CJS), where `USB`
 *   extends `EventEmitter` and exposes `findPrinter`, `open`, `write`,
 *   `close`, plus the standard `detach` / `disconnect` events.
 *
 *   Production code MUST go through `services/printer.ts`, never import
 *   this module directly — that wrapper translates `escpos-usb` errors
 *   into `PrinterErrorCode` values and exposes a typed
 *   `Printer.print(buf, vid, pid)` surface.
 */
declare module 'escpos-usb' {
  import { EventEmitter } from 'node:events';

  /**
   * Subset of `libusb` device shape from `node-usb`. We only model the
   * fields F5.1 reads (vendorId/productId/descriptor metadata); the rest
   * lives on the real `usb` package.
   */
  export interface EscposUsbDevice {
    vendorId: number;
    productId: number;
    /** Always `0x07` for devices reported by `findPrinter()`. */
    bDeviceClass?: number;
  }

  /**
   * The class `escpos-usb` exports as `module.exports`. F5.1 calls:
   *   - `USB.findPrinter()` to enumerate
   *   - `new USB(vid, pid)` to bind
   *   - `.open(cb)` / `.write(buf, cb)` / `.close(cb)` to push bytes
   *   - listens on `'detach'` and `'disconnect'` for hot-unplug signals
   */
  export class EscposUsbDeviceHandle extends EventEmitter {
    static findPrinter(): EscposUsbDevice[];
    constructor(vid: number, pid: number);
    constructor(device: EscposUsbDevice);
    device: EscposUsbDevice | null;

    open(callback: (err: Error | null) => void): this;
    write(data: Buffer, callback?: (err: Error | null) => void): this;
    close(callback?: (err: Error | null) => void): this;

    /** Emitted by the underlying `usb` package when the kernel reports detach. */
    on(event: 'detach' | 'disconnect', listener: (device: EscposUsbDevice) => void): this;
    on(event: 'connect' | 'close' | 'data', listener: (...args: unknown[]) => void): this;

    off(event: string, listener: (...args: unknown[]) => void): this;
    emit(event: string, ...args: unknown[]): boolean;
  }

  /** CJS export — `const USB = require('escpos-usb')`. */
  const EscposUsb: typeof EscposUsbDeviceHandle;
  export = EscposUsb;
}