# Spec Delta: hu-f1-5-mv-ocupacion-diaria

> **Change**: `hu-f1-5-mv-ocupacion-diaria`
> **Capability**: `operational`
> **Date**: 2026-09-14
> **Source of truth**: `openspec/changes/hu-f1-5-mv-ocupacion-diaria/proposal.md`
> (D-HU-F1.5-1..10, KD-1..6 + D-7 NEW), `exploration.md` (14 secciones, KD-1..6
> preliminares, archivos a tocar §13), `design.md` (11 secciones, 7 KD, SQL
> skeleton §4, Python skeleton §5, endpoint §6, schema §7, repo §8, threat
> matrix §9, traceability §10, test plan §11), `verify-report.md`
> (SHIPPED, 4/4 REQ, 7/7 KD, 18/18 tasks, 0 CRITICAL/HIGH/MEDIUM, 3 LOW
> pre-existing baseline, 1 deliberate deviation D-F1.5-1 KD-6-respecting),
> `plan.md` (HU-F1.5 lines 707–731, DEC-SUC-11 línea 426, polling 10s
> línea 1427, dependencia F1.6-T3 línea 792, RIESGO-SUC-02 línea 2677),
> `modelo_datos_er.mmd` (`ingreso` 577–596 [L-E], `cantidad_vehiculos_sucursal`
> 428–446 [V], `tipos_vehiculo` 87–104 [V], `salidas` 761–777 [A],
> `anulaciones` [L-W]).
>
> **Precedente upstream**: este change extiende la capability **operational**
> ya consolidada en `openspec/specs/operations/spec.md` (último REQ-OPS-NNN
> vigente: REQ-OPS-029 tras el merge de HU-F1.3 en `4d530a4`). HU-F1.5
> introduce 4 requirements nuevos (REQ-OPS-030..033) sobre esa misma
> capability; los REQ-OPS-001..029 NO se modifican.

## Purpose

HU-F1.5 closes the "almost-live" occupancy gap for the operator screen
(`plan.md:1422-1442` F4.3 `OcupacionStrip`) and the cupo-validation
prerequisite for F1.6 (`plan.md:792` `POST /operacion/ingresos`):

1. **Materialized view `prod.mv_ocupacion_diaria`** — encapsulate the
   "ingreso activo" predicate (`ingreso - salidas - anulaciones`,
   grouped by `(uuid_sucursal, uuid_tipo_vehiculo)`) as a single source
   of truth. Today `api/v1/operacion.py:152-168` derives the active
   state per-row ad-hoc; the MV materializes it for every combination
   at once, base of the polling pattern. **DEC-SUC-11** at `plan.md:426`
   forbids a mutable `disponible` column on `cantidad_vehiculos_sucursal`:
   the MV is the only acceptable implementation.
3. **`GET /api/v1/operacion/ocupacion?uuid_sucursal=X`** — the
   per-tipo breakdown endpoint, read-only, with per-sucursal
   authorization (KD-3): `operador-` pinned, `admin-` scoped to
   `claims["sucursales_permitidas"]`. Always returns `200 OK`; never
   `404`/`503` for the missing-cupo case (KD-6 accepts `disponible < 0`
   as a valid signal that the admin has not configured capacity).
4. **Refresh worker `parkos_core.jobs.refresh_mv_ocupacion`** — a
   dedicated NSSM service (`python -m parkos_core.jobs.refresh_mv_ocupacion`)
   with `REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria`
   + KD-5 fallback to plain `REFRESH` on failure + `asyncio.sleep(10)`
   between cycles. Lag max `2 × refresh_interval_s` documented as
   `RIESGO-SUC-02`.

The migration `0024_add_mv_ocupacion_diaria.py` creates the MV, the
`UNIQUE INDEX CONCURRENTLY` (KD-2 mandatory for `REFRESH CONCURRENTLY`),
and the pre-flight `DO $$` block (KD-7: 10M NOTICE / 50M ABORT). The
worker subclasses `WorkerRunner` verbatim (zero modifications to
`jobs/runner.py` — `worker_base_intact` CI gate from F1.1 / F1.3
precedent). The endpoint is a thin pass-through to
`repo/ocupacion.py::get_ocupacion_puros_activos` which encapsulates the
SQL JOIN (`tipos_vehiculo` LEFT JOIN `cantidad_vehiculos_sucursal` LEFT
JOIN `mv_ocupacion_diaria` — D-F1.5-1 KD-6-respecting refactor).

## ADDED Requirements

### REQ-OPS-030 — `GET /api/v1/operacion/ocupacion?uuid_sucursal=X` returns per-tipo breakdown with `Cache-Control: no-store`

**Given** a JWT request reaches `GET /api/v1/operacion/ocupacion`
carrying either an `operador-` or `admin-` issuer and a valid `TenantContext`
(extracted by `get_tenant_ctx`, F1.2)
**When** the handler `get_ocupacion` resolves the target `uuid_sucursal`
via `(query_param OR ctx.sucursal_uuid)` and the `operador-/admin-`
authorization chain (KD-3) passes
**Then** the endpoint MUST return `200 OK` with a body matching
`OcupacionResponse { uuid_sucursal: UUID, items: list[OcupacionItem],
generado_en: datetime }` where each `OcupacionItem` carries
`{ uuid_tipo_vehiculo: UUID, tipo: str, cupo_maximo: int, activos: int,
disponible: int }` ordered `ORDER BY tv.tipo` (KD-4 deterministic order)
**And** the response MUST include the header `Cache-Control: no-store`
(consistent with F1.3 R8 / F1.8 R8) on every `2xx`/`4xx`/`5xx` response
emitted by the handler
**And** the endpoint MUST NOT mutate state: `INSERT|UPDATE|DELETE|TRUNCATE|MERGE`
tokens MUST NOT appear in the handler body, enforced by the AST walk
in `tests/static/test_no_write_in_ocupacion.py`
**And** the SQL MUST use bind params (`:uuid_sucursal`) — NO string
interpolation — enforced by the helper signature
`get_ocupacion_puros_activos(session, *, uuid_sucursal: UUID)`.
**RFC 2119**: MUST (response shape, header, ordering, bind params,
no write verbs); SHALL (the JSON response use ISO-8601 with `Z` suffix
for `generado_en`).

#### Scenario: operador queries own branch returns 200 with breakdown
**Given** an `operador-` JWT carrying `ctx.sucursal_uuid = X` and the
branch has 1 active `ingreso(X, Auto)` with `cantidad_vehiculos_sucursal(X, Auto) = 50`
and 0 active `ingreso(X, Moto)`
**When** the operator calls
`GET /operacion/ocupacion?uuid_sucursal=X`
**Then** the response MUST be `200 OK` with
`{ uuid_sucursal: X, items: [{ uuid_tipo_vehiculo: T_auto, tipo: "Auto",
cupo_maximo: 50, activos: 1, disponible: 49 }, { uuid_tipo_vehiculo:
T_moto, tipo: "Moto", cupo_maximo: 0, activos: 0, disponible: 0 }],
generado_en: "2026-09-14T...Z" }`
**And** the `Cache-Control: no-store` header MUST be present.

#### Scenario: admin queries branch within permitted set returns 200
**Given** an `admin-` JWT carrying `claims["sucursales_permitidas"] = [X, Y]`
and the request includes `X-Sucursal-Context: X`
**When** the admin calls
`GET /operacion/ocupacion?uuid_sucursal=X`
**Then** the response MUST be `200 OK` with the breakdown for branch X.
**And** the `Cache-Control: no-store` header MUST be present.

#### Scenario: cupo not configured surfaces `disponible < 0`, response remains 200
**Given** branch X has `tipos_vehiculo(Auto, Moto)` vigente but no
`cantidad_vehiculos_sucursal` row for `(X, Auto)` (admin has not
configured capacity) and 3 active `ingreso(X, Auto)`
**When** an operator calls `GET /operacion/ocupacion?uuid_sucursal=X`
**Then** the response MUST be `200 OK` (NEVER `404` / `503`) with the
Auto item carrying `{ cupo_maximo: 0, activos: 3, disponible: -3 }`
**And** the `Cache-Control: no-store` header MUST be present.
**And** the client is the authority on UX (`-3` is interpreted as
"configuration missing, contact admin" — KD-6 invariant).

### REQ-OPS-031 — Per-sucursal authorization with typed errors (KD-3 chain)

**Given** a JWT request reaches `GET /api/v1/operacion/ocupacion` with
either an `operador-` or `admin-` issuer prefix
**When** the handler `get_ocupacion` resolves the target `uuid_sucursal`
**Then** the dependency chain MUST be `_ingreso_issuer_dep =
requires_issuer("operador-", "admin-")` (already defined at
`api/v1/operacion.py:64`) followed by `get_tenant_ctx` and `get_session`
**And** if `uuid_sucursal` query param is absent AND
`ctx.sucursal_uuid is None` (e.g. `admin-` issuer without
`X-Sucursal-Context` header and without `claims["sucursales_permitidas"]`),
the handler MUST raise `HTTPException(status_code=400, detail={"error":
"missing_sucursal_context"})`
**And** if the issuer is `operador-` AND `target != ctx.sucursal_uuid`
(cross-tenant), the handler MUST raise
`TenantScopeViolation(actor_uuid=ctx.actor_uuid)` (existing typed error
in `auth/tenancy.py:60-65`) which the global exception handler maps to
`403 {"error": "tenant_scope_violation"}`
**And** if the issuer is `admin-` AND `target not in
ctx.claims["sucursales_permitidas"]`, the handler MUST raise
`SucursalNotPermitted(target_sucursal=target)` (existing typed error in
`auth/tenancy.py:115-131`) which maps to
`403 {"error": "sucursal_not_permitted"}`
**And** the response body MUST contain **only** the typed error
discriminator (`tenant_scope_violation`, `sucursal_not_permitted`,
`missing_sucursal_context`); the pgcode `"23505"`, the raw Postgres
error message, the `uuid_sucursal` value, and any driver-level diagnostic
strings MUST NOT appear in the body, headers, or any log line emitted
at `info` or higher visibility
**And** the precedence MUST be strictly
`400 missing_sucursal_context > 403 tenant_scope_violation > 403 sucursal_not_permitted`;
no other ordering is permitted.
**RFC 2119**: MUST (issuer acceptance, 400, 403 mappings, no pgcode in
body, precedence); SHALL (log the rejection at `warning` level with
`event="ocupacion_authz_rejected"` and `actor_uuid`/`issuer_prefix` for
ops triage, but without the pgcode and without the target value).

#### Scenario: operador cross-tenant returns 403 `tenant_scope_violation`
**Given** an `operador-` JWT with `ctx.sucursal_uuid = X`
**When** the operator calls
`GET /operacion/ocupacion?uuid_sucursal=Y` (different branch)
**Then** the response MUST be `403 Forbidden` with body
`{"error": "tenant_scope_violation"}`
**And** the body MUST NOT contain `uuid_sucursal=Y`, no pgcode, no
driver string.

#### Scenario: admin without context returns 400 `missing_sucursal_context`
**Given** an `admin-` JWT without `X-Sucursal-Context` header AND without
`claims["sucursales_permitidas"]`
**When** the admin calls `GET /operacion/ocupacion` (no query param)
**Then** the response MUST be `400 Bad Request` with body
`{"error": "missing_sucursal_context"}`
**And** the body MUST NOT contain the `uuid_sucursal` value.

#### Scenario: admin outside permitted set returns 403 `sucursal_not_permitted`
**Given** an `admin-` JWT with `claims["sucursales_permitidas"] = [X]`
**When** the admin calls
`GET /operacion/ocupacion?uuid_sucursal=Z` (Z not in permits)
**Then** the response MUST be `403 Forbidden` with body
`{"error": "sucursal_not_permitted"}`
**And** the body MUST NOT contain `uuid_sucursal=Z`.

### REQ-OPS-032 — `prod.mv_ocupacion_diaria` materialized view with `CREATE UNIQUE INDEX CONCURRENTLY` + pre-flight `DO $$` (KD-7 10M NOTICE / 50M ABORT)

**Given** an Alembic migration `0024_add_mv_ocupacion_diaria.py` is
applied against a Postgres database where `prod.ingreso`,
`prod.salidas`, `prod.anulaciones`, `prod.tipos_vehiculo`,
`prod.cantidad_vehiculos_sucursal` already exist
**When** the migration's `upgrade()` executes
**Then** the migration MUST first execute a pre-flight `DO $$` block
that runs `SELECT count(*) INTO _n_ingreso FROM prod.ingreso`,
`SELECT count(*) INTO _n_anul FROM prod.anulaciones`, `SELECT count(*)
INTO _n_salidas FROM prod.salidas`, and emits
`RAISE NOTICE 'mv_ocupacion_diaria_preflight: prod.ingreso=% filas,
prod.salidas=% filas, prod.anulaciones=% filas. El primer REFRESH puede
tardar segundos a minutos.'`
**And** if `_n_ingreso > 50_000_000` (KD-7 hard limit), the block MUST
emit `RAISE EXCEPTION 'mv_ocupacion_diaria_preflight_abort: prod.ingreso
tiene % filas (umbral 50M). Aplique índice (uuid_sucursal,
uuid_tipo_vehiculo) en prod.ingreso antes de continuar.'` which aborts
the migration with a typed message; Alembic MUST record no version
bump on abort (rollback automatic)
**And** the migration MUST then execute `CREATE MATERIALIZED VIEW
prod.mv_ocupacion_diaria AS SELECT i.uuid_sucursal, i.uuid_tipo_vehiculo,
count(*) AS activos FROM prod.ingreso i WHERE i.uuid_tipo_vehiculo IS
NOT NULL AND NOT EXISTS (SELECT 1 FROM prod.salidas s WHERE
s.uuid_ingreso = i.uuid AND s.uuid_sucursal = i.uuid_sucursal) AND NOT
EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_ingreso = i.uuid
AND a.estado = 'ejecutada' AND a.tipo_anulable IN ('ingreso', 'salida'))
GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo`
**And** the migration MUST then execute `CREATE UNIQUE INDEX CONCURRENTLY
IF NOT EXISTS prod.uq_mv_ocupacion_diaria_sucursal_tipo ON
prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo)` —
mandatory for `REFRESH MATERIALIZED VIEW CONCURRENTLY` (KD-2); the
natural composite is unique by the view's `GROUP BY`, NO synthetic
column is added
**And** the migration MUST then execute `GRANT SELECT ON
prod.mv_ocupacion_diaria TO parkos_app`
**And** `revision` MUST equal `"0024_mv_ocupacion_diaria"` and
`down_revision` MUST equal `"0023_unique_active_sesion_per_user"` (F1.3
chain head, commit `ca3f9bf`)
**And** `downgrade()` MUST execute `DROP MATERIALIZED VIEW IF EXISTS
prod.mv_ocupacion_diaria` (drops the view + its indexes).
**RFC 2119**: MUST (pre-flight, threshold constants, MV definition,
CONCURRENTLY, GRANT, downgrade symmetry, chain head); SHALL (constants
`_PREFLIGHT_THRESHOLD_INFO = 10_000_000` and
`_PREFLIGHT_THRESHOLD_ABORT = 50_000_000` extracted at module level for
traceability); SHOULD (operator schedules rollback off-peak because
`DROP MATERIALIZED VIEW` acquires `AccessExclusiveLock` regardless of
`CONCURRENTLY`).

#### Scenario: pre-flight NOTICE at 10M rows, no abort
**Given** the `prod.ingreso` table holds between `10_000_001` and
`50_000_000` rows
**When** migration `0024_add_mv_ocupacion_diaria` applies
**Then** the pre-flight MUST emit a `RAISE NOTICE` carrying the exact
prefix `mv_ocupacion_diaria_preflight: prod.ingreso=` with the row count
**And** the migration MUST NOT abort (10M is informational only).
**And** the view MUST be created, the UNIQUE INDEX applied, and the
GRANT issued.

#### Scenario: pre-flight EXCEPTION at 50M+ rows aborts the migration
**Given** the `prod.ingreso` table holds `50_000_001` rows (or more)
**When** migration `0024_add_mv_ocupacion_diaria` applies
**Then** the pre-flight MUST emit `RAISE EXCEPTION` carrying the exact
prefix `mv_ocupacion_diaria_preflight_abort:` with the offending count
**And** Alembic MUST record no version bump (no half-applied state)
**And** the view MUST NOT exist after rollback (`prod.mv_ocupacion_diaria`
absent from `pg_class`).

#### Scenario: UNIQUE INDEX CONCURRENTLY is created outside transaction
**Given** a clean Postgres database where the migration is being applied
**When** the upgrade function reaches the UNIQUE INDEX statement
**Then** Postgres MUST execute `CREATE UNIQUE INDEX CONCURRENTLY IF NOT
EXISTS prod.uq_mv_ocupacion_diaria_sucursal_tipo ON
prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo)` without
acquiring `AccessExclusiveLock` on the underlying table
**And** `pg_index.indisunique` MUST equal `True` for the new index.
**And** the migration MUST be idempotent against `alembic upgrade` retries
(IF NOT EXISTS avoids `42P07` `duplicate_object`).

### REQ-OPS-033 — `RefreshMvOcupacionWorker` executes `REFRESH CONCURRENTLY` + KD-5 fallback + `asyncio.sleep(refresh_interval_s=10)` post-cycle

**Given** a dedicated NSSM service runs
`python -m parkos_core.jobs.refresh_mv_ocupacion` against the branch
database with `PARKOS_BRANCH_DB_DSN` configured
**When** `RefreshMvOcupacionWorker(WorkerRunner)` enters its
`async def cycle()` body
**Then** the worker MUST first attempt
`await self._session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY
prod.mv_ocupacion_diaria"))` + `await self._session.commit()` (KD-5
happy path)
**And** if the CONCURRENTLY branch raises any exception (typically
because the UNIQUE INDEX was dropped, or because Postgres is under
load), the worker MUST log at `warning` level with structured
`extra={"event": "refresh_mv_concurrently_failed_fallback",
"exception_class": type(exc).__name__}` (NO pgcode, NO repr of the
exception, NO DSN fragment — R6 mitigation), MUST
`await self._session.rollback()`, and MUST fall back to
`await self._session.execute(text("REFRESH MATERIALIZED VIEW
prod.mv_ocupacion_diaria"))` + `await self._session.commit()` (KD-5
fallback, plain REFRESH, brief `AccessExclusiveLock`)
**And** if the fallback also raises, the worker MUST log at `error`
level with `extra={"event": "refresh_mv_ocupacion_both_branches_failed",
"exception_class": type(inner_exc).__name__}` and MUST
`await self._session.rollback()` — the worker MUST NOT crash the loop;
the next cycle retries fresh (NO circuit breaker)
**And** after the refresh — successful or fallback — the worker MUST
`await asyncio.sleep(self.refresh_interval_s)` (default `10s`, floored
to `max(5, ...)` in `__init__`) before the next cycle (R1 startup
resilience: refresh runs immediately after worker restart, not after
sleep)
**And** the CLI MUST be invokable as
`python -m parkos_core.jobs.refresh_mv_ocupacion --refresh-interval-s 10
--database-url $PARKOS_BRANCH_DB_DSN` with exit codes inherited from
`WorkerRunner` (0 success / 1 application error / 2 SIGTERM)
**And** the `WorkerRunner` base (`backend/packages/parkos_core/src/
parkos_core/jobs/runner.py`) MUST remain unmodified — verified by the
`worker_base_intact` CI gate (`git diff jobs/runner.py` returns empty).
**RFC 2119**: MUST (cycle shape, KD-5 fallback, inner-resilience, log
shape with `exception_class` only, post-cycle sleep, CLI, base intact);
SHALL (the structured log keys `event` and `exception_class` be present
in every warning/error line emitted by the worker cycle); SHOULD
(deploy ONE service per branch DB — documented in the NSSM install guide,
not in code).

#### Scenario: normal cycle executes REFRESH CONCURRENTLY then sleeps
**Given** a `RefreshMvOcupacionWorker(session=mock, refresh_interval_s=10)`
with the UNIQUE INDEX present
**When** `cycle()` is awaited once
**Then** the worker MUST call `session.execute` with exactly
`text("REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria")`
**And** the worker MUST call `session.commit()`
**And** the worker MUST call `asyncio.sleep(10)` AFTER the refresh
(post-cycle sleep, R1 resilience).

#### Scenario: KD-5 fallback when CONCURRENTLY fails
**Given** a `RefreshMvOcupacionWorker(session=mock_with_concurrently_failure,
refresh_interval_s=10)` whose first `session.execute` raises
`psycopg2.errors.FeatureNotSupported` (simulating missing UNIQUE INDEX)
**When** `cycle()` is awaited
**Then** the worker MUST log a `warning` line with structured
`event="refresh_mv_concurrently_failed_fallback"` and
`exception_class="FeatureNotSupported"`
**And** the worker MUST call `session.rollback()`
**And** the worker MUST call `session.execute` again with exactly
`text("REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria")` (plain,
no `CONCURRENTLY`)
**And** the worker MUST call `session.commit()`
**And** the worker MUST NOT raise (the cycle completes — KD-5 acceptance).
**And** the captured log MUST NOT contain the substring `pgcode` or the
literal `"23505"` (R6 mitigation).

#### Scenario: both branches fail does not crash the loop
**Given** a `RefreshMvOcupacionWorker(session=mock_double_failure)` whose
both REFRESH attempts raise exceptions
**When** `cycle()` is awaited
**Then** the worker MUST log an `error` line with structured
`event="refresh_mv_ocupacion_both_branches_failed"` and
`exception_class=...` (matching the inner exception class)
**And** the worker MUST call `session.rollback()` (twice)
**And** the worker MUST return normally without raising (next cycle
retries fresh — no crash, no circuit breaker).

## Modified Capabilities

- `operational`: HU-F1.4 vigente filter (REQ-OPS-017..021), HU-F1.8
  cotización surface (REQ-OPS-022..025), and HU-F1.3 sesión única
  (REQ-OPS-026..029) are preserved unchanged; this delta adds the
  read-only `GET /operacion/ocupacion` endpoint with KD-3 per-sucursal
  authorization, the `prod.mv_ocupacion_diaria` materialized view with
  UNIQUE INDEX + pre-flight, and the `RefreshMvOcupacionWorker` with
  KD-5 fallback (REQ-OPS-030..033). The merged main spec
  (`openspec/specs/operations/spec.md`) gains four requirements and no
  existing requirement is modified.
- `backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py`
  (NUEVO, ~142 LOC) — pre-flight `DO $$` with `_n_ingreso/_n_anul/_n_salidas`
  counts + `RAISE NOTICE` 10M / `RAISE EXCEPTION` 50M + `CREATE MATERIALIZED
  VIEW prod.mv_ocupacion_diaria` (NOT EXISTS salidas + NOT EXISTS
  anulaciones) + `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
  prod.uq_mv_ocupacion_diaria_sucursal_tipo ON prod.mv_ocupacion_diaria
  (uuid_sucursal, uuid_tipo_vehiculo)` + `GRANT SELECT ON
  prod.mv_ocupacion_diaria TO parkos_app` + `DROP MATERIALIZED VIEW`
  downgrade. `revision = "0024_mv_ocupacion_diaria"`,
  `down_revision = "0023_unique_active_sesion_per_user"`. KD-2 + KD-7.
- `backend/packages/parkos_core/src/parkos_core/jobs/refresh_mv_ocupacion.py`
  (NUEVO, ~177 LOC) — `RefreshMvOcupacionWorker(WorkerRunner)` with
  `DEFAULT_REFRESH_INTERVAL_S = 10`; `__init__(self, *, session:
  AsyncSession, refresh_interval_s: int = 10)` flooring at `max(5, ...)`;
  `async def cycle()` executing `REFRESH MATERIALIZED VIEW CONCURRENTLY`
  + commit, fallback `REFRESH MATERIALIZED VIEW` plain + commit on
  failure (KD-5), inner-resilience `refresh_mv_ocupacion_both_branches_failed`
  log, post-cycle `asyncio.sleep(self.refresh_interval_s)` (R1
  resilience); CLI `main(argv)` with `--refresh-interval-s` and
  `--database-url`. NO modifications to `jobs/runner.py` (`worker_base_intact`
  CI gate). KD-1 + KD-5.
- `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py`
  (NUEVO, ~128 LOC) — `@dataclass(frozen=True) class OcupacionItemRow`
  with `@property def disponible(self) -> int: return self.cupo_maximo
  - self.activos`; `async def get_ocupacion_puros_activos(session:
  AsyncSession, *, uuid_sucursal: uuid_lib.UUID) -> list[OcupacionItemRow]`
  with bind-param SQL JOIN (`FROM prod.tipos_vehiculo tv LEFT JOIN
  prod.cantidad_vehiculos_sucursal cvs … LEFT JOIN prod.mv_ocupacion_diaria
  mv … WHERE tv.vigente_hasta IS NULL ORDER BY tv.tipo`). **D-F1.5-1**
  KD-6-respecting: `tipos_vehiculo` drives (LEFT JOIN MV), not MV
  LEFT JOIN `tipos_vehiculo` — surfaces every configured tipo even when
  `activos == 0` (F4.3 `OcupacionStrip` empty-state UX). KD-4 + KD-6.
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py`
  (MODIFICAR, +106/-1 LOC) — handler `get_ocupacion` registered via
  `@router.get("/ocupacion", response_model=OcupacionResponse,
  responses={400, 403, 503})`; KD-3 chain: target resolution →
  `400 missing_sucursal_context` → `403 tenant_scope_violation` (operador-)
  / `403 sucursal_not_permitted` (admin-); delegates SQL to repo helper;
  sets `response.headers["Cache-Control"] = "no-store"`. `api/v1/__init__.py`
  remains untouched (router mounted at línea 143). KD-3 + KD-4.
- `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py`
  (MODIFICAR, +38 LOC) — `OcupacionItem(uuid_tipo_vehiculo, tipo,
  cupo_maximo, activos, disponible)` and `OcupacionResponse(uuid_sucursal,
  items: list[OcupacionItem], generado_en: datetime)`; both inherit
  `extra='forbid'` from `_Base` (F1.8 precedent); `disponible` may be
  negative (KD-6 documented inline). KD-6.
- `backend/tests/unit/test_operacion_ocupacion.py` (NUEVO, ~510 LOC, 4
  parametrized tests) — T1 operador self 200, T2 operador cross-tenant
  403 `tenant_scope_violation`, T3 admin allowed branch 200, T4 admin
  no-context 400 `missing_sucursal_context`. REQ-OPS-030 + REQ-OPS-031.
- `backend/tests/integration/test_mv_ocupacion_diaria_db.py` (NUEVO,
  ~380 LOC, 2 tests) — T1 `insert_ingreso + REFRESH → activos=1,
  cupo_maximo=0, disponible=-1` (KD-6 valid negative); T2
  `insert_ingreso + insert_salida + REFRESH → empty` (NOT EXISTS
  predicate verified). REQ-OPS-030 + REQ-OPS-032.
- `backend/tests/integration/test_migration_0024_mv.py` (NUEVO, ~462 LOC,
  2 tests) — T1 `apply with dirty data (5 ingresos, 2 salidas, 1
  anulada) → view + UNIQUE INDEX OK`; T2 `preflight_aborts_on_simulated_50m_rows`
  via mock count(`*`) > 50_000_000. REQ-OPS-032.
- `backend/tests/integration/test_refresh_mv_job.py` (NUEVO, ~221 LOC,
  2 tests) — T1 normal `cycle()` with `AsyncMock(spec=AsyncSession)`;
  T2 `FeatureNotSupported` on CONCURRENTLY → KD-5 fallback to plain
  REFRESH + `refresh_mv_concurrently_failed_fallback` log (no pgcode).
  REQ-OPS-033.
- `backend/tests/static/test_no_write_in_ocupacion.py` (NUEVO, ~127 LOC,
  1 test) — AST walk over `api/v1/operacion.py::get_ocupacion` rejects
  `INSERT|UPDATE|DELETE|TRUNCATE|MERGE|FOR UPDATE|FOR SHARE` tokens
  outside strings/comments. Locks the read-only contract (REQ-OPS-030).
- `openspec/specs/operations/spec.md` (raíz) — entry in
  `## Modified Capabilities`: "GET /operacion/ocupacion endpoint with
  per-tipo breakdown + Cache-Control no-store (REQ-OPS-030)" +
  "Per-sucursal authorization with typed errors 400/403 (REQ-OPS-031)" +
  "`prod.mv_ocupacion_diaria` materialized view + UNIQUE INDEX
  CONCURRENTLY + pre-flight `DO $$` (REQ-OPS-032)" + "RefreshMvOcupacionWorker
  with KD-5 fallback + CLI (REQ-OPS-033)".

## Out of Scope

- `admin-` cross-branch global visibility (consult any `uuid_sucursal`
  globally) — out of scope; admin_views cloud-only is a separate product.
  KD-3 limits to `claims["sucursales_permitidas"]`.
- Push of occupancy via WebSocket / SSE — out of scope; the client
  polls every 10s (`plan.md:1422-1442`). Long-lived connections are
  outside the operational SLA.
- `OcupacionMaterializadaError` 503 surface (D-HU-F1.5-8) — declared
  in proposal but not exercised in F1.5 because `REFRESH CONCURRENTLY`
  typically succeeds; the endpoint MAY return 503 only when the MV is
  catastrophically unavailable. Future observability HU owns the
  metrics + alerts (`refresh_duration_s > refresh_interval_s`).
- `GET /operacion/ocupacion/{uuid_tipo_vehiculo}` filtered by tipo —
  the breakdown fits in one response JSON; no server-side filter needed.
- `SELECT … FOR SHARE` pessimistic lock on `ingreso` / `salidas` /
  `anulaciones` — the materialized view uses MVCC snapshot consistency;
  atomicity is guaranteed by `REFRESH CONCURRENTLY` with UNIQUE INDEX.
- `(uuid_sucursal, uuid_tipo_vehiculo)` index on `prod.ingreso` to
  accelerate the first refresh — precondition documented in pre-flight
  (>50M rows aborts); out of scope.
- NSSM installation of `refresh_mv_ocupacion` — operational ownership
  belongs to `infra/`; this change delivers the script only.
- Frontend versioning (Fase 2 — `OcupacionStrip` consumes the endpoint).
- Metrics / observability of the refresh (cycle counter, p99 latency,
  alerts on lag) — aligned with the future F1.X observability HU.
- `categorias_vehiculo` table to group tipos (Auto/Moto/Camioneta) —
  does not exist in the ER; not introduced here.
- `GET /operacion/ocupacion/resumen` aggregated
  `{cupo_total, activos_total, disponible_total}` — KD-4 chose
  per-tipo breakdown; the client computes aggregate when needed.
- Auto-cleanup of orphans (active sessions without close, ingresos
  without salida) — owner decides manually.
- Replicating the materialized view pattern to other `[L-*]` tables
  (e.g. `prod.caja`, `prod.factura`) — out of scope; the pattern is
  documented for future reference.
- Circuit breaker with auto-recovery after N successful refreshes —
  KD-5 accepts transient failures; breaker is a future observability
  concern.