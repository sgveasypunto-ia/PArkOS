# Tasks: HU-F5.1 — Servicio de impresora térmica (main process)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines (production) | 480 |
| Estimated changed lines (incl. tests) | ~945 |
| 400-line budget risk | Low (AGENTS.md 800-line budget binding; SDD-default 400-line threshold would flag Medium) |
| 800-line budget risk (AGENTS.md gitflow) | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | not applicable (single PR) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | F5.1 complete | PR 1 (single) | `cd apps\electron-sucursal && npx vitest run electron/types electron/services electron/__tests__ && npx playwright test e2e/printer.spec.ts && npx tsc --noEmit` | Manual: launch Electron dev shell with real USB printer, send `bridge.imprimir`, disconnect cable mid-print, reconnect, observe queue drain | Delete 8 NEW files + revert 6 MOD files + remove `parkos.print.queue.v1` key on next boot (no DB migration, no backend change) |

## Phase 1: Foundation — types, build config, dependencies

- [ ] 1.1 Add `node-usb-mock` to `apps/electron-sucursal/package.json` `devDependencies` (latest from npm registry). Verify `pnpm install` does NOT hang (sandbox F.6 — use `--ignore-scripts` if needed; `escpos-usb@3.0.0-alpha.4` requires `node-gyp rebuild` for `node-usb` native binding).
- [ ] 1.2 Attempt `pnpm add -D @types/escpos-usb` from `apps/electron-sucursal/`. If 404, create local `electron/types/escpos-usb.d.ts` shim: `declare module 'escpos-usb' { function findPrinter(vid: number, pid: number): Promise<Device> | Device; class Device { open(): void; close(): void; print(buf: Buffer): void; cashdraw(): void; cut(): void; }; export = escpos; const escpos: { Printer: typeof Device; findPrinter: typeof findPrinter }; }` (Plan B documented in design §6 Decision 6).
- [ ] 1.3 Create `apps/electron-sucursal/electron/types/print.ts` with Zod schemas (`printPayloadSchema`, `printResultSchema`, `queueItemSchema`, `queueStatusSchema`, `printerErrorSchema`) + types via `z.infer`. Extend `USBDevice` with `class: number` field.
- [ ] 1.4 Create `apps/electron-sucursal/build/entitlements.mac.plist` with `<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>com.apple.security.device.usb</key><true/></dict></plist>`.
- [ ] 1.5 Update `apps/electron-sucursal/electron-builder.yml`: consolidate the two pre-existing `mac:` blocks (lines 23-31 and 50-52) into a single `mac:` block containing `target`, `icon`, `category`, `artifactName`, `hardenedRuntime: true`, `gatekeeperAssess: false`, AND `entitlements: build/entitlements.mac.plist` + `entitlementsInherit: build/entitlements.mac.plist`. (Housekeeping: closes a pre-existing YAML schema violation flagged by the LSP.)

## Phase 2: Core implementation — hardware wrapper + retry queue

- [ ] 2.1 Create `apps/electron-sucursal/electron/services/printer.ts` with `listDevices(): USBDevice[]` (uses `node-usb` via `escpos-usb`'s underlying `usb` export — enumerate + filter `bDeviceClass === 0x07`), `print(buf: Buffer, vid: number, pid: number): Promise<void>` (wraps `new escpos.Printer(vid, pid).open().print(buf).close()`; catches all `escpos-usb` throws and re-raises as `PrinterError`), `startWatcher(intervalMs: number, onChange: (devices: USBDevice[]) => void): () => void` (poll 5s, diff against previous Set).
- [ ] 2.2 Create `apps/electron-sucursal/electron/services/printQueue.ts` with `class PrintQueue { constructor(store, log); enqueue(item): string (returns queueId); drain(): Promise<void>; getQueue(): QueueStatus; clearFailed(ticketId): void }`. Backoff schedule `[5000, 15000, 60000, 60000, 60000][attempt-1]` ms for attempts 1..5. Persists under `parkos.print.queue.v1`. On boot, drains past-due items. Never deletes items from disk; only marks `fallido_permanente`.
- [ ] 2.3 Create `apps/electron-sucursal/electron/ipc/imprimir.ts` with `registerImprimirHandlers({ ipcMain, queue, mainWindow, log })` registering `print:ticket` (Zod-validate FIRST, dispatch to `printer.print` or `queue.enqueue`), `print:queue:get` (returns `queue.getQueue()`), `print:queue:clear-failed` (delegates to `queue.clearFailed`). Emits `webContents.send('print:status', { type, queueId, ticketId, error })` on every state transition.

## Phase 3: Integration — IPC bridge surface + main wiring

- [ ] 3.1 Update `apps/electron-sucursal/electron/bridge.d.ts`: (a) add `import type { PrintPayload, PrintResult, QueueStatus, PrinterErrorCode } from './types/print'`; (b) replace inline `PrintPayload`/`PrintResult` with the imports; (c) extend `USBDevice` with `class: number`; (d) change `imprimir: (payload) => Promise<PrintResult>` to `imprimir: { (payload): Promise<PrintResult>; getQueue(): Promise<QueueStatus>; onStatus(handler): () => void }`; (e) fix JSDoc at lines 5-11 from "6 groups, 8 methods" to "7 groups, 12 methods" (closes F4.2 drift).
- [ ] 3.2 Update `apps/electron-sucursal/electron/preload.ts`: (a) replace `imprimir: (payload) => ipcRenderer.invoke('print:ticket', payload)` with `imprimir: Object.assign((payload) => ipcRenderer.invoke('print:ticket', payload), { getQueue: () => ipcRenderer.invoke('print:queue:get'), onStatus: (handler) => { const listener = (_e, payload) => handler(payload); ipcRenderer.on('print:status', listener); return () => ipcRenderer.off('print:status', listener); } })`; (b) keep whitelist discipline (no spread, no `ipcRenderer` exposure).
- [ ] 3.3 Update `apps/electron-sucursal/electron/main.ts`: in `app.whenReady()` instantiate `PrintQueue` (passing the existing `electron-store` instance used by kiosko at lines 82-83, or extract a named `electronStore`), instantiate `printer`, then call `registerImprimirHandlers({ ipcMain, queue, mainWindow, log })`. Register handler BEFORE `registerIpcHandlers` so `print:ticket` is available in the same `ipcMain.handle` batch.
- [ ] 3.4 Update `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts`: (a) update expected `Object.keys(exposed).sort()` — `imprimir` is now an OBJECT (was a function). Adjust test to check `typeof exposed.imprimir === 'object'` and that it has both `getQueue` and `onStatus`; (b) add assertion `imprimir.getQueue()` invokes `'print:queue:get'`; (c) add assertion `imprimir.onStatus(handler)` registers listener on `'print:status'` and returns unsubscribe function that calls `ipcRenderer.off`.

## Phase 4: Tests — unit + e2e + perf

- [ ] 4.1 Create `apps/electron-sucursal/electron/types/print.test.ts` with Vitest cases: `printPayloadSchema.parse({buffer: 'AA==', ticketId: 't-1', cut: false})` succeeds; missing `buffer` fails with path `['buffer']`; `uuidRegistro: 'not-a-uuid'` fails with `Invalid uuid`; empty `buffer` fails with `min(1)`; `vid > 0xffff` fails with `max(0xffff)`. Per-file coverage threshold (vitest.config.ts): 95% lines.
- [ ] 4.2 Create `apps/electron-sucursal/electron/services/printer.test.ts` with `vi.mock('escpos-usb')` (or `vi.mock('node-usb')` if shim path used) + `node-usb-mock`. Cases: `listDevices()` filters 0x07; `print()` calls `open/print/close` exactly once; `print()` throws typed `PrinterError('printer_offline')` when `node-usb-mock` simulates disconnect.
- [ ] 4.3 Create `apps/electron-sucursal/electron/services/printQueue.test.ts` with `StoreLike` in-memory mock. Cases: enqueue persists JSON to store; backoff `[5000, 15000, 60000, 60000, 60000]` for attempts 1-5; `nextRetryAt = failedAt + schedule[attempts-1]`; drain loop respects `nextRetryAt`; 5 attempts → `fallido_permanente` + emits `print_failed_terminal` event; `clearFailed(ticketId)` only changes display flag, never deletes from store.
- [ ] 4.4 Create `apps/electron-sucursal/e2e/printer.spec.ts` with Playwright `_electron.launch` + `node-usb-mock` injected via `main.ts` test entry. 4 scenarios: (a) `bridge.usb.list()` returns at least one `USBDevice` with `class === 0x07`; (b) `bridge.imprimir({ buffer: base64(1024 bytes ESC/POS), ticketId: 'e2e-1', cut: true })` returns `{ok:true}`; (c) simulate disconnect via `node-usb-mock` API mid-print → IPC returns `{ok:false, error:'printer_offline', queueId}` AND `app.isReady() === true` after; (d) PERF: 100 sequential `bridge.imprimir` calls with 1 KB buffer — P95 <500 ms (use `performance.now()` deltas logged via `window.bridge.imprimir.getQueue()` then `electron-log` channel `print.perf` post-mortem).

## Phase 5: Verify & ship

- [ ] 5.1 From `apps\electron-sucursal\`, run `npx tsc --noEmit` — must exit 0 (validates bridge typing end-to-end including the new `imprimir.getQueue`/`onStatus` shape).
- [ ] 5.2 From `apps\electron-sucursal\`, run `npx vitest run electron/types electron/services electron/__tests__` — 0 failed; coverage gates per `vitest.config.ts`.
- [ ] 5.3 From `apps\electron-sucursal\`, run `npx playwright test e2e/printer.spec.ts` — 4/4 escenarios PASS; P95 <500 ms recorded.
- [ ] 5.4 Manual smoke: connect real USB printer (Epson TM-T20 compatible), launch Electron dev shell, execute `bridge.imprimir({ buffer: base64(init + 'PRUEBA' + cut), ticketId: 'smoke-1', cut: true })` from devtools, observe physical printout, unplug USB mid-print, observe banner, reconnect, observe queue drain.

## Commit Strategy

Single PR per orchestrator preflight (`chained_prs_recommended=No`). Suggested commit sequence inside the PR:
1. `chore(electron): add node-usb-mock devDep + mac usb entitlements plist` (T1.1 + T1.4 + T1.5)
2. `feat(electron): Zod schemas + types for printer IPC payload` (T1.3)
3. `feat(electron): printer service with USB 0x07 detection + escpos-usb wrapper` (T2.1)
4. `feat(electron): printQueue with backoff 5s/15s/60s persisted in electron-store` (T2.2)
5. `feat(electron): print:ticket IPC handler with Zod validation + status events` (T2.3)
6. `feat(electron): extend bridge.imprimir with getQueue + onStatus + fix JSDoc drift` (T3.1 + T3.2 + T3.3)
7. `test(electron): preload contract + Zod + printer + queue + e2e + perf` (T3.4 + Phase 4)

Author every commit as `Parkos Dev <dev@parkos.local>`. No AI co-author trailers. Branch: `feature/hu-f5-1-printer-service` (DO NOT create yet — orchestrator creates after tasks.md is approved).

## References

- plan.md lines 1446-1474 (HU-F5.1 contract, ACs verbatim)
- plan.md line 423 (DEC-SUC-08: escpos-usb + backoff 5s/15s/60s × 5)
- plan.md lines 432, 434 (DEC-SUC-17, DEC-SUC-19)
- plan.md lines 456-457 (A-05)
- `openspec/changes/fase-5-1-printer-service/proposal.md`, `specs/impresion/spec.md`, `design.md`
- `openspec/changes/archive/2026-09-17-fase-4-2-tarifas-vigentes/` (precedent)
- `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/` (precedent)