# Proposal: HU-F5.2 — `escposBuilder` base y fallback de navegador

## Intent

Fase 5 existe para construir **primero** la base de impresión térmica antes de que las Fases 6-8 (CU-15E/CU-15S/CU-15SM y reimpresión con costo) necesiten emitir tiquetes. **HU-F5.1** entrega el servicio de main-process (`escpos-usb` + cola `electron-store` + IPC `bridge.imprimir`); **HU-F5.2 entrega lo que el renderer le pasa al bridge**: una librería pura `escposBuilder.build(<tipo>, payload): Buffer` que serializa cualquiera de los 4 tipos de tiquete (entrada, salida, salida-mensualidad, reimpresión) a la secuencia ESC/POS canónica exigida por plan.md:1481, más un `fallbackBrowser.print(payload)` que dispara `window.print()` con la plantilla `@page{size:80mm auto;margin:2mm}` de DEC-SUC-08 cuando la térmica no responde.

Sin F5.2, F6.x (ingreso + tiquete CU-15E) no puede llamar `bridge.imprimir(payload)` con bytes pre-serializados — F5.1 diseñó su contrato justamente como `payload.buffer` (base64) enviado directo a `escpos-usb` (ver F5.1/proposal.md risk row 7). F5.2 NO toca main process, IPC, storage ni USB; es **lógica pura** serializable, testeable con vitest+jsdom sin hardware.

## Scope

### In Scope

- `apps/electron-sucursal/src/lib/print/escposBuilder.ts` — entrypoint `build(tipo, payload): Buffer`. Dispatcher puro sobre las 4 variantes; cero I/O.
- `apps/electron-sucursal/src/lib/print/escposTemplates.ts` — interfaces TS `EntradaPayload`, `SalidaPayload`, `SalidaMensualidadPayload`, `ReimpresionPayload` (cada una con campos del tiquete + `qrPayload` + `logoDataUrl` per DEC-SUC-26); constructores `build*Payload(...)` que validan con Zod antes de serializar; funciones `render*TiqueteEscpos(payload)` que producen un `Buffer` para un tipo específico.
- `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` — `print(<tipo>, payload)` dispara `window.print()` inyectando un `<style>` con `@page { size: 80mm auto; margin: 2mm }` + HTML semántico. La función `render*TiqueteHtml(payload)` vive en este módulo y espeja el layout del builder para que el fallback visual sea equivalente.
- `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.test.ts` — fixtures byte-a-byte (5+ tests) que verifican la presencia de `0x1B 0x40` init, `0x1D 0x56 0x00` partial cut, `0x1B 0x61 0x01` center, `0x1B 0x45` bold, `0x1B 0x21 0x30` 2x height.
- `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.types.test.ts` — un test por tipo de tiquete (entrada/salida/salida-mensualidad/reimpresión) verificando payload → bytes end-to-end y asserting contra el `Buffer` esperado.
- Helper `formatCOP` importado desde `src/lib/format/formatCOP.ts` (creado por F2.x, reusado).
- Helpers `utf8Encode` (Buffer.from) y un shim mínimo de `Buffer` para vitest+jsdom cuando se ejecute dentro del runner de tests (ver Risks).

### Out of Scope

- IPC, USB enumeration, hot-plug watcher, cola de reintento con backoff — todo eso es **F5.1**.
- Persistencia del estado de impresión (`log_transaccional`, A-05) — pertenece a F6.x (caller que ya tiene el `ingreso.uuid` y dispara el bridge).
- Componentes visuales de preview de tiquete en la UI — esos viven en F6.2 y F7.3, no en F5.2.
- Definición de campos literales CU-15E/S/SM (15/19/15) — eso es scope de F6.2 y F7.3, no del builder. F5.2 expone las interfaces, los HU de cada fase las llenan.
- Cifrado/hash DIAN — eso es cloud-only (FE), fuera de F5.2.
- Sin cambios en `backend/`, `modelo_datos_er.mmd`, ni en `apps/ui-kit`.

## Capabilities

### New Capabilities

- `impresion-tickets` — dominio nuevo que cubre la composición renderer-side de tiquetes térmicos (bytes ESC/POS + fallback HTML/CSS). Vive en `openspec/changes/fase-5-2-escpos-builder-fallback/specs/impresion/spec.md` y luego promueve a `openspec/specs/impresion/spec.md` al archivar.

### Modified Capabilities

- Ninguna. `electron-bridge` (F5.1) ya declara `payload.buffer` (base64) como contrato de F5.2; la spec canónica `openspec/specs/operations/spec.md` referencia REQ-OPS-112 como forward hook que F5.2 cumplimenta **sin modificar** la spec de F5.1.

## Approach

Tres archivos en `src/lib/print/`:

1. **`escposTemplates.ts`** (tipos + Zod): define `EntradaPayload`, `SalidaPayload`, `SalidaMensualidadPayload`, `ReimpresionPayload` con campos declarados por el call-site (NO acoplados al backend ER — el caller convierte `ingreso`/`salidas`/`facturas` al payload). Validador `validatePayload(tipo, payload)` que corre `zodSchema.parse(...)` y lanza `escpos_invalid_payload` (custom Error class).

2. **`escposBuilder.ts`** (orquestador): exporta `build(tipo, payload)` que dispatcha a `buildEntradaBuffer()`, `buildSalidaBuffer()`, etc. Cada `build*Buffer()` concatena los helpers `ESC_INIT`, `CUT_PARTIAL`, `CENTER_ON`, `BOLD_ON`, `BOLD_OFF`, `TEXT_2X_ON`, `TEXT_2X_OFF`, `LF` (todos como `Buffer.from([0x1B, ...])` exported desde el mismo archivo). El `Buffer` final se devuelve al caller; F5.1 lo recibe como base64 desde `bridge.imprimir`.

3. **`fallbackBrowser.ts`** (DOM-target): exporta `print(tipo, payload)` que (a) crea un `<div>` off-screen con el HTML del tiquete, (b) inyecta un `<style>` con `@page { size: 80mm auto; margin: 2mm }` (DEC-SUC-08 verbatim), (c) llama `window.print()`. La función `render*TiqueteHtml(payload)` espeja la composición ESC/POS pero con `<div>`s.

Orden de chequeo al aplicar `escposBuilder.build()`:
1. `validatePayload(tipo, payload)` lanza `escpos_invalid_tipo` (tipo desconocido) o `escpos_payload_missing_field` (Zod fail).
2. Si el `tipo` es válido y payload parsea, dispatch al constructor del subtipo.
3. Devuelve `Buffer`.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | New | Interfaces TS + Zod schemas + constructores de payload |
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | New | `build(tipo, payload): Buffer` + dispatcher 4-way + helpers ESC/POS |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` | New | `print(tipo, payload)` + `render*TiqueteHtml()` + CSS `@page` template |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.test.ts` | New | Fixtures byte-a-byte de los 5 comandos ESC/POS |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.types.test.ts` | New | 4 tests end-to-end payload → Buffer por tipo de tiquete |
| `apps/electron-sucursal/vitest.config.ts` | Modified | Setup `Buffer` global polyfill para jsdom (ver Risks) |
| `apps/electron-sucursal/src/renderer/global.d.ts` | Modified | `declare global { var Buffer: typeof import('buffer').Buffer }` |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `vitest` en environment `jsdom` no provee `Buffer` global. El `escposBuilder.ts` devuelve `Buffer` per DEC-SUC-08/contrato F5.1; los tests deben poder construir y comparar `Buffer` sin importar `node:buffer`. | Medium | Opción A: agregar `buffer@^6.0.3` a `dependencies` y `setupFiles: ['./src/renderer/test-setup.ts']` con `import { Buffer } from 'buffer'; globalThis.Buffer = Buffer;`. Plan B: cambiar return type a `Uint8Array` y que F5.1 haga `Buffer.from(uint8array.buffer, uint8array.byteOffset, uint8array.byteLength)` — pero esto es **decisión de producto** con impacto en F5.1 (no en F5.2). Default: Opción A, documentado en design.md. |
| Deps cero o mínimas — `@types/qrcode` necesario? | Low | Plan A: el QR no se serializa a ESC/POS en F5.2 — el caller (F6.2) provee un payload `qrDataUrl` (string base64) en el payload. El builder embebe la imagen vía `GS ( L` (ESC/POS raster bit-image) o simplemente la omite si la térmica no soporta gráficos y cae al fallback. **Decisión a tomar en design.md**: pasar `qrDataUrl` (string) o pre-serializar a bytes ESC/POS. Default: el builder recibe el string, F5.2 lo deja pasar al `bridge.imprimir` (F5.1 decide si rasteriza). Confirmado en design. |
| `formatCOP` aún no existe — F2.x está comprometido pero no shipped. | Medium | Plan A: declarar `formatCOP` en `escposTemplates.ts` (inline) hasta que F2.x lo materialice en `src/lib/format/formatCOP.ts`; luego refactor de import. Plan B (preferida): **bloqueador declarado** — si F2.x no tiene el módulo cuando F5.2 entra a apply, F5.2 declara el suyo propio y emite alerta de sync pendiente con F2.x. |
| `Buffer.from([0x1B, 0x40])` produce un Buffer `node` que jsdom no entiende sin shim. | Medium | Misma mitigación que Risk 1: setup global. |

## Rollback Plan

1. Borrar `apps/electron-sucursal/src/lib/print/` (directorio completo, 3 archivos TS + 2 archivos test).
2. Revertir `vitest.config.ts` (sin setup de Buffer polyfill).
3. Revertir `src/renderer/global.d.ts` (sin declaración de Buffer global).
4. Sin migración de DB, sin cambios en backend, sin cambios en `modelo_datos_er.mmd`.
5. F5.1 queda intacto — su `bridge.imprimir` esperaba `payload.buffer` (base64); al reversar F5.2 nadie lo produce pero F5.1 sigue válido y se reusa cuando F6.x arme sus propios bytes.

## Dependencies

- `Buffer` (built-in node + polyfill `buffer` package para jsdom)
- `Zod@^3.23.8` (ya en dependencies)
- Helpers `formatCOP` (de F2.x — bloqueador potencial; ver Risks)

## Success Criteria

- [ ] `escposBuilder.build('entrada', payload)` produce un `Buffer` con la secuencia exacta de 5 comandos (init/cut/center/bold/2x) verificable byte-a-byte en test.
- [ ] `fallbackBrowser.print(...)` inyecta un `<style>` con `@page { size: 80mm auto; margin: 2mm }` y llama `window.print()`.
- [ ] 4 tests end-to-end pasan (uno por tipo de tiquete), con cobertura ≥95% líneas / ≥85% branches en `src/lib/print/`.
- [ ] `npx vitest run src/lib/print` exit 0; `tsc -b` exit 0; `eslint src/lib/print --max-warnings 0` exit 0.
- [ ] Ningún caller de F5.2 importa desde `electron/`, `bridge`, ni toca USB.
