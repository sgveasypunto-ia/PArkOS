# Delta for operations — qa-2026-09-17-bug-remediation

> **Change**: `qa-2026-09-17-bug-remediation` · **Phase**: spec · **Capability**: `operations`
> **Delta**: 5 ADDED (REQ-OPS-131..135). **Delivery**: single PR.

---

## ADDED Requirements

### Requirement: REQ-OPS-131 — `AuthUser.uuid` + `<FormMessage>` for `uuid_*`

`useAuth()` MUST return `user: { uuid: string; email: string }`. `AbrirTurno` MUST read `user?.uuid` and render inline `<FormMessage>` for `uuid_sucursal`/`uuid_usuario`. Invalid token MUST collapse to `404 not_found` (REQ-OPS-108). (Previously N/A)

#### Scenario: AuthUser shape + Zod inline reject
- **Given** mock `/auth/me` returns `{ uuid: 'u-1', email: 'op@parkos.local' }` and `sucursal?.uuid = ''`
- **When** `AbrirTurno` submits
- **Then** return MUST be `{ user: { uuid: 'u-1', ... } }` (no `user.id`); Zod MUST reject empty `uuid_sucursal`; `<FormMessage>` MUST render.

#### Scenario: invalid token → 404 not_found
- **Given** `accessToken` is expired
- **When** `useAuth()` refreshes
- **Then** response MUST be 404 `not_found`; `useAuthStore.clear()` + `parkos:auth:cleared` MUST dispatch.

---

### Requirement: REQ-OPS-132 — `useOcupacion` fetcher closure

Hook MUST call `useSWR(key, () => getOcupacion(uuid_sucursal), opts)` — fetcher ignores the SWR key. Mirrors `useSesionActiva.ts:55-57` (REQ-OPS-120) and `useIngresoActivo.ts:67-69`. (Previously N/A)

#### Scenario: fetcher receives raw UUID, not the key
- **Given** `uuid_sucursal = 's-1'` and SWR key = `/operacion/ocupacion?uuid_sucursal=s-1`
- **When** `useOcupacion()` invokes the fetcher
- **Then** `getOcupacion` MUST be called with `'s-1'` (no `?` query string)
- **And** `useOcupacion.test.ts::test_fetcher_receives_uuid_not_key` MUST assert `mock.calls[0][0] === 's-1'`.

#### Scenario: 10s polling cadence preserved
- **Given** operator with active polling (REQ-OPS-022 cadence, REQ-OPS-033 refresh)
- **When** SWR cycle elapses
- **Then** `refreshInterval: 10_000` MUST persist and `Cache-Control: no-store` MUST hold.

---

### Requirement: REQ-OPS-133 — `prod.mv_ocupacion_diaria` MUST exist; CI gate enforces it

`check_schema_match.py` MUST assert `to_regclass('prod.mv_ocupacion_diaria') IS NOT NULL` on branch DB. Migration `0034_recreate_mv_ocupacion_diaria_idempotent.py` MUST use `CREATE OR REPLACE VIEW … AS SELECT …` + post-upgrade `to_regclass` abort-on-miss. Migration `0024` MUST gain `IF NOT EXISTS`. (Previously N/A; extends REQ-OPS-032)

#### Scenario: CI gate fails when MV missing
- **Given** branch DB without `prod.mv_ocupacion_diaria` (bug-3 drift)
- **When** `python openspec/scripts/check_schema_match.py` runs in CI
- **Then** exit code MUST be non-zero; stdout MUST contain `mv_ocupacion_diaria_missing`.

#### Scenario: migration 0034 heals already-0024 container
- **Given** `alembic_version = '0024_mv_ocupacion_diaria'` but MV is absent
- **When** `alembic upgrade head` applies 0034
- **Then** `CREATE OR REPLACE VIEW` MUST recreate the view, post-upgrade `to_regclass` MUST pass, `RefreshMvOcupacionWorker` MUST refresh next cycle.

---

### Requirement: REQ-OPS-134 — `detectar_tipo_vehiculo` lowercase + explicit UUID

`repo/placa.py::detectar_tipo_vehiculo` MUST look up `TiposVehiculo.tipo IN ('carro', 'moto', 'bicicleta', 'patineta')` (lowercase, matching `replicate_catalogs_to_branch.py:20`). When payload carries explicit `uuid_tipo_vehiculo`, handler MUST honour it first; else fall back to regex. `test_repo_placa.py` MUST seed lowercase rows. (Previously N/A; extends REQ-OPS-038)

#### Scenario: regex-matched plate resolves to lowercase `carro`
- **Given** `TiposVehiculo` seeded with `{ tipo: 'carro' }` (no `Auto` row)
- **When** `detectar_tipo_vehiculo('ABC123')` runs
- **Then** it MUST return the `uuid_tipo_vehiculo` whose `tipo='carro'`.

#### Scenario: explicit UUID overrides regex; invalid plate still 422
- **Given** payload carries `uuid_tipo_vehiculo = T_moto` AND plate matches `FORMATO_AUTO`
- **When** the ingreso handler resolves the tipo
- **Then** `T_moto` MUST be used (regex ignored); `INSERT INTO prod.ingreso` MUST reference `T_moto`
- **And** plate `XY-Z-99` with no explicit UUID MUST still return 422 `placa_formato_invalido`.

---

### Requirement: REQ-OPS-135 — `prod.sesion.observaciones: TEXT NULL` end-to-end

Per REQ-OPS-119, the backend MUST add `observaciones: TEXT NULL` on `prod.sesion`, surface it in `SesionCreate` (`max_length=500`), `Sesion` ORM, `open_session`. Migration `0035_add_observaciones_to_sesion.py` MUST use `ALTER TABLE … ADD COLUMN … TEXT NULL` (PG11+ instant, ADR-002 AUDIT-FIRST). When provided, value MUST be persisted into `prod.log_transaccional.datos_nuevos`. (Previously N/A; extends REQ-OPS-119)

#### Scenario: POST `/caja-sesion/sesiones` accepts `observaciones` + audit log
- **Given** `SesionCreate` payload includes `observaciones: 'Apertura turno mañana'`
- **When** the operator submits the form
- **Then** response MUST be `200 OK` with `SesionRead.observaciones = 'Apertura turno mañana'`
- **And** `prod.log_transaccional.datos_nuevos->>'observaciones'` MUST equal `'Apertura turno mañana'`.

#### Scenario: `observaciones` omitted → NULL; `extra='forbid'` rejects unknowns
- **Given** payload omits `observaciones` but includes unknown `foo: 'bar'`
- **When** POST runs
- **Then** `prod.sesion.observaciones` MUST be `NULL` and response MUST be 422 `extra_forbidden`.

---

## Cross-reference table

| REQ-OPS | Bug | Files affected | Anchor REQ |
|---|---|---|---|
| 131 | 1 | `apps/ui-kit/src/hooks/useAuth.ts`, `AbrirTurno.tsx`, `useAuth.test.ts`, `AbrirTurno.test.tsx` | REQ-OPS-119, REQ-OPS-106..112 |
| 132 | 2 | `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.ts`, `useOcupacion.test.ts` (NEW) | REQ-OPS-022, REQ-OPS-024, REQ-OPS-033 |
| 133 | 3 | `migrations/versions/0034_recreate_mv_ocupacion_diaria_idempotent.py` (NEW), `0024_…` (modify), `openspec/scripts/check_schema_match.py` | REQ-OPS-031, REQ-OPS-032 |
| 134 | 4 | `backend/.../repo/placa.py`, `api/v1/operacion.py`, `tests/unit/test_repo_placa.py` | REQ-OPS-038 |
| 135 | 5 | `migrations/versions/0035_add_observaciones_to_sesion.py` (NEW), `models/L_S/sesion.py`, `schemas/caja.py`, `repo/session_cycle.py` | REQ-OPS-119 |