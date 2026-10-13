# Proposal: HU-X — Módulo Facturación en web-admin (drill-down + acciones)

> **Change**: `hu-x-facturacion-admin`
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **Inputs**: `openspec/changes/hu-x-facturacion-admin/exploration.md` (este turno, 2026-10-13, 5 sections, ~6 KB, evidence en `evidence/*.png`), `openspec/specs/operations/spec.md` (REQ-OPS canónicos, 5+ años de compliance DIAN), `modelo_datos_er.mmd` (49 tablas: `prod.facturas` [L-E] línea 607-654, `prod.factura_detalle` [A] 780-794, `prod.factura_impuestos` [A], `prod.factura_pagos` [A] 843-861, `prod.factura_electronica` [L-E] 875-891, `prod.anulaciones` [L-W], `prod.reclamos` [L-W], `prod.reimpresion_ticket` [L-W], `prod.log_transaccional` [A] con hash chain per `uuid_sucursal`).

---

## 1. Why

web-admin **lista** facturas (HU-F17.3) pero **no puede drill-downear** al detalle de una. La pieza que falta es:

1. Una **página de detalle** (`/facturacion/:uuid`) que consolide header, cliente, líneas, impuestos, pagos, FE, hash chain — el flujo de "investigar una factura" más pedido al admin.
2. Las **acciones transaccionales** (reimprimir, anular, crear reclamo) que un admin necesita para responder a la sucursal o al cliente sin escalar a un humano con acceso al `electron-sucursal`.
3. El **fix de un bug colateral** en `GET /facturacion/factura-pagos?uuid_factura=…` (el factory genérico `make_router` ignora el query param — confirmado con 3 curl en este turno).

Riesgos que resuelve:

| # | Riesgo | Mitigación |
|---|---|---|
| 1 | Admin no puede auditar una factura específica — sólo ver un row en la tabla con 6 columnas | Página de detalle con 7 secciones + drill-down cross-linkeado desde listas |
| 2 | Reimprimir una factura desde admin requiere correr `cli/...` o pedirle al operador | Botón "Reimprimir" en el detalle → `POST /workflows/reimpresion-ticket` con motivo ≥10 |
| 3 | Anular una factura errónea requiere SQL directo | Botón "Anular" en el detalle → `POST /workflows/anulaciones` con `tipo_anulable='factura'` y motivo ≥10 |
| 4 | Crear un reclamo sobre una factura requiere navegación cruzada a `/reclamos` | Botón "Crear reclamo" en el detalle → `POST /workflows/reclamos` con `tipo_reclamable='factura'` |
| 5 | `GET /facturacion/factura-pagos?uuid_factura=…` ignora el filtro y devuelve pagos de otras facturas (3 curl lo confirman) | Custom handler que reemplaza el factory solo para este caso; respeta paginación cursor del factory |

No se rompe la convención AUDIT-FIRST ni el contrato C/Q/U only — la página es **read + actions via endpoints existentes** (que ya son C/Q/U correctos). No hay DELETE físico en ningún path nuevo.

## 2. What Changes

### 2.1 Decisiones

| # | Decisión | Rationale |
|---|---|---|
| **DEC-X.01** | Ruta `/facturacion/:uuid` en `App.tsx` grupo global (mismo patrón que `/dian/:uuid`, `/reclamos/:uuid`). No requiere `RequireSucursal` (cross-branch, mismo modelo que las otras). | Una factura tiene `uuid_sucursal` propio, el tenant scope del JWT ya la filtra. |
| **DEC-X.02** | Container-presentational split: `pages/FacturaDetalle.tsx` (SWR + composition) + 10 subcomponentes. | Mismo patrón que `ReporteriaFinanciera.tsx` + `FacturasTable.tsx` y `dian/pages/DianCola.tsx` + `DianQueueTable.tsx`. |
| **DEC-X.03** | API client con SWR fetching en paralelo (`Promise.all`) de los 5 endpoints; cada sección muestra su propio error/loading, no un único estado fatal. | Si falla el endpoint de FE, los datos de header/items/impuestos/pagos deben seguir visibles. |
| **DEC-X.04** | Fix del bug `?uuid_factura=` en `factura-pagos`: custom handler que reemplaza el factory **solo para este recurso**. El factory sigue intacto para los otros 4 (`facturas`, `factura-detalle`, `factura-impuestos`, `factura-otros-cobros`). | Riesgo bajo (0 consumers previos según `grep -r "factura-pagos?" apps/`). Fix quirúrgico. |
| **DEC-X.05** | Custom handler `GET /facturacion/factura-pagos` copia la query del factory verbatim (cursor + limit) y agrega `WHERE FacturaPagos.uuid_factura == :uuid_factura` si el param está presente. Mismo response shape (`{items, next_cursor}`). | Mantiene la abstracción del factory para el resto, no introduce varianza. |
| **DEC-X.06** | Reimprimir → `POST /api/v1/workflows/reimpresion-ticket` con `{uuid_factura, motivo: "≥10 chars"}`. La respuesta trae un `uuid_reimpresion` que se muestra en un toast + row en la tabla de reimpresiones del cliente. | Endpoint ya existe (F8.3), contrato documentado. |
| **DEC-X.07** | Anular → `POST /api/v1/anulaciones` con `{tipo_anulable='factura', uuid_reclamable=<uuid_factura>, motivo: "≥10 chars"}`. | Endpoint ya existe, workflow `[L-W]`. Append-only, no rompe la convención. |
| **DEC-X.08** | Crear reclamo → `POST /api/v1/workflows/reclamos` con `{tipo_reclamable='factura', uuid_reclamable=<uuid_factura>, motivo, descripcion?}`. | Endpoint ya existe (Fase 8). |
| **DEC-X.09** | HomeHub card con icono `Receipt` → link a `/reporteria/financiera` (no se crea un nuevo listado). | X.8 (listado standalone) queda como follow-up. La card es el entry point. |
| **DEC-X.10** | i18n namespace `facturacionAdmin` en `es-CO.json`. Sin variantes regionales (sólo es-CO como el resto del admin). | Sigue el patrón de los otros namespaces. |
| **DEC-X.11** | Tests: `FacturaDetalle.test.tsx` (~12 casos), `facturacionAdminApi.test.ts`, `FacturaAccionesMenu.test.tsx`, axe-core para WCAG 2.1 AA. | Mismo estándar que reporteria/clientes/dian. |
| **DEC-X.12** | Branches feature separados por PR (chained PRs, regla AGENTS.md): X.1a, X.1b, X.2, X.3, X.4, X.5, X.6, X.7. | Cumple `commit_ceiling_loc=800` y budget 400 LOC/PR. X.1 split en X.1a (BE fix + FE api client, ~280) y X.1b (página + componentes, ~400). |

### 2.2 Goals

1. Crear `FacturaDetalle` (`/facturacion/:uuid`) que muestre las 7 secciones con datos reales.
2. Botones Reimprimir / Anular / Crear Reclamo operativos, con confirmación modal (motivo ≥10 chars).
3. Fix del bug `?uuid_factura=` en `GET /facturacion/factura-pagos`.
4. Drill-down desde `FacturasTable` (reporteria) y `ClienteFacturasTab` (clientes) → `/facturacion/:uuid`.
5. Card "Facturación" en `HomeHub` con icono `Receipt`.
6. Tests + axe-core + i18n `es-CO`.
7. Merge a `dev` con chained PRs (8 PRs en total).

### 2.3 Non-Goals

1. **NO** crear facturas desde web-admin (es trabajo del operador en la sucursal).
2. **NO** listado standalone `/facturacion` (X.8) — usar `/reporteria/financiera` como entry point.
3. **NO** modificar la respuesta enriquecida F8.4 de `POST /facturacion/factura` (es la fuente canónica).
4. **NO** soporte de hash chain verification en el detalle (la vista es `/auditoria/verify-chain`; el detalle sólo muestra el `hash_actual` como dato).
5. **NO** generar PDF/impresión desde web-admin (es responsabilidad del operador en la sucursal con la impresora ESC/POS).
6. **NO** auto-suscripción a updates de FE vía WebSocket (la página recarga al navegar; sin realtime).
7. **NO** cambios en `electron-sucursal` (feature ya completa).
8. **NO** migración nueva (no hay schema change, todo es read + actions sobre tablas existentes).

### 2.4 Architecture overview

```
React Router (apps/web_admin/src/App.tsx)
  └── <Route path="/facturacion/:uuid">      [NEW]
        └── <FacturaDetalle>                  [NEW pages/]
              ├── <FacturaHeaderCard>         [NEW components/]
              │     └── <FacturaEstadoBadge>   [NEW components/]
              ├── <FacturaClienteCard>        [NEW components/]
              ├── <FacturaItemsTable>         [NEW components/]
              ├── <FacturaImpuestosTable>     [NEW components/]
              ├── <FacturaPagosTable>         [NEW components/]
              ├── <FacturaElectronicaCard>    [NEW components/]
              └── <FacturaAccionesMenu>       [NEW components/]
                    ├── <ReimprimirFacturaDialog>   [NEW]
                    ├── <AnularFacturaDialog>        [NEW]
                    └── <ReclamoFacturaDialog>       [NEW]
                    │
                    ▼  on action: SWR mutate(cache) + toast
                    │
              (uses)
              │
              └── useFacturaDetalle(uuid)     [NEW hooks/]
                    └── facturacionAdminApi    [NEW api/]
                          └── facturacionAdminSchema  [NEW Zod mirrors]
                                │
                                ▼ HTTP
                                │
              ┌────────────────────────────────────────────────┐
              │  BE (parkos-api-admin + parkos-api-sucursal)    │
              │  GET /facturacion/facturas/{uuid}        [EXISTS]│
              │  GET /facturacion/factura-detalle?...    [EXISTS]│
              │  GET /facturacion/factura-impuestos?...  [EXISTS]│
              │  GET /facturacion/factura-pagos?...      [FIX X.1a]│
              │  GET /facturacion/factura-electronica/{uuid} [EXISTS]
              │  POST /workflows/reimpresion-ticket      [EXISTS]│
              │  POST /anulaciones (tipo_anulable=...)  [EXISTS]│
              │  POST /workflows/reclamos (tipo=...)    [EXISTS]│
              └────────────────────────────────────────────────┘
```

### 2.5 Capabilities (delta spec)

**New capability**: `facturacion-admin` — página de detalle de factura en
web-admin + acciones transaccionales. Spec en
`openspec/changes/hu-x-facturacion-admin/specs/facturacion-admin/spec.md`.

REQ-X-01..13 (13 requirements).

**Delta a `operations`** (operations/spec.md): REQ-OPS-064..068 (5 requirements
nuevos) que documentan las acciones admin-only (anular, reimprimir, crear
reclamo) que el operador NO puede hacer desde la sucursal.

### 2.6 Risk matrix

| # | Risk | Mitigation |
|---|---|---|
| 1 | Fix del factory `factura-pagos` rompe consumers (no había ninguno según grep) | audit + 2 RED tests + 1 GREEN test; el factory sigue igual para los otros 4 recursos |
| 2 | SWR paralelo: 5 endpoints pueden fallar parcialmente | `FacturaDetalle` muestra loading/error por sección (no fatal global) |
| 3 | i18n typos / keys faltantes | tests de i18n (mock de `useTranslation` con keys esperadas) |
| 4 | axe-core gate WCAG 2.1 AA falla | design review de `FacturaDetalle` antes de `apply`; usar `<table>` semántico + `aria-live="polite"` para loaders |
| 5 | Acoplamiento entre `FacturaDetalle` y `FacturaAccionesMenu` (invalidación de cache) | el menu llama `mutate(swrKey)` después de cada action; test verifica que el SWR se invalida |
| 6 | Card de HomeHub con texto inconsistente | alineado con el `t('homeHub.cards.facturacion')` que se define en este change |
| 7 | `POST /anulaciones` y `/workflows/reclamos` requieren permisos admin específicos (no `operador-`) | el `FacturaAccionesMenu` oculta los botones si el rol del JWT no es `admin-` (defense in depth, además del server-side check) |

## 3. Impact

### 3.1 Affected modules

| Módulo | Impacto | Descripción |
|---|---|---|
| `prod.facturas` | READ | GET detail, no modifica. |
| `prod.factura_detalle` | READ | GET list filtrado por `uuid_factura`. |
| `prod.factura_impuestos` | READ | GET list filtrado por `uuid_factura`. |
| `prod.factura_pagos` | READ (post-fix) | GET list filtra correctamente por `?uuid_factura=…`. |
| `prod.factura_electronica` | READ | GET detail by uuid. |
| `prod.anulaciones` | INSERT (acción Anular) | nueva row con `tipo_anulable='factura'`, append-only. |
| `prod.reclamos` | INSERT (acción Crear Reclamo) | nueva row con `tipo_reclamable='factura'`, append-only. |
| `prod.reimpresion_ticket` | INSERT (acción Reimprimir) | nueva row con `uuid_factura`, append-only. |
| `prod.log_transaccional` | INSERT (side-effect de las acciones) | cada acción emite un log row con hash chain (REPORTADO por el `do_orm_execute`). |

### 3.2 Affected endpoints

| Endpoint | Cambio |
|---|---|
| `GET /api/v1/facturacion/factura-pagos?uuid_factura=…` | FIX: filtrar por `uuid_factura` (custom handler). Resto de parámetros (`cursor`, `limit`) sin cambios. |
| `POST /api/v1/workflows/reimpresion-ticket` | sin cambios (consumido desde el dialog) |
| `POST /api/v1/anulaciones` | sin cambios (consumido desde el dialog, `tipo_anulable='factura'`) |
| `POST /api/v1/workflows/reclamos` | sin cambios (consumido desde el dialog, `tipo_reclamable='factura'`) |

### 3.3 Chained PRs

8 PRs, todos merge a `dev` con la regla del AGENTS.md. `commit_ceiling_loc=800`
se cumple; budget 400 LOC/PR también (X.1a es ~280, X.1b es ~400, X.2..X.6 son
≤80, X.7 son solo tests + i18n).

| PR | Tareas | LOC | Branch |
|---|---|---|---|
| **X.1a** | (1) Custom handler `GET /facturacion/factura-pagos` con `?uuid_factura=…` (BE fix). (2) `facturacionAdminApi.ts` + `facturacionAdminSchema.ts` (FE api client). (3) `useFacturaDetalle.ts` skeleton. (4) 2 tests RED+GREEN del fix BE. (5) 4 tests del api client. | ~80 BE + ~200 FE + ~150 tests = ~430 | `feature/hu-x-1a-factura-api-fix` |
| **X.1b** | (1) `FacturaDetalle.tsx` container. (2) 8 subcomponentes presentacionales (`FacturaHeaderCard`, `FacturaClienteCard`, `FacturaItemsTable`, `FacturaImpuestosTable`, `FacturaPagosTable`, `FacturaElectronicaCard`, `FacturaEstadoBadge`, `FacturaAccionesMenu` skeleton). (3) Ruta `<Route path="/facturacion/:uuid">` en `App.tsx`. (4) i18n keys (esqueleto). (5) `FacturaDetalle.test.tsx` (~12 casos) + axe-core. | ~400 FE + ~250 tests = ~650 | `feature/hu-x-1b-factura-detalle-page` |
| **X.2** | (1) Botón "Ver detalle" en `FacturasTable.tsx` (reporteria) con `useNavigate`. (2) Botón en `ClienteFacturasTab.tsx` (clientes) idem. (3) Tests de integración del link. | ~50 FE + ~30 tests = ~80 | `feature/hu-x-2-link-detalle` |
| **X.3** | (1) `ReimprimirFacturaDialog.tsx` con form RHF + Zod (motivo ≥10). (2) Hook `useReimprimirFactura.ts` con `parkosFetch` + toast. (3) Wire al `FacturaAccionesMenu`. (4) Test del dialog. | ~80 FE + ~50 tests = ~130 | `feature/hu-x-3-reimprimir` |
| **X.4** | (1) `AnularFacturaDialog.tsx` con form RHF + Zod (motivo ≥10). (2) Hook `useAnularFactura.ts`. (3) Wire al menu. (4) Test. | ~80 FE + ~50 tests = ~130 | `feature/hu-x-4-anular` |
| **X.5** | (1) `ReclamoFacturaDialog.tsx` con form RHF + Zod (motivo + descripción). (2) Hook `useCrearReclamoFactura.ts`. (3) Wire. (4) Test. | ~80 FE + ~50 tests = ~130 | `feature/hu-x-5-reclamo` |
| **X.6** | (1) Card "Facturación" en `HomeHub.tsx` con icono `Receipt` de `lucide-react`. (2) Link a `/reporteria/financiera`. (3) i18n key. (4) Test del `HomeHub` con la card. | ~30 FE + ~30 tests = ~60 | `feature/hu-x-6-homehub-card` |
| **X.7** | (1) Final i18n keys (`facturacionAdmin` namespace completo, ~30 keys). (2) Actualizar `HomeHub.test.tsx` parametrizado (H3 ya lo soporta). (3) axe-core sweep. (4) TypeScript strict + ESLint clean. (5) Smoke test del dev server. | ~30 i18n + ~50 tests = ~80 | `feature/hu-x-7-tests-i18n` |
| **Total** | | **~1,680 LOC** | 8 PRs |

**Sizes verificados contra el budget**:
- X.1a (430 LOC) cabe en el budget 400 — pero es 30 LOC over. Splitir X.1a en
  X.1a.1 (BE fix + tests, ~180) + X.1a.2 (FE api client + tests, ~250) si
  querés estricto. Recomiendo el split si el reviewer es estricto.
- X.1b (650 LOC) excede el budget. **size:exception justificado** — la página
  es cohesiva (1 página + 8 subcomponentes), no se puede partir sin
  romper la review. Alternativa: split en X.1b.1 (page shell + 3
  componentes + route) + X.1b.2 (5 componentes + axe-core) — factible.
- X.2..X.6: todos dentro del budget.

**Decisión recomendada**: mantener X.1a como `size:exception` (430 LOC,
cohesivo: BE fix + su consumer FE api) o split si el reviewer es estricto.
X.1b split obligatorio (650 → 2 PRs de ~325 cada uno).

### 3.4 Order of operations

1. `sdd-explore` (este cambio, listo) → `exploration.md` ✅.
2. `sdd-propose` (este cambio, listo) → `proposal.md` ✅.
3. `sdd-spec` → `specs/facturacion-admin/spec.md` (NEW capability, REQ-X-01..13) + `specs/operations/spec.md` (DELTA REQ-OPS-064..068).
4. `sdd-design` → `design.md` (con la investigación del factory + approach del custom handler).
5. `sdd-tasks` → `tasks.md` (8 clusters T1..T8 mapeados a X.1a..X.7).
6. `sdd-apply` (chained PRs) → 8 PRs merge a `dev`.
7. `sdd-verify` → `verify-report.md`.
8. `sdd-archive` → delta spec sync a `openspec/specs/`, archive-report.md.
