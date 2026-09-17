# Proposal: HU-F5.1 — Servicio de impresora térmica (main process)

## Intent

Fase 5 existe para construir **primero** el servicio de impresión térmica antes de los tiquetes de las Fases 6-8, de modo que CU-15E/CU-15S/CU-15SM y la reimpresión con costo (Fase 8) no queden bloqueadas por un bloqueador de bajo nivel a medio terminar (plan.md:1448). HU-F5.1 entrega ese servicio en el main process de Electron: detección USB 0x07, impresión <500 ms P95, manejo defensivo ante desconexión, validación Zod antes de tocar hardware, y cola de reintento con backoff 5s/15s/60s persistida en `electron-store` (DEC-SUC-08). El bridge IPC `imprimir` ya está wireado en F2.2 (`apps/electron-sucursal/electron/bridge.d.ts:18-33, 51-58` + `preload.ts:25`); F5.1 implementa el handler real y la maquinaria de reintento que faltaba.

## Scope

### In Scope

- `electron/services/printer.ts` — `listDevices()` (USB enumeration clase `0x07`), `print(buffer, vid, pid)` (canal a `escpos-usb`), lifecycle (`startWatcher()` re-emite cambios por hot-plug).
- `electron/services/printQueue.ts` — cola persistente de reintento con backoff `5s/15s/60s` × 5 intentos, persistida en `electron-store` bajo clave `parkos.print.queue.v1`, sobrevive a reinicio de la app.
- `electron/ipc/imprimir.ts` — handler `ipcMain.handle('print:ticket', ...)` con validación Zod del payload **antes** de tocar hardware; emite `webContents.send('print:status', ...)` para que el renderer actualice el banner.
- `electron/types/print.ts` — schemas Zod (`printPayloadSchema`, `queueItemSchema`) + tipos derivados (`PrintPayload`, `PrintResult`, `QueueStatus`, `PrinterErrorCode`).
- Extensión `electron/bridge.d.ts` + `preload.ts` para adicionar `imprimir.getQueue()` (poll de estado de cola para el banner del renderer); corrección del JSDoc de línea 5-11 a "7 groups, 12 methods" (drift acumulado de F4.2 que F5.1 cierra).
- `electron/__tests__/preload.contract.test.ts` — extender el contrato (3 nuevas aserciones para el canal `print:status` y el grupo `imprimir.getQueue`).
- `build/entitlements.mac.plist` (NEW) con `com.apple.security.device.usb = true` + `electron-builder.yml` (añadir `mac.entitlements: build/entitlements.mac.plist`).
- `e2e/printer.spec.ts` con `node-usb-mock` (detección, impresión OK, desconexión no crashea) + test de performance P95 <500 ms para buffer 1 KB (`performance.now()` medido en main).
- Documentación de riesgos de instalación (escpos-usb requiere `node-usb` nativo; ver Riesgos).

### Out of Scope

- HU-F5.2 (`escposBuilder` base + fallback `window.print()`) — change independiente.
- Visual demo kiosko (DEC-SUC-19), auto-update flow (DEC-SUC-18) — otros HU.
- Lógica de reintento del lado cloud (no toca este service).
- Sin cambios en `apps/ui-kit`, `backend/`, ni en `modelo_datos_er.mmd`.

## Capabilities

### New Capabilities

Ninguna — el dominio `electron-bridge` ya existe (creado por F2.2); este change **extiende** un dominio existente con comportamiento nuevo (handler real + cola persistente + push events), pero no introduce una capacidad nueva a nivel de spec.

### Modified Capabilities

- `electron-bridge` — la spec canónica `openspec/specs/operations/spec.md` referencia REQ-OPS-112 (`bridge.imprimir invokes escpos-usb with PrintPayload`) marcada como forward hook a F5.1. F5.1 cumple ese REQ. Delta spec en este change describe la extensión.

## Approach

Tres módulos en main process:

1. **`printer.ts`** (hardware puro): envuelve `escpos-usb` (paquete específico, NO `escpos` genérico — DEC-SUC-08). Expone `listDevices()` que filtra por USB class `0x07` (Printer, valor estándar USB-IF), `print(buffer, vid, pid)` que abre dispositivo, escribe y cierra. `escpos-usb` puede tirar `device not found`, `EPERM`, `EBUSY` — todo eso se mapea a `PrinterErrorCode` y se eleva como excepción tipada.

2. **`printQueue.ts`** (persistencia + scheduling): cola FIFO en `electron-store`. Cada ítem lleva `attempts`, `nextRetryAt`, `buffer`, `deviceKey (vid:pid)`, `uuidRegistro` (link al `ingreso.uuid`/`salidas.uuid`/`facturas.uuid` para A-05). Al subir un payload al handler, si la impresión falla, se encola y un timer (`setTimeout` con cleanup en `app.on('before-quit')`) la drena cuando `nextRetryAt <= now`. 5 intentos, después `estado='fallido_permanente'` + el renderer recibe `print:status` con `type='print_failed_terminal'` para mostrar el banner final.

3. **`imprimir.ts`** (IPC handler): `ipcMain.handle('print:ticket', payload)` valida con `printPayloadSchema.parse(payload)` PRIMERO. Si falla → `throw new ZodError(...)` que el preload propaga al renderer (caller ve `422`-like con detalle). Si pasa → llama a `printer.print()`; éxito → `{ ok: true, queueId: null }`; fallo recuperable → enqueue + `{ ok: false, queueId: 'q-...', error: 'printer_offline' }`; fallo permanente → `{ ok: false, error: 'printer_disconnected' }`.

El renderer hace `bridge.imprimir(payload)` y obtiene respuesta inmediata (no espera 5+15+60 segundos). El push `print:status` actualiza el banner cuando la cola progresa o termina. Adicionalmente se expone `bridge.imprimir.getQueue()` para polling manual.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `apps/electron-sucursal/electron/types/print.ts` | New | Zod schemas + tipos derivados |
| `apps/electron-sucursal/electron/services/printer.ts` | New | USB 0x07 enum + `print(buffer, vid, pid)` wrapper de `escpos-usb` |
| `apps/electron-sucursal/electron/services/printQueue.ts` | New | Cola persistente en `electron-store` + drain timer |
| `apps/electron-sucursal/electron/ipc/imprimir.ts` | New | Handler `print:ticket` + emitter `print:status` |
| `apps/electron-sucursal/electron/main.ts` | Modified | Registra handlers + instancia la cola |
| `apps/electron-sucursal/electron/bridge.d.ts` | Modified | Importa tipos desde `./types/print`; corrige JSDoc group-count (F4.2 drift); añade `imprimir.getQueue()` |
| `apps/electron-sucursal/electron/preload.ts` | Modified | Añade `imprimir.getQueue` → `ipcRenderer.invoke('print:queue:get')`; añade push listener `imprimir.onStatus(handler)` |
| `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` | Modified | Aserciones para `print:queue:get` + `print:status` |
| `apps/electron-sucursal/electron/services/printer.test.ts` | New | Unit: `listDevices` filtra 0x07; `print` happy path con `node-usb-mock` |
| `apps/electron-sucursal/electron/services/printQueue.test.ts` | New | Unit: persistencia + backoff schedule + 5 intentos → fallido_permanente |
| `apps/electron-sucursal/build/entitlements.mac.plist` | New | `com.apple.security.device.usb = true` |
| `apps/electron-sucursal/electron-builder.yml` | Modified | Añade `mac.entitlements: build/entitlements.mac.plist` |
| `apps/electron-sucursal/e2e/printer.spec.ts` | New | E2E: detección, impresión OK, desconexión no crashea; perf P95 |
| `apps/electron-sucursal/package.json` | Modified | `devDeps`: `node-usb-mock`; `types`: shim local si `@types/escpos-usb` no existe |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `escpos-usb@^3.0.0-alpha.4` requiere `node-usb` (binario nativo). En Windows + sandbox F.6, `pnpm install` puede colgarse (>300s) durante `node-gyp rebuild`. | High | Documentar en PR description. Mitigation: (a) `pnpm install` con `--ignore-scripts` para develop; (b) build pipeline usa Windows con Visual Studio Build Tools instaladas (verificado por F2.1). Documentar tiempo esperado (3-5 min primer build). |
| `@types/escpos-usb` puede NO existir en DefinitelyTyped para la versión `3.0.0-alpha.4`. | Medium | Plan A: `pnpm add -D @types/escpos-usb`. Plan B: shim local `electron/types/escpos-usb.d.ts` con declaraciones `declare module 'escpos-usb'` cubriendo `findPrinter(vid,pid)` y la clase `Printer` con `open/close/print/cashdraw/cut`. |
| Drift acumulado del JSDoc group-count en `bridge.d.ts` (F4.2 no actualizó línea 11; sigue diciendo "6 groups, 8 methods" cuando ya son 7 grupos/11 métodos). | Low (cosmético) | F5.1 corrige a "7 groups, 12 methods" tras añadir `imprimir.getQueue` (un método nuevo). Verificación: `preload.contract.test.ts` cuenta los top-level keys. |
| Hot-plug USB no emite eventos en `node-usb` v2/v3 de forma consistente entre Windows/macOS/Linux. | Medium | `printer.startWatcher()` poll cada 5s con diff (`Set<vid:pid>`) — fallback robusto si `usb.on('attach')` no dispara. Test e2e cubre hot-plug con `node-usb-mock`. |
| `electron-store` async vs sync mismatch: v8 es sync (default). Si la cola intenta `set/get` sincrónico en IPC handler async, no hay problema; pero si en drain timer (sync) llama a un path async, hay deadlock potencial. | Low | Toda la API `electron-store` se llama en main process (sync OK). El timer llama métodos sync. Sin async path en `printQueue`. |
| Tiquete referencia `ingreso.uuid` / `salidas.uuid` (retention DIAN 5+ años per A-05 + `RNF-COMP-01`). El estado de impresión se persiste como fila en `log_transaccional` (`accion='impreso'`). F5.1 NO escribe en `log_transaccional` (eso es backend / F6.1+), pero el `uuidRegistro` debe propagarse al backend vía `PrintPayload.uuidRegistro` para que F6+ pueda enlazar. | Medium | `PrintPayload` incluye `uuidRegistro: string` opcional. F5.1 valida que, si viene, sea UUID v4. La integración con `log_transaccional` queda diferida a F6.1 (caller del bridge.imprimir). Documentado en `## Spec` (constraint not behavior). |
| Drift entre spec y código: `bridge.d.ts` ya tiene `PrintPayload` con `lines: PrintLine[]` (formato estructurado). `escpos-usb` recibe un `Buffer` ya serializado. F5.1 decide si `bridge.imprimir(payload)` recibe `lines` (renderer-side) o `Buffer` (ya serializado por `escposBuilder` en F5.2). | Medium | F5.1 acepta ambos: si `payload.buffer` viene presente (base64), se envía directo a `escpos-usb`; si viene `payload.lines`, se rechaza con `bridge_imprimir_invalid_payload` (F5.2 será el caller que serializa). **NO se serializa en F5.1** — mantener el servicio F5.1 agnóstico al formato, F5.2 hace la composición. Documentado en `## Spec`. |

## Rollback Plan

1. Borrar archivos nuevos: `electron/types/print.ts`, `electron/services/printer.ts`, `electron/services/printQueue.ts`, `electron/ipc/imprimir.ts`, `electron/services/printer.test.ts`, `electron/services/printQueue.test.ts`, `e2e/printer.spec.ts`, `build/entitlements.mac.plist`.
2. Revertir `electron/bridge.d.ts` (eliminar `import { ... } from './types/print'`, restaurar JSDoc a "6 groups, 8 methods", remover `imprimir.getQueue`).
3. Revertir `electron/preload.ts` (eliminar `imprimir.getQueue` y `imprimir.onStatus`).
4. Revertir `electron/__tests__/preload.contract.test.ts` (quitar aserciones para `print:queue:get`).
5. Revertir `electron/main.ts` (quitar registro de `ipcMain.handle('print:ticket')` y `ipcMain.on('print:status')`).
6. Revertir `electron-builder.yml` (quitar `mac.entitlements`).
7. Revertir `package.json` (quitar `node-usb-mock` devDep).
8. Borrar clave `parkos.print.queue.v1` del electron-store en próximo boot (sin migración: el código que la usa ya no existe).
9. **Sin** migración de DB, **sin** cambios en backend, **sin** cambios en `modelo_datos_er.mmd`. Rollback idempotente.

## Dependencies

- **escpos-usb@^3.0.0-alpha.4** (ya en `dependencies` línea 40 de `apps/electron-sucursal/package.json`).
- **electron-store@^8.2.0** (ya en `dependencies` línea 38).
- **zod@^3.23.8** (ya en `dependencies` línea 51).
- **node-usb-mock** (NUEVO devDep) — mock USB para tests sin hardware físico.
- **@types/escpos-usb** (NUEVO devDep, condicional) — solo si DefinitelyTyped lo provee; si no, shim local.

## Success Criteria

- [ ] `npx tsc --noEmit` exit 0 en `apps/electron-sucursal/` (validates bridge typing end-to-end).
- [ ] `npx vitest run electron/services electron/__tests__ electron/types` → 0 failed tests.
- [ ] `npx playwright test e2e/printer.spec.ts` → 3 escenarios pasan (detect, print OK, disconnect no crash) + P95 <500 ms para buffer 1 KB.
- [ ] `bridge.imprimir(payload)` con payload inválido → renderer recibe `ZodError` tipada (no `500` genérico).
- [ ] `bridge.imprimir(payload)` con impresora desconectada → respuesta inmediata `{ok:false, error:'printer_offline', queueId:'q-...'}`; renderer muestra banner; cola persiste en `electron-store`; al reconectar impresora y `nextRetryAt <= now`, la cola drena automáticamente sin intervención del operador.
- [ ] `escpos-usb` integrado sin warnings de tipos en `tsc --noEmit`.

## Regulatory Impact

F5.1 NO toca datos retenidos DIAN. NO escribe en `factura_electronica`, `revocacion_factura`, `log_transaccional`, `envio_dian`. La retención 5+ años (RNF-COMP-01) aplica a `ingreso.uuid` / `salidas.uuid` que el tiquete referencia, pero esos registros los crea F6+ (back-end), no F5.1. F5.1 solo emite bytes ESC/POS a la impresora. El estado de impresión persistido como fila en `log_transaccional` (`accion='impreso'`) lo escribe el caller (F6.1+) con el `uuidRegistro` recibido en `PrintPayload.uuidRegistro`. F5.1 no añade columna a `log_transaccional`.

## Adjacent Concerns (informational, NOT in this change)

- **CU-15x logo y QR** (DEC-SUC-26) — contenido del tiquete, no del servicio. F5.2.
- **A-01 Póliza RC** — F5.2 (lee vía `GET /documentos`).
- **Reimpresión inmediata gratuita (E3 de CU-15E, post-F5.1)** — F6.1+ (caller decide si reimprime; F5.1 no distingue).
- **Reimpresión con costo (`reimpresion_ticket`)** — Fase 8. F5.1 expone el mismo `bridge.imprimir`; F8 usa `print.ticketId` para correlacionar.

## References

- plan.md lines 1446-1474 (Fase 5 + HU-F5.1 contract)
- plan.md line 423 (DEC-SUC-08: `escpos-usb` específicamente; cola backoff 5s/15s/60s × 5; persistida en `electron-store`; fallback `window.print()`)
- plan.md lines 432-434 (DEC-SUC-17: `contextIsolation:true`; DEC-SUC-19: single-instance + kiosko)
- plan.md lines 456-457 (A-05 — estado de impresión vía `log_transaccional`)
- plan.md lines 481-493 (§0.6 Estrategia de pruebas; axe-core 0 violaciones WCAG 2.1 AA)
- modelo_datos_er.mmd: `ingreso` [L-E] línea ~339, `salidas` [A] línea ~512, `log_transaccional` [A] línea 1049, `reimpresion_ticket` [L-W] línea 598
- Precedente de bridge extension: `openspec/changes/archive/2026-09-17-fase-4-2-tarifas-vigentes/` (F4.2 añadió `tarifasStore` group)
- F2.2 bridge stub: `apps/electron-sucursal/electron/bridge.d.ts` líneas 18-33, 51-58 + `preload.ts:25`