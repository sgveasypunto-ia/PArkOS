# Spec delta: operations (HU-X admin actions on invoices)

> **Capability**: `operations` (delta)
> **Change**: `hu-x-facturacion-admin`
> **Date**: 2026-10-13
> **Status**: ready for `sdd-design` + `sdd-tasks`

This is a delta to `openspec/specs/operations/spec.md` adding admin-only
actions on existing `prod.facturas` rows. The pre-existing REQ-OPS-053..063
(HU-F1.9 operator flow) and REQ-OPS-064..074 (HU-F1.10 FE numbering) are
the foundation; this delta adds the admin surface that operates on the
rows they create.

## REQ-OPS-200 — Reimprimir factura desde web-admin

**Source**: HU-X (drill-down detail)  **Priority**: MEDIUM  **RFC 2119 keywords**: MUST

**Statement**:
`POST /api/v1/workflows/reimpresion-ticket` MUST accept admin-authenticated
calls (issuer `admin-` already permitted per F8.3) for a `uuid_factura`
that exists, with `motivo: str` ≥ 10 chars. The endpoint already exists
(F8.3) but was historically only consumed from the operator's
`electron-sucursal` UI. The web-admin drill-down (HU-X) consumes it from
a new dialog. No new endpoint, no contract change.

**Rationale**:
The re-impresión flow is the same regardless of caller (operator o
admin). The endpoint already validates the `uuid_factura` and the `motivo`.
The only new requirement is that the admin's web-ui can call it (issuer
permiso + UI dialog). This is purely a frontend wire-up.

**Source**: `backend/.../api/v1/workflows_reimpresion.py:84` (`POST /reimpresion-ticket`).

#### Scenario: admin reimprime una factura

- **Given** admin autenticado en web-admin
- **And** la factura `d8c22ebb-…` existe
- **And** `FacturaAccionesMenu` muestra el botón "Reimprimir" (rol=admin-)
- **When** el admin abre el dialog e ingresa `motivo="Cliente solicita reimpresión para archivo"`
- **And** hace click en "Confirmar"
- **Then** el FE genera un `Idempotency-Key: <uuid4>` fresco
- **And** POSTea `/api/v1/workflows/reimpresion-ticket` con `{uuid_factura: "d8c22ebb-…", motivo: "…", idempotency_key: "…"}`
- **And** recibe 201 con `{uuid_reimpresion, uuid_factura, motivo, timestamp_evento, …}`
- **And** el toast success muestra el `uuid_reimpresion` (8 chars) + link futuro a la bitácora
- **And** un `prod.reimpresion_ticket` row nuevo se inserta (append-only, sin UPDATE/DELETE)
- **And** un `prod.log_transaccional` row nuevo se inserta con `hash_actual` extendido (per F11.2 chain verifier)

#### Scenario: motivo corto → 422

- **When** el admin ingresa `motivo="corto"` (5 chars)
- **Then** el FE Zod schema rechaza (min_length=10)
- **And** el dialog muestra error inline sin POSTear al BE

## REQ-OPS-201 — Anular factura desde web-admin

**Source**: HU-X  **Priority**: HIGH  **RFC 2119 keywords**: MUST

**Statement**:
`POST /api/v1/anulaciones` MUST accept admin-authenticated calls for a
`uuid_reclamable` of type `factura` with `motivo: str` ≥ 10 chars. The
endpoint already exists (Fase 6) and the `tipo_anulable` discriminator
already includes `'factura'` as a valid value. The web-admin drill-down
consumes it from a new dialog. No new endpoint.

**Rationale**:
La anulación es workflow `[L-W]` con la misma semántica append-only
que la de ingresos/salidas (HU-F6). El admin debe poder anular
facturas erróneas sin tener que pedirle al operador que anule la salida
asociada. El estado derivado `V_FACTURA_ESTADO` will flip to
`'anulada'` automatically because the `anulaciones` row exists
(REQ-OPS-196 already in the spec).

**Source**: `backend/.../api/v1/workflows_anulaciones.py:132` (`POST /anulaciones`).

#### Scenario: admin anula una factura vigente

- **Given** admin autenticado, la factura `d8c22ebb-…` está vigente
- **When** el admin abre el dialog "Anular" e ingresa `motivo="Error de digitación — número de placa incorrecto"`
- **Then** el FE POSTea `/api/v1/anulaciones` con `{tipo_anulable: "factura", uuid_reclamable: "d8c22ebb-…", motivo: "…"}`
- **And** recibe 201 con `{uuid_anulacion, tipo_anulable, uuid_reclamable, estado: "solicitada", …}`
- **And** redirige a `/anulaciones/{uuid_anulacion}` (la página de detalle del workflow de anulación, que ya existe)
- **And** un `prod.anulaciones` row nuevo se inserta (tipo_anulable='factura')
- **And** un `prod.log_transaccional` row nuevo se inserta

**Note (importante)**: HU-F1.9 marca las facturas como **inmutables**
(`fn_facturas_inmutable` trigger, MIGRATION 0027). Por lo tanto, la
"anulación" NO modifica `prod.facturas` directamente. La anulación es
un evento append-only en `prod.anulaciones` y el estado derivado
`V_FACTURA_ESTADO` lo refleja automáticamente. Esto preserva la
convención AUDIT-FIRST y C/Q/U only.

#### Scenario: ya anulada → 409

- **Given** la factura `d8c22ebb-…` ya tiene una anulación
- **When** el admin intenta anular de nuevo
- **Then** el BE retorna 409 con `{"error": "ya_anulada", "uuid_anulacion_existente": "…"}`
- **And** el FE muestra el alert inline y NO redirige

## REQ-OPS-202 — Crear reclamo sobre factura desde web-admin

**Source**: HU-X  **Priority**: MEDIUM  **RFC 2119 keywords**: MUST

**Statement**:
`POST /api/v1/workflows/reclamos` MUST accept admin-authenticated calls
for a `uuid_reclamable` of type `factura` with `motivo: str` ≥ 10 chars
+ `descripcion: str` opcional ≥ 20 chars. The endpoint already exists
(Fase 8) and the `tipo_reclamable` discriminator includes `'factura'`.

**Source**: `backend/.../api/v1/workflows_reclamos.py:81` (`POST /reclamos`).

#### Scenario: admin crea un reclamo

- **When** el admin abre el dialog "Crear reclamo" e ingresa motivo + descripción
- **Then** el FE POSTea `/api/v1/workflows/reclamos` con `{tipo_reclamable: "factura", uuid_reclamable: "d8c22ebb-…", motivo: "…", descripcion: "…"}`
- **And** recibe 201 con `{uuid_reclamo, …}`
- **And** redirige a `/reclamos/{uuid_reclamo}`

## REQ-OPS-203 — Fix: `GET /facturacion/factura-pagos` debe filtrar por `?uuid_factura=…`

**Source**: HU-X.1a  **Priority**: HIGH (blocks REQ-X-06)  **RFC 2119 keywords**: MUST

**Statement**:
`GET /api/v1/facturacion/factura-pagos?uuid_factura=<uuid>` MUST return
ONLY the `prod.factura_pagos` rows whose `uuid_factura` matches the
supplied parameter. When the parameter is omitted, the endpoint returns
the same global paginated list as before (backward-compat).

**Bug confirmed**: el factory genérico `make_router` (`backend/
packages/parkos_core/src/parkos_core/api/router_factory.py:189-255`)
define `list_endpoint(cursor, limit, session, ctx, _claims)` SIN un
`Query('uuid_factura', ...)` param, por lo que FastAPI descarta
silenciosamente cualquier `?uuid_factura=…` enviado por el cliente.
Verificado con 3 curl en este turno: 7 items returned, los mismos 7 con
o sin filter, `?limit=2` sí filtra.

**Resolution**: reemplazar el factory para `factura-pagos` con un custom
handler en `api/v1/facturacion.py` que:
1. Copia la query del factory verbatim (`select(FacturaPagos).order_by(...)`).
2. Acepta `uuid_factura: uuid_lib.UUID | None = Query(None)` como param opcional.
3. Si presente, agrega `WHERE FacturaPagos.uuid_factura == :uuid_factura`.
4. Mantiene la paginación cursor-based idéntica al factory.
5. Mantiene el `repo_kind="versioned"` no, `repo_kind="append_only"` (la tabla es [A], no tiene `vigente_hasta`).

**Out of scope (explícito)**: NO se extienden los demás endpoints
`factura-detalle`, `factura-impuestos`, `factura-otros-cobros` con el
mismo filter en este change. Si se necesitan, se abre un follow-up.
La página de detalle HU-X sólo depende de `factura-pagos` filtrado.

**Source**: `backend/.../api/v1/facturacion.py:170-177` (mount del factory para `factura-pagos`).

#### Scenario: filter funciona

- **Given** la factura `d8c22ebb-…` existe con N pagos
- **When** `GET /api/v1/facturacion/factura-pagos?uuid_factura=d8c22ebb-…`
- **Then** retorna 200 con `{items: [<solo los N pagos de esta factura>], next_cursor: ...}`

#### Scenario: filter vacío

- **When** `GET /api/v1/facturacion/factura-pagos?uuid_factura=00000000-0000-0000-0000-000000000000`
- **Then** retorna 200 con `{items: [], next_cursor: null}`

#### Scenario: sin filter (backward-compat)

- **When** `GET /api/v1/facturacion/factura-pagos`
- **Then** retorna 200 con la lista global paginada (mismo comportamiento que antes del fix)

#### Scenario: limit + filter combinados

- **When** `GET /api/v1/facturacion/factura-pagos?uuid_factura=…&limit=2&cursor=…`
- **Then** el filter se aplica ANTES de la paginación (sólo cuenta los rows que matchean)

## REQ-OPS-204 — Drill-down page `/facturacion/:uuid` en web-admin

**Source**: HU-X  **Priority**: HIGH  **RFC 2119 keywords**: MUST

**Statement**:
`apps/web_admin/src/App.tsx` MUST declarar `<Route path="/facturacion/:uuid"
element={<FacturaDetalle />}>` en el grupo global (no requiere
`RequireSucursal`, mismo patrón que `/dian/:uuid`, `/reclamos/:uuid`).

`<FacturaDetalle>` MUST fetch los 5 endpoints en paralelo via SWR:
- `GET /api/v1/facturacion/facturas/{uuid}` (header)
- `GET /api/v1/facturacion/factura-detalle?uuid_factura={uuid}` (líneas)
- `GET /api/v1/facturacion/factura-impuestos?uuid_factura={uuid}` (impuestos)
- `GET /api/v1/facturacion/factura-pagos?uuid_factura={uuid}` (pagos)
- `GET /api/v1/facturacion/factura-electronica/{feUuid}` (FE, opcional)

**Source**: `apps/web_admin/src/features/facturacion/pages/FacturaDetalle.tsx` (NEW), `apps/web_admin/src/App.tsx:38-39` (patrón de `/dian/:uuid`).

#### Scenario: 5 fetches en paralelo, errores independientes

- **When** el admin navega a `/facturacion/d8c22ebb-…`
- **Then** los 5 fetches inician en paralelo
- **And** si el endpoint de FE retorna 404, el resto de las secciones siguen visibles
- **And** el card FE muestra "Esta factura no tiene FE generada"

#### Scenario: tenant scope cross-branch

- **When** un admin con `sucursales_permitidas=[BOG-CEN]` intenta ver una factura de otra sucursal
- **Then** el header fetch retorna 404 (server filtra)
- **And** la página muestra "Factura no encontrada" + link de retorno a `/reporteria/financiera`

## REQ-OPS-205 — Drill-down links desde `FacturasTable` y `ClienteFacturasTab`

**Source**: HU-X  **Priority**: HIGH  **RFC 2119 keywords**: MUST

**Statement**:
- `apps/web_admin/src/features/reporteria/components/FacturasTable.tsx` MUST
  agregar en cada fila un `<Link to={/facturacion/${row.uuid}}>` o un
  botón "Ver detalle" con `useNavigate`.
- `apps/web_admin/src/features/clientes/components/ClienteFacturasTab.tsx`
  MUST agregar el mismo link en cada fila.

Click → navega a `/facturacion/{uuid}`. La SPA usa el `uuid` del row (no
el de FE).

**Source**: `apps/web_admin/src/features/reporteria/components/FacturasTable.tsx` (modificado); `apps/web_admin/src/features/clientes/components/ClienteFacturasTab.tsx` (modificado).

#### Scenario: click en fila navega al detalle

- **Given** el admin está en `/reporteria/financiera` con la tabla de facturas poblada
- **When** clickea "Ver detalle" en la fila de `d8c22ebb-…`
- **Then** navega a `/facturacion/d8c22ebb-948e-4745-aaa1-52e0a698124a`
- **And** la página de detalle monta con los 5 fetches

## REQ-OPS-206 — HomeHub card "Facturación"

**Source**: HU-X  **Priority**: LOW  **RFC 2119 keywords**: MUST

**Statement**:
`apps/web_admin/src/pages/HomeHub.tsx` MUST agregar una card
"Facturación" con icono `Receipt` (de `lucide-react`) + link a
`/reporteria/financiera`. Sigue el patrón parametrizado del
`H3` de HU-F15.2 (agregar card sin tocar el render del grid).

**Source**: `apps/web_admin/src/pages/HomeHub.tsx:34-51` (H2 → 3 cards, ahora 4).

#### Scenario: card visible en HomeHub

- **When** el admin está en `/`
- **Then** ve la card "Facturación" en el grid
- **And** clickearla navega a `/reporteria/financiera`

## Cross-cutting (XR)

### REQ-OPS-XR1 — Defense in depth: server-side check es autoridad

El client-side hide de los botones (cuando el rol NO es `admin-`) es UX,
no security. La autoridad es el server-side check del issuer prefix en
cada endpoint. Si el cliente bypassea el hide, el server retorna 403
igualmente. Cita: AGENTS.md "KD-3 issuer chain".

### REQ-OPS-XR2 — Idempotency-Key en cada action

`useReimprimirFactura`, `useAnularFactura`, `useCrearReclamoFactura` MUST
generar un `Idempotency-Key: <uuid4>` fresco por cada submit. Backend
ya respeta el header (PR2 `IdempotencyKeyMiddleware`).

### REQ-OPS-XR3 — No DELETE físico

Las 3 actions son append-only:
- Reimprimir → INSERT en `prod.reimpresion_ticket`.
- Anular → INSERT en `prod.anulaciones` (con `tipo_anulable='factura'`).
- Crear reclamo → INSERT en `prod.reclamos` (con `tipo_reclamable='factura'`).

Ninguna modifica `prod.facturas` directamente (DEC-FACT-01 + trigger
`fn_facturas_inmutable` MIGRATION 0027).

## Validation matrix

| Layer | Validator | Threshold |
|---|---|---|
| BE unit + integration | `pytest backend/tests` with testcontainers | REQ-OPS-203: 4 new RED+GREEN tests; total 14 new scenarios green; coverage ≥80% on `api/v1/facturacion.py` for the custom handler |
| BE lint | `ruff check` + `mypy --strict` | 0 errors on touched files |
| FE unit (X) | `pnpm --filter @apps/web_admin vitest run` | 12 new scenarios for `FacturaDetalle.test.tsx` + 4 for `facturacionAdminApi.test.ts` + 1 for `FacturaAccionesMenu.test.tsx` |
| FE types + lint | `tsc --noEmit` + `eslint` | 0 errors |
| a11y | `@axe-core/playwright` on `FacturaDetalle` | 0 WCAG 2.1 AA violations |
| schema drift | `python openspec/scripts/check_schema_match.py` | exits `0`; no migration (no schema change) |

## Risk acknowledgements

- **R-X-1** — El fix del factory `factura-pagos` puede romper consumers
  que ya esperan el comportamiento roto. Auditamos:
  `grep -r "factura-pagos?" apps/` → 0 matches. La única consumer es
  HU-X.1a (no escrita aún). Riesgo bajo.
- **R-X-2** — El custom handler debe mantener la firma del response
  shape `{items, next_cursor}` idéntica al factory. Si cambia, los
  consumers que esperan ese shape fallan. Mitigación: tests
  integration que comparan shape con un snapshot del factory.
- **R-X-3** — Las actions (anular/reclamo) tienen semántica append-only
  que puede confundir al admin ("¿por qué la factura sigue vigente
  después de anular?"). Mitigación: el card de estado muestra
  "Anulada — solicitud {uuid}" en lugar de "Vigente" cuando hay
  `anulaciones` row asociada. El V_FACTURA_ESTADO view se evalúa
  client-side.
- **R-X-4** — Sandbox F.6 limitation: Playwright contra Electron
  no es posible; los e2e de los dialogs de actions son vitest unit
  con mocks del hook. Mismo patrón que F8.3.

## Out of scope (delta explícito)

- NO se crea un endpoint display enriquecido (alternativa C de REQ-X-03
  del spec de facturacion-admin). El cliente en MVP se muestra como
  "Consumidor final".
- NO se modifica el shape de la respuesta de `POST /facturacion/factura`
  (la fuente canónica enriquecida F8.4).
- NO se extiende el filter `?uuid_factura=…` a los otros 3 endpoints
  (`factura-detalle`, `factura-impuestos`, `factura-otros-cobros`).
- NO listado standalone `/facturacion` (X.8 del exploration) — sigue
  siendo follow-up.
- NO se modifican los endpoints existentes de reimpresión/anulación/
  reclamo. Sólo se agregan nuevos consumers en el FE.
