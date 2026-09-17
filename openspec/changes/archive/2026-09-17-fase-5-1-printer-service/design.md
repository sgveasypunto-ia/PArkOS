# Design: HU-F5.1 — Servicio de impresora térmica (main process)

## Technical Approach

Tres módulos en el main process de Electron detrás de un único handler IPC `print:ticket`. Validación Zod al borde (defensa en profundidad contra un renderer comprometido, DEC-SUC-17). El handler NUNCA espera el backoff — la cola persiste y los reintentos drenan en background via timer. `electron-store` provee persistencia entre reinicios sin acoplar a Postgres (que vive en `api-sucursal`, no en Electron). El renderer hace `bridge.imprimir(payload)` y recibe respuesta inmediata; el estado de la cola se consulta con `bridge.imprimir.getQueue()` (poll) o se entera via push `print:status` para actualizar banners.

## Architecture Decisions

### Decision: Type-source-of-truth en `electron/types/print.ts` con Zod

**Choice**: `electron/types/print.ts` define `printPayloadSchema`, `queueItemSchema`, `printerErrorSchema` como Zod schemas y exporta los tipos vía `z.infer<typeof ...>`. `bridge.d.ts` los re-exporta via `import type { PrintPayload, ... } from './types/print'`. El handler `ipc/imprimir.ts` importa el schema runtime para validar.
**Alternatives considered**:
- (a) Mantener tipos hand-written en `bridge.d.ts` con un schema Zod paralelo en `electron/types/print.ts`. Rejected: duplicación, drift inevitable entre tipo y schema.
- (b) Generar tipos desde el schema con `zod-to-openapi`. Rejected: añade build step sin valor en MVP.
**Rationale**: single source of truth, `.d.ts` y `.ts` conviven en `tsconfig.main.json` (que ya incluye ambos).

### Decision: Sync `electron-store` access para la cola

**Choice**: `printQueue` opera 100% sync contra `electron-store@^8.2.0`. El IPC handler es async (porque `ipcMain.handle` lo requiere), pero el handler llama a `printer.print()` (que internamente delega a `escpos-usb` que SÍ es sync en su API de write) y a `queue.enqueue()` (sync). El drain timer (`setTimeout` recursivo) llama los mismos métodos sync.
**Alternatives considered**:
- (a) `electron-store` async via `setImmediate`. Rejected: complica la lógica del drain timer; el queue ya está en memoria, sólo el flush final necesita persistencia.
- (b) BBDD Postgres en `api-sucursal` para la cola. Rejected: acopla el cliente a la API; además, `electron-store` es lo que dicta DEC-SUC-05 ("electron-store para cache persistente entre reinicios").
**Rationale**: Sync dentro de Electron main process es idiomático y suficiente; tamaño de queue <1MB incluso en casos extremos (10 tiquetes × ~10KB = 100KB).

### Decision: Push `print:status` + poll `getQueue()`, NO WebSocket

**Choice**: Main process envía `webContents.send('print:status', payload)` para eventos one-way (item completado, item failed_terminal, queue grew). Renderer se suscribe via `bridge.imprimir.onStatus(handler)` que internamente envuelve `ipcRenderer.on('print:status', ...)`. Adicionalmente `bridge.imprimir.getQueue()` para casos "refresh manual".
**Alternatives considered**:
- (a) Solo poll cada N segundos. Rejected: latencia innecesaria cuando el usuario está mirando la pantalla; batería/RAM innecesario cuando no hay nada que reportar.
- (b) WebSocket entre renderer y main process. Rejected: ya tenemos IPC que es lo mismo pero tipado.
**Rationale**: IPC push + poll hybrid es el patrón Electron estándar; ya lo usa `electron-updater` internamente para `update-downloaded`.

### Decision: NO serialización de bytes ESC/POS en F5.1

**Choice**: `printPayloadSchema` acepta SOLO `buffer: string` (base64). La composición de bytes (`0x1B 0x40` init, `0x1D 0x56 0x00` cut, etc.) es responsabilidad de `escposBuilder` en HU-F5.2.
**Alternatives considered**:
- (a) Aceptar `lines: PrintLine[]` y serializar aquí. Rejected: viola la separación F5.1/F5.2; F5.2 debe ser independiente porque incluye fallback `window.print()` que NO usa ESC/POS.
- (b) Aceptar ambos `buffer` y `lines` (renderer decide). Rejected: doble superficie, doble código de validación, sin beneficio claro.
**Rationale**: la composición de tiquetes es un concern de HU-F5.2 (F5.1+5.2 = "Servicio de impresión térmica" en plan.md); mezclar rompe la atomicidad de F5.2.

### Decision: NO shim local de `escpos-usb` por defecto; intentar `@types/escpos-usb` primero

**Choice**: Tasks T9 incluye `pnpm add -D @types/escpos-usb`. Si `pnpm` resuelve (DefinitelyTyped lo provee), se usa. Si falla (404, incompatible con alpha), fallback `electron/types/escpos-usb.d.ts` con `declare module 'escpos-usb' { ... }` cubriendo la API mínima usada (`findPrinter(vid, pid): Device`, clase `Device` con `open(): void`, `close(): void`, `print(buf: Buffer): void`, `cashdraw(): void`, `cut(): void`).
**Rationale**: alpha packages a veces no llegan a DefinitelyTyped; el shim local es plan B que no agrega complejidad si Plan A funciona.

## Data Flow

```
Renderer (React)
   │
   ├─ bridge.imprimir(payload: {buffer, ticketId, cut, uuidRegistro?, ...})
   │       │
   │       ▼  contextBridge.exposeInMainWorld → ipcRenderer.invoke('print:ticket', payload)
   │
Main process (Electron)
   │
   ├─ ipcMain.handle('print:ticket', async (_e, payload) => {
   │     const parsed = printPayloadSchema.parse(payload);       // R4: Zod first
   │     try {
   │       await printer.print(parsed.buffer, vid, pid);          // R2: <500ms P95
   │       return { ok: true, queueId: null };
   │     } catch (e) {
   │       const code = mapEscposError(e);                       // R3: typed
   │       if (code === 'printer_offline') {
   │         const queueId = queue.enqueue(parsed);               // R5: persist
   │         return { ok: false, error: code, queueId };
   │       }
   │       return { ok: false, error: code };                    // printer_disconnected
   │     }
   │   })
   │
   ├─ printer.print(buf, vid, pid)
   │     └─ new escpos.Printer(vid, pid).open()
   │           .print(buf)                                        // sync write to USB
   │           .close()
   │
   ├─ queue (FIFO in electron-store key parkos.print.queue.v1)
   │     ├─ enqueue(item) → item.attempts=0, nextRetryAt=now+5000
   │     ├─ drain() → for each item where nextRetryAt <= now: printer.print; on fail: bump attempts + reschedule per backoff
   │     └─ on app boot → load queue + drain immediately any past-due
   │
   └─ webContents.send('print:status', { type, queueId, ... })    // push to renderer
```

### State machine (queue item)

```
pending (attempts=0)
   │  printer.print fails
   ▼
retrying_1 (attempts=1, nextRetryAt=now+5s)
   │  fail → nextRetryAt=now+15s
   ▼
retrying_2 (attempts=2, nextRetryAt=now+15s)
   │  fail → nextRetryAt=now+60s
   ▼
retrying_3 (attempts=3, nextRetryAt=now+60s)
   │  fail → nextRetryAt=now+60s
   ▼
retrying_4 (attempts=4, nextRetryAt=now+60s)
   │  fail → nextRetryAt=now+60s
   ▼
retrying_5 (attempts=5, nextRetryAt=now+60s)
   │  fail → emits print_failed_terminal
   ▼
fallido_permanente (stays in electron-store; display-only clear via clearFailed)
```

## File Changes

| File | Action | Description |
|---|---|---|
| `electron/types/print.ts` | Create | Zod schemas (`printPayloadSchema`, `queueItemSchema`, `printerErrorSchema`) + tipos derivados (`PrintPayload`, `PrintResult`, `QueueStatus`, `PrinterErrorCode`, `USBDevice` class extended with `class: 0x07`) |
| `electron/services/printer.ts` | Create | `listDevices(): USBDevice[]` (USB enum + class filter) + `print(buf: Buffer, vid: pid): Promise<void>` (escpos-usb wrapper) + `startWatcher(intervalMs, onChange)` (poll 5s diff) |
| `electron/services/printQueue.ts` | Create | `class PrintQueue { enqueue, drain, getQueue, clearFailed }` backed by `electron-store` key `parkos.print.queue.v1`; backoff `[5000,15000,60000,60000,60000]` ms |
| `electron/ipc/imprimir.ts` | Create | `registerIpcHandlers({ queue, mainWindow, store })` — registers `print:ticket`, `print:queue:get`, `print:queue:clear-failed`, plus emitter for `print:status` |
| `electron/main.ts` | Modify | `app.whenReady()` instanciates `PrintQueue`, llama `registerIpcHandlers` con la queue y `mainWindow` |
| `electron/bridge.d.ts` | Modify | (1) `import type { PrintPayload, PrintResult, QueueStatus, PrinterErrorCode } from './types/print'`; (2) `PrintPayload`/`PrintResult` ahora vienen del import; (3) `BridgeSurface.imprimir` se mantiene `imprimir(payload): Promise<PrintResult>` + se añade `imprimir.getQueue(): Promise<QueueStatus>`; (4) `BridgeSurface.imprimir.onStatus(handler): () => void` (subscribe + unsubscribe); (5) línea 5-11 JSDoc: "7 groups, 12 methods" (corrige drift F4.2) |
| `electron/preload.ts` | Modify | (1) Añade `imprimir.getQueue: () => ipcRenderer.invoke('print:queue:get')`; (2) Añade `imprimir.onStatus: (handler) => { const listener = (_e, payload) => handler(payload); ipcRenderer.on('print:status', listener); return () => ipcRenderer.off('print:status', listener); }` |
| `electron/__tests__/preload.contract.test.ts` | Modify | (1) Añade `'imprimir'` que ahora es objeto (`getQueue`/`onStatus`) en `Object.keys(exposed).sort()`; (2) Nueva aserción `imprimir.getQueue` invoca `'print:queue:get'`; (3) Nueva aserción `imprimir.onStatus` registra listener en `'print:status'` y devuelve unsubscribe |
| `electron/services/printer.test.ts` | Create | Unit: `listDevices` con `node-usb-mock` — filtra 0x07; `print` happy path con dispositivo simulado |
| `electron/services/printQueue.test.ts` | Create | Unit: enqueue persiste JSON en `StoreLike` mock; backoff schedule correcto; drain loop respeta `nextRetryAt`; 5 attempts → terminal |
| `build/entitlements.mac.plist` | Create | `<?xml ...><plist><dict><key>com.apple.security.device.usb</key><true/></dict></plist>` |
| `electron-builder.yml` | Modify | Añade `entitlements: build/entitlements.mac.plist` y `entitlementsInherit: build/entitlements.mac.plist` bajo el bloque `mac:` (singular, no los dos `mac:` que ya existen — fix preexistente) |
| `e2e/printer.spec.ts` | Create | 4 escenarios: (1) `bridge.usb.list()` retorna device 0x07; (2) `bridge.imprimir` happy path; (3) desconexión mid-print NO crashea; (4) perf P95 <500 ms (100 calls secuenciales) |
| `package.json` | Modify | devDeps: `node-usb-mock`; condicional `@types/escpos-usb` o shim local |

## Interfaces / Contracts

```ts
// electron/types/print.ts
import { z } from 'zod';

export const printPayloadSchema = z.object({
  buffer: z.string().min(1),                              // base64; F5.2 serializa
  ticketId: z.string().min(1).max(64),
  cut: z.boolean().default(false),
  cashDrawer: z.boolean().optional(),
  vid: z.number().int().min(0).max(0xffff).optional(),   // if absent, uses first printer
  pid: z.number().int().min(0).max(0xffff).optional(),
  uuidRegistro: z.string().uuid().optional(),              // link to ingreso/salida/factura
});

export type PrintPayload = z.infer<typeof printPayloadSchema>;

export const printerErrorSchema = z.enum([
  'bridge_imprimir_invalid_payload',
  'printer_offline',
  'printer_disconnected',
  'print_failed_terminal',
]);
export type PrinterErrorCode = z.infer<typeof printerErrorSchema>;

export const printResultSchema = z.object({
  ok: z.boolean(),
  error: printerErrorSchema.optional(),
  queueId: z.string().uuid().nullable(),
  issues: z.array(z.object({ path: z.array(z.union([z.string(), z.number()])), message: z.string() })).optional(),
});
export type PrintResult = z.infer<typeof printResultSchema>;

export const queueItemSchema = z.object({
  id: z.string().uuid(),
  buffer: z.string(),                                      // base64
  vid: z.number().int(),
  pid: z.number().int(),
  ticketId: z.string(),
  uuidRegistro: z.string().uuid().optional(),
  attempts: z.number().int().min(0).max(5),
  nextRetryAt: z.number().int(),                           // epoch ms
  addedAt: z.number().int(),
  estado: z.enum(['pending', 'retrying', 'fallido_permanente']),
  lastError: printerErrorSchema.optional(),
});
export type QueueItem = z.infer<typeof queueItemSchema>;

export const queueStatusSchema = z.object({
  pending: z.number().int().min(0),
  retrying: z.number().int().min(0),
  fallido_permanente: z.number().int().min(0),
  lastSuccessAt: z.number().int().nullable(),
  lastError: printerErrorSchema.nullable(),
});
export type QueueStatus = z.infer<typeof queueStatusSchema>;
```

```ts
// electron/bridge.d.ts (relevant excerpts)
import type { PrintPayload, PrintResult, QueueStatus, PrinterErrorCode } from './types/print';

export interface USBDevice {
  vendorId: number;
  productId: number;
  productName: string | null;
  serialNumber: string | null;
  class: number;   // F5.1: extended with USB class (0x07 = Printer)
}

export interface BridgeSurface {
  imprimir: {
    (payload: PrintPayload): Promise<PrintResult>;
    getQueue(): Promise<QueueStatus>;
    onStatus(handler: (event: { type: 'print_succeeded' | 'print_failed' | 'print_failed_terminal' | 'queue_grew'; queueId: string; ticketId?: string; error?: PrinterErrorCode }) => void): () => void;
  };
  usb: { list(): Promise<USBDevice[]> };
  // ... kiosk, app, apiStatus, authStore unchanged
}
```

## Testing Strategy

| Layer | What | Test command |
|---|---|---|
| Unit (services) | `listDevices` filtra 0x07; `print` happy path con `node-usb-mock`; queue persistence + backoff schedule + 5 attempts → terminal | `npx vitest run electron/services/printer.test.ts electron/services/printQueue.test.ts` |
| Unit (bridge contract) | `imprimir.getQueue` invoca `'print:queue:get'`; `imprimir.onStatus` suscribe y devuelve unsubscribe | `npx vitest run electron/__tests__/preload.contract.test.ts` |
| Unit (types) | Zod schemas accept/reject con happy paths y edge cases (`uuidRegistro` inválido, buffer vacío) | `npx vitest run electron/types/print.test.ts` |
| E2E (Playwright) | 4 escenarios: (a) detección 0x07; (b) impresión OK via `bridge.imprimir`; (c) desconexión mid-print NO crashea; (d) P95 <500 ms para buffer 1 KB | `npx playwright test e2e/printer.spec.ts` |
| Manual | Lanzar Electron dev shell, conectar impresora real, imprimir tiquete de prueba, desconectar cable USB, reconectar, verificar que la cola drena | `cd apps/electron-sucursal && npm run dev:main` + ventana Electron |

## Threat Matrix

N/A — la modificación no toca routing, shell, subprocess, VCS/PR automation, executable-file classification, ni process-integration boundaries. `escpos-usb` usa `node-usb` (libusb) que NO es shell-out; es FFI/binding nativo via `node-gyp`. El IPC handler corre en main process, sin subprocesos. El único boundary nuevo es el USB device access, que ya está gobernado por `build/entitlements.mac.plist` y el BrowserWindow webPreferences hardenizado (DEC-SUC-17).

## Migration / Rollout

No DB migration. No backend changes. Feature flag NO necesario (F5.1 es infraestructura pura sin UX visible — los banners del renderer los cablea F6.1+).

**Rollout**: el branch `feature/hu-f5-1-printer-service` mergea a `dev` per gitflow. `main` solo recibe via release branch. Verificar `electron-builder.yml` antes del primer build macOS (sin entitlements = build falla con `hardenedRuntime`). En Windows/Linux el cambio de YAML es invisible pero las verificaciones e2e cubren los caminos principales.

## Open Questions

- [ ] ¿`escpos-usb@3.0.0-alpha.4` ya está publicado en npm y descargable? El `package.json` lo declara pero `node_modules/` no lo tiene instalado. El apply phase debe resolver esto antes de `pnpm install`.
- [ ] ¿`@types/escpos-usb` existe en DefinitelyTyped? Si no, el shim local es el plan B (declaration only, sin build step).
- [ ] ¿Vale la pena `node-usb-mock` o usamos un mock más liviano escrito in-repo? `node-usb-mock` es el estándar de la comunidad; bajo riesgo.
- [ ] ¿El operator UI quiere el banner auto-cleared tras `print_succeeded`, o un toast persistente que requiera dismiss manual? F6.1+ owns UI; F5.1 solo emite el evento.

## References

- plan.md lines 1446-1474 (HU-F5.1)
- plan.md line 423 (DEC-SUC-08)
- plan.md lines 432, 434 (DEC-SUC-17, DEC-SUC-19)
- plan.md lines 456-457 (A-05)
- `apps/electron-sucursal/electron/bridge.d.ts` (F2.2 stub; F4.2 added tarifasStore)
- `apps/electron-sucursal/electron/preload.ts` (F2.2 whitelist)
- `apps/electron-sucursal/electron/main.ts` (F2.3 registers kiosko/api/app handlers)
- `openspec/changes/archive/2026-09-17-fase-4-2-tarifas-vigentes/` (precedent: bridge extension + JSDoc drift)
- `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/` (precedent: bridge stub then fill)