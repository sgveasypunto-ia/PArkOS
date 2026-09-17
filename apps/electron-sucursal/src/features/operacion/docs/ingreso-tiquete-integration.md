# F6.2 — Tiquete de entrada: Integration Contract

> **Audience**: F6.1 implementer (`feature/hu-f6-1-flujo-ingreso`).
> **Status**: Documentation only — no F6.1 code change ships in F6.2.
> **Contract binding**: `escposBuilder.build('entrada', payload)` + `bridge.imprimir({ buffer })`.

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
│   3. buffer = escposBuilder.build('entrada', payload)                       │
│      → returns Buffer (DEC-SUC-08 byte stream)                             │
│                                                                              │
│   4. await bridge.imprimir({                                                │
│        buffer: buffer.toString('base64'),                                  │
│        timeoutMs: 500,                                                       │
│      })                                                                       │
│      → ok:true   → A-05 hook (backend concern, F6.2 documents payload)    │
│      → ok:false  → fallbackBrowser.print('entrada', payload)               │
│                  → DOM injection + window.print() (one shot)                │
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

## 3. `electron-store` documents cache contract

Per `design.md` §"A-01 integration: fetch `documentos` for logo + póliza
RC" and the spec scenario "Logo + Póliza RC MUST come from `documentos`":

| Field | Value |
|-------|-------|
| Cache key | `parkos.documents.v1` |
| TTL | 24 h |
| Refresh trigger | TTL expiry OR cache miss |
| Source | `GET /documentos?uuid_sucursal={X}&tipo=logo` and `tipo=certificado` |
| Strategy | `Promise.all([logo, certificado])` on cold cache; sequential reads NOT required |
| Failure mode | Empty array → `logoDataUrl = ''` → builder renders `▢` placeholder (DEC-SUC-08) |

The builder is PURE (F5.2 R4). It NEVER hits the `documentos` ER or
the cache. The caller (F6.1) is responsible for hydration.

## 4. ABIERTO-01 QR content

Default content (per ABIERTO-01): `parkos://ingreso/<ingreso.uuid>?placa=<ingreso.placa>`.

The QR rasterizer is the CALLER's responsibility — production callers
use a `qrcode` library to produce `data:image/png;base64,...`. The
builder accepts the resulting data-URL string verbatim.

`buildEntradaPayload()` ships a deterministic base64 sentinel for unit
tests; production callers MUST overwrite the `qrDataUrl` value before
calling `escposBuilder.build('entrada', payload)`.

## 5. Mensualidad handling

`buildEntradaPayload()` derives `esMensualidad` from
`ingreso.uuid_subscripcion_cliente IS NOT NULL` (DEC-SUC-21 — `tipo_entrada`
MUST NOT be persisted as a column on `ingreso`). The builder emits a
bold `MENSUALIDAD` tag under the sello when `esMensualidad === true`.

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
| `bridge_imprimir_failure` | Typed result `{ok:false, error:'printer_offline' \| 'printer_disconnected' \| 'invalid_payload', queueId?}` | Fallback to `fallbackBrowser.print('entrada', payload)`; UI shows transient banner |

## 8. Out of scope (F6.2)

- Backend `log_transaccional` INSERT endpoint — separate HU.
- Auto-discovery of `documents` cache — future enhancement (F6.x sync catalog).
- CU-15S (salida) / CU-15SM (salida-mensualidad) — F7.x per plan.
- PDF generation, email/SMS delivery — Fase 21+ scope.

## 9. Files referenced

| File | Role |
|------|------|
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | `EntradaPayload`, `TiqueteEntradaCampos`, `buildEntradaPayload()` |
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | `build('entrada', payload)` → Buffer |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` | `print('entrada', payload)` → DOM + window.print() |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | `tiquete_entrada_titulo`, `ingreso_registrado_exitoso`, `ingreso_observaciones_forzado` |
