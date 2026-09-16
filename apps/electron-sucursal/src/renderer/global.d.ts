/**
 * Renderer global type augmentations.
 *
 * Triple-slash ref to the IPC bridge surface (F2.2 — DEC-FETCH-08) so
 * `window.bridge.imprimir(payload)` etc. autocomplete in the renderer
 * and `tsc` enforces the contract end-to-end.
 *
 * The actual implementation lives in `electron/preload.ts`; this file
 * is types-only (no runtime).
 */

/// <reference types="../../electron/bridge.d.ts" />

export {};
