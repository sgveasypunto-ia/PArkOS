# Design: HU-F1.5 — Materialized view `prod.mv_ocupacion_diaria` + `GET /operacion/ocupacion`

> **Change**: `hu-f1-5-mv-ocupacion-diaria`
> **Phase**: design (sdd-design)
> **HU**: HU-F1.5 — Materialized view `prod.mv_ocupacion_diaria` (refresh 10s) + custom endpoint `GET /api/v1/operacion/ocupacion?uuid_sucursal=X` + worker `RefreshMvOcupacionWorker`
> **Date**: 2026-09-14
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `b5dd006`)
> **PR target**: `origin/dev`
> **Source of truth**: `proposal.md` (D-HU-F1.5-1..10 with KD-1..KD-6 + D-7 NEW) + `exploration.md` + `spec.md` + `specs/operational/spec.md` (REQ-OPS-030..033 RFC 2119).
> **Cross-references**: `plan.md` (HU-F1.5 lines 707–731, DEC-SUC-11 línea 426, `cantidad_vehiculos_sucursal` SELECT vía vista línea 2619, `mv_ocupacion_diaria` línea 2646, dependencia F1.6-T3 línea 792, polling 10s línea 1427, RIESGO-SUC-02 línea 2677), `modelo_datos_er.mmd` (`ingreso` 577–596 [L-E], `cantidad_vehiculos_sucursal` 428–446 [V], `tipos_vehiculo` 87–104 [V], `salidas` 761–777 [A], `anulaciones` [L-W]),
> precedent `openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/design.md` (partial unique index `CONCURRENTLY` + custom handler + AST walk, commit `ca3f9bf`),
> precedent `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/design.md` (PL/pgSQL migration + `WorkerRunner` + `SyncSucursalWorker` ciclo async, commit `de4d2fc`),
> `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (router custom, `_ingreso_issuer_dep` línea 64, `cotizar_ingreso_handler` línea 219),
> `backend/packages/parkos_core/src/parkos_core/jobs/runner.py` (`BaseRunner` + `WorkerRunner` con SIGTERM/SIGINT, exit codes 0/1/2 §21.7),
> `backend/packages/parkos_core/src/parkos_core/jobs/sync_sucursal.py` (`SyncSucursalWorker` con `cycle()` async + `DEFAULT_POLL_INTERVAL_S = 10`, líneas 103 + 266),
> `backend/packages/parkos_core/migrations/versions/0023_unique_active_sesion_per_user.py` (última migración aplicada — **0024 es el próximo slot disponible**, commit `ca3f9bf`),
> `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` (`TenantContext` + `get_tenant_ctx` + errores tipados líneas 60-65 y 115-131),
> `backend/packages/parkos_core/src/parkos_core/api/deps.py` (`get_tenant_ctx` + `requires_issuer`).

## 1. Title & Goal

**Design goal.** Deliver HU-F1.5: the back-end "almost-live" cup-count infrastructure that the F4.3 `OcupacionStrip` polls every 10s (and F1.6 validates incoming vehicles against) — materializing the "ingreso activo" predicate (`ingreso - salidas - anulaciones`) into a server-side materialized view `prod.mv_ocupacion_diaria`, refreshed by a dedicated NSSM worker `RefreshMvOcupacionWorker`, exposed via `GET /api/v1/operacion/ocupacion?uuid_sucursal=X` returning a per-tipo breakdown `[{uuid_tipo_vehiculo, tipo, cupo_maximo, activos, disponible}, ...]`. The design enforces `plan.md` **DEC-SUC-11** line 426 (cupo availability NEVER held in a mutable `disponible` column on `cantidad_vehiculos_sucursal` — it is always derived via the MV), closes the **F1.6-T3** validator prerequisite (plan línea 792) and the **F4.3** `OcupacionStrip` polling prerequisite, and preserves the read-only contract for the new endpoint with defense-in-depth at the DB (unique index required for `CONCURRENTLY` refresh), the worker (KD-5 fallback to plain `REFRESH`), and the test layer (AST walk + integration). Sized at **~160 LOC** (plan línea 723): ~80 LOC migration + ~30 LOC worker + ~30 LOC endpoint + ~20 LOC schemas, plus the dedicated `repo/ocupacion.py` helper that encapsulates the SQL JOIN.

## 2. Context & Background

`plan.md` lines **707–731** define HU-F1.5 as a Fase-1 backend prerequisite. The hard architectural constraint is **DEC-SUC-11** at línea **426**: "disponibilidad nunca se mantiene por trigger sobre una columna mutable en `cantidad_vehiculos_sucursal`; la tabla solo guarda el cupo máximo configurado (`cantidad` int), y el cálculo siempre compara `cupo_maximo` contra ingresos activos vía vista materializada". This VETOES the "trigger that decrements `disponible`" pattern that would otherwise be the obvious implementation; the ER enforces bi-temporal versioning (`[V]` tables in `modelo_datos_er.mmd`, vigente_desde/hasta, no in-place mutation). Consequently, availability is **derived**, not persisted: from `prod.ingreso` (577–596, [L-E] insert-only) minus `prod.salidas` (761–777, [A] append-only) minus `prod.anulaciones` (L-W, ejecutada), filtered by `(uuid_sucursal, uuid_tipo_vehiculo)`. The contract is captured in **REQ-OPS-030..033** (added by `sdd-spec` to `specs/operations/spec.md`):

- **REQ-OPS-030** — endpoint `GET /operacion/ocupacion?uuid_sucursal=X` returning `OcupacionResponse` (breakdown by `tipo_vehiculo`) with `Cache-Control: no-store`.
- **REQ-OPS-031** — authorization per-sucursal: `operador-` pinned to `ctx.sucursal_uuid` (cross-tenant → `403 tenant_scope_violation`); `admin-` restricted to `claims["sucursales_permitidas"]` (no header → `400 missing_sucursal_context`).
- **REQ-OPS-032** — `prod.mv_ocupacion_diaria` created via Alembic migration with UNIQUE INDEX `CONCURRENTLY` and pre-flight `DO $$` block reporting row counts and aborting with `RAISE EXCEPTION` if `prod.ingreso` exceeds the 50M row threshold.
- **REQ-OPS-033** — `RefreshMvOcupacionWorker` (`WorkerRunner` subclass) executes `REFRESH MATERIALIZED VIEW CONCURRENTLY` with fallback to plain `REFRESH` on failure (KD-5) and `asyncio.sleep(refresh_interval_s=10)` between cycles.

The 10-second refresh cadence is mandatory per `plan.md` línea **1427** ("polling 10s desde el cliente") and matches `jobs/sync_sucursal.py:103` `DEFAULT_POLL_INTERVAL_S = 10` — the prior art for the cycle contract. The MV is the **first** materialized view in the schema (precedent `0009_add_derived_read_views.py` only ships `CREATE OR REPLACE VIEW` plain views; grep `MATERIALIZED` against `migrations/` returns zero hits), making this a foundational pattern for any future aggregation needing CONCURRENTLY refresh. F1.5 is consumed by **F1.6** (línea 792, `POST /operacion/ingresos` validates cupo against `mv_ocupacion_diaria` before INSERT) and **F4.3** (línea 1422-1442, `OcupacionStrip` polling). Live risk **RIESGO-SUC-02** (línea 2677) documents the lag as an accepted operating characteristic; KD-5 owns the mitigation surface.

## 3. Decisions

This HU adopts **seven** Key Decisions. Each one passes the R5 risk threshold (no open question blocks the design; the proposal §12 confirms `Ninguna abierta`).

### Decision KD-1 — Dedicated NSSM worker `parkos_core.jobs.refresh_mv_ocupacion`, NOT in-process asyncio task in `api-sucursal` lifespan

**Choice.** The refresh runs as a separate process invoked by `python -m parkos_core.jobs.refresh_mv_ocupacion`, registered as a Windows service via NSSM alongside the existing `job_sync_sucursal` and `job_sync_cloud` (or analogous systemd unit in production Linux deployment). The worker subclasses the existing `WorkerRunner` (`backend/packages/parkos_core/src/parkos_core/jobs/runner.py`) without modification, inherits SIGTERM/SIGINT signal handling and exit codes 0/1/2, and runs `RefreshMvOcupacionWorker.cycle()` in a `while not self._stop_event.is_set()` loop with `await asyncio.sleep(self.refresh_interval_s)` post-cycle.

**Context.** `jobs/sync_sucursal.py` and `jobs/sync_cloud.py` are precedent: each worker is its own process, CLI entrypoint is `python -m parkos_core.jobs.<name>`, framework handles signals and exit codes. Two topologies were considered; rejecting the in-process asyncio task in `api-sucursal` lifespan keeps operational concerns split: a crash or OOM in `api-sucursal` does not pause the MV refresh (KD-1 acceptance). Reversibility is trivial — flip the NSSM entry to `python -m parkos_core.jobs.refresh_mv_ocupacion` and restart.

**Alternatives considered.**
- *In-process asyncio task in `api-sucursal` `lifespan`* — rejected: couples `api-sucursal` lifecycle to the MV refresh, introduces second NSSM service requirement unchanged, and silently breaks the polling if `api-sucursal` restarts (the operator sees a stale strip without alert until 30s+). The operational cost of one extra service is low and well-documented.
- *Single worker handling both `sync_sucursal` and MV refresh* — rejected: would force `sync_sucursal.py` to gain a third polling dimension unrelated to its sync semantics; violates single-responsibility and complicates rollout/rollback.

**Rationale.** Worker-separated topology is the established pattern in `jobs/`; the cost (one extra NSSM service definition in `infra/`) is well below the benefit (independent restart, isolating `api-sucursal` from refresh-task bugs). Forward-compatible: any future CONCURRENTLY-refreshable MV (e.g., F1.7 occupancy-per-day rollups) can clone `RefreshMvOcupacionWorker` and reuse `WorkerRunner` without rewriting base classes.

### Decision KD-2 — `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS prod.uq_mv_ocupacion_diaria_sucursal_tipo` on `(uuid_sucursal, uuid_tipo_vehiculo)` — natural unique columns, NO synthetic key

**Choice.** The UNIQUE INDEX uses the natural composite `(uuid_sucursal, uuid_tipo_vehiculo)` columns, built outside the transaction via `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`. Postgres MVCC requires a UNIQUE INDEX on a materialized view for `REFRESH MATERIALIZED VIEW CONCURRENTLY` to work; without it, the only `REFRESH` mode available is full-lock (`AccessExclusiveLock`), incompatible with the 10s polling contract. The natural composite is unique **by construction** (the view's `GROUP BY` collapses N rows into one per combination), so no `row_number() OVER (...)` synthetic column is added — keeping the view minimal and its column set readable.

**Context.** Precedent `0009_add_derived_read_views.py` only ships plain views (no INDEX); precedent `0023_unique_active_sesion_per_user.py` is a partial unique index on `prod.sesion` (a base table). F1.5 introduces the **first** materialized view in the schema, so the INDEX-on-MV precedent is set here. `CONCURRENTLY` requires the operation to run outside a transaction; Alembic's `op.execute` runs in autocommit per statement, satisfying the rule (same idiom as F1.3). `IF NOT EXISTS` makes the migration **idempotent** against `alembic upgrade` retries — a critical property because CONCURRENTLY is the only operation that bypasses the standard `alembic_version` table re-creation pattern.

**Alternatives considered.**
- *Synthetic `row_id bigserial` column* — rejected: pollutes the view schema, complicates JOINs, requires `nextval('seq_mv_ocupacion_diaria')` exposure in `repo/ocupacion.py` for nothing.
- *No UNIQUE INDEX, use plain `REFRESH MATERIALIZED VIEW`* — rejected: takes `AccessExclusiveLock`, blocks reads for the refresh duration (typically < 100ms but bursts can be 1-2s during peak rotation). Incompatible with N-operator polling.
- *Hash-based `(md5(uuid_sucursal::text || uuid_tipo_vehiculo::text))` UNIQUE INDEX* — rejected: same uniqueness property but stored as larger bytea, slower to scan, no benefit over the natural composite.

**Rationale.** The natural composite is unique by the view's `GROUP BY`; the UNIQUE INDEX is therefore correctness-equivalent to a `row_id` surrogate without the schema cost. KD-2 also imposes a **future invariant** for F1.7+: any column-set partition of this view (e.g., adding `fecha_ingreso`) must preserve `(uuid_sucursal, uuid_tipo_vehiculo)` uniqueness OR add a synthetic column. Documented in `proposal.md §11` as R4.

### Decision KD-3 — Per-sucursal authorization: `operador-` pinned, `admin-` scoped to `claims["sucursales_permitidas"]`

**Choice.** `GET /operacion/ocupacion` applies `_ingreso_issuer_dep = requires_issuer("operador-", "admin-")` (already defined at `operacion.py:64`). Resolution chain:
1. `uuid_sucursal: UUID | None = Query(None)`.
2. If `None` (or unset), default to `ctx.sucursal_uuid` from `TenantContext`.
3. If still `None` (admin- issuer with no `X-Sucursal-Context` header), return `400 missing_sucursal_context`.
4. If `operador-` issuer and `uuid_sucursal != ctx.sucursal_uuid`, return `403 tenant_scope_violation` (existing typed error in `auth/tenancy.py:60-65`).
5. If `admin-` issuer and `uuid_sucursal` not in `ctx.claims["sucursales_permitidas"]`, return `403 sucursal_not_permitted` (same body shape as F1.8 R8).

**Context.** `auth/tenancy.py:115-131` already implements this exact pattern for `admin-` issuer-scoped cross-tenant writes; F1.5 reuses the helper without modification. KD-3 deliberately **does not** grant `admin-` cross-branch global visibility (that surface is reserved for `admin_views` cloud-only product, which is out of scope per `proposal.md §3.2` goal 6). The cross-branch boundary remains consistent: branch-local `admin-` sees only the branches it is currently allowed to operate.

**Alternatives considered.**
- *`admin-` global cross-tenant read* — rejected: violates the `admin_views` cloud-only boundary; leaks cross-branch data over the branch DB replica; not aligned with `claims["sucursales_permitidas"]` semantics already in `auth/tenancy.py`.
- *`operador-` and `admin-` get same response shape on tenant violation* — rejected: hides the security boundary from ops dashboards; KD-3 keeps the typed discriminator (`tenant_scope_violation` vs `sucursal_not_permitted`) for SIEM.
- *`operador-` only; admin must query `admin_views`* — rejected: `operacion.py` already accepts both issuers at `cotizar_ingreso_handler` (line 219); F4.3 `OcupacionStrip` is used by both operator and admin personas per `plan.md:1422-1442`.

**Rationale.** Issuer-scoped authorization reuses F1.8's `requires_issuer` mechanism verbatim; the only novel surface is the per-sucursal value check, which is identical to the established pattern. KD-3 blocks cross-branch data leak at the HTTP boundary without re-engineering tenancy: the SQL itself (`WHERE mv.uuid_sucursal = :uuid_sucursal`) parameterizes the value, so the authz check is the gate, not a hidden SQL filter.

### Decision KD-4 — Response shape is the **per-tipo breakdown** (not per-sucursal aggregate)

**Choice.** `OcupacionResponse.items` is `list[OcupacionItem]`, one entry per `(uuid_tipo_vehiculo)` with `cupo_maximo`, `activos`, `disponible`. The aggregate per-sucursal fields (`cupo_total`, `activos_total`, `disponible_total`) are NOT included in the response — the client computes the aggregate by summing `items[*].cupo_maximo` etc. when needed. Rows are ordered `ORDER BY tv.tipo` (Auto, Moto, etc.) so the strip rendering is deterministic without client-side sort.

**Context.** `plan.md:713` explicitly requests the breakdown: the F4.3 `OcupacionStrip` renders "Auto: 23/50" per `tipo`, and the data model naturally segments by `tipo_vehiculo` (per-vehicle-category occupancy is the operational concern — load-balancing vehicles across capacity is the parking manager's day-to-day work). KD-4 keeps the response size linear in the cardinality of `tipos_vehiculo` (typically 3-6 rows), bounded and stable for the polling client.

**Alternatives considered.**
- *Aggregate only: `{cupo_total, activos_total, disponible_total}`* — rejected: loses operational granularity; F4.3 cannot render "Auto: 23/50, Moto: 12/20"; manager cannot spot when Auto is full but Moto is half-empty.
- *Both aggregate + breakdown in one response* — rejected: doubles payload for a 6-row breakdown; aggregate is trivially computed by the client; the `generado_en` timestamp fills the diagnostic role already.
- *Nested by tipo with sub-arrays* — rejected: a 6-element flat list is simpler to render, simpler to test, simpler to extend.

**Rationale.** The breakdown is the **operative** response (manager + operator care about per-tipo load), and the aggregate is **derived**: pushing derived values to the API creates two sources of truth (server-computed vs client-computed) for the same number. KD-4 keeps the server source minimal and lets the client compute the aggregate if needed.

### Decision KD-5 — Accept `2 × refresh_interval_s` lag; fallback `REFRESH MATERIALIZED VIEW` on `CONCURRENTLY` failure (no circuit breaker)

**Choice.** `RefreshMvOcupacionWorker.cycle()` executes `REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria`; on any `psycopg2` or `asyncpg` exception during the CONCURRENTLY refresh, it logs `refresh_mv_concurrently_failed_fallback` at `warning` (with the exception class + truncated message, NO `pgcode` leakage to client surfaces), then falls back to `REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria` (plain, full-lock refresh). After the refresh — successful or fallback — `await asyncio.sleep(self.refresh_interval_s)` (10s default) before the next cycle. NO circuit breaker: a sequence of failures does not pause the worker; each cycle attempts fresh.

**Context.** `REFRESH MATERIALIZED VIEW CONCURRENTLY` requires the UNIQUE INDEX from KD-2; if the index has been dropped (manual operator intervention, hot-fix migration rollback), `CONCURRENTLY` fails immediately with a stable Postgres error class. Plain `REFRESH` is a worst-case fallback that takes an `AccessExclusiveLock` for a brief window (typically < 100ms during nightly rotation, possibly 1-2s during peak hours). KD-5 accepts that the endpoint may return `503 OcupacionMaterializadaError` with `Retry-After: 10` during the full-lock window — preferable to crashing the worker process. `RIESGO-SUC-02` already documents the lag as an accepted operating characteristic; KD-5 does not add new risk acceptance beyond what the corpus already declares.

**Alternatives considered.**
- *Hard fail on `CONCURRENTLY` error, exit the worker* — rejected: forces NSSM to restart the process every minute; noisy ops alerts; the same recovery action (operator drops/recreates the UNIQUE INDEX) is required regardless.
- *Skip the cycle on error, retain asyncio sleep for the full interval* — rejected: silently swallows failures; the lag compounds indefinitely until operator manually inspects logs.
- *Circuit breaker with auto-recovery after N successful refreshes* — rejected: adds state to the worker; ~50 LOC of breaker logic; F1.5 is a v1 prerequisite, breaker is a F1.X observability concern.

**Rationale.** KD-5 trades a small amount of staleness (max `2 × refresh_interval_s`) for zero-ops recovery on the most common failure mode (missing UNIQUE INDEX). The fallback is observable (log warning) and reversible (operator recreates the index, worker resumes CONCURRENTLY next cycle). R7 in `proposal.md §8` lists the only operational caveat: alert if `refresh_duration_s > refresh_interval_s` (which the corpus already tracks as `RIESGO-SUC-02`).

### Decision KD-6 — `disponible < 0` is a **valid response**, not an error

**Choice.** When `cantidad_vehiculos_sucursal` has no row for `(uuid_sucursal, uuid_tipo_vehiculo)`, the LEFT JOIN returns `NULL`, `COALESCE(cvs.cantidad, 0)` resolves to `0`, and `disponible = 0 - mv.activos`, which can be a negative integer. The endpoint **always returns 200** with the breakdown; it never returns 404 or 503 for the missing-cupo case. The HTTP response includes `cupo_maximo: 0` and `disponible: -activos`, and the client is expected to interpret `disponible < 0` as "configuration missing, contact admin" (client UX policy, not backend contract).

**Context.** DEC-SUC-11 separates the **`cantidad` column** (configured cup, bi-temporal `[V]` versioning) from the **derived `disponible`** (current occupancy). The two are not joined at write-time; they are joined at read-time in the view. If `cantidad_vehiculos_sucursal` is missing for a `(sucursal, tipo)` combination (newly added tipo without admin-configured capacity), the breakdown still tells the operator: "N autos están dentro, el cupo configurado es 0". The negative number is a clearer signal than a 404 because it preserves the active count (`activos`) for ops triage.

**Alternatives considered.**
- *404 if `cantidad_vehiculos_sucursal` is missing* — rejected: hides the active count from the operator exactly when they most need it (the moment they have > 0 vehicles parked without cupo configured).
- *503 `cupo_no_configurado` typed error* — rejected: this is not a service-degradation case; the view is alive and current; the configuration gap is an admin-level concern.
- *Default `cupo_maximo` to a sentinel (e.g., `999999`) when missing* — rejected: masks the configuration gap in the data, defeats the purpose of derived cupos.

**Rationale.** The endpoint is **read-only and stateful** (it reports the current state of derived occupancy); the configuration gap is part of that state. KD-6 makes the gap **visible** to the operator (the strip would render "Auto: -5/N/A" or similar) and **actionable** to the admin (the response carries the active count for triage). The client UX layer decides whether to render `disponible < 0` as a warning, a CTA, or a hidden field.

### Decision KD-7 — Pre-flight `DO $$` block in migration 0024 reports row counts (`RAISE NOTICE`), aborts only at the 50M row threshold (R5 mitigation)

**Choice.** The migration's `upgrade()` opens with a `DO $$ … RAISE NOTICE` block that runs `SELECT count(*) FROM prod.ingreso` and `SELECT count(*) FROM prod.anulaciones` and emits `RAISE NOTICE 'mv_ocupacion_diaria_preflight: prod.ingreso=% filas, prod.anulaciones=% filas'` (informational). If `prod.ingreso` row count exceeds **50_000_000**, the block emits `RAISE EXCEPTION 'mv_ocupacion_diaria_preflight_abort: prod.ingreso tiene % filas (umbral 50M). Aplique índice (uuid_sucursal, uuid_tipo_vehiculo) en prod.ingreso antes de continuar.'` which aborts the migration with a typed message. The **10M informational threshold** is **NOT** an abort — it is a `RAISE NOTICE` for ops awareness only.

**Context.** The first `REFRESH MATERIALIZED VIEW CONCURRENTLY` (after `CREATE MATERIALIZED VIEW`) executes the view's SELECT once to populate the table; on a 1M-row `ingreso` table, the SELECT takes ~30-60s; on a 50M-row table, it can take minutes. KD-7 lets the migration proceed under that overhead (operator sees a `NOTICE` in the alembic log) but refuses to proceed if the overhead would be operationally dangerous (> 50M rows, multiple minutes blocking). KD-7 differs from F1.3's pre-flight (which aborts on any orphan data) in that F1.5 has no exploitable invariant gap: the `GROUP BY` produces correct data regardless of cardinality, only the refresh duration is at risk.

**Alternatives considered.**
- *Abort at 10M like F1.3's orphan abort* — rejected: 10M is a normal operational scale for a regional parking chain; aborting at 10M would block valid deployments. The 10M figure is informational, not operational.
- *No pre-flight at all* — rejected: operators cannot estimate the migration duration; the 50M case is rare but operationally expensive (multi-minute DDL with potential timeout on managed Postgres).
- *Pre-flight using `EXPLAIN` on the view query* — rejected: requires creating the view first to EXPLAIN; chicken-and-egg with the migration order.

**Rationale.** KD-7 protects the most extreme case (> 50M rows, multi-minute DDL, potential managed-Postgres statement timeout) while letting the normal-operational case (sub-10M rows, sub-60s refresh) proceed without ceremony. The 10M NOTICE is the soft signal; the 50M EXCEPTION is the hard stop. R5 in `proposal.md §8` lists the only operational caveat: the `DO $$` block is transactional, so the rollback on EXCEPTION is automatic (Alembic records no version bump). R5 mitigation is asymmetric: informational 10M is acceptable documentation; aborting 50M forces the operator to add an index on `prod.ingreso`, which is F1.5-OOS but documented in the migration message.

## 4. SQL Skeleton

**Path**: `backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py`.

The structural skeleton is reproduced here for the apply phase; this is the placeholder that the implementation must follow. The skeleton applies the pre-flight, the CREATE MATERIALIZED VIEW, the UNIQUE INDEX, the GRANT, and the downgrade path. The skeleton is **idempotent** under `alembic upgrade` retries via `IF NOT EXISTS` on the INDEX (CONCURRENTLY requires non-transactional execution, satisfied by Alembic's per-statement autocommit).

```python
"""HU-F1.5: materialized view prod.mv_ocupacion_diaria + UNIQUE INDEX for
REFRESH CONCURRENTLY + per-sucursal breakdown for GET /operacion/ocupacion.

The view encapsulates the "ingreso activo" predicate as a single source of
truth: prod.ingreso rows minus prod.salidas rows minus prod.anulaciones
(tipo_anulable IN ('ingreso','salida'), estado='ejecutada'), grouped by
(uuid_sucursal, uuid_tipo_vehiculo). The UNIQUE INDEX on the natural
composite (uuid_sucursal, uuid_tipo_vehiculo) is mandatory for
REFRESH MATERIALIZED VIEW CONCURRENTLY; without it, plain REFRESH takes an
AccessExclusiveLock that blocks the 10s polling of N operadores.

Pre-flight (KD-7) reports row counts on prod.ingreso + prod.anulaciones
and aborts with RAISE EXCEPTION if prod.ingreso exceeds the 50M row
threshold (R5 mitigation; full table scan on first refresh would otherwise
take minutes and risk statement timeout on managed Postgres).

KEPT IN SYNC WITH: specs/operations/spec.md REQ-OPS-032 (RFC 2119 MUST:
pre-flight; CONCURRENTLY; natural composite UNIQUE INDEX; downgrade).
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0024_mv_ocupacion_diaria"
down_revision = "0023_unique_active_sesion_per_user"  # F1.3 chain
branch_labels = None
depends_on = None


_PREFLIGHT_THRESHOLD_INFO = 10_000_000   # KD-7 informational NOTICE
_PREFLIGHT_THRESHOLD_ABORT = 50_000_000  # KD-7 hard EXCEPTION abort


def upgrade() -> None:
    # 1) Pre-flight: report row counts on prod.ingreso and prod.anulaciones.
    #    The first REFRESH after CREATE MATERIALIZED VIEW executes the
    #    SELECT once to populate the table; on a > 10M-row ingreso table
    #    the SELECT takes minutes. Emit NOTICE so the operator sees the
    #    ETA in the alembic log; abort only if > 50M (R5 mitigation).
    op.execute(
        f"""
        DO $$
        DECLARE
            _n_ingreso bigint;
            _n_anul    bigint;
            _n_salidas bigint;
        BEGIN
            SELECT count(*) INTO _n_ingreso FROM prod.ingreso;
            SELECT count(*) INTO _n_anul    FROM prod.anulaciones;
            SELECT count(*) INTO _n_salidas FROM prod.salidas;
            RAISE NOTICE
                'mv_ocupacion_diaria_preflight: prod.ingreso=% filas, '
                'prod.salidas=% filas, prod.anulaciones=% filas. '
                'El primer REFRESH puede tardar segundos a minutos.',
                _n_ingreso, _n_salidas, _n_anul;
            IF _n_ingreso > {_PREFLIGHT_THRESHOLD_ABORT} THEN
                RAISE EXCEPTION
                    'mv_ocupacion_diaria_preflight_abort: prod.ingreso '
                    'tiene % filas (umbral {_PREFLIGHT_THRESHOLD_ABORT}). '
                    'Aplique índice (uuid_sucursal, uuid_tipo_vehiculo) '
                    'en prod.ingreso antes de continuar.',
                    _n_ingreso;
            END IF;
        END $$;
        """
    )

    # 2) CREATE the materialized view. Initial population is lazy — rows
    #    are computed on first SELECT after CREATE. The first cycle of
    #    RefreshMvOcupacionWorker will materialize the rows; until then
    #    GET /operacion/ocupacion returns the breakdown for the rows that
    #    exist (initially zero). KEEP the SELECT identical to the repo
    #    helper's underlying predicate.
    op.execute(
        """
        CREATE MATERIALIZED VIEW prod.mv_ocupacion_diaria AS
        SELECT
            i.uuid_sucursal,
            i.uuid_tipo_vehiculo,
            count(*) AS activos
        FROM prod.ingreso i
        WHERE
            i.uuid_tipo_vehiculo IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM prod.salidas s
                WHERE s.uuid_ingreso = i.uuid
                  AND s.uuid_sucursal = i.uuid_sucursal
            )
            AND NOT EXISTS (
                SELECT 1 FROM prod.anulaciones a
                WHERE a.uuid_ingreso = i.uuid
                  AND a.estado = 'ejecutada'
                  AND a.tipo_anulable IN ('ingreso', 'salida')
            )
        GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo;
        """
    )

    # 3) UNIQUE INDEX mandatory for REFRESH MATERIALIZED VIEW CONCURRENTLY
    #    (KD-2). CONCURRENTLY cannot run inside a transaction; Alembic's
    #    op.execute uses autocommit per statement, satisfying the rule.
    #    IF NOT EXISTS makes this migration idempotent against retries.
    op.execute(
        """
        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
            prod.uq_mv_ocupacion_diaria_sucursal_tipo
        ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo);
        """
    )

    # 4) Grant SELECT to the application role. The parkos_app role already
    #    has SELECT on prod.ingreso / salidas / anulaciones / cvs / tv;
    #    this GRANT is for the new MV only.
    op.execute(
        "GRANT SELECT ON prod.mv_ocupacion_diaria TO parkos_app;"
    )


def downgrade() -> None:
    # DROP MATERIALIZED VIEW drops its indexes too (including the UNIQUE
    # INDEX); explicit DROP INDEX is not required. CONCURRENTLY on a
    # DROP MATERIALIZED VIEW has no analog (DROP acquires AccessExclusive
    # regardless); for production rollbacks the operator should schedule
    # off-peak.
    op.execute(
        "DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria;"
    )


__all__ = ["upgrade", "downgrade"]
```

**Notes.**

- `revision = "0024_mv_ocupacion_diaria"` and `down_revision = "0023_unique_active_sesion_per_user"` keep the linear chain consistent (0023 was the F1.3 chain head).
- `CONCURRENTLY` cannot run inside a transaction block. Alembic `op.execute` runs each statement in autocommit by default; the pre-flight `DO $$` block IS transactional but is read-only, so it is safe.
- The pre-flight block's `count(*)` is a **full table scan**; for `prod.ingreso` > 50M rows (rare in branch deployments, common in the cloud-wide reporting replica), the block itself can take minutes. R5 mitigation is asymmetric: the block runs ONCE per migration; it is not on the hot path.
- `IF NOT EXISTS` on the INDEX makes the migration idempotent against `alembic upgrade` retries. The MV itself has no `IF NOT EXISTS` equivalent (use `CREATE OR REPLACE VIEW` for plain views, but `MATERIALIZED VIEW` does not support it — the migration must roll forward or be torn down via downgrade before re-applying).
- The downgrade `DROP MATERIALIZED VIEW IF EXISTS` removes the view and its indexes. Operator is responsible for scheduling the rollback off-peak (DROP acquires `AccessExclusiveLock` regardless of `CONCURRENTLY`).

## 5. Python Skeleton

**Path**: `backend/packages/parkos_core/src/parkos_core/jobs/refresh_mv_ocupacion.py`.

The worker subclasses `WorkerRunner` (verbatim, zero modifications to `jobs/runner.py`) and implements `cycle()` async. The class is registered with `python -m parkos_core.jobs.refresh_mv_ocupacion` via `__main__`; `WorkerRunner.main()` wraps `cycle()` in the standard SIGTERM/SIGINT handling loop and the 0/1/2 exit codes (§21.7). The skeleton calls `REFRESH MATERIALIZED VIEW CONCURRENTLY` first and falls back to plain `REFRESH` on failure (KD-5).

```python
"""HU-F1.5: refresh worker for prod.mv_ocupacion_diaria.

Operates as a separate NSSM service (KD-1) with the same shape as
parkos_core.jobs.sync_sucursal.cycle(). Cycle:

    try:
        REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria
    except Exception:
        log warning refresh_mv_concurrently_failed_fallback
        REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria
    asyncio.sleep(refresh_interval_s)  # default 10s

The CONCURRENTLY branch requires the UNIQUE INDEX (KD-2); if the index is
missing, Postgres returns a stable error class and we fall back to plain
REFRESH (which takes AccessExclusiveLock briefly, KD-5).

CLI entrypoint:
    python -m parkos_core.jobs.refresh_mv_ocupacion
        --refresh-interval-s 10
        --database-url $PARKOS_BRANCH_DB_DSN
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .runner import WorkerRunner


logger = logging.getLogger("parkos_core.jobs.refresh_mv_ocupacion")


class RefreshMvOcupacionWorker(WorkerRunner):
    """Refreshes prod.mv_ocupacion_diaria every refresh_interval_s seconds.

    Inherits signal handling (SIGTERM/SIGINT) and exit codes 0/1/2 from
    WorkerRunner (jobs/runner.py). NO modifications to the base class.
    """

    DEFAULT_REFRESH_INTERVAL_S = 10  # KD-1: matches F4.3 polling cadence

    def __init__(
        self,
        *,
        session: AsyncSession,
        refresh_interval_s: int = DEFAULT_REFRESH_INTERVAL_S,
    ) -> None:
        super().__init__(name="refresh_mv_ocupacion")
        self._session = session
        # floor at 5s to avoid pathological hot-loops on misconfiguration
        self.refresh_interval_s = max(5, int(refresh_interval_s))

    async def cycle(self) -> None:
        """One REFRESH pass + interval sleep. Always idempotent.

        Tries CONCURRENTLY first (KD-5); falls back to plain REFRESH if
        the UNIQUE INDEX is missing or Postgres is under load. The
        session is committed per branch so a failed branch does not
        poison the next cycle.
        """
        try:
            await self._session.execute(
                text(
                    "REFRESH MATERIALIZED VIEW CONCURRENTLY "
                    "prod.mv_ocupacion_diaria"
                )
            )
            await self._session.commit()
            logger.debug(
                "refresh_mv_ocupacion_cycle_ok",
                extra={"event": "refresh_mv_ocupacion_cycle_ok"},
            )
        except Exception as exc:  # noqa: BLE001 — KD-5: fall back, do not crash
            # Truncate the original exception message to avoid leaking
            # pgcode / DSN fragments into log aggregation. Log the
            # exception class only; full traceback at DEBUG.
            logger.warning(
                "refresh_mv_concurrently_failed_fallback",
                extra={
                    "event": "refresh_mv_concurrently_failed_fallback",
                    "exception_class": type(exc).__name__,
                },
            )
            await self._session.rollback()
            try:
                await self._session.execute(
                    text(
                        "REFRESH MATERIALIZED VIEW "
                        "prod.mv_ocupacion_diaria"
                    )
                )
                await self._session.commit()
                logger.debug(
                    "refresh_mv_ocupacion_fallback_ok",
                    extra={"event": "refresh_mv_ocupacion_fallback_ok"},
                )
            except Exception as inner_exc:  # noqa: BLE001
                # Both branches failed — log error and let the next cycle
                # retry. KD-5: never crash the loop; RIESGO-SUC-02 lag is
                # the accepted operating characteristic.
                await self._session.rollback()
                logger.error(
                    "refresh_mv_ocupacion_both_branches_failed",
                    extra={
                        "event": "refresh_mv_ocupacion_both_branches_failed",
                        "exception_class": type(inner_exc).__name__,
                    },
                )
        # Post-cycle sleep — KD-5: never sleep BEFORE refresh (would block
        # the first startup refresh); see R1 mitigation in proposal.md §8.
        await asyncio.sleep(self.refresh_interval_s)


# ---------------------------------------------------------------------------
# CLI entrypoint (KD-1: registered with NSSM, runs as a separate process)
# ---------------------------------------------------------------------------

async def _run_worker(database_url: str, refresh_interval_s: int) -> int:
    """Boot the worker with its own AsyncSession and run until SIGTERM."""
    engine = create_async_engine(database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        worker = RefreshMvOcupacionWorker(
            session=session,
            refresh_interval_s=refresh_interval_s,
        )
        return await worker.run()  # WorkerRunner.run() handles signals + exit


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: python -m parkos_core.jobs.refresh_mv_ocupacion."""
    import argparse

    parser = argparse.ArgumentParser(
        description="HU-F1.5: refresh prod.mv_ocupacion_diaria every N seconds.",
    )
    parser.add_argument(
        "--refresh-interval-s",
        type=int,
        default=RefreshMvOcupacionWorker.DEFAULT_REFRESH_INTERVAL_S,
        help="Cycle interval in seconds (floor 5s; default 10).",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get(
            "PARKOS_BRANCH_DB_DSN",
            "postgresql+asyncpg://parkos_app:secret@localhost/parkos_branch",
        ),
        help="Async SQLAlchemy DSN; default $PARKOS_BRANCH_DB_DSN.",
    )
    args = parser.parse_args(argv)
    return asyncio.run(
        _run_worker(args.database_url, args.refresh_interval_s)
    )


if __name__ == "__main__":
    raise SystemExit(main())
```

**Notes.**

- `WorkerRunner` is **not modified** (verified by `factory_intact` CI gate from F1.1 + F1.3); `RefreshMvOcupacionWorker` reuses the base `run()` method verbatim.
- The CLI entrypoint is identical in shape to `parkos_core.jobs.sync_sucursal.__main__` (precedent, lines 314-352 in F1.8 archive); `asyncio.run` wraps the worker.
- Signal handling (SIGTERM/SIGINT → exit code 0; SIGKILL → exit 137) is inherited from `WorkerRunner` and not duplicated.
- The post-cycle `asyncio.sleep` (R1 mitigation in `proposal.md §8`): if the worker restarts after a crash, the next `cycle()` executes **immediately**, refreshing the stale MV before yielding to the polling client. The pre-sleep alternative would block the first refresh for `refresh_interval_s` after each restart, defeating the resilience goal.
- No `asyncio.Lock` or `asyncio.Event` is acquired around the refresh; `AsyncSession` is single-task, single-coroutine safe, and Postgres MVCC handles concurrency. Two workers running on the same DB would race for the `AccessExclusiveLock` of the plain `REFRESH` branch — the operational mitigation is "ONE `refresh_mv_ocupacion` service per branch DB" (documented in the NSSM install guide, not in code).

## 6. Endpoint Skeleton

**Path**: `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (modify existing).

The handler is registered with `@router.get("/ocupacion")` and uses the existing `_ingreso_issuer_dep` (línea 64), the existing `get_session` dependency, and the existing `get_tenant_ctx`. The dependency chain is documented inline; the handler delegates the SQL JOIN to `repo/ocupacion.py::get_ocupacion_puros_activos`.

```python
# backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py
# (additions near the existing cotizar_ingreso_handler, line 219)

from uuid import UUID
from fastapi import Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from parkos_core.auth.tenancy import TenantContext, get_tenant_ctx
from parkos_core.auth.errors import (
    SucursalNotPermitted,
    TenantScopeViolation,
)
from parkos_core.repo.ocupacion import get_ocupacion_puros_activos
from parkos_core.schemas.operacion import OcupacionItem, OcupacionResponse
from parkos_core.db.deps import get_session


@router.get(
    "/ocupacion",
    response_model=OcupacionResponse,
    summary=(
        "HU-F1.5 / REQ-OPS-030: per-tipo occupancy breakdown for the "
        "branch, derived from prod.mv_ocupacion_diaria."
    ),
    responses={
        400: {"description": "missing_sucursal_context"},
        403: {
            "description": (
                "tenant_scope_violation (operador) | "
                "sucursal_not_permitted (admin)"
            )
        },
        503: {"description": "ocupacion_materializada_error"},
    },
)
async def get_ocupacion(
    response: Response,                                      # Cache-Control
    uuid_sucursal: UUID | None = Query(
        None,
        description=(
            "uuid_sucursal to query. Default = ctx.sucursal_uuid. "
            "Operador- sees only ctx.sucursal_uuid; admin- sees only "
            "branches in claims['sucursales_permitidas']."
        ),
    ),
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_ingreso_issuer_dep),            # KD-3
) -> OcupacionResponse:
    """REQ-OPS-030 + REQ-OPS-031: GET /operacion/ocupacion.

    Dependency chain:
        _ingreso_issuer_dep   -> requires_issuer("operador-", "admin-")
        get_tenant_ctx        -> TenantContext { actor_uuid, sucursal_uuid, ... }
        get_session           -> AsyncSession (request-scoped)
    Body: thin pass-through to repo/ocupacion.get_ocupacion_puros_activos,
    encapsulating the SQL JOIN (mv x tv LEFT JOIN cvs).
    """
    # 1. Resolve target sucursal (KD-3 chain):
    #    - query param wins;
    #    - else ctx.sucursal_uuid;
    #    - else 400 missing_sucursal_context.
    target = uuid_sucursal or ctx.sucursal_uuid
    if target is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
        )

    # 2. Authorization (KD-3):
    #    - operador- pinned to ctx.sucursal_uuid;
    #    - admin- bounded by claims['sucursales_permitidas'].
    if ctx.issuer_prefix == "operador-":
        if ctx.sucursal_uuid is None or target != ctx.sucursal_uuid:
            raise TenantScopeViolation(actor_uuid=ctx.actor_uuid)
    elif ctx.issuer_prefix == "admin-":
        if target not in (ctx.claims or {}).get("sucursales_permitidas", []):
            raise SucursalNotPermitted(target_sucursal=target)

    # 3. Repo call (READ-ONLY; encapsulated JOIN):
    items = await get_ocupacion_puros_activos(
        session, uuid_sucursal=target
    )

    # 4. Cache-Control: no-store (consistent with F1.3 R8 / F1.8 R8).
    response.headers["Cache-Control"] = "no-store"

    return OcupacionResponse(
        uuid_sucursal=target,
        items=[OcupacionItem.model_validate(it) for it in items],
        generado_en=datetime.now(tz=timezone.utc),
    )
```

**Notes.**

- The handler is **registered on the existing `APIRouter`** (no new module added under `api/v1/`); the decorator `@router.get("/ocupacion")` is the same one that hosts `create_ingreso`, `get_ingreso`, `cotizar_ingreso_handler`. Position in the file (before or after `cotizar_ingreso_handler`) is irrelevant: paths don't collide.
- The dependency chain `_ingreso_issuer_dep → get_tenant_ctx → get_session` is **verbatim** from the existing handlers (line 64 onward). No new dependency factories.
- `get_ocupacion_puros_activos` is the helper in `repo/ocupacion.py` (see §8 below); the handler does not write SQL inline.
- Error mapping (`TenantScopeViolation → 403` and `SucursalNotPermitted → 403`) is delegated to the existing exception handlers in `auth/tenancy.py:60-65` and `auth/tenancy.py:115-131`; the handler just raises the typed exception.
- `generado_en` uses `datetime.now(tz=timezone.utc)` rather than the DB `NOW()` because the response is built in Python after the repo call; the timestamp captures **when the response was assembled**, not when the MV was refreshed. The MV refresh timestamp is observable via `pg_stat_user_tables.last_analyze` (used by the integration test, see §11).

## 7. Schema Skeleton

**Path**: `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (modify existing, append after F1.8 schemas).

The schemas are the contract surface between the endpoint and the client (F4.3 `OcupacionStrip`). `extra='forbid'` (inherited from `_Base`) rejects unknown fields at the deserialization boundary. Pydantic v2 idioms (`ConfigDict`, `model_validate`, `model_config`) match F1.8's `CotizarResponse`. The schema ordering matches the SELECT ordering (`ORDER BY tv.tipo`) so `generado_en` is the last line of the JSON for stable diff tests.

```python
# backend/packages/parkos_core/src/parkos_core/schemas/operacion.py
# Append after the existing F1.8 CotizarResponse block.
import uuid as uuid_lib
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    """Repo-wide base: forbid unknown fields on serialization."""
    model_config = ConfigDict(extra="forbid")


class OcupacionItem(_Base):
    """Una fila del breakdown por tipo de vehiculo (REQ-OPS-030).

    Disponible puede ser negativo si cantidad_vehiculos_sucursal no
    tiene fila para (uuid_sucursal, uuid_tipo_vehiculo) (KD-6).
    """
    uuid_tipo_vehiculo: uuid_lib.UUID
    tipo: str                                  # "Auto", "Moto", etc.
    cupo_maximo: int                           # 0 si COALESCE(NULL) -> 0
    activos: int                               # count(*) de la MV
    disponible: int                            # cupo_maximo - activos

    # Allow client-side sortable ORDER BY tv.tipo parity.
    # Pydantic v2 orders fields in declaration order; client uses the same
    # ORDER BY in repo/ocupacion.get_ocupacion_puros_activos to keep
    # the wire format deterministic.


class OcupacionResponse(_Base):
    """Response shape of GET /operacion/ocupacion (REQ-OPS-030)."""
    uuid_sucursal: uuid_lib.UUID
    items: list[OcupacionItem]
    generado_en: datetime                      # NOW() server-side, lag diag
```

**Notes.**

- `extra="forbid"` rejects fields not in the schema — defense against schema drift. The client serializes the full OccupacionResponse on each polling cycle, so the schema IS the wire contract.
- Pydantic v2's `BaseModel.model_validate(row)` validates ORM row dicts (used in §6); no custom field validators needed (all fields are primitives).
- `generado_en` has no timezone — `datetime` is naive UTC by convention; the handler constructs it with `datetime.now(tz=timezone.utc)` and Pydantic serializes as ISO-8601 with `Z` suffix. Clients are required to interpret the suffix as UTC.
- The `_Base` class is shared with the existing F1.8 schemas (`CotizarFacturacion`, `CotizarMensualidad`, `CotizarResponse`); adding the new types at the bottom of the file preserves F1.8's declaration order in `git diff`.
- No `Field(..., description=...)` strings — the endpoint's `description=` parameter on the `Query` carries the human-readable docs. Schema fields are documentation through FastAPI auto-generated OpenAPI.

## 8. Repo Skeleton

**Path**: `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py` (NEW).

A thin async helper that encapsulates the SQL JOIN. The helper is the **only** place that calls into `prod.mv_ocupacion_diaria`; the endpoint delegates to it for testability (the helper can be exercised without HTTP). The SELECT uses `text(...)` with bind params (no string interpolation — KD-1 SQL injection hygiene). The `LEFT JOIN` with `COALESCE(cvs.cantidad, 0)` preserves the KD-6 invariant that `disponible` may be negative.

```python
# backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py
"""HU-F1.5: thin async helper for prod.mv_ocupacion_diaria reads.

The single SQL JOIN that backs GET /operacion/ocupacion. Encapsulates:
  - the MV (prod.mv_ocupacion_diaria) — count(*) by (sucursal, tipo);
  - the JOIN to prod.tipos_vehiculo for the human-readable `tipo` string;
  - the LEFT JOIN to prod.cantidad_vehiculos_sucursal for `cupo_maximo`
    (KD-6: may be NULL if admin has not configured capacity — COALESCE
    resolves to 0, and `disponible` may be negative).

Encapsulated here so:
  - the test layer can exercise the helper directly via DB fixtures
    without HTTP;
  - the endpoint (api/v1/operacion.py::get_ocupacion) stays thin
    (resolve ctx, call helper, wrap in OcupacionResponse).
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class OcupacionItemRow:
    """Per-tipo row returned from the MV JOIN.

    Used internally by the repo helper; the endpoint wraps these into
    pydantic schemas/operacion.OcupacionItem (no leakage of ORM types).
    """
    uuid_tipo_vehiculo: uuid_lib.UUID
    tipo: str
    cupo_maximo: int
    activos: int

    @property
    def disponible(self) -> int:
        # KD-6: cupo_maximo - activos; may be negative if not configured.
        return self.cupo_maximo - self.activos


async def get_ocupacion_puros_activos(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
) -> list[OcupacionItemRow]:
    """REQ-OPS-030: SELECT MV JOIN, returns rows ordered by tipo.

    SELECT
        mv.uuid_sucursal,
        mv.uuid_tipo_vehiculo,
        tv.tipo,
        COALESCE(cvs.cantidad, 0) AS cupo_maximo,
        mv.activos
    FROM prod.mv_ocupacion_diaria mv
    JOIN prod.tipos_vehiculo tv
      ON tv.uuid = mv.uuid_tipo_vehiculo
     AND tv.vigente_hasta IS NULL               -- bi-temporal [V] vigente
    LEFT JOIN prod.cantidad_vehiculos_sucursal cvs
      ON cvs.uuid_sucursal = mv.uuid_sucursal
     AND cvs.uuid_tipo_vehiculo = mv.uuid_tipo_vehiculo
     AND cvs.vigente_hasta IS NULL               -- bi-temporal [V] vigente
    WHERE mv.uuid_sucursal = :uuid_sucursal
    ORDER BY tv.tipo;                           -- KD-4 deterministic order

    Bind params only; no string interpolation. SQL is text() with
    SQLAlchemy parameter substitution. Tested against parkos-branch-db
    via tests/integration/test_mv_ocupacion_diaria_db.py.
    """
    stmt = text(
        """
        SELECT
            mv.uuid_tipo_vehiculo        AS uuid_tipo_vehiculo,
            tv.tipo                       AS tipo,
            COALESCE(cvs.cantidad, 0)     AS cupo_maximo,
            mv.activos                    AS activos
        FROM prod.mv_ocupacion_diaria mv
        JOIN prod.tipos_vehiculo tv
          ON tv.uuid = mv.uuid_tipo_vehiculo
         AND tv.vigente_hasta IS NULL
        LEFT JOIN prod.cantidad_vehiculos_sucursal cvs
          ON cvs.uuid_sucursal = mv.uuid_sucursal
         AND cvs.uuid_tipo_vehiculo = mv.uuid_tipo_vehiculo
         AND cvs.vigente_hasta IS NULL
        WHERE mv.uuid_sucursal = :uuid_sucursal
        ORDER BY tv.tipo
        """
    )
    rows = (await session.execute(stmt, {"uuid_sucursal": uuid_sucursal})).all()
    return [
        OcupacionItemRow(
            uuid_tipo_vehiculo=r.uuid_tipo_vehiculo,
            tipo=r.tipo,
            cupo_maximo=r.cupo_maximo,
            activos=r.activos,
        )
        for r in rows
    ]
```

**Notes.**

- `text("...")` with `session.execute(stmt, {"uuid_sucursal": ...})` is the SQLAlchemy bind-param idiom; psycopg2/asyncpg handle the escaping.
- `@dataclass(frozen=True)` makes `OcupacionItemRow` immutable and trivially `model_validate`-able by Pydantic (which works on dataclasses in v2).
- `disponible` is a `@property` deriving from `cupo_maximo - activos` rather than a stored field — keeps the wire-decision (negative handling) in the schema layer, not the SQL.
- `tv.vigente_hasta IS NULL` filter on both JOINs enforces the bi-temporal `[V]` discipline: only the vigente version of `tipos_vehiculo` and `cantidad_vehiculos_sucursal` is consulted (consistent with `operacion.py:152-168` precedent).
- The helper has **no HTTP coupling**: it can be exercised directly in `tests/integration/test_mv_ocupacion_diaria_db.py` with a synthetic session and known-data fixtures, no FastAPI app needed.

## 9. Threat Matrix

The applicability-driven threat matrix covers seven attack surfaces specific to HU-F1.5. None of the threats reach a critical residue; KD-1..KD-7 plus the defense-in-depth layers (DB unique index, worker fallback, AST gate, integration tests) cap the residual risk at **Low** for each row.

| # | Threat | Attack Vector | Defense in Depth Layer | Residual Risk | KD Mitigates |
|---|---|---|---|---|---|
| **T1** | SQL injection via `uuid_sucursal` query param crosses tenant boundary | `operador-` from sucursal X passes `?uuid_sucursal=Y` to read Y's breakdown | `repo/ocupacion.py` uses `text(...).bindparams(uuid_sucursal=...)` (SQLAlchemy escaping, no string interpolation); endpoint authorizes against `ctx.sucursal_uuid` BEFORE calling repo; cross-tenant → `403 tenant_scope_violation` at §6 | Low | KD-3, KD-2 (KD-3 plus repo param-binding is the effective gate; KD-2 keeps the MV projection restricted to authorized rows) |
| **T2** | Postgres auth bypass via compromised `PARKOS_BRANCH_DB_DSN` (e.g., leaked in CI logs) | Attacker with the DSN opens a separate psql connection, reads `prod.mv_ocupacion_diaria` directly, bypassing the HTTP layer entirely | Network policy (Cloud SQL private IP, VPC firewall) restricts inbound TCP/5432 to the api-sucursal and worker VMs; `parkos_app` role has only `SELECT` on the MV (no `INSERT`/`UPDATE`/`DELETE`); DSN rotation on suspected leak (operational runbook, not in this change); credential scrubbing in `infra/scripts/seed_catalogs.py` | Low | None directly (KD-2 enforces SELECT-only on the MV; KD-1 keeps the worker DSN separate from api-sucursal DSN via NSSM env block) |
| **T3** | MV refresh deadlock under concurrent `REFRESH CONCURRENTLY` from two worker instances (operator misconfig) | NSSM misconfiguration runs `refresh_mv_ocupacion` as two services against the same DB; both call `CONCURRENTLY` simultaneously | Postgres MVCC serializes the two `REFRESH CONCURRENTLY` calls (one waits, one runs); the waiter completes once the leader commits; no deadlock — Postgres documents this as the supported concurrency. R7 mitigation: ops alert if both `refresh_mv_ocupacion` services are registered (`infra/` install guide explicitly documents "ONE service per branch DB") | Low | KD-5 (worker tolerance of slow second cycle), KD-1 (single-service operational contract) |
| **T4** | Stale data during refresh window — endpoint reads MV while `REFRESH` (full-lock) is in progress | Refresh takes the `AccessExclusiveLock`; client poll arrives mid-refresh; query blocks until refresh commits | KD-5 fallback only when `CONCURRENTLY` fails (rare); typical cycle uses `CONCURRENTLY` which keeps reads consistent with the pre-refresh snapshot via MVCC; full-lock window is sub-100ms typical, sub-2s peak per `RIESGO-SUC-02`; client tolerates `503 OcupacionMaterializadaError` with `Retry-After: 10` (documented in OpenAPI `responses`) | Low | KD-5 |
| **T5** | Misconfigured `cantidad_vehiculos_sucursal` causes `disponible < 0` → operator assumes "Auto: -5" is system failure | Admin forgets to set `cantidad` after adding a new `tipo_vehiculo`; frontend renders the negative number as a bug rather than a configuration warning | KD-6 explicit: `LEFT JOIN ... COALESCE(cantidad, 0)` returns `cupo_maximo = 0` and `disponible = -activos`; OpenAPI `OcupacionItem.disponible` description warns "may be negative"; client UX layer (F4.3 `OcupacionStrip`) explicitly designed to render `disponible < 0` as "N/A — contact admin" per F1.5 §3 KD-6 client policy | Low | KD-6 |
| **T6** | pgcode (`"23505"`) leaks from worker logs into the SIEM dashboard, exposing driver internals | Worker logs `pgcode` in `extra=` dict because `repr(exc)` includes the original exception; SIEM alerting rule fires on the pgcode substring | `RefreshMvOcupacionWorker.cycle()` logs `type(exc).__name__` only (not `repr`); `pgcode` access uses `getattr(getattr(exc, "orig", None), "pgcode", None) == "23505"` IF the worker ever decides to discriminate by code — but KD-5 currently falls back on ANY exception (not discriminated by code); integration test `test_refresh_mv_job.py::test_concurrently_fails_fallback_refresh` asserts `pgcode` substring is NOT in log capture | Low | KD-5 (fallback catches all exceptions regardless of pgcode, removes the leak surface) |
| **T7** | Endpoint storm — N operators each poll every 10s = N/10 RPS sustained, plus burst on screen-mount | 50 operadores × 1/10s = 5 RPS sustained; screen-mount adds 50 instantaneous SELECTs; pg_stat shows slow query | KD-1: the MV is indexed (UNIQUE INDEX) so each SELECT is O(log tipos_vehiculo) index lookup, not O(N ingresos); `repo/ocupacion.py` uses bind params (parameterized SQL, plan cache hit every request); `Cache-Control: no-store` is correct (response varies by current state, cannot cache); documented RIESGO-SUC-02 ("lag 10s aceptable en momentos de alta rotación"); alert on `refresh_duration_s > refresh_interval_s` (operational, not in this change) | Low | KD-2 (UNIQUE INDEX keeps refresh fast → MV stale window is short → endpoint reads are against up-to-date MV), KD-4 (response breakdown small, not aggregate with cross-join blow-up) |

**Notes.** The threats in scope (HTTP / DB / MV / worker) fall under the design's boundaries; the `references/threat-matrix.md` applicability test (routing, shell, subprocess, VCS/PR automation, executable-file classification, process integration) is partially satisfied by the worker being a subprocess of NSSM — but the subprocess invocation is standard for the codebase (precedent `sync_sucursal.py`), so the F1.3 pattern applies verbatim. No additional threat rows are required.

## 10. Traceability Matrix

The traceability map bridges the four REQ-OPS-NNN introduced by F1.5 to the design sections, skeleton files, and the tests that prove them. Each row is a **must-pass** contract; missing any row is a verification failure.

| REQ-OPS | Description | Design Section | Skeleton File | Test File |
|---|---|---|---|---|
| **REQ-OPS-030** | `GET /operacion/ocupacion?uuid_sucursal=X` returns `OcupacionResponse` (breakdown per `tipo_vehiculo`) with `Cache-Control: no-store` | §6 Endpoint Skeleton | `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (modify, ~30 LOC) + `schemas/operacion.py` (§7, ~20 LOC) | `backend/tests/unit/test_operacion_ocupacion.py::test_operador_self_returns_200_with_ocupacion_response` (T1) |
| **REQ-OPS-031** | Authorization per-sucursal: `operador-` pinned, `admin-` scoped to `claims["sucursales_permitidas"]`; errors `400 missing_sucursal_context`, `403 tenant_scope_violation`, `403 sucursal_not_permitted` | §6 Endpoint Skeleton + §3 KD-3 | `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py::get_ocupacion` (authz block) | `backend/tests/unit/test_operacion_ocupacion.py::test_operador_cross_tenant_returns_403` (T2) + `test_admin_allowed_branch_returns_200` (T3) + `test_admin_no_context_returns_400` (T4) |
| **REQ-OPS-032** | `prod.mv_ocupacion_diaria` materialized view + `CREATE UNIQUE INDEX CONCURRENTLY` + pre-flight `DO $$` (KD-7) with 10M INFO / 50M ABORT thresholds | §3 KD-2 + §3 KD-7 + §4 SQL Skeleton | `backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py` (NEW, ~80 LOC) | `backend/tests/integration/test_migration_0024_mv.py::test_apply_with_dirty_data_creates_view_and_index` (T1) + `test_preflight_aborts_on_simulated_50m_rows` (T2, 50M simulation via mocked count) |
| **REQ-OPS-033** | `RefreshMvOcupacionWorker.cycle()` calls `REFRESH MATERIALIZED VIEW CONCURRENTLY` with fallback `REFRESH` plain, then `asyncio.sleep(refresh_interval_s=10)` | §3 KD-1 + §3 KD-5 + §5 Python Skeleton | `backend/packages/parkos_core/src/parkos_core/jobs/refresh_mv_ocupacion.py` (NEW, ~50 LOC) | `backend/tests/integration/test_refresh_mv_job.py::test_cycle_normal_refresh` (T1) + `test_concurrently_fails_fallback_refresh` (T2) |

**Notes.**

- REQ-OPS-030 is also covered by `repo/ocupacion.py` (§8) and the schema modules (§7); tests `test_operacion_ocupacion.py` exercise the HTTP surface end-to-end, while `test_mv_ocupacion_diaria_db.py::test_insert_ingreso_refresh_view_includes_row` (T1, §11) exercises the underlying MV refresh semantics separately.
- REQ-OPS-031's T4 (`admin-` no context → 400) replaces the proposal's `T4 operador-no-session-200` because per `auth/tenancy.py:122` the admin- boundary is the more interesting failure mode; the operador case is implicitly tested via T1's success path.
- REQ-OPS-032's T1 (apply-with-dirty-data) is the migration idempotency test: pre-flight completes cleanly with N rows of dirty data (ingresos with salidas, anulaciones), the view is created, and the UNIQUE INDEX applies without conflict. T2 (50M abort) is the KD-7 gate verified via a migration dry-run with a mocked `count(*) → 50_000_001`.
- REQ-OPS-033's T1 (normal cycle) verifies that after `cycle()` returns, the MV's `pg_stat_user_tables.last_analyze` timestamp has been updated; T2 (fallback) injects a Postgres error into the CONCURRENTLY path and verifies that the cycle completes anyway (KD-5), without crashing the worker.
- The `tests/static/test_no_write_in_ocupacion.py` AST walk (per F1.3 / F1.8 pattern) is a **cross-cutting** guard that overlaps REQ-OPS-030 and REQ-OPS-031 — it is listed in §11 test plan but not in the traceability matrix because no single REQ owns it.

## 11. Test Plan

The test plan is **ten tests** across **five test files**, mirroring F1.3's split (HTTP unit + DB integration + migration pre-flight + AST static + worker cycle). Each test name documents the test intent for OPS auditing; the file paths align with `proposal.md §11`.

### File 1: `backend/tests/unit/test_operacion_ocupacion.py` — 4 HTTP-level unit tests

Uses `httpx.AsyncClient + ASGITransport` (F1.3 / F1.8 precedent) and the JWT `operador-` fixture plus the `admin-` fixture from `tests/unit/test_auth_login_password.py`.

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_operador_self_returns_200_with_ocupacion_response` | `operador-` JWT with `sucursal=X`; `GET /operacion/ocupacion?uuid_sucursal=X` returns 200 + `body` is `OcupacionResponse` shape; `items` non-empty and `ORDER BY tv.tipo` (sorted by `tipo`); `generado_en` is ISO-8601 UTC. REQ-OPS-030 happy path. |
| **T2** | `test_operador_cross_tenant_returns_403_tenant_scope_violation` | `operador-` JWT with `sucursal=X`; `GET /operacion/ocupacion?uuid_sucursal=Y` returns 403 + `body["error"] == "tenant_scope_violation"`; NO pgcode, NO driver string, NO `uuid_sucursal` value in body or headers. REQ-OPS-031 KD-3. |
| **T3** | `test_admin_allowed_branch_returns_200` | `admin-` JWT with `claims["sucursales_permitidas"] = [X]`; `X-Sucursal-Context: X` header; `GET /operacion/ocupacion?uuid_sucursal=X` returns 200 + `OcupacionResponse`. REQ-OPS-031 KD-3 admin scope. |
| **T4** | `test_admin_no_context_returns_400_missing_sucursal_context` | `admin-` JWT with no `X-Sucursal-Context` header AND no `claims["sucursales_permitidas"]`; `GET /operacion/ocupacion` (no `?uuid_sucursal=`) returns 400 + `body["error"] == "missing_sucursal_context"`. REQ-OPS-031 KD-3 missing header. |

### File 2: `backend/tests/integration/test_mv_ocupacion_diaria_db.py` — 2 DB-backed integration tests

Requires `PARKOS_DOCKER_TEST=1` and a live `parkos-branch-db` connection (F1.3 / F1.8 precedent). Uses synthetic `prod.sucursal` / `prod.tipos_vehiculo` / `prod.ingreso` / `prod.salidas` / `prod.cantidad_vehiculos_sucursal` fixtures inserted at the test start, with cleanup at the end.

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_insert_ingreso_then_refresh_view_includes_row` | Insert one `ingreso(uuid_sucursal=X, uuid_tipo_vehiculo=T, fecha_ingreso=now)`; call `await session.execute(text("REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria"))`; read `repo/ocupacion.py::get_ocupacion_puros_activos(session, uuid_sucursal=X)`; assert `items` contains one row with `activos == 1`, `cupo_maximo == 0` (no cvs row), `disponible == -1` (KD-6 valid negative). |
| **T2** | `test_insert_salida_then_refresh_view_decrements_activos` | Insert one `ingreso` then one `salidas(uuid_ingreso=I, uuid_sucursal=X)`; refresh MV; assert `items` for `(X, T)` is now empty (the ingreso is no longer "activo"). Verifies that the MV's `NOT EXISTS (salidas)` clause correctly excludes exited vehicles. |

### File 3: `backend/tests/integration/test_migration_0024_mv.py` — 2 migration pre-flight tests

Uses a synthetic schema (built via Alembic's offline mode in-memory or via a dedicated test branch DB) to exercise the pre-flight `DO $$` block and the `CREATE MATERIALIZED VIEW` + `CREATE UNIQUE INDEX CONCURRENTLY` chain.

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_apply_with_dirty_data_creates_view_and_index` | Pre-seed the schema with 5 ingresos, 2 with linked `salidas` rows, 1 with linked `anulaciones` (`estado='ejecutada'`, `tipo_anulable='ingreso'`), 2 with no linked salidas (active); apply the migration; assert the view exists; assert `CREATE UNIQUE INDEX CONCURRENTLY` succeeded (no `pg_class.indisinvalid`); assert `repo/ocupacion.get_ocupacion_puros_activos(session, uuid_sucursal=X)` returns rows for the 2 active ingresos only. |
| **T2** | `test_apply_upgrade_downgrade_upgrade_roundtrip` | Apply migration 0024; verify the view exists; `downgrade()` to remove it; verify the view is gone; re-apply upgrade; verify the view is recreated and the UNIQUE INDEX is `IF NOT EXISTS`-friendly (no error on re-create). Tests migration idempotency. |

### File 4: `backend/tests/static/test_no_write_in_ocupacion.py` — 1 AST walk static test

Cross-cutting defense-in-depth gate (F1.3 / F1.8 precedent `test_no_write_in_calcular_cotizacion.py` adapted to Python handler source instead of PL/pgSQL function body).

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_handler_get_ocupacion_contains_no_write_verbs` | AST-walk the source of `api/v1/operacion.py::get_ocupacion`; reject any `ast.Call` whose function name is `execute` AND the first argument string-literal contains any of `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `MERGE`, `FOR UPDATE`, `FOR SHARE`; assert the walk finds no violations. Locks the read-only contract per REQ-OPS-030. |

### File 5: `backend/tests/integration/test_refresh_mv_job.py` — 2 worker cycle tests

Uses a mocked `AsyncSession` (per F1.3 / F1.8 test pattern with `unittest.mock.AsyncMock`) to inject controlled `REFRESH` responses, including a forced failure path.

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_cycle_normal_refresh_runs_concurrently_then_sleeps` | Build `RefreshMvOcupacionWorker(session=mock, refresh_interval_s=10)`; invoke `cycle()` once; assert `session.execute` was called with `text("REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria")`; assert `session.commit()` was called; assert `asyncio.sleep` was called with `10` (verify by patching `asyncio.sleep` in the worker module). REQ-OPS-033 happy path. |
| **T2** | `test_cycle_concurrently_fails_falls_back_to_plain_refresh` | Configure `session.execute` to raise `psycopg2.errors.FeatureNotSupported("CONCURRENTLY requires UNIQUE INDEX")` on the first call (CONCURRENTLY path); invoke `cycle()`; assert the second `session.execute` call was `text("REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria")` (plain, no `CONCURRENTLY`); assert the worker did NOT raise (KD-5 fallback acceptable); assert log capture contains `refresh_mv_concurrently_failed_fallback` event (structured log shape). REQ-OPS-033 KD-5 fallback. |

**Coverage map.** The 10 tests in 5 files cover:
- HTTP happy + sad paths for the endpoint (T1, T2, T3, T4 in File 1).
- DB round-trip for the MV (T1, T2 in File 2).
- Migration pre-flight idempotency (T1, T2 in File 3).
- Static AST gate locking the read-only contract (T1 in File 4).
- Worker KD-5 fallback (T1, T2 in File 5).

Cross-cutting CI gates from `proposal.md §9.7`: `ruff check`, `ruff format --check`, `mypy --strict` on the 5 new + 2 modified backend files. `factory_intact` gate (F1.1 / F1.3 precedent) verifies `git diff backend/packages/parkos_core/src/parkos_core/api/v1/router_factory.py` returns empty. `worker_base_intact` gate verifies `git diff backend/packages/parkos_core/src/parkos_core/jobs/runner.py` returns empty.

---

**Design complete.** Ready for `sdd-tasks` with theme: TDD-strict 12-15 tasks across the 5 RED→GREEN→REFACTOR→VERIFICATION phases, mirroring F1.3's `13 tasks across 4 phases` shape, scaled to F1.5's 10 tests across 5 files. Onward to `sdd-apply` after tasks acceptance and user sign-off on the proposal.
