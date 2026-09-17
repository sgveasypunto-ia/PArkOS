import '@testing-library/jest-dom/vitest';

/**
 * F5.2 (HU-F5.2) — Buffer polyfill for vitest + jsdom.
 *
 * jsdom does not provide `Buffer` as a global (it emulates a browser
 * environment). `escposBuilder.build(...)` returns a Node `Buffer`
 * (per DEC-SUC-08 / F5.1 `bridge.imprimir` contract: `payload.buffer`
 * base64 → `escpos-usb` `Device.print(Buffer)`), and the byte-level
 * fixtures in `escposBuilder.test.ts` need `Buffer.from([...])`.
 *
 * Resolution: import the `buffer` npm package (devDependency added in
 * F5.2 T1.2 — `buffer@^6.0.3`) and assign to `globalThis.Buffer` so
 * every test file in this app sees the global.
 *
 * Additive — keeps F4.x tests passing (they did not reference Buffer;
 * adding the global is a no-op for them).
 */
import { Buffer as NodeBuffer } from 'buffer';

(globalThis as { Buffer: typeof NodeBuffer }).Buffer = NodeBuffer;