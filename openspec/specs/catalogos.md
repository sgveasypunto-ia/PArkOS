# Catalogos Specification

## Purpose

Cliente-side surface for the operador to view the tarifa aplicable to a given vehicle type, always the vigente at the moment of the query. Mirrors the server-side HU-F1.4 contract (`GET /api/v1/empresa/tarifas-sucursal?vigente_en=<ahora>`). The cliente MUESTRA el valor — nunca lo calcula (DEC-SUC-12 verbatim; A-02 tiempo_tar_plena server-side only).

This spec covers the second reusable primitive of the `catalogos` feature (HU-F4.1 = `useTiposVehiculo`, HU-F4.2 = `useTarifasVigentes`, HU-F4.3 = ocupacion).

## Requirements

### Requirement: Cliente must display the tarifa vigente for the detected vehicle type

The system SHALL surface, for the detected `uuid_tipo_vehiculo`, the row from `prod.tarifas_sucursal` where `vigente_desde <= NOW() AND (vigente_hasta IS NULL OR vigente_hasta > NOW()) AND estado = 'activo'`. The cliente MUST NOT compute the cotización total — server-side only (DEC-SUC-12).

The system MUST expose a SWR hook `useTarifasVigentes(uuidTipoVehiculo: string)` returning `{ tarifa: TarifaVigente | null, fetchedAt: number | null, isStale: boolean, isFromFallback: boolean, refresh(): Promise<void> }`. The system MUST cache the last successful response in `electron-store` under the key `parkos.tarifas.cache.v1` and hydrate it as `fallbackData` on first paint.

#### Scenario: Tipo detectado → tarifa vigente

- GIVEN `useTarifasVigentes('uuid-auto')` is invoked with a valid `accessToken`
- AND `GET /api/v1/empresa/tarifas-sucursal?vigente_en=<ahora-utc>` returns 200 with a list including the row `{ uuid_tipo_vehiculo: 'uuid-auto', valor: 8000, valor_plena: 80000, ... }`
- WHEN the SWR fetch resolves
- THEN `tarifa.valor === 8000`
- AND `tarifa.valor_plena === 80000`
- AND `fetchedAt` is a non-null `number` (epoch ms of the resolution)
- AND `isStale === false`
- AND `isFromFallback === false`

#### Scenario: API caída → cache válido

- GIVEN `useTarifasVigentes('uuid-auto')` is invoked
- AND `electron-store` has key `parkos.tarifas.cache.v1` with `{ items: [...], fetchedAt: <recent-ts> }`
- AND `GET /api/v1/empresa/tarifas-sucursal?vigente_en=...` returns `ParkosHttpError 500`
- WHEN the hook renders
- THEN `tarifa` equals the cached item for `uuid_tipo_vehiculo === 'uuid-auto'`
- AND `fetchedAt === <recent-ts>`
- AND `isStale === false` (within the 1h window)
- AND `isFromFallback === true`

#### Scenario: Cache >1h → stale mark

- GIVEN `useTarifasVigentes('uuid-auto')` is invoked
- AND `electron-store` has key `parkos.tarifas.cache.v1` with `fetchedAt: <now - 2h>`
- AND the API is unreachable (5xx or network)
- WHEN the hook renders
- THEN `tarifa` equals the cached value
- AND `isStale === true`
- AND the `<TarifaBadge>` renders the stale mark
- AND the stale help text element has `id="tarifa-stale-help"`
- AND the badge container has `aria-describedby="tarifa-stale-help"`

#### Scenario: Cambio de tarifa programada entrando en vigencia

- GIVEN `useTarifasVigentes('uuid-auto')` last resolved at T0 with `valor: 8000`
- AND a backend-managed bi-temporal swap publishes a new row for `('uuid-auto')` whose `vigente_desde` falls between T0 and now
- WHEN `dedupingInterval` (5 min) expires
- AND SWR revalidates against `GET ...?vigente_en=<now>`
- THEN `tarifa.valor` reflects the NEW row (the previous row is no longer vigente)
- AND `fetchedAt` updates to the new resolution timestamp
- AND no application restart is required

### Requirement: Cache invalidation must follow uuid_tipo_vehiculo changes

The system SHALL treat the cache as key-less (one snapshot per branch). When the consumer passes a different `uuid_tipo_vehiculo`, the hook MUST return the matching item from the SAME cached snapshot (not refetch). The next SWR revalidation cycle will refresh the underlying snapshot.

#### Scenario: Invalidación tras cambio de tipo (same session, cache hit)

- GIVEN `useTarifasVigentes('uuid-auto')` returns `{ valor: 8000 }` from the cache
- WHEN the consumer renders `useTarifasVigentes('uuid-moto')` with the SAME cached snapshot
- THEN the hook returns `{ valor: 4000 }` (the moto row from the cache)
- AND NO additional HTTP request fires (cache served from SWR dedup)

### Requirement: Cliente must NEVER compute el tiempo de tarifa plena (A-02)

The system MUST NOT derive `tiempo_tar_plena = (valor_plena / valor) * unidad_minutos` in the cliente. That derivation is the responsibility of `prod.calcular_cotizacion(:uuid_ingreso)` (PL/pgSQL, F1.8). The cliente MAY display `valor_plena` literally as a separate field if the supervisor UI needs it, but MUST NOT use it for any time math.

#### Scenario: Cliente nunca computa tiempo_tar_plena

- GIVEN the hook returns `valor: 100` and `valor_plena: 10000`
- WHEN the renderer accesses any derived time field
- THEN no field of type `tiempo_*` is exposed by the hook
- AND the renderer MUST call a dedicated cotización endpoint (out of F4.2 scope) to obtain any time-derived value

## Error Catalog

| Code | Trigger | UX behavior | Severity |
|------|---------|-------------|----------|
| `tarifas_endpoint_missing` | Backend `GET /api/v1/empresa/tarifas-sucursal` not reachable AND `electron-store` has no `parkos.tarifas.cache.v1` key. (Note: HU-F1.4 endpoint is shipped; this code is for the edge case where the endpoint is removed in a future rollback.) | Badge hidden (`tarifa === null`). NO error toast. | blocker for spec scope — flagged as a follow-up risk only. |
| `tarifas_cache_stale` | `fetchedAt` is older than 1h AND the API is unreachable. | Badge renders the cached value with the stale mark + `aria-describedby`. NO error toast. | warning, not error. |

## Notes

- The dedicated HU-F1.4 handler (`backend/.../api/v1/empresa.py:179-213`) exposes `vigente_en` as a query param but does NOT expose `uuid_tipo_vehiculo`. The cliente filters `uuid_tipo_vehiculo` from the returned `TarifasSucursalRead[]` (consistent with F4.1 `useTiposVehiculo` pattern: full catalog → consumer filters). The dataset for a branch is small (<50 rows at `limit=50`); client-side filter is the documented refinement.
- `formatCOP` reused from `apps/electron-sucursal/src/features/caja/lib/format.ts` (F3.3, already shipped and tested with the exact fixtures `"$ 8.000"` and `"$ 1.234.567"`). No new formatter module.
- WCAG 2.1 AA wiring: stale help is a hidden `text` element (`sr-only` or visually-hidden) reachable via `aria-describedby`. DEC-SUC-10 — `@axe-core/playwright` 0-violation gate covers it.
- DEC-SUC-12 server-side-only calculation: this spec never invokes a calculation; it only displays the row the server already returned. The cliente does not need `valor_plena` math.