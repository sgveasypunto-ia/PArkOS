# Spec: facturacion-admin (NEW capability)

> **Capability**: `facturacion-admin` — vista de detalle de factura + acciones transaccionales en web-admin
> **Owner**: admin
> **Status**: ready for `sdd-design` + `sdd-tasks`
> **Source**: `openspec/changes/hu-x-facturacion-admin/{exploration,proposal}.md`
> **Precedentes en el repo**: `reporteria-financiera` (HU-F17.3, REQ-OPS-188..200), `dian-queue` (HU-F20.5), `cliente-facturas-tab` (HU-F20.1)

## Purpose

Permitir al admin de Parkos investigar el detalle completo de una factura
existente (header, cliente, líneas, impuestos, pagos, FE, hash chain) y
ejecutar 3 acciones transaccionales sin necesidad de escalar al operador
de la sucursal: **reimprimir**, **anular**, **crear reclamo**.

El ciclo de **creación** de facturas sigue siendo exclusivo del operador
en la sucursal (HU-F1.9 + F8.4 — el admin no crea facturas).

## Requirements

### REQ-X-01: Ruta `/facturacion/:uuid`

`App.tsx` debe declarar una ruta `/facturacion/:uuid` que monte
`<FacturaDetalle>` dentro del grupo global con auth (no requiere
`RequireSucursal` porque la factura misma tiene `uuid_sucursal` propio y
el tenant scope del JWT filtra correctamente).

**Given** un admin autenticado con permisos `emitir_factura` o `gestionar_facturas`
**And** un uuid válido en la URL
**When** navega a `/facturacion/{uuid}`
**Then** la página `<FacturaDetalle>` se monta con SWR fetching los 5 endpoints en paralelo.

**And** si la URL no matchea ningún recurso válido (404 desde el BE), la
página muestra un estado "Factura no encontrada" con un link de retorno a
`/reporteria/financiera`.

### REQ-X-02: Sección header (`FacturaHeaderCard`)

La página muestra un card con:

| Campo | Source | Obligatorio |
|---|---|---|
| `uuid` (truncado a 8 chars + copy-to-clipboard) | `GET /facturacion/facturas/{uuid}.uuid` | sí |
| `created_at` (formato local es-CO) | `GET /facturacion/facturas/{uuid}.created_at` | sí |
| `subtotal` (formato COP con separadores) | `GET /facturacion/facturas/{uuid}.subtotal` | sí |
| `descuento` (formato COP, "0" si null) | `GET /facturacion/facturas/{uuid}.descuento` | sí |
| `total` (formato COP, negrita) | `GET /facturacion/facturas/{uuid}.total` | sí |
| `estado` (badge) — derivado: `vigente` (green) o `anulada` (destructive) | derivado de `V_FACTURA_ESTADO` (vía query) o del campo `estado` si existe en el response | sí |
| `numero_completo` (prefijo + consecutivo FE) o "—" si no hay FE | `GET /facturacion/factura-electronica/{uuid}.prefijo+.consecutivo` | sí |
| `hash_actual` (mono font, copy-to-clipboard) | `GET /admin/log-transaccional?uuid_referencia={uuid}&limit=1` | sí |

### REQ-X-03: Sección cliente (`FacturaClienteCard`)

El card de cliente muestra:
- **Consumidor final** (cuando no hay cliente) — texto estático.
- O: `tipo_identificador` + `numero_identificacion` (+ `dv` si NIT) + `nombre` + `apellido` (link al detalle de cliente en `/clientes/:uuid` si el cliente existe).

**Source**: el `FacturaRead` enriquecida de la respuesta de `POST /facturacion/factura` trae `cliente` y `datos_sucursal` poblados. **Pero** el GET `/facturacion/facturas/{uuid}` (plural) sólo trae el row crudo. Por lo tanto, la sección de cliente se debe obtener de:
- Alternativa A: cambiar el shape de la respuesta del GET detail para que traiga los joins (BE work, fuera de X.1a).
- Alternativa B: hacer un segundo fetch al endpoint de reporteria `GET /admin/reporteria/facturas?uuid_sucursal=…&desde=…&hasta=…` (over-fetch, no práctico).
- **Alternativa C (recomendada)**: agregar un nuevo endpoint `GET /admin/facturacion/facturas/{uuid}/display` que devuelva el shape enriquecido F8.4 (header + cliente + sucursal + vehiculo + items + impuestos + pagos + FE). LOC: ~80 BE + tests. Trade-off: hay que escribir el handler, pero es el approach limpio.

**Decisión de scope**: X.1b NO incluye el endpoint display. En X.1b, la
sección de cliente muestra "Consumidor final" por default. Si en el
futuro se justifica (cuando se llame a drill-down desde un cliente con
facturas con datos), se abre un HU aparte para agregar el display endpoint.

### REQ-X-04: Sección items (`FacturaItemsTable`)

Tabla con columnas: `concepto` | `cantidad` | `valor_unitario` (COP) |
`subtotal` (COP). Una fila por item de `prod.factura_detalle`.

**Source**: `GET /facturacion/factura-detalle?uuid_factura={uuid}` filtrado por uuid.

### REQ-X-05: Sección impuestos (`FacturaImpuestosTable`)

Tabla con columnas: `nombre_impuesto` | `porcentaje_aplicado` (%) |
`base_calculo` (COP) | `valor` (COP). Una fila por impuesto aplicado.

**Source**: `GET /facturacion/factura-impuestos?uuid_factura={uuid}` (post-fix del factory si se extiende para soportar filtros, sino un endpoint dedicado). Si el factory ignora `?uuid_factura=`, X.1b lo documenta como "no implementable en este sprint" o X.1a lo fixea.

**Decisión de scope**: REQ-X-05 requiere el fix de X.1a (`factura-pagos`
+ `factura-impuestos` + `factura-detalle`). Si la fix de X.1a se extiende a
los 3, X.1b lo consume; si no, X.1b muestra "No implementado" para esos
casos y se abre un follow-up.

### REQ-X-06: Sección pagos (`FacturaPagosTable`)

Tabla con columnas: `timestamp_evento` | `medio_pago` (badge con color
por tipo: efectivo=neutral, tarjeta=info, datafono=info, transferencia=info,
mixto=warning) | `valor` (COP) | `referencia` (mono font, "—" si null) |
`tipo_movimiento` (badge: "pago" verde, "reverso" destructive).

**Source**: `GET /facturacion/factura-pagos?uuid_factura={uuid}` filtrado
por uuid. **Este endpoint tiene el bug de filter**: X.1a lo fixea.

### REQ-X-07: Sección FE (`FacturaElectronicaCard`)

Si `GET /facturacion/factura-electronica/{uuid}` retorna 200:

| Campo | Source |
|---|---|
| `prefijo` | del response |
| `consecutivo` | del response |
| `estado_dian` (badge con color: pendiente=warning, enviado=info, aceptado=success, rechazado=destructive) | del response |
| `cufe` (mono font, copy-to-clipboard, visible SOLO si `estado_dian='aceptado'`) | del response |
| Botón "Reintentar" (visible SOLO si `estado_dian='rechazado'`) | abre confirmación → POST `/facturacion/factura-electronica/{uuid}/reintentar` |

Si retorna 404 (`factura_electronica_no_encontrada`):
- Mostrar mensaje: "Esta factura no tiene factura electrónica generada."
- Si la factura original tenía `factura_electronica_pendiente=true` (campo del POST response — no expuesto en GET, X.1b no lo muestra), no se puede detectar; X.1b simplemente muestra el 404.

### REQ-X-08: Acciones (Reimprimir / Anular / Reclamo) en `FacturaAccionesMenu`

El menu muestra 3 botones (visibles solo si el rol del JWT es `admin-`):

1. **Reimprimir** → abre `ReimprimirFacturaDialog` (form: motivo ≥10 chars). Submit → `POST /api/v1/workflows/reimpresion-ticket` con `{uuid_factura, motivo}`. Response 201 → toast success + invalidate SWR cache.
2. **Anular** → abre `AnularFacturaDialog` (form: motivo ≥10 chars). Submit → `POST /api/v1/anulaciones` con `{tipo_anulable: 'factura', uuid_reclamable: uuid, motivo}`. Response 201 → toast + invalidate + redirect a `/anulaciones/:uuid` (el nuevo uuid de anulación).
3. **Crear Reclamo** → abre `ReclamoFacturaDialog` (form: motivo ≥10, descripción opcional ≥20). Submit → `POST /api/v1/workflows/reclamos` con `{tipo_reclamable: 'factura', uuid_reclamable: uuid, motivo, descripcion?}`. Response 201 → toast + redirect a `/reclamos/:uuid`.

**Defense in depth**: el server-side check de rol es la autoridad. El
client-side hide-if-not-admin es UX, no security.

### REQ-X-09: Drill-down desde listas

`FacturasTable.tsx` (en `features/reporteria/components/`) agrega en cada
fila un `<Link to={/facturacion/${row.uuid}}>` con icono `ExternalLink` o
un botón "Ver detalle" al final de la fila. Mismo para
`ClienteFacturasTab.tsx` en `features/clientes/components/`.

Click → navega a `/facturacion/:uuid`. La SPA usa el `uuid` del response
del reporteria (que es el `uuid` de la factura base, no el de FE).

### REQ-X-10: HomeHub card

`HomeHub.tsx` agrega una card `Facturación` con:
- Icono: `Receipt` de `lucide-react` (ya disponible).
- Título: `t('homeHub.cards.facturacion', 'Facturación')`.
- Descripción: `t('homeHub.cards.facturacionDesc', 'Reportes financieros, FE, pagos y drill-down de facturas.')`.
- Link: `/reporteria/financiera`.

Sigue el patrón existente parametrizado (H3 del exploration del HU-F15.2).

### REQ-X-11: Estado de carga y error por sección

`FacturaDetalle` no falla-globally si una sección falla. Cada componente
presentacional tiene su propio loading (skeleton) y error (alert inline).
El header es obligatorio (sin header, la página muestra error fatal).

Estados:
- Loading global (header aún no cargó): skeleton de la página completa.
- Header cargado, sección X cargando: skeleton inline en la sección X.
- Header cargado, sección X falló: alert inline en la sección X con
  `role="alert"`, `aria-live="assertive"`, y botón "Reintentar" que
  llama `mutate(swrKey)` local.

### REQ-X-12: i18n namespace `facturacionAdmin`

`apps/web_admin/src/i18n/locales/es-CO.json` agrega el namespace
`facturacionAdmin` con al menos estas keys (las acciones y los badges
agregan las suyas):

```
facturacionAdmin.header.title
facturacionAdmin.header.subtitle
facturacionAdmin.header.uuidLabel
facturacionAdmin.header.fechaLabel
facturacionAdmin.header.subtotalLabel
facturacionAdmin.header.descuentoLabel
facturacionAdmin.header.totalLabel
facturacionAdmin.header.estadoLabel
facturacionAdmin.header.estado.vigente
facturacionAdmin.header.estado.anulada
facturacionAdmin.header.numeroCompletoLabel
facturacionAdmin.header.hashLabel
facturacionAdmin.header.notFound
facturacionAdmin.header.notFoundBackLink
facturacionAdmin.cliente.title
facturacionAdmin.cliente.consumidorFinal
facturacionAdmin.items.title
facturacionAdmin.items.concepto
facturacionAdmin.items.cantidad
facturacionAdmin.items.valorUnitario
facturacionAdmin.items.subtotal
facturacionAdmin.impuestos.title
facturacionAdmin.impuestos.nombre
facturacionAdmin.impuestos.porcentaje
facturacionAdmin.impuestos.baseCalculo
facturacionAdmin.impuestos.valor
facturacionAdmin.pagos.title
facturacionAdmin.pagos.timestamp
facturacionAdmin.pagos.medioPago
facturacionAdmin.pagos.valor
facturacionAdmin.pagos.referencia
facturacionAdmin.pagos.tipoMovimiento
facturacionAdmin.fe.title
facturacionAdmin.fe.estado
facturacionAdmin.fe.cufe
facturacionAdmin.fe.reintentar
facturacionAdmin.fe.noGenerada
facturacionAdmin.acciones.reimprimir
facturacionAdmin.acciones.anular
facturacionAdmin.acciones.reclamo
facturacionAdmin.dialogs.motivoLabel
facturacionAdmin.dialogs.motivoPlaceholder
facturacionAdmin.dialogs.motivoMinLength
facturacionAdmin.dialogs.descripcionLabel
facturacionAdmin.dialogs.cancelar
facturacionAdmin.dialogs.confirmar
facturacionAdmin.errors.headerFail
facturacionAdmin.errors.retry
facturacionAdmin.errors.actionFail
facturacionAdmin.toasts.reimpresionExitosa
facturacionAdmin.toasts.anulacionExitosa
facturacionAdmin.toasts.reclamoExitoso
```

### REQ-X-13: WCAG 2.1 AA + axe-core

`FacturaDetalle.test.tsx` y cada componente presentacional pasan el gate
de `axe-core` con 0 violations:
- `<table>` semántico con `<caption>` + `scope="col"`.
- `role="status"` + `aria-live="polite"` para loaders.
- `role="alert"` + `aria-live="assertive"` para errores.
- Focus management en los dialogs (focus trap + return focus on close).
- Color nunca es el único medio (badges con texto + color).

## Cross-cutting requirements (XR)

### REQ-X-XR1: Caching e invalidación SWR

Después de cada action (reimprimir, anular, crear reclamo), el hook
correspondiente llama `mutate(<swrKey>)` para forzar refetch de la
sección afectada. Toast success con link al recurso creado (anulación,
reclamo, reimpresión).

### REQ-X-XR2: Idempotency-Key

`useReimprimirFactura`, `useAnularFactura`, `useCrearReclamoFactura`
generan un `Idempotency-Key` (UUID4 fresco) por cada submit para que un
doble-click no genere 2 reimpresiones / 2 anulaciones / 2 reclamos.
Backend ya respeta este header (PR2 idempotency keys).

### REQ-X-XR3: tenant scope post-load

`FacturaDetalle` valida en el cliente que `data.uuid_sucursal` esté en
`ctx.sucursales_permitidas`. Si no, muestra "No tiene permisos para ver
esta factura" + link de retorno. Defense in depth (el server también
filtra).

## Scenarios (Esc-…)

### Esc-X-01: Happy path FE-only
**Given** admin autenticado en web-admin
**And** la factura `d8c22ebb-…` existe en cloud con FE
**When** navega a `/facturacion/d8c22ebb-948e-4745-aaa1-52e0a698124a`
**Then** ve el header con uuid, fecha, total=5.000, estado=Vigente, numero_completo=null
**And** ve el card "Consumidor final"
**And** ve la tabla de items con 1 row (concepto, cantidad, valor, subtotal)
**And** ve la tabla de impuestos con 1 row (IVA 19% sobre 5.000, valor 950)
**And** ve la tabla de pagos (puede ser 0 o 1 row — el fix de X.1a)
**And** ve el card "FE no generada" (porque no hay FE row)

### Esc-X-02: Drill-down con FE generada (caso BOG-CEN+resolución)
**Given** una factura con FE generada y estado `aceptado`
**When** el admin navega al detalle
**Then** ve el card FE con prefijo + consecutivo + estado=aceptado + cufe visible
**And** NO ve el botón "Reintentar"

### Esc-X-03: Drill-down con FE rechazada
**Given** una factura con FE estado `rechazado`
**When** el admin navega al detalle
**Then** ve el card FE con estado=rechazado + botón "Reintentar" visible
**And** el botón está disabled mientras `isMutating` y abre confirmación al click
**And** el submit POSTea `/facturacion/factura-electronica/{uuid}/reintentar`
**And** el toast success muestra el nuevo `uuid_envio`

### Esc-X-04: Reimprimir
**Given** la sección de acciones es visible (rol=admin-)
**When** el admin clickea "Reimprimir" e ingresa motivo "Cliente solicita reimpresión para archivo"
**Then** el dialog valida motivo ≥10 chars (Zod schema)
**And** al confirmar, POSTea `/api/v1/workflows/reimpresion-ticket`
**And** recibe 201 con `uuid_reimpresion`
**And** el toast success muestra el uuid + link a `/reimpresiones/{uuid}` (futuro HU)
**And** SWR del header se invalida (no aplica a este caso — la reimpresión no cambia la factura)

### Esc-X-05: Anular
**Given** la factura está vigente
**When** el admin clickea "Anular" e ingresa motivo "Error de digitación — número de placa incorrecto"
**Then** el dialog valida motivo ≥10 chars
**And** al confirmar, POSTea `/api/v1/anulaciones` con `tipo_anulable='factura'`
**And** recibe 201 con `uuid_anulacion`
**And** redirige a `/anulaciones/{uuid_anulacion}`
**And** el SWR del header se invalida (el estado debe cambiar a "anulada" en el próximo fetch — derivado de V_FACTURA_ESTADO)

### Esc-X-06: Crear reclamo
**Given** la factura tiene un cliente (no consumidor final)
**When** el admin clickea "Crear reclamo" e ingresa motivo "Monto no coincide con lo cobrado en caja"
**And** descripción "El operador cobró $6.000 pero la factura dice $5.000"
**Then** el dialog valida motivo ≥10 + descripción ≥20
**And** al confirmar, POSTea `/api/v1/workflows/reclamos` con `tipo_reclamable='factura'`
**And** recibe 201 con `uuid_reclamo`
**And** redirige a `/reclamos/{uuid_reclamo}`

### Esc-X-07: Drill-down desde `/reporteria/financiera`
**Given** el admin está en `/reporteria/financiera` con branch BOG-CEN
**And** ve la tabla de facturas con la fila de `d8c22ebb-…`
**When** clickea el botón "Ver detalle" en la fila
**Then** navega a `/facturacion/d8c22ebb-…`
**And** la página monta con los 5 fetches en paralelo

### Esc-X-08: Drill-down desde `/clientes/:uuid`
**Given** el admin está en `/clientes/<uuid>` tab "Facturas"
**And** ve la tabla con la fila de `d8c22ebb-…`
**When** clickea el botón "Ver detalle" en la fila
**Then** navega a `/facturacion/d8c22ebb-…` (mismo destino que Esc-X-07)

### Esc-X-09: 404 (uuid no existe)
**When** el admin navega a `/facturacion/00000000-0000-0000-0000-000000000000`
**Then** el header fetch retorna 404
**And** la página muestra "Factura no encontrada" + link de retorno a `/reporteria/financiera`

### Esc-X-10: Tenant scope (operador cross-branch)
**Given** un operador con sucursales_permitidas=[BOG-CEN]
**When** intenta navegar a `/facturacion/<uuid_de_otra_sucursal>`
**Then** el header fetch retorna 404 (server filtra)
**And** la página muestra Esc-X-09

### Esc-X-11: Card HomeHub
**When** el admin está en `/`
**Then** ve la card "Facturación" (3ª o 4ª en el grid)
**And** clickearla navega a `/reporteria/financiera`

### Esc-X-12: Bug fix `?uuid_factura=` en `GET /facturacion/factura-pagos`
**Given** la factura `d8c22ebb-…` existe
**When** X.1a está aplicado
**And** el test RED+GREEN verifica:
- `?uuid_factura=d8c22ebb-…` → 200 con sólo pagos de esa factura
- `?uuid_factura=00000000-…` → 200 con 0 items (no existe)
- (sin params) → 200 con todos los pagos (comportamiento actual preservado)

### Esc-X-13: axe-core WCAG 2.1 AA
**Given** el dev server corriendo en :5173
**When** `axe-core` corre sobre `FacturaDetalle` y cada subcomponente
**Then** 0 violations de:
- color-contrast
- region (todos los landmarks)
- label (todos los form controls)
- button-name
- link-name
- image-alt
- list
- table (caption, scope)

## Capability cross-references

- REQ-X-02..07 (secciones) → consumen los endpoints BE que HU-F1.9
  (req-ops-053..063) y F1.10 (req-ops-064..074) ya implementaron.
- REQ-X-08 (acciones) → consumen los endpoints de HU-F8.3
  (reimpresion-ticket), Fase 6 (anulaciones) y Fase 8 (reclamos).
- REQ-X-09 (drill-down) → consume el campo `uuid` que ya retorna el
  endpoint `GET /admin/reporteria/facturas` (HU-F17.3).
- REQ-X-10 (HomeHub) → sigue el patrón parametrizado de HU-F15.2.

## Out of scope (explícitamente)

- **Endpoint display enriquecido** (alternativa C de REQ-X-03) — sección
  cliente queda como "Consumidor final" en MVP. Si en el futuro se
  necesita el cliente real desde el drill-down, abrir un HU aparte.
- **Realtime updates** vía WebSocket o SSE — la página es read-on-mount.
- **Generar PDF/impresión** desde web-admin — responsabilidad del
  operador con su impresora ESC/POS.
- **Hash chain verification UI** dentro del detalle — la vista
  `/auditoria/verify-chain` ya existe; el detalle sólo muestra el
  `hash_actual` como dato.
- **Listado standalone `/facturacion`** (X.8 del exploration) — el entry
  point es `/reporteria/financiera`. Follow-up.
- **Filtros adicionales en `GET /facturacion/factura-pagos`** (ej.
  `?uuid_sucursal=`, `?desde=`, `?hasta=`) — sólo `?uuid_factura=` se
  implementa en X.1a. Si se necesitan más, abrir HU aparte.
