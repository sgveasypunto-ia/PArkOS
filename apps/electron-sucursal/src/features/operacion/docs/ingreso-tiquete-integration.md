# F6.2 — Tiquete de entrada: Integration Contract

> **Audience**: F6.1 implementer (`feature/hu-f6-1-flujo-ingreso`).
> **Status**: Documentation only — no F6.1 code change ships in F6.2.
> **Contract binding**: `tiquetePrint.imprimirTiquete('entrada', payload)` (ESC/POS por `bridge.imprimir({ buffer })` o HTML + `window.print`).
>
> **Formato vigente (80 mm)**: todos los tickets de la app (ingreso, reimpresion, salida, salida con mensualidad, recibo de pago, arqueo parcial, factura y cierres) comparten una sola base (`lib/print/ticketBase.ts`): rollo termico de 80 mm, area imprimible de 72 mm / 576 dots, 48 columnas Font A, logo easypunto en encabezado y pie, **sin QR**. El tiquete se construye como lista de lineas (`lib/print/tiqueteLineas.ts`) y la misma lista alimenta ESC/POS (`escposBuilder.build`) y HTML (`fallbackBrowser.renderTiqueteHtml`). Las secciones 3 y 4 de este documento describian el diseno anterior (logo del cache `documentos` y QR) y quedan solo como historia.

## 1. Call chain (F6.1 Principal.tsx → F6.2 → F5.1)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ F6.1 — Principal.tsx onSuccess after POST /operacion/ingresos                │
│                                                                              │
│   1. Promise.all([                                                          │
│        fetchLogo(uuid_sucursal),          // from `parkos.documents.v1`     │
│        fetchCertificado(uuid_sucursal),   // from `parkos.documents.v1`     │
│      ])                                                                       │
│                                                                              │
│   2. payload = buildEntradaPayload({                                       │
│        ingreso:  POST.ingreso,             // uuid, placa, fecha_ingreso,   │
│                                           // uuid_subscripcion_cliente      │
│        sucursal: <cached>,                 // horario_atencion              │
│        empresa:  <cached>,                 // nombre, nit, direccion, regimen│
│        operario: authStore.uuid_usuario,                                   │
│        tipoVehiculo: 'auto' | 'moto',                                      │
│        tarifa: <cached>,                   // valor_hora_cents              │
│        documentos: [logo, certificado],                                     │
│        fechaHora: new Date().toISOString(),                                │
│      })                                                                       │
│                                                                              │
│   3. imprimirTiquete('entrada', payload, { ticketId })                      │
│      → Electron: escposBuilder.build(...) + logo raster → base64           │
│        → bridge.imprimir({ buffer, ticketId, cut })                        │
│      → navegador: fallbackBrowser.renderTiqueteHtml(...) → window.print()  │
│      → fallo: aviso visible con reintento (avisoImpresion.ejecutarImpresion)│
└──────────────────────────────────────────────────────────────────────────────┘
```

## 2. A-05 backend hook (documented, NOT implemented by F6.2)

Per `plan.md` lines 446-462 and the F6.2 spec section "A-05 hook MUST be
the backend concern (F6.2 documents, does not implement)", the backend
MUST INSERT into `prod.log_transaccional` after `bridge.imprimir`
resolves. The row payload shape:

```json
{
  "tabla_afectada": "ingreso",
  "uuid_registro_afectado": "<ingreso.uuid>",
  "accion": "impreso",
  "datos_nuevos": {
    "estado": "impresa"
  }
}
```

When `bridge.imprimir` returns `{ok: false, error: 'printer_offline' | 'printer_disconnected'}` and the caller falls back to `fallbackBrowser.print(...)`:

```json
{
  "tabla_afectada": "ingreso",
  "uuid_registro_afectado": "<ingreso.uuid>",
  "accion": "impreso",
  "datos_nuevos": {
    "estado": "pendiente de impresión"
  }
}
```

Retention 5+ años inherits from `log_transaccional.fecha_retencion_hasta`
per `modelo_datos_er.mmd` lines 386-404. The SHA256 hash chain
(`hash_anterior` / `hash_actual`) continues unbroken.

**Backend endpoint is a separate HU** — F6.2 ships the row payload
shape contract only. The operator UI shows a transient banner until
the endpoint lands.

## 3. `electron-store` documents cache contract (historico)

El tiquete ya no imprime el logo del cache `documentos`: la marca es el logo easypunto
(`lib/print/marcaTicket.ts`), en encabezado y pie. `documentos` solo alimenta la
`polizaRC` (tipo `certificado`) cuando el llamador usa `buildEntradaPayload()`.

## 4. QR (retirado)

El tiquete de entrada no lleva QR y el payload ya no tiene `qrDataUrl` ni `logoDataUrl`.
Antecedentes (verificados con `rg` sobre `apps/` y `backend/`): el QR nunca se leia en
ninguna parte (no hay escaner, ni busqueda por folio a partir de un QR, ni dependencia
`qrcode`); en produccion `printBuilder` pasaba `qrDataUrl: ''`, asi que ESC/POS imprimia una
linea literal `;QR:` y el HTML una `<img alt="QR ingreso">` vacia. La salida se identifica
por placa / consecutivo / folio.

## 5. Mensualidad handling

`buildEntradaPayload()` derives `esMensualidad` from
`ingreso.uuid_subscripcion_cliente IS NOT NULL` (DEC-SUC-21 — `tipo_entrada`
MUST NOT be persisted as a column on `ingreso`). The builder emits a
bold `Tipo: MENSUALIDAD` / `Tipo: ROTACIÓN` line under the sello (siempre explicita).

**Caller side**: no action required. The factory handles the boolean
transparently.

## 6. DEC-SUC-21 enforcement

The tiquete de entrada MUST NOT carry a `tipo_entrada` column on the
`ingreso` row. The Mensualidad tag is a presentation concern derived
at render time from the existing `uuid_subscripcion_cliente` foreign
key. If producto later wants `tipo_entrada` persisted, that's a
separate ER migration (`modelo_datos_er.mmd` change) and NOT F6.2 scope.

## 7. Error surface (F6.2 Error Catalog)

| Code | Class | Caller action |
|------|-------|--------------|
| `escpos_payload_missing_field` | `EscposPayloadMissingFieldError` | Bubble to operator UI; surface the field path from `error.issues` |
| `escpos_invalid_tipo` | `EscposInvalidTipoError` | Bubble to caller; F6.2 inherits from F5.2 |
| `bridge_imprimir_failure` | Typed result `{ok:false, error:'printer_offline' \| 'printer_disconnected' \| 'invalid_payload', queueId?}` | `imprimirTiquete` devuelve `{ ok: false }` y `ejecutarImpresion` muestra el aviso con reintento |

## 8. Out of scope (F6.2)

- Backend `log_transaccional` INSERT endpoint — separate HU.
- Auto-discovery of `documents` cache — future enhancement (F6.x sync catalog).
- CU-15S (salida) / CU-15SM (salida-mensualidad) — F7.x per plan.
- PDF generation, email/SMS delivery — Fase 21+ scope.

## 9. Files referenced

| File | Role |
|------|------|
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | `EntradaPayload`, `TiqueteEntradaCampos`, `buildEntradaPayload()` |
| `apps/electron-sucursal/src/lib/print/tiqueteLineas.ts` | `construirEntrada(payload)` → lineas 80 mm (fuente unica de ESC/POS y HTML) |
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | `build('entrada', payload, marca?)` → Buffer (validacion Zod + ESC/POS 80 mm) |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` | `renderTiqueteHtml` / `print('entrada', payload)` → HTML 80 mm + window.print() |
| `apps/electron-sucursal/src/lib/print/tiquetePrint.ts` | `imprimirTiquete(tipo, payload, { ticketId })`: ruta unica por canal |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | `tiquete_entrada_titulo`, `ingreso_registrado_exitoso`, `ingreso_observaciones_forzado` |
