# Spec: Impresión térmica (HU-F5.1)

## Purpose

Servicio de impresión térmica de tiquetes en el main process de Electron. Habilita a las Fases 6-8 (tiquetes de entrada/salida/salida-mensualidad y reimpresión con costo) sin que cada una reinvente el ciclo USB→ESC/POS→manejo de error→reintento.

## Scope

**Incluido**: detección de dispositivos USB clase `0x07`, envío de buffer ESC/POS pre-serializado a `escpos-usb`, validación Zod del payload antes de tocar hardware, manejo de `printer_offline` con cola persistente en `electron-store`, push de eventos `print:status` al renderer, métricas de performance P95 <500 ms.
**Excluido**: composición de bytes ESC/POS (`escposBuilder`, HU-F5.2), fallback `window.print()` (HU-F5.2), kiosko/auto-update (DEC-SUC-18/19).

## Requirements

### Requirement: USB enumeration MUST filter Printer class

The system MUST expose `bridge.usb.list()` (ya wireado por F2.2 en `bridge.d.ts:55-58`) returning ONLY devices whose `bDeviceClass === 0x07` (Printer class, USB-IF standard).

#### Scenario: printer USB class 0x07 detected

- GIVEN a USB thermal printer is connected (vid:pid reported by the OS)
- WHEN `bridge.usb.list()` is invoked from the renderer
- THEN the returned list MUST contain a `USBDevice` with the printer's `vendorId`/`productId`
- AND the device's `class` MUST equal `0x07`

#### Scenario: non-printer USB devices filtered out

- GIVEN a USB hub, mass storage, or HID device is connected
- WHEN `bridge.usb.list()` is invoked
- THEN the returned list MUST NOT include those devices
- AND any list operation MUST complete in <100 ms

### Requirement: Print latency MUST meet P95 <500 ms for 1 KB buffer

The system MUST complete a synchronous print (no enqueue) of a 1024-byte ESC/POS buffer in P95 <500 ms wall-clock, measured between IPC handler entry and `escpos-usb` `print()` callback resolution, on the developer reference hardware (Windows + Epson TM-T20 compatible).

#### Scenario: 1 KB buffer prints under P95 budget

- GIVEN a connected thermal printer with an empty queue
- WHEN `bridge.imprimir({ buffer: '<base64 1024 bytes>', ticketId: 'p-001', cut: true })` is invoked
- THEN the response MUST arrive within 500 ms in at least 95 of 100 sequential calls
- AND each call MUST measure `performance.now()` deltas recorded to `electron-log` (channel `print.perf`)

#### Scenario: repeated calls do not degrade

- GIVEN the previous scenario ran 100 times consecutively
- WHEN the 100th call is observed
- THEN its latency MUST be ≤ 2× the median of the first 10 calls (no thermal throttling detected)

### Requirement: Disconnection at mid-print MUST NOT crash main process

The system MUST catch any exception thrown by `escpos-usb` during `print()` (`device not found`, `EPERM`, `EBUSY`, USB stall), log it via `electron-log` with `channel: 'print.error'`, emit `print:status` to the renderer, and return a typed error to the IPC handler. Main process MUST NOT exit.

#### Scenario: printer disconnected mid-print

- GIVEN a print is in flight on a connected printer
- WHEN the USB cable is unplugged during the print
- THEN the `escpos-usb` call raises (error code `LIBUSB_ERROR_NO_DEVICE` or similar)
- AND the IPC handler returns `{ ok: false, error: 'printer_offline', queueId: 'q-<uuid>' }` to the renderer
- AND `webContents.send('print:status', { type: 'print_failed', queueId, error: 'printer_offline' })` fires
- AND main process continues running (`app.isReady()` returns `true` after the call)

#### Scenario: device list cleared after disconnect

- GIVEN a print failed with `printer_offline` 3 times in a row
- WHEN `bridge.usb.list()` is invoked
- THEN the returned list MUST be empty (the OS no longer reports the device)
- AND the renderer MUST update its banner to "Impresora desconectada" (vs "Reintentando…")

### Requirement: IPC payload MUST be Zod-validated BEFORE hardware access

The system MUST call `printPayloadSchema.parse(payload)` BEFORE any `escpos-usb` call. If validation fails, the handler MUST throw a `ZodError` (FastAPI-equivalent 422) carrying the field path and expected type, never reaching hardware.

#### Scenario: payload missing required field

- GIVEN the renderer calls `bridge.imprimir({ /* no buffer, no ticketId */ })`
- WHEN the IPC handler receives the payload
- THEN validation MUST fail with `ZodError` carrying `[{ path: ['buffer'], message: 'Required' }, { path: ['ticketId'], message: 'Required' }]`
- AND no `escpos-usb` call MUST occur (verify via spy in unit test)
- AND the renderer receives a `422`-shaped error (`{ ok: false, error: 'bridge_imprimir_invalid_payload', issues: [...] }`)

#### Scenario: payload has invalid uuidRegistro

- GIVEN the renderer sends `bridge.imprimir({ buffer: 'AA==', ticketId: 't-1', cut: false, uuidRegistro: 'not-a-uuid' })`
- WHEN validation runs
- THEN it MUST fail at `uuidRegistro` with `Invalid uuid` (Zod's `.uuid()` v4 validator)
- AND no hardware call MUST occur

### Requirement: Retry queue MUST survive app restart

The system MUST persist the print queue in `electron-store` under key `parkos.print.queue.v1` as a JSON array of items `{ buffer: string (base64), vid: number, pid: number, ticketId: string, uuidRegistro?: string, attempts: number, nextRetryAt: number (epoch ms), addedAt: number }`. On app start, the queue MUST be re-loaded and any items with `nextRetryAt <= now` MUST be drained immediately; future-dated items MUST schedule a timer.

#### Scenario: app restart resumes queue

- GIVEN a print is enqueued with `attempts: 1, nextRetryAt: <now + 5s>` and the app is killed
- WHEN the app restarts 30 seconds later
- THEN the queue MUST be re-loaded from `electron-store`
- AND the item MUST be picked up by the drain loop (its `nextRetryAt` is in the past)
- AND retry MUST occur without operator action

#### Scenario: backoff schedule is 5s/15s/60s

- GIVEN a print fails for attempt N (1 ≤ N ≤ 5)
- WHEN the queue scheduler picks the next retry
- THEN `nextRetryAt = failedAt + [5000, 15000, 60000, 60000, 60000][N-1]` ms
- AND `attempts` MUST increment to N+1

#### Scenario: 5 attempts exhausted → permanent failure

- GIVEN a print has `attempts: 5` and fails again
- WHEN the drain loop processes it
- THEN the item MUST be marked `estado: 'fallido_permanente'` (in-memory; not persisted as terminal)
- AND `webContents.send('print:status', { type: 'print_failed_terminal', ticketId, uuidRegistro, lastError })` MUST fire
- AND the item MUST remain in the queue (NOT deleted) for post-mortem inspection — physical delete would violate the audit-first principle for an append-only queue log; the item keeps `fallido_permanente` state until the renderer drains it via `bridge.imprimir.clearFailed(ticketId)` which only clears display, never disk.

### Requirement: `bridge.imprimir` MUST return immediately, not wait for backoff

The system MUST NOT block the renderer on the backoff schedule. The handler MUST return a `PrintResult` synchronously after the first attempt; subsequent retries happen in the background.

#### Scenario: first attempt fails → immediate response

- GIVEN the printer is offline
- WHEN `bridge.imprimir(payload)` is invoked
- THEN within 500 ms the renderer MUST receive `{ ok: false, error: 'printer_offline', queueId: 'q-<uuid>' }`
- AND the renderer MUST show the banner "Impresora no disponible, reintentando…"
- AND the renderer MUST NOT block its own UI thread

#### Scenario: queue drain emits status events

- GIVEN the queue has 3 items and the printer reconnects
- WHEN the drain loop processes them
- THEN each successful print MUST emit `print:status` with `type: 'print_succeeded', queueId`
- AND the renderer MUST clear the banner once all items succeed
- OR if any item fails terminally, the renderer MUST show the strongest error state

## Error Catalog

| Code | Origin | Renderer Action |
|---|---|---|
| `bridge_imprimir_invalid_payload` | `ZodError` from `printPayloadSchema.parse` | "Formato de impresión inválido" toast; no retry |
| `printer_offline` | `escpos-usb` raised recoverable error | "Impresora no disponible, reintentando…" banner; poll `bridge.imprimir.getQueue()` every 30s |
| `printer_disconnected` | `escpos-usb` raised unrecoverable error (3 consecutive `printer_offline`) | "Impresora desconectada" banner; `bridge.usb.list()` returns empty |
| `print_failed_terminal` | Queue drain, 5 attempts exhausted | "Tiquete no impreso — reimprimir manualmente" toast; banner stays until cleared |

## Constraints

- **Buffer format**: F5.1 accepts ONLY `buffer: string` (base64-encoded bytes). Rejects `lines: PrintLine[]` (F5.2's job to compose).
- **No silent deletes**: queue items in `fallido_permanente` state are NEVER removed from `electron-store`; only `clearFailed(ticketId)` flag changes display.
- **No DIAN write**: F5.1 does not write `log_transaccional`; the caller (F6.1+) writes `accion='impreso'` using `uuidRegistro` from `PrintPayload`.
- **Single instance**: queue state is per-process; relies on DEC-SUC-19 single-instance lock to avoid concurrent queues from a second `electron-sucursal` invocation.
- **macOS hardenedRuntime**: requires `build/entitlements.mac.plist` `com.apple.security.device.usb = true`; `electron-builder.yml` `mac.entitlements` MUST reference it before any macOS build succeeds.

## Dependencies

- `escpos-usb@^3.0.0-alpha.4` (already in `dependencies`)
- `electron-store@^8.2.0` (already in `dependencies`)
- `zod@^3.23.8` (already in `dependencies`)
- `node-usb-mock` (devDep, NEW) — required for `e2e/printer.spec.ts` and unit tests; simulates USB devices and disconnect events
- `@types/escpos-usb` (devDep, NEW, conditional) — Plan A via DefinitelyTyped; Plan B is a local `electron/types/escpos-usb.d.ts` shim if `@types/escpos-usb` does not resolve for `3.0.0-alpha.4`

## Out of Scope (Forward References)

- **HU-F5.2** — `escposBuilder.build(tipo, payload): Buffer` (init, cut, centrado, negrita, QR, logo) + `fallbackBrowser.print(payload)`. F5.2 calls `bridge.imprimir({ buffer: base64(escposBuilder.build(...)) })` — F5.1 receives the pre-serialized buffer.
- **Fase 6 / CU-15E** — auto-print on `POST /operacion/ingresos` 200 (plan.md:1509). Caller (F6.1+) constructs `escposBuilder.build('entrada', payload)` and invokes `bridge.imprimir`.
- **Fase 7 / CU-15S + CU-15SM** — auto-print after payment (CU-04). Same pattern as CU-15E.
- **Fase 8 / `reimpresion_ticket`** — post-paid reprint. Caller checks workflow state then invokes `bridge.imprimir` with `uuidRegistro` set to the `facturas.uuid`.

## References

- plan.md lines 1446-1474 (HU-F5.1 contract, ACs verbatim)
- plan.md line 423 (DEC-SUC-08 — `escpos-usb`; backoff 5s/15s/60s × 5; `electron-store` key; `@page{size:80mm auto;margin:2mm}` fallback)
- plan.md line 432 (DEC-SUC-17 — renderer hardenizado)
- plan.md line 434 (DEC-SUC-19 — single-instance lock)
- plan.md lines 456-457 (A-05 — estado de impresión vía `log_transaccional`)
- `openspec/specs/operations/spec.md` REQ-OPS-112 (forward hook fulfilled by F5.1)
- `openspec/changes/archive/2026-09-17-fase-4-2-tarifas-vigentes/` — precedent for bridge extension + JSDoc drift closure