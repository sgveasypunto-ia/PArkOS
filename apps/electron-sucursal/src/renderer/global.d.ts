/**
 * Renderer global type augmentations.
 *
 * Triple-slash ref to the IPC bridge surface (F2.2 — DEC-FETCH-08) so
 * `window.bridge.imprimir(payload)` etc. autocomplete in the renderer
 * and `tsc` enforces the contract end-to-end.
 *
 * The actual implementation lives in `electron/preload.ts`; this file
 * is types-only (no runtime).
 *
 * F5.2 (HU-F5.2) — Buffer global declaration. jsdom + vitest do not
 * expose `Buffer`; `test-setup.ts` imports the `buffer` npm polyfill
 * and assigns it to `globalThis.Buffer` so renderer code (specifically
 * `escposBuilder.build(...)`) can use the Node `Buffer` API without a
 * per-file `import { Buffer } from 'buffer'`. This declaration tells
 * `tsc` the global exists.
 */

/// <reference types="../../electron/bridge.d.ts" />

declare global {
  // eslint-disable-next-line no-var
  var Buffer: typeof import('buffer').Buffer;
}

export {};