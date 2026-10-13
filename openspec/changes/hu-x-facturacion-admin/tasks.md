# Tasks: hu-x-facturacion-admin

> **Change**: `hu-x-facturacion-admin`
> **Phase**: tasks (sdd-tasks) — checklist only, do NOT implement
> **Status**: ready for `sdd-apply`
> **Branch topology**: rama base `dev` (HEAD `2bd9856e`); 8 PRs chained (X.1a, X.1b, X.2, X.3, X.4, X.5, X.6, X.7), cada uno mergea a `dev` con `--ff-only` cuando es descendiente directo o `--no-ff` cuando hay rebase upstream (regla AGENTS.md §Gitflow Estricto).
> **Inputs**: `exploration.md`, `proposal.md`, `design.md`, `specs/facturacion-admin/spec.md` (REQ-X-01..13), `specs/operations/spec.md` (REQ-OPS-200..206 delta), `evidence/*.png` (5 screenshots).
> **Precedentes en repo**: `hu-f15-2-empresa` (cambio activo, mismo patrón de HomeHub parametrizado), `hu-f16-usuarios` (cambio activo, patrón de dialogs), `reporteria/financiera` (HU-F17.3 archivada, container-presentational split), `dian/` (HU-F20.5, retry button en card), `electron-sucursal/facturacion/api/facturaApi.ts` (Zod mirror pattern con `decimalNumber`), `reimpresion_ticket` HU-F8.3 (workflow `[L-W]` con motivo ≥10).
> **Skills loaded**: `gentle-sdd-tasks`.

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~1,680 LOC across 8 PRs (BE 80 + FE 1,000 + tests 600 + i18n 60) |
| Total tasks | ~50 (8 clusters) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | **Low** — X.1a es 430 (size:exception justificado: cohesivo BE fix + FE api consumer), X.1b es 650 (split en X.1b.1 ~325 + X.1b.2 ~325 — recomendado), X.2..X.6 ≤ 130, X.7 ≤ 80 |
| Chained PRs recommended | **Yes** (8 PRs, ~1,680 LOC) |
| Chain strategy | `feature/hu-x-1a-...` → `feature/hu-x-1b-...` → `feature/hu-x-2-...` → ... → `feature/hu-x-7-...`, todas mergean a `dev` con regla gitflow |
| Suggested split | X.1b en X.1b.1 (page shell + 4 componentes + route + i18n esqueleto, ~325) + X.1b.2 (4 subcomponentes + axe-core + tests, ~325) si reviewer es estricto. X.1a queda como 1 PR (`size:exception` justificado por cohesión BE+FE). |
| Delivery strategy | `auto-chain` (cached per precedent) |
| `size:exception` required? | **Yes** para X.1a (430 LOC) o para X.1b (650 LOC) si no se splitea. **Justificación**: ambos son cohesivos (BE fix + su consumer FE; página completa + sus subcomponentes). |

| Cluster | Tareas | LOC est. impl | LOC est. tests | Cumulative LOC |
|---------|--------|---------------|----------------|----------------|
| X.1a BE fix + FE api | 9 | ~80 BE + ~200 FE | ~150 BE + ~150 FE = ~300 | 580 |
| X.1b page + componentes | 14 | ~400 FE | ~250 tests | 1,230 |
| X.2 drill-down links | 4 | ~50 FE | ~30 tests | 1,310 |
| X.3 reimprimir dialog | 6 | ~80 FE | ~50 tests | 1,440 |
| X.4 anular dialog | 6 | ~80 FE | ~50 tests | 1,570 |
| X.5 reclamo dialog | 7 | ~80 FE | ~50 tests | 1,700 |
| X.6 HomeHub card | 3 | ~30 FE | ~30 tests | 1,760 |
| X.7 tests + i18n final | 5 | ~30 i18n | ~50 tests | 1,840 |
| **Total** | **54** | **~1,030 FE + ~80 BE** | **~660 tests + ~30 i18n** | **~1,800 net** |

> Tope por commit: <800 LOC. Cada cluster cabe en ≤800 LOC net. X.1a (580) y X.1b (650) entran con `size:exception` o split.

Decision needed before apply: No (todo cerrado con el plan).
Chained PRs recommended: Yes.
Chain strategy: 8 PRs chained a `dev`.
400-line budget risk: Low.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| X.1a | BE fix + FE api client + i18n esqueleto | commit 1 | `pnpm --filter @apps/web_admin vitest run facturacionAdminApi.test.ts` + `pytest backend/tests/integration/test_factura_pagos_filter.py` | Real DB (testcontainers) para BE; vitest con mocks para FE | Rollback del custom handler + restore `_mount_factura('factura-pagos', ...)` + delete `facturacionAdminApi.ts` |
| X.1b | Página + componentes + route | commit 2 | `pnpm --filter @apps/web_admin vitest run FacturaDetalle.test.tsx` | vitest con SWR mocks; axe-core | Revertir la route + delete los subcomponentes |
| X.2 | onClick en listas | commit 3 | `pnpm --filter @apps/web_admin vitest run FacturasTable.test.tsx ClienteFacturasTab.test.tsx` | vitest con router mocks | Revertir el link; las listas siguen funcionando |
| X.3 | Reimprimir dialog | commit 4 | `pnpm --filter @apps/web_admin vitest run ReimprimirFacturaDialog.test.tsx` | vitest con parkosFetch mocks | Revertir el dialog; el endpoint sigue accesible |
| X.4 | Anular dialog | commit 5 | idem | idem | idem |
| X.5 | Reclamo dialog | commit 6 | idem | idem | idem |
| X.6 | HomeHub card | commit 7 | `pnpm --filter @apps/web_admin vitest run HomeHub.test.tsx` | vitest | Revertir la card |
| X.7 | i18n final + axe-core sweep | commit 8 | `pnpm --filter @apps/web_admin vitest run` + `pnpm --filter @apps/web_admin exec playwright test a11y/factura-detalle.spec.ts` | full suite verde | Revertir i18n; la app sigue funcionando con keys default |

## Tareas

### Cluster X.1a — BE fix + FE api client (~80 BE + ~200 FE + ~300 tests, total ~580)

- [ ] **T-HU-X.1a-T1** [RED] — Write failing integration test for `GET /facturacion/factura-pagos?uuid_factura=…` que verifica que el filter funciona (Escenario REQ-OPS-203 #1).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_factura_pagos_filter_returns_only_matching` — seed 2 pagos de F y 1 pago de F2; `?uuid_factura=F` retorna solo el de F.
  - **Patrón F1.9**: HTTP integration con `httpx.AsyncClient + ASGITransport` + JWT admin fixture.
  - **Acción**: importar `FacturaPagosReadList` from `parkos_core.schemas.facturacion`; usar `pytest_asyncio.fixture`; asserts via response JSON.
  - **Archivo**: `backend/tests/integration/test_factura_pagos_filter.py` (NEW).
  - **Validación**: T1 test FAIL (filter no filtra, retorna 3 en lugar de 1) — el factory ignora `?uuid_factura=`.

- [ ] **T-HU-X.1a-T2** [GREEN] — Implement custom handler `list_factura_pagos` en `backend/.../api/v1/facturacion.py` (~50 LOC).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (modified, append custom handler).
  - **Contenido**: `async def list_factura_pagos(cursor, limit, uuid_factura, session, _ctx, _claims)` con `select(FacturaPagos).order_by(...)` + WHERE si `uuid_factura` + cursor pagination + `FacturaPagosReadList` response. Eliminar el `_mount_factura('factura-pagos', ...)` de la línea 170-177.
  - **Imports**: `from ..router_factory import _parse_cursor_timestamp, cursor_decode, cursor_encode, Cursor, InvalidCursorError`, `from fastapi import Query`, `from sqlalchemy import select`, `from ..models.A.factura_pagos import FacturaPagos`.
  - **Acción**: append handler antes de la línea 195 (donde empieza el POST `/factura`).
  - **Validación**: T1 test PASS.

- [ ] **T-HU-X.1a-T3** [RED] — Write failing test for the other 3 scenarios del fix (REQ-OPS-203 #2, #3, #4).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T2: `test_factura_pagos_filter_empty_uuid_returns_zero_items` — `?uuid_factura=00000000-…` retorna `items: []`.
    - T3: `test_factura_pagos_no_filter_returns_global_list` — sin filter, retorna todos los pagos (backward-compat).
    - T4: `test_factura_pagos_filter_with_cursor_pagination` — `?uuid_factura=F&limit=2&cursor=…` pagina correctamente dentro del filter.
  - **Acción**: append a `test_factura_pagos_filter.py`.
  - **Validación**: T2..T4 PASS post T2 GREEN.

- [ ] **T-HU-X.1a-T4** [REFACTOR] — Add docstring + tenant scope rationale al custom handler; add `__all__` export.
  - **Archivo**: mismo file. Add docstring con REQ-OPS-203 reference + DEC-X.04 reference + nota sobre `do_orm_execute` listener que auto-filtra por `uuid_sucursal`.

- [ ] **T-HU-X.1a-T5** [RED] — Write failing tests for `facturacionAdminApi.ts::fetchFacturaByUuid` (Zod parse correct).
  - **Tests** (pure unit, no DB):
    - T1: `test_fetchFacturaByUuid_parses_response_with_decimal_strings` — mock `fetchJson` retorna `{uuid: "…", created_at: "…", subtotal: "5000.0000", descuento: "0", total: "5000.0000", uuid_sucursal: "…"}` → `FacturaDetailReadSchema.parse(raw)` succeeds y `subtotal: 5000, total: 5000`.
    - T2: `test_fetchFacturaByUuid_propagates_ParkosHttpError` — mock retorna 500 → throw.
  - **Patrón**: vitest con `vi.mock('@/lib/api/fetchJson')`.
  - **Archivo**: `apps/web_admin/src/features/facturacion/api/facturacionAdminApi.test.ts` (NEW).
  - **Validación**: ImportError al inicio (RED); PASS post T6 GREEN.

- [ ] **T-HU-X.1a-T6** [GREEN] — Create `facturacionAdminApi.ts` + `facturacionAdminSchema.ts` (~200 LOC, 5 funciones + 5 Zod schemas).
  - **Archivos**:
    - `apps/web_admin/src/features/facturacion/api/facturacionAdminSchema.ts` (NEW, ~80 LOC, 5 schemas).
    - `apps/web_admin/src/features/facturacion/api/facturacionAdminApi.ts` (NEW, ~120 LOC, 5 funciones: `fetchFacturaByUuid`, `fetchFacturaDetalle`, `fetchFacturaImpuestos`, `fetchFacturaPagos`, `fetchFacturaElectronicaByUuid`).
  - **Contenido schemas**: `FacturaDetailReadSchema` (zod con `decimalNumber` transform), `FacturaDetalleItemSchema`, `FacturaDetalleListSchema`, `FacturaImpuestoItemSchema`, `FacturaImpuestoListSchema`, `FacturaPagoItemSchema`, `FacturaPagoListSchema`, `FacturaElectronicaReadSchema`. Mirror del response shape verificado este turno con curl.
  - **Contenido api**: 5 funciones `fetchJson`-based, cada una `Schema.parse(raw)` antes de retornar.
  - **Validación**: T5 tests PASS.

- [ ] **T-HU-X.1a-T7** [RED] — Write failing tests for `useFacturaDetalle.ts` SWR hook.
  - **Tests** (vitest con `vi.mock('swr')`):
    - T1: `useFacturaDetalle(uuid='valid')` llama los 5 endpoints en paralelo (verifica que `useSWR` se invoca con las keys correctas).
    - T2: `useFacturaDetalle(uuid=null)` no llama ningún endpoint (SWR key = null).
    - T3: El fetch del FE sólo se dispara si `header.data.uuid_factura_electronica` está presente.
  - **Archivo**: `apps/web_admin/src/features/facturacion/hooks/useFacturaDetalle.test.ts` (NEW, ~80 LOC, 3 tests).
  - **Validación**: ImportError RED.

- [ ] **T-HU-X.1a-T8** [GREEN] — Create `useFacturaDetalle.ts` hook (~60 LOC, 6 useSWR calls).
  - **Archivo**: `apps/web_admin/src/features/facturacion/hooks/useFacturaDetalle.ts` (NEW).
  - **Contenido**: 6 useSWR calls: `header`, `detalle`, `impuestos`, `pagos`, `fe` (conditional), `hash`. Cada uno con key `['factura-{kind}', uuid]` y `revalidateOnFocus: false`.
  - **Imports**: `useSWR` from `swr`, las 5 funciones de `facturacionAdminApi`, `fetchFacturaHash` (helper interno que llama `/admin/log-transaccional?uuid_referencia=…`).
  - **Validación**: T7 tests PASS.

- [ ] **T-HU-X.1a-T9** [GREEN] — Create `lib/estadoFactura.ts` (~25 LOC, derivación de estado).
  - **Archivo**: `apps/web_admin/src/features/facturacion/lib/estadoFactura.ts` (NEW).
  - **Contenido**: `deriveEstadoFactura(anulacionesCount: number, fechaAnulacion: string | null): 'vigente' | 'anulada'`. Por ahora: si `anulacionesCount > 0` → 'anulada'; sino 'vigente'. En el futuro, refinar con `V_FACTURA_ESTADO` view cuando esté expuesta.
  - **Validación**: unit test inline (3 casos).

  **Commit suggestion**: `feat(web_admin,backend): HU-X.1a — drill-down api: facturacionAdminApi + fix ?uuid_factura= filter`.

  **Exit criteria X.1a**: T1..T9 verde; ~580 LOC cumulative; 0 lint/type errors; 1 BE RED+GREEN fix + 5 FE test files green.

### Cluster X.1b — Página + componentes + route (~400 FE + ~250 tests, total ~650)

> **Decisión**: si el reviewer es estricto con el budget 400, split en X.1b.1 (page shell + 4 componentes + route + i18n esqueleto, ~325) + X.1b.2 (4 subcomponentes + axe-core + tests finales, ~325). Las tareas T1..T14 abajo asumen el PR único; si se splitea, cortar en T7.

- [ ] **T-HU-X.1b-T1** [GREEN] — Create `FacturaHeaderCard.tsx` (~70 LOC).
  - **Archivo**: `apps/web_admin/src/features/facturacion/components/FacturaHeaderCard.tsx` (NEW).
  - **Contenido**: Card con uuid truncado + copy-to-clipboard, fecha formateada, subtotal/descuento/total, badge de estado, numero_completo ("—" si no hay FE), hash_actual con copy-to-clipboard.
  - **Imports**: shadcn `Card`, `Badge`, `Button`; lucide `Copy`; `useTranslation`.
  - **Validación**: render en `FacturaDetalle.test.tsx` T1..T2 (ver T12).

- [ ] **T-HU-X.1b-T2** [GREEN] — Create `FacturaClienteCard.tsx` (~30 LOC).
  - **Archivo**: `apps/web_admin/src/features/facturacion/components/FacturaClienteCard.tsx` (NEW).
  - **Contenido**: Card con "Consumidor final" por default (REQ-X-03 alternativa C: no hay display endpoint en MVP).
  - **Validación**: T2 de `FacturaDetalle.test.tsx`.

- [ ] **T-HU-X.1b-T3** [GREEN] — Create `FacturaItemsTable.tsx` (~50 LOC).
  - **Archivo**: `apps/web_admin/src/features/facturacion/components/FacturaItemsTable.tsx` (NEW).
  - **Contenido**: shadcn Table con columnas concepto, cantidad, valor_unitario, subtotal. Loading skeleton, error alert con retry.
  - **Validación**: T5 de `FacturaDetalle.test.tsx`.

- [ ] **T-HU-X.1b-T4** [GREEN] — Create `FacturaImpuestosTable.tsx` (~50 LOC).
  - **Archivo**: `apps/web_admin/src/features/facturacion/components/FacturaImpuestosTable.tsx` (NEW).
  - **Contenido**: Tabla con nombre_impuesto, porcentaje, base_calculo, valor. Mismo patrón que `FacturaItemsTable`.
  - **Validación**: T2 de `FacturaDetalle.test.tsx`.

- [ ] **T-HU-X.1b-T5** [GREEN] — Create `FacturaPagosTable.tsx` (~60 LOC).
  - **Archivo**: `apps/web_admin/src/features/facturacion/components/FacturaPagosTable.tsx` (NEW).
  - **Contenido**: Tabla con timestamp, medio_pago (badge con color por tipo), valor, referencia, tipo_movimiento (badge).
  - **Validación**: T2 + T5 de `FacturaDetalle.test.tsx`.

- [ ] **T-HU-X.1b-T6** [GREEN] — Create `FacturaElectronicaCard.tsx` (~80 LOC).
  - **Archivo**: `apps/web_admin/src/features/facturacion/components/FacturaElectronicaCard.tsx` (NEW).
  - **Contenido**: Card con prefijo, consecutivo, estado_dian badge (pendiente=warning, enviado=info, aceptado=success, rechazado=destructive), cufe (visible SOLO si aceptado), botón "Reintentar" (visible SOLO si rechazado).
  - **Validación**: T4 de `FacturaDetalle.test.tsx`.

- [ ] **T-HU-X.1b-T7** [GREEN] — Create `FacturaEstadoBadge.tsx` (~25 LOC).
  - **Archivo**: `apps/web_admin/src/features/facturacion/components/FacturaEstadoBadge.tsx` (NEW).
  - **Contenido**: Badge derivado del `estado` prop, color por estado. Mismo patrón que `EstadoEnvioDianBadge`.
  - **Validación**: T2 + T11 de `FacturaDetalle.test.tsx`.

- [ ] **T-HU-X.1b-T8** [GREEN] — Create `FacturaAccionesMenu.tsx` skeleton (~30 LOC, sin los 3 dialogs).
  - **Archivo**: `apps/web_admin/src/features/facturacion/components/FacturaAccionesMenu.tsx` (NEW).
  - **Contenido**: 3 botones con role-gate `if (me.rol !== 'admin-') return null`. Los dialogs se importan pero se referencian como `null` (placeholders que se llenan en X.3..X.5).
  - **Validación**: T12 de `FacturaDetalle.test.tsx` (muestra los 3 botones visibles).

- [ ] **T-HU-X.1b-T9** [GREEN] — Add route `/facturacion/:uuid` en `App.tsx`.
  - **Archivo**: `apps/web_admin/src/App.tsx` (modified, +2 LOC).
  - **Contenido**: `<Route path="/facturacion/:uuid" element={<FacturaDetalle />} />` en el grupo global con `RequireAdmin` (NO `RequireSucursal`).
  - **Validación**: vite dev server arranca sin warnings.

- [ ] **T-HU-X.1b-T10** [GREEN] — Create `FacturaDetalle.tsx` container (~150 LOC).
  - **Archivo**: `apps/web_admin/src/features/facturacion/pages/FacturaDetalle.tsx` (NEW).
  - **Contenido**: skeleton mientras header carga; 404 si header error; 7 secciones con sus loaders/errors; `FacturaAccionesMenu` al final.
  - **Imports**: todos los subcomponentes creados en T1..T8; `useFacturaDetalle` de T8 del X.1a; `useParams`, `useTranslation`.
  - **Validación**: T1..T12 de `FacturaDetalle.test.tsx`.

- [ ] **T-HU-X.1b-T11** [RED] — Write failing tests for `FacturaDetalle.tsx` (12 escenarios).
  - **Tests** (vitest con `vi.mock('@/features/facturacion/hooks/useFacturaDetalle')`):
    - T1: skeleton mientras header loading.
    - T2: render header + 6 secciones con datos mock.
    - T3: 404 del header → "Factura no encontrada".
    - T4: 404 del FE → "FE no generada" sin tapar el resto.
    - T5: error de detalle → alert inline.
    - T6: tenant scope cross-branch → 404.
    - T7: copy-to-clipboard del hash (mock `navigator.clipboard`).
    - T8: copy-to-clipboard del uuid.
    - T9: números formateados con `es-CO` (regex: contiene separador de miles).
    - T10: fecha formateada con timezone local.
    - T11: badge de estado con texto + color.
    - T12: renderiza `FacturaAccionesMenu` si rol=admin-.
  - **Archivo**: `apps/web_admin/src/features/facturacion/pages/FacturaDetalle.test.tsx` (NEW, ~250 LOC).
  - **Validación**: 12 tests PASS post T10 GREEN.

- [ ] **T-HU-X.1b-T12** [GREEN] — Create `FacturaAccionesMenu.test.tsx` (1 test: role-gate).
  - **Tests** (vitest con `vi.mock('@/lib/api/me')`):
    - T1: renderiza 3 botones si rol=admin-; renderiza `null` si rol=operador-.
  - **Archivo**: `apps/web_admin/src/features/facturacion/components/FacturaAccionesMenu.test.tsx` (NEW, ~80 LOC).
  - **Validación**: T1 PASS.

- [ ] **T-HU-X.1b-T13** [GREEN] — Add i18n keys (esqueleto, ~20 keys para el header + secciones básicas).
  - **Archivo**: `apps/web_admin/src/i18n/locales/es-CO.json` (modified, +60 LOC, namespace `facturacionAdmin` con keys de T1..T10).
  - **Contenido**: las 30+ keys listadas en REQ-X-12 (versión inicial).
  - **Validación**: i18n mock test verifica keys esperadas.

- [ ] **T-HU-X.1b-T14** [REFACTOR] — Add `data-testid` attributes a todos los subcomponentes (testability).
  - **Archivos**: cada subcomponente de T1..T8 + page T10.
  - **Validación**: `FacturaDetalle.test.tsx` usa los testids; axe-core no se queja.

  **Commit suggestion**: `feat(web_admin): HU-X.1b — página /facturacion/:uuid con 7 secciones + route`.

  **Exit criteria X.1b**: T1..T14 verde; ~650 LOC cumulative; 0 lint/type errors; 12 tests del page + 1 del menu green; axe-core 0 violations.

### Cluster X.2 — Drill-down links en listas (~50 FE + ~30 tests, total ~80)

- [ ] **T-HU-X.2-T1** [RED] — Write failing test para el link en `FacturasTable`.
  - **Tests**:
    - T1: `FacturasTable.test.tsx` — agregar test que verifica que cada fila tiene un `<a>` o `<button>` con `href` o `to={/facturacion/${row.uuid}}`.
  - **Patrón**: vitest con `vi.mock('react-router-dom')` y `MemoryRouter`.
  - **Acción**: append a `apps/web_admin/src/features/reporteria/components/FacturasTable.test.tsx` (+30 LOC).
  - **Validación**: T1 FAIL post.

- [ ] **T-HU-X.2-T2** [GREEN] — Add link en `FacturasTable.tsx`.
  - **Archivo**: `apps/web_admin/src/features/reporteria/components/FacturasTable.tsx` (modified, +20 LOC).
  - **Contenido**: nueva columna o última celda con `<Link to={/facturacion/${row.uuid}}>` usando lucide `ExternalLink` + texto "Ver detalle" (i18n: `reporteriaFinanciera.facturas.verDetalle`).
  - **Validación**: T1 PASS.

- [ ] **T-HU-X.2-T3** [RED + GREEN] — Idem para `ClienteFacturasTab`.
  - **Tests**: append a `ClienteFacturasTab.test.tsx` (+20 LOC, 1 test).
  - **Archivo**: `apps/web_admin/src/features/clientes/components/ClienteFacturasTab.tsx` (modified, +20 LOC).
  - **Validación**: test PASS.

- [ ] **T-HU-X.2-T4** [REFACTOR] — Add i18n keys para los 2 textos "Ver detalle".
  - **Archivo**: `apps/web_admin/src/i18n/locales/es-CO.json` (+2 keys: `reporteriaFinanciera.facturas.verDetalle` + `clienteFacturas.verDetalle`).

  **Commit suggestion**: `feat(web_admin): HU-X.2 — link a /facturacion/:uuid desde listas`.

  **Exit criteria X.2**: 2 tests verdes; 2 archivos modificados; 0 lint/type errors.

### Cluster X.3 — Reimprimir dialog (~80 FE + ~50 tests, total ~130)

- [ ] **T-HU-X.3-T1** [RED] — Write failing test for `useReimprimirFactura` hook.
  - **Tests**:
    - T1: `trigger(uuid, motivo)` POSTea `/api/v1/workflows/reimpresion-ticket` con `Idempotency-Key` y `{uuid_factura, motivo}`.
    - T2: trigger propaga `ParkosHttpError` en caso de error.
  - **Archivo**: `apps/web_admin/src/features/facturacion/hooks/useReimprimirFactura.test.ts` (NEW, ~50 LOC, 2 tests).
  - **Validación**: ImportError RED.

- [ ] **T-HU-X.3-T2** [GREEN] — Create `useReimprimirFactura.ts` (~30 LOC).
  - **Archivo**: `apps/web_admin/src/features/facturacion/hooks/useReimprimirFactura.ts` (NEW).
  - **Contenido**: `trigger(uuid, motivo): Promise<{uuid_reimpresion, ...}>` con `useMutation` de SWR + `Idempotency-Key` + `parkosFetch`.
  - **Validación**: T1..T2 PASS.

- [ ] **T-HU-X.3-T3** [RED] — Write failing tests for `ReimprimirFacturaDialog`.
  - **Tests**:
    - T1: motivo < 10 chars → Zod error inline, no POSTea.
    - T2: motivo ≥ 10 chars → trigger llamado, dialog cierra, toast success.
    - T3: trigger falla → toast error.
  - **Archivo**: `apps/web_admin/src/features/facturacion/components/ReimprimirFacturaDialog.test.tsx` (NEW, ~80 LOC, 3 tests).
  - **Validación**: ImportError RED.

- [ ] **T-HU-X.3-T4** [GREEN] — Create `ReimprimirFacturaDialog.tsx` (~50 LOC).
  - **Archivo**: `apps/web_admin/src/features/facturacion/components/ReimprimirFacturaDialog.tsx` (NEW).
  - **Contenido**: RHF + Zod schema (motivo min=10), Dialog con form, submit con `useReimprimirFactura`, toast + onOpenChange.
  - **Validación**: T1..T3 PASS.

- [ ] **T-HU-X.3-T5** [GREEN] — Wire dialog en `FacturaAccionesMenu`.
  - **Archivo**: `apps/web_admin/src/features/facturacion/components/FacturaAccionesMenu.tsx` (modified, replace el placeholder con `<ReimprimirFacturaDialog ...>`).
  - **Validación**: T8 de `FacturaDetalle.test.tsx` sigue PASS; botón "Reimprimir" abre el dialog.

- [ ] **T-HU-X.3-T6** [REFACTOR] — Add i18n keys para el dialog.
  - **Archivo**: `es-CO.json` (+3 keys: `dialogs.reimprimirTitle`, `dialogs.motivoLabel` ya está, `toasts.reimpresionExitosa`).

  **Commit suggestion**: `feat(web_admin): HU-X.3 — reimprimir factura`.

  **Exit criteria X.3**: 5 tests verdes; 0 lint/type errors.

### Cluster X.4 — Anular dialog (~80 FE + ~50 tests, total ~130)

- [ ] **T-HU-X.4-T1** [RED] — Write failing test for `useAnularFactura` hook.
  - **Tests**:
    - T1: `trigger(uuid, motivo)` POSTea `/api/v1/anulaciones` con `{tipo_anulable: 'factura', uuid_reclamable: uuid, motivo}`.
    - T2: en success, `navigate(/anulaciones/{uuid_anulacion})` se llama.
  - **Archivo**: `useAnularFactura.test.ts` (NEW, ~50 LOC, 2 tests).
  - **Validación**: RED.

- [ ] **T-HU-X.4-T2** [GREEN] — Create `useAnularFactura.ts` (~30 LOC).
  - **Archivo**: `useAnularFactura.ts` (NEW).
  - **Contenido**: igual a X.3 pero con endpoint `/anulaciones` y `navigate` en onSuccess.
  - **Validación**: T1..T2 PASS.

- [ ] **T-HU-X.4-T3** [RED] — Write failing tests for `AnularFacturaDialog`.
  - **Tests**: 3 tests (motivo corto, motivo válido, error).
  - **Archivo**: `AnularFacturaDialog.test.tsx` (NEW, ~80 LOC).

- [ ] **T-HU-X.4-T4** [GREEN] — Create `AnularFacturaDialog.tsx` (~50 LOC).
  - **Archivo**: mismo file.
  - **Contenido**: mismo patrón que `ReimprimirFacturaDialog` + variante de copy ("Anular factura" / "Esta acción es irreversible...").

- [ ] **T-HU-X.4-T5** [GREEN] — Wire dialog en `FacturaAccionesMenu`.
  - **Archivo**: `FacturaAccionesMenu.tsx` (modified, +5 LOC).

- [ ] **T-HU-X.4-T6** [REFACTOR] — Add i18n keys.

  **Commit suggestion**: `feat(web_admin): HU-X.4 — anular factura`.

  **Exit criteria X.4**: 5 tests verdes.

### Cluster X.5 — Reclamo dialog (~80 FE + ~50 tests, total ~130)

- [ ] **T-HU-X.5-T1** [RED] — Write failing test for `useCrearReclamoFactura`.
  - **Tests**:
    - T1: `trigger(uuid, motivo, descripcion)` POSTea `/api/v1/workflows/reclamos` con `{tipo_reclamable: 'factura', uuid_reclamable: uuid, motivo, descripcion}`.
    - T2: en success, `navigate(/reclamos/{uuid_reclamo})`.
  - **Archivo**: `useCrearReclamoFactura.test.ts` (NEW).

- [ ] **T-HU-X.5-T2** [GREEN] — Create `useCrearReclamoFactura.ts` (~30 LOC).

- [ ] **T-HU-X.5-T3** [RED] — Write failing tests for `ReclamoFacturaDialog` (4 tests: motivo corto, motivo sin descripción, motivo+descripción válidos, error).
  - **Archivo**: `ReclamoFacturaDialog.test.tsx` (NEW, ~100 LOC, 4 tests).

- [ ] **T-HU-X.5-T4** [GREEN] — Create `ReclamoFacturaDialog.tsx` (~60 LOC).
  - **Contenido**: RHF + Zod con motivo min=10 + descripción min=20 opcional.

- [ ] **T-HU-X.5-T5** [GREEN] — Wire dialog en `FacturaAccionesMenu`.

- [ ] **T-HU-X.5-T6** [GREEN] — Add i18n keys.

- [ ] **T-HU-X.5-T7** [REFACTOR] — Update `FacturaAccionesMenu.test.tsx` para verificar que los 3 dialogs abren correctamente.

  **Commit suggestion**: `feat(web_admin): HU-X.5 — crear reclamo sobre factura`.

  **Exit criteria X.5**: 7 tests verdes; 0 lint/type errors.

### Cluster X.6 — HomeHub card (~30 FE + ~30 tests, total ~60)

- [ ] **T-HU-X.6-T1** [RED] — Write failing test para la nueva card.
  - **Tests**:
    - T1: `HomeHub.test.tsx` — verificar que la card "Facturación" se renderiza con icono `Receipt` y link a `/reporteria/financiera`.
  - **Archivo**: `HomeHub.test.tsx` (modified, +20 LOC, 1 test).
  - **Validación**: T1 FAIL.

- [ ] **T-HU-X.6-T2** [GREEN] — Add card a `HomeHub.tsx`.
  - **Archivo**: `apps/web_admin/src/pages/HomeHub.tsx` (modified, +10 LOC).
  - **Contenido**: nueva card con icono `Receipt` de lucide, título y descripción i18n, link a `/reporteria/financiera`. H3 ya parametrizado (HU-F15.2), así que sólo se agrega la card al array.
  - **Validación**: T1 PASS.

- [ ] **T-HU-X.6-T3** [REFACTOR] — Add i18n keys (`homeHub.cards.facturacion`, `homeHub.cards.facturacionDesc`).

  **Commit suggestion**: `feat(web_admin): HU-X.6 — HomeHub card Facturación`.

  **Exit criteria X.6**: 1 test verde.

### Cluster X.7 — i18n final + axe-core sweep (~30 i18n + ~50 tests, total ~80)

- [ ] **T-HU-X.7-T1** [GREEN] — Completar las 30+ keys del namespace `facturacionAdmin`.
  - **Archivo**: `es-CO.json` (modified, +30 keys finales: estados de pagos, estados de FE, mensajes de retry, etc.).

- [ ] **T-HU-X.7-T2** [RED + GREEN] — Test de a11y: axe-core scan sobre `FacturaDetalle`.
  - **Tests**:
    - T1: `FacturaDetalle.a11y.test.tsx` con `@axe-core/playwright` — 0 violations de WCAG 2.1 AA.
  - **Archivo**: NEW (~30 LOC, 1 test).
  - **Validación**: T1 PASS.

- [ ] **T-HU-X.7-T3** [GREEN] — TypeScript strict + ESLint clean sobre todos los archivos nuevos.
  - **Comando**: `pnpm --filter @apps/web_admin typecheck` + `pnpm --filter @apps/web_admin lint`.
  - **Validación**: 0 errors.

- [ ] **T-HU-X.7-T4** [GREEN] — Smoke test del dev server.
  - **Comando**: vite dev server arranca en :5173 sin warnings; admin login OK; navegar a `/reporteria/financiera`; ver la fila de `d8c22ebb-…`; click "Ver detalle" → navega a `/facturacion/d8c22ebb-…`; ve el detalle con las 7 secciones.
  - **Validación**: screenshot manual + comando curl al endpoint del nuevo page.

- [ ] **T-HU-X.7-T5** [REFACTOR] — Update `openspec/changes/hu-x-facturacion-admin/{proposal,exploration,design}.md` con los PRs finales (commits + líneas merged).

  **Commit suggestion**: `test(web_admin): HU-X.7 — cobertura final + a11y + i18n + smoke`.

  **Exit criteria X.7**: 4 tests verdes; full suite verde; typecheck/lint clean; dev server arranca sin warnings; smoke test OK.

## Validation matrix (consolidated)

| Layer | Validator | Threshold |
|---|---|---|
| BE unit + integration | `pytest backend/tests` con testcontainers | REQ-OPS-203: 4 tests green; total 14 nuevos; coverage ≥80% en el custom handler |
| BE lint | `ruff check` + `mypy --strict` | 0 errors |
| FE unit | `pnpm --filter @apps/web_admin vitest run` | 30+ new scenarios green (4 api + 12 detalle + 1 menu + 1 homehub + 3 dialog reimprimir + 3 dialog anular + 4 dialog reclamo + 1 a11y + tests de lista 2 + 1 homehub) |
| FE types + lint | `tsc --noEmit` + `eslint` | 0 errors |
| a11y | `@axe-core/playwright` en `FacturaDetalle` | 0 WCAG 2.1 AA violations |
| schema drift | `python openspec/scripts/check_schema_match.py` | exits `0`; no migration |

## Risk acknowledgements (carryover)

- **R-X.1** — Custom handler de `factura-pagos` puede romper consumers
  pre-existentes. Audit: 0 matches en `apps/`. Bajo.
- **R-X.2** — Custom handler debe mantener shape del response idéntico
  al factory. Mitigación: tests con snapshot comparison.
- **R-X.3** — Acciones (anular/reclamo) son append-only, pueden confundir
  al admin. Mitigación: `FacturaEstadoBadge` muestra "Anulada — solicitud
  {uuid}" cuando hay `anulaciones` row.
- **R-X.4** — Sandbox F.6 limitation: e2e de dialogs son vitest unit con
  mocks, no playwright real.

## Closed risks (NONE — first PR of the change)

## Forward hooks

- HU-X.8 — listado standalone `/facturacion` con búsqueda global.
- Display endpoint enriquecido (`GET /admin/facturacion/facturas/{uuid}/display`) para mostrar cliente real en drill-down (alternativa C de REQ-X-03).
- Polling realtime de FE via SWR `refreshInterval` o WebSocket (v2).
- Extender el filter `?uuid_factura=…` a los otros 3 endpoints (`factura-detalle`, `factura-impuestos`, `factura-otros-cobros`).
- Refactor del factory `make_router` con soporte de filtros per-resource (riesgo cross-cutting).
