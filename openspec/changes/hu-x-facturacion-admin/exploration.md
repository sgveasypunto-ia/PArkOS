# Exploration: hu-x-facturacion-admin

> **Change**: `hu-x-facturacion-admin`
> **Phase**: explore (sdd-explore)
> **Status**: ready for `sdd-propose` + `sdd-spec` + `sdd-design` + `sdd-tasks`
> **Branch**: dev (HEAD `2bd9856e`) — clean
> **Date**: 2026-10-13

## Why

Sesión de Q&A con el operador (2026-10-13 00:00–01:00 UTC) sobre la superficie de
facturación en ambos frontends. Resultado:

1. **web-sucursal (`apps/electron-sucursal`)** tiene un módulo `facturacion/`
   completo y operativo (cobro de salida, FE, reimpresión, anulación de
   reimpresión, factura de servicio suelto). Cubre el ciclo de vida del
   operador sin necesidad de UI admin.
2. **web-admin (`apps/web_admin`)** tiene la superficie de facturas
   **dispersa** entre features, sin una página de drill-down dedicada:
   - `reporteria/financiera` (HU-F17.3) lista facturas, FE y pagos en 3 tabs.
   - `clientes/:uuid` muestra un tab "Facturas" (`ClienteFacturasTab`,
     HU-F20.1) filtrado por cliente (cross-branch).
   - `dian` (HU-F20.5) lista la cola de envíos FE.
   - `parametrizacion/sucursales/:uuid` configura resoluciones DIAN.
   - `dashboard` muestra KPIs de facturas.
   - `auditoria/log` registra `crear_factura`.
   - `workflows/reclamos` admite `tipo_reclamable='factura'`.

   **Falta**: una página de detalle (`/facturacion/:uuid`) que consolide
   header, cliente, líneas, impuestos, pagos, FE, hash chain, y permita
   acciones (reimprimir, anular, crear reclamo).

3. **Bug colateral**: `GET /api/v1/facturacion/factura-pagos?uuid_factura=…`
   **ignora** el query param. El factory genérico `make_router` (`backend/
   packages/parkos_core/src/parkos_core/api/router_factory.py:189-255`)
   define `list_endpoint(cursor, limit, ...)` sin un `Query` para
   `uuid_factura`, así que FastAPI lo descarta silenciosamente. Verificado
   con `curl`:

   | Filtro | HTTP | items | Observación |
   |---|---|---|---|
   | (sin params) | 200 | 7 | los 7 pagos históricos de otras facturas |
   | `?uuid_factura=d8c22ebb-…` | 200 | 7 | **mismos 7 items** — filter ignorado |
   | `?uuid_factura=00000000-…` | 200 | 7 | **mismos 7 items** — filter ignorado |
   | `?limit=2` | 200 | 2 | limit SÍ funciona |

   La página de detalle que vamos a construir llama a este endpoint, así
   que el bug hay que arreglarlo en el mismo PR (sino, la página mostraría
   los pagos de la factura equivocada).

4. **El BE del drill-down ya existe**. Verificado con `curl` (todos 200):
   - `GET /api/v1/facturacion/facturas/{uuid}` (plural) — header
   - `GET /api/v1/facturacion/factura-detalle?uuid_factura=…` — líneas
   - `GET /api/v1/facturacion/factura-impuestos?uuid_factura=…` — IVA
   - `GET /api/v1/facturacion/factura-pagos?uuid_factura=…` — pagos (con el bug)
   - `GET /api/v1/facturacion/factura-electronica/{uuid}` — FE detail

   La nota en mi plan inicial ("el BE no tiene drill-down") fue incorrecta:
   confundí el singular `POST /facturacion/factura` con la hipotética
   `GET /facturacion/factura/{uuid}`. La ruta correcta es **plural**:
   `/facturacion/facturas/{uuid}`. El error fue de grep, no del BE.

5. **No hay una página de creación en web-admin**, y no la necesitamos:
   la creación de facturas es trabajo del operador en la sucursal (HU-F1.9
   + F8.4). El admin sólo necesita **leer y actuar** sobre facturas
   existentes.

## Visual verification (chrome-devtools, este turno)

Pantallazos en `evidence/`:

- `01_homehub.png`: HomeHub post-login admin. KPI "TOP SUCURSAL (30 DÍAS):
  BOG-CEN — $88.190" incluye el monto de la factura creada en este turno
  (`5.000 + 950 IVA` en la FE más el acumulado histórico).
- `02_reporteria_facturas.png`: `/reporteria/financiera` con branch BOG-CEN
  + rango 2026-10-01..2026-10-13 → tab **Facturas** muestra la fila
  `— | 2026-10-12 19:27:57 | 5.000 | 0 | 950 | 5.000 | Vigente` (la factura
  creada). **Número vacío** porque BOG-CEN no tiene resolución DIAN activa
  (`factura_electronica=null`, `factura_electronica_pendiente=true`).
- `03_drill_down_gap.png`: navegación directa a
  `/facturacion/d8c22ebb-948e-4745-aaa1-52e0a698124a` → **redirect a `/`**
  (HomeHub). El catch-all `*` routea a Home porque no hay ruta
  `/facturacion/:uuid` en `App.tsx`. **Gap visual confirmado**.
- `04_dian_queue.png`: `/dian` con branch BOG-CEN → cola vacía (no hay FE
  dispatched porque la resolución no existe).
- `05_audit_factura.png`: `/auditoria/log?tabla_afectada=factura` →
  aparece la entrada `crear facturas` con hash chain.

## What exists (no se reimplementa)

| Pieza | Ubicación | Reutilizable |
|---|---|---|
| Endpoint detalle header | `backend/.../api/v1/facturacion.py` (factory → `GET /factura-pagos/{uuid}`) | sí, vía `getFacturaByUuid(uuid)` |
| Endpoint detalle líneas | factory `GET /factura-detalle?uuid_factura=…` | sí, vía `getFacturaDetalle(uuidFactura)` |
| Endpoint detalle impuestos | factory `GET /factura-impuestos?uuid_factura=…` | sí, vía `getFacturaImpuestos(uuidFactura)` |
| Endpoint detalle pagos (con bug) | factory `GET /factura-pagos?uuid_factura=…` | sí, post-fix |
| Endpoint detalle FE | `GET /factura-electronica/{uuid}` (custom) | sí, vía `getFacturaElectronica(uuid)` |
| Reimprimir | `POST /api/v1/workflows/reimpresion-ticket` (existe, F8.3) | sí |
| Anular | `POST /api/v1/workflows/anulaciones` con `tipo_anulable='factura'` (existe) | sí |
| Crear reclamo | `POST /api/v1/workflows/reclamos` con `tipo_reclamable='factura'` (existe) | sí |
| Componentes shadcn | `apps/web_admin/src/components/ui/` (Card, Badge, Tabs, Dialog, Button, Table) | sí, ya usados en `clientes/`, `reporteria/` |
| Hooks SWR | `apps/web_admin/src/lib/` (`useApi`, `fetchJson`) | sí |
| Zod schemas pattern | `reporteria/api/reporteriaSchema.ts`, `dian/api/envioDianSchema.ts` | sí, mismo patrón |
| i18n namespace | `apps/web_admin/src/i18n/locales/es-CO.json` | agregar `facturacionAdmin` |
| Container-presentational | `ReporteriaFinanciera.tsx` + `FacturasTable.tsx` | replicar mismo split |

## What is missing (alcance de este change)

| Pieza | Diseño |
|---|---|
| Ruta `/facturacion/:uuid` en `App.tsx` (grupo global, mismo patrón que `/dian/:uuid`, `/reclamos/:uuid`) | ~10 LOC |
| Página `FacturaDetalle.tsx` (container) | ~150 LOC |
| Componentes presentacionales: `FacturaHeaderCard`, `FacturaClienteCard`, `FacturaItemsTable`, `FacturaImpuestosTable`, `FacturaPagosTable`, `FacturaElectronicaCard`, `FacturaAccionesMenu`, `ReimprimirFacturaDialog`, `AnularFacturaDialog`, `ReclamoFacturaDialog` | ~400 LOC |
| API client: `facturacionAdminApi.ts` + `facturacionAdminSchema.ts` (Zod mirror) | ~120 LOC |
| Hooks SWR: `useFacturaDetalle.ts` con fetch paralelo + cache invalidation | ~60 LOC |
| Botón "Ver detalle" en `FacturasTable.tsx` (`reporteria/`) | ~20 LOC |
| Botón "Ver detalle" en `ClienteFacturasTab.tsx` (`clientes/`) | ~20 LOC |
| Card en `HomeHub.tsx` con icono `Receipt` → link a `/reporteria/financiera` | ~30 LOC |
| Namespace i18n `facturacionAdmin` en `es-CO.json` | ~30 keys |
| Tests: `FacturaDetalle.test.tsx` (~12 casos), `facturacionAdminApi.test.ts`, axe-core | ~600 LOC |
| **Fix BE**: `GET /facturacion/factura-pagos` debe aceptar `?uuid_factura=…` y filtrar | ~30 LOC + 2 tests |

## Files to touch

### Nuevos
- `apps/web_admin/src/features/facturacion/api/facturacionAdminApi.ts` — wrapper SWR.
- `apps/web_admin/src/features/facturacion/api/facturacionAdminSchema.ts` — Zod mirrors.
- `apps/web_admin/src/features/facturacion/hooks/useFacturaDetalle.ts` — fetch paralelo.
- `apps/web_admin/src/features/facturacion/pages/FacturaDetalle.tsx` — container.
- `apps/web_admin/src/features/facturacion/components/FacturaHeaderCard.tsx`
- `apps/web_admin/src/features/facturacion/components/FacturaClienteCard.tsx`
- `apps/web_admin/src/features/facturacion/components/FacturaItemsTable.tsx`
- `apps/web_admin/src/features/facturacion/components/FacturaImpuestosTable.tsx`
- `apps/web_admin/src/features/facturacion/components/FacturaPagosTable.tsx`
- `apps/web_admin/src/features/facturacion/components/FacturaElectronicaCard.tsx`
- `apps/web_admin/src/features/facturacion/components/FacturaAccionesMenu.tsx`
- `apps/web_admin/src/features/facturacion/components/ReimprimirFacturaDialog.tsx`
- `apps/web_admin/src/features/facturacion/components/AnularFacturaDialog.tsx`
- `apps/web_admin/src/features/facturacion/components/ReclamoFacturaDialog.tsx`
- `apps/web_admin/src/features/facturacion/components/FacturaEstadoBadge.tsx`
- `apps/web_admin/src/features/facturacion/__tests__/FacturaDetalle.test.tsx`
- `apps/web_admin/src/features/facturacion/__tests__/facturacionAdminApi.test.ts`
- `apps/web_admin/src/features/facturacion/__tests__/FacturaAccionesMenu.test.tsx`
- `openspec/changes/hu-x-facturacion-admin/evidence/*.png` (5)

### Modificados
- `apps/web_admin/src/App.tsx` — agregar `<Route path="/facturacion/:uuid">`.
- `apps/web_admin/src/features/reporteria/components/FacturasTable.tsx` — botón "Ver detalle" / link en fila.
- `apps/web_admin/src/features/clientes/components/ClienteFacturasTab.tsx` — idem.
- `apps/web_admin/src/pages/HomeHub.tsx` — card "Facturación" con icono `Receipt`.
- `apps/web_admin/src/i18n/locales/es-CO.json` — namespace `facturacionAdmin`.
- `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` — custom handler para `GET /facturacion/factura-pagos` que filtra por `?uuid_factura=…` (reemplaza el factory solo para este caso).

## Out of scope (explícitamente)

- Crear facturas desde web-admin (el operador las crea en la sucursal).
- Modificar la FE en web-sucursal (ciclo de vida del operador ya está).
- Cambiar el shape de `FacturaRead` enriquecida F8.4 (es la respuesta de `POST /facturacion/factura`; el GET detail no la replica).
- Soporte de hash chain verification en el detalle (es una vista separada `/auditoria/verify-chain`; el detalle muestra el `hash_actual` como dato, no verifica).
- Listado standalone `/facturacion` (X.8) — usar `/reporteria/financiera` como entry point. Si en el futuro se justifica, se abre `hu-x-8-…`.

## Risks

1. **El fix del factory** `factura-pagos` puede romper otros consumidores que
   ya esperan el comportamiento roto (no aplicar el filtro). Auditamos:
   `grep -r "factura-pagos?" apps/` — 0 matches. La única consumer es la
   nueva página de detalle (no escrita aún). Riesgo bajo.
2. **Custom handler de `GET /factura-pagos`** debe respetar el patrón de
   paginación cursor del factory (mismo shape de respuesta). Lo copiamos
   literal y agregamos el WHERE opcional.
3. **SWR paralelo** con 5 endpoints puede fallar parcialmente. El `FacturaDetalle`
   debe mostrar un estado de error por sección (no un único error fatal)
   para que un fallo de FE no tape los datos principales.
4. **i18n**: 30 keys es manejable. Riesgo: bajo, sigue el patrón de otros
   namespaces (`reporteriaFinanciera`, `dian`, `clientes`).
5. **Test de axe-core**: el `FacturaDetalle` debe pasar WCAG 2.1 AA. Mismo
   gate que usan los otros features.
