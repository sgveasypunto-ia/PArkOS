# Proposal: HU-F4.1 — Detección de tipo de vehículo por placa (frontend)

## Intent

The operador needs the system to detect the vehicle type (`Auto` / `Moto`) automatically when they type a placa in the ingreso form — no manual selector, no override. This HU ships the first reusable validation primitive of the `catalogos` feature and the first purely-client-side regex function of the `web_sucursal` renderer.

## Scope

### In Scope
- Pure function `detectarTipoVehiculo(placa): 'Auto' | 'Moto' | null` at `apps/electron-sucursal/src/lib/validation/placa.ts`.
- SWR hook `useTiposVehiculo()` at `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts`, with a hardcoded `{auto, moto}` fallback when the local `api-sucursal` is unreachable.
- 6 unit tests for the pure function (plus 2 constant tests) at `src/lib/validation/__tests__/placa.test.ts` (already co-located at `src/lib/validation/placa.test.ts`).
- Inline error message `operacion.placa_formato_invalido` in i18n namespace `operacion`.

### Out of Scope
- Any backend change. `GET /api/v1/catalogos/tipos-vehiculo` is already mounted at `backend/.../api/v1/catalogos.py:140-147` (verified, NOT a blocker).
- The type-tolerant search `buscarIngresoTolerante()` (Fase 7, CU-02/03 salida) — lives in a separate function in a separate file by design (DEC-SUC-22).
- New regex formats (Bicicleta / Patineta) — the corpus has no CU justification (A-03 explicit note).
- Persistence of the regex anywhere — the ER has no `regex_pattern` column on `tipos_vehiculo` (4NF canon).

## Capabilities

### New Capabilities
- `operacion`: frontend-side placa validation and vehicle-type detection for the ingreso flow.

### Modified Capabilities
- None. `openspec/specs/operations/spec.md` REQ-OPS-038 (server-side V5 regex derivation) is unchanged — this HU complements it from the renderer.

## Approach

Pure deterministic function (regex-only, no network, no DOM, no store) + a SWR hook with `dedupingInterval: 5*60*1000` and a literal hardcoded `{auto, moto}` fallback. Hardcoded regex per A-03; no tolerance per DEC-SUC-22. Backend `repo/placa.py::detectar_tipo_vehulo()` stays the server-side authority (defense in depth — server overwrites client `uuid_tipo_vehiculo`).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `apps/electron-sucursal/src/lib/validation/placa.ts` | New | Pure detection function + exported regex constants. |
| `apps/electron-sucursal/src/lib/validation/placa.test.ts` | New | 6 verbatim test cases U1..U6 from `plan.md:1381` (+ U7/U8 constant tests). |
| `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` | New | `parkosFetch` wrapper around `GET /api/v1/catalogos/tipos-vehiculo`. |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` | New | SWR hook + hardcoded fallback + `isFromFallback` flag. |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | Modified | Adds `operacion.placa_formato_invalido` key. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Regex drift between client and backend | Low | JSDoc cross-reference (`operacion.py:215-277`) + the existing CI integration test for `repo/placa.py` catches divergence. |
| Operator types an unsupported placa format | Medium | Inline error message literal; field stays open for correction; no override path (BR2 CU-01). |
| Catalog API down → empty screen | Medium | Hardcoded `{auto, moto}` fallback + `isFromFallback` flag for downstream `<Tooltip>` surface (F4.3/F6.x). |

## Rollback Plan

Delete the 3 new files (`placa.ts`, `placa.test.ts`, `tiposVehiculoApi.ts`, `useTiposVehiculo.ts`) and the i18n key. No DB migration, no backend change, no other consumer depends on these artifacts yet (F4.2/F4.3/F6.x ship later).

## Dependencies

- Backend endpoint `GET /api/v1/catalogos/tipos-vehiculo` — **already mounted**, verified in `backend/.../api/v1/catalogos.py:140-147`. Not a blocker.
- `@parkos/ui-kit/fetch` `ParkosHttpError` and `useAuthStore` from the shared kit (F2.x precedent).

## Success Criteria

- [ ] 6 verbatim tests U1..U6 (`plan.md:1381`) plus constant tests U7/U8 pass.
- [ ] `vitest run src/lib/validation/__tests__/placa.test.ts` exits 0.
- [ ] No file outside `openspec/changes/fase-4-1-deteccion-tipo-vehiculo/` and Engram was modified.