# Design: QA 2026-09-17 Bug Remediation

> **Change**: `qa-2026-09-17-bug-remediation` · **Phase**: design (sdd-design)
> **Capability**: `operations` (REQ-OPS-131..135, extensions to REQ-OPS-032, REQ-OPS-038, REQ-OPS-119)
> **Delivery**: `single-pr` (user-approved override; 3 stacked commits via `work-unit-commits` FE / BE-MV / BE-CATALOG-SESION boundaries)
> **Budget**: ~330 LOC across 10 files; PR `<800` LOC
> **Migration head**: `0033_login_historic_index` → next: `0034`, `0035`

## Threat Matrix

**N/A — DB DDL + form validation + SWR fetcher only — no routing/shell/subprocess/VCS automation delta.** Per `references/threat-matrix.md` applicability rule.

## Technical Approach

Five surgical, file-local fixes; no architectural surface change. Each bug has a one-line root cause mapped to a one-file primary edit, plus 1-2 test/migration companions. Audit-FIRST canon preserved: bug 5's `ADD COLUMN` is PG11+ instant (no rewrite); bug 3's `CREATE OR REPLACE` is idempotent; bug 4's helper change is internal (UUID return, not string). Frontend renames propagate through the `apps/ui-kit` workspace (version bump is the only cross-package surface).

## Architecture Decisions

### Decision D1 — Frontend type contract rename strategy

**Choice**: rename `AuthUser.id` → `AuthUser.uuid` in `apps/ui-kit` and propagate to all in-tree consumers (`AbrirTurno.tsx`, `useAuth.test.ts`, `AbrirTurno.test.tsx`).
**Alternatives considered**: (a) keep `id` and add `uuid` alias — DRY violation, two ways to do the same thing; (b) wrap `user` in a domain-specific `Operador` type — heavier refactor and lands in a non-`ui-kit` package.
**Rationale**: backend is source of truth (`UserItem.uuid` canonical per `schemas/auth.py`); identity drift is the bug. Workspace-internal consumers only — no published npm surface.

### Decision D2 — SWR fetcher-closure pattern

**Choice**: rewrite `useOcupacion` to `useSWR(key, () => getOcupacion(uuid_sucursal), opts)` with a closure that captures only the UUID.
**Alternatives considered**: (a) drop SWR cache key — loses the 5s `dedupingInterval`; (b) have `getOcupacion` parse UUID out of the path arg — convoluted, ties API to SWR internals.
**Rationale**: matches the established precedent `useSesionActiva.ts:55-57` and `useIngresoActivo.ts:67-69` in the same feature folder; SWR convention is that the key is opaque.

### Decision D3 — MV remediation migration shape

**Choice**: new migration `0034_recreate_mv_ocupacion_diaria_idempotent.py` with `CREATE OR REPLACE MATERIALIZED VIEW prod.mv_ocupacion_diaria AS … ` (idempotent) + post-upgrade `to_regclass` assertion. Also edit `0024_add_mv_ocupacion_diaria.py` to add `IF NOT EXISTS` for fresh-container safety.
**Alternatives considered**: (a) re-run all migrations head — over-broad, breaks isolation; (b) CHECK constraint that recreates on next refresh — `refresh_mv_ocupacion` worker would need a refresh-from-scratch branch.
**Rationale**: idempotent DDL is the only safe path against partial-commit migration state. CI gate `check_schema_match.py` extended with `to_regclass IS NOT NULL` prevents future drift.

### Decision D4 — Detector-tipo + explicit-uuid precedence

**Choice**: in `repo/placa.py::detectar_tipo_vehiculo`, look up `tipo IN ('carro','moto','bicicleta','patineta')` (lowercase matching `replicate_catalogs_to_branch.py:20`). In `api/v1/operacion.py::create_ingreso_handler`, honour `payload.uuid_tipo_vehiculo` first if present, else fall through to regex detection.
**Alternatives considered**: (a) seed uppercase `Auto`/`Moto` rows — schema-level churn for cosmetic alignment; (b) uppercase the regex helper before query — masks the spec drift.
**Rationale**: catalog seeds are the canon (`replicate_catalogs_to_branch.py`); align the helper to the canon. Honouring explicit `uuid_tipo_vehiculo` matches the F6.1 frontend contract.

### Decision D5 — `observaciones` column add + audit propagation

**Choice**: new migration `0035_add_observaciones_to_sesion.py` with `op.add_column('prod.sesion', sa.Column('observaciones', sa.Text(), nullable=True))`; update `models/L_S/sesion.py`, `schemas/caja.py::SesionCreate` (`max_length=500`), `repo/session_cycle.py::open_session`. In `record_event`, when observations is non-empty, write to `prod.log_transaccional.datos_nuevos` for audit (REQ-OPS-021).
**Alternatives considered**: (a) widen `_Base` schema to `extra="allow"` — violates canon audit-first; (b) JSON `audit_metadata` column for ALL free-text — bigger scope, F3.3-specific.
**Rationale**: REQ-OPS-119 mandates the field shape. AUDIT-FIRST canon requires the value to be persisted in `log_transaccional`. `ALTER TABLE ADD COLUMN TEXT NULL` is PG11+ instant.

## Data Flow

```
[OPERADOR] login → POST /api/v1/auth/login → JWT(operador-)
   ↓
[Frontend] useAuth().user.uuid      [Backend] /auth/me 200 OK
   ↓
[UI] AbrirTurno.tsx reads user.uuid → Zod passes → POST /caja-sesion/sesiones
   ↓
[UI] OcupacionStrip polls /operacion/ocupacion?uuid_sucursal=<UUID> (no extra encoding)
   ↓
[Backend] get_ocupacion_puros_activos() LEFT JOIN prod.mv_ocupacion_diaria
   ↓                                       ↑
[Worker] job_sync_cloud periodically REFRESH MATERIALIZED VIEW CONCURRENTLY
```

## File Changes

| File | Action | Description |
|---|---|---|
| `apps/ui-kit/src/hooks/useAuth.ts:33-36` | Modify | `AuthUser.id` → `AuthUser.uuid` (interface field rename) |
| `apps/ui-kit/src/hooks/useAuth.test.ts:43-56` | Modify | mock shape uses `{ uuid, email }` |
| `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.tsx:51` | Modify | `user?.uuid`; add `<FormMessage>` for `uuid_*` |
| `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.test.tsx:131-135` | Modify | mock `user: { uuid, email }`; assert FormMessage renders on reject |
| `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.ts:77` | Modify | fetcher closure `() => getOcupacion(uuid_sucursal)` |
| `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.test.ts` | Create | U-O10 regression: `getOcupacion` called with raw UUID |
| `backend/.../migrations/versions/0024_add_mv_ocupacion_diaria.py:89` | Modify | add `IF NOT EXISTS` on `CREATE MATERIALIZED VIEW` |
| `backend/.../migrations/versions/0034_recreate_mv_ocupacion_diaria_idempotent.py` | Create | `CREATE OR REPLACE` + `to_regclass` post-check |
| `backend/.../migrations/versions/0035_add_observaciones_to_sesion.py` | Create | `ADD COLUMN observaciones TEXT NULL` |
| `backend/.../models/L_S/sesion.py` | Modify | add `observaciones: Mapped[str \| None]` |
| `backend/.../schemas/caja.py::SesionCreate` | Modify | `observaciones: str \| None = Field(default=None, max_length=500)` |
| `backend/.../repo/session_cycle.py::open_session` | Modify | accept `observaciones: str \| None = None`; log to `log_transaccional.datos_nuevos` |
| `backend/.../src/parkos_core/repo/placa.py:48-60` | Modify | `tipo_nombre = "carro"/"moto"` (lowercase) |
| `backend/.../api/v1/operacion.py:177` | Modify | honour `payload.uuid_tipo_vehiculo` first |
| `backend/tests/unit/test_repo_placa.py:30-41,140-151` | Modify | fixture seeds `tipo='carro'`; asserts lowercase match |
| `backend/tests/unit/test_operacion_ingresos_handler.py` | Modify | assert explicit-uuid precedence |
| `backend/tests/integration/test_migration_0034_mv.py` | Create | assert `to_regclass('prod.mv_ocupacion_diaria') IS NOT NULL` after `alembic upgrade head` |
| `backend/tests/integration/test_sesion_observaciones.py` | Create | `test_open_session_persists_observations_and_logs` |
| `openspec/scripts/check_schema_match.py` | Modify | extend scan to assert MV + UNIQUE INDEX |
| `apps/ui-kit/package.json` | Modify | workspace version bump (breaking `AuthUser` shape) |

**Aggregate**: 12 MODIFIED + 6 CREATE + 0 DELETE.

## Interfaces / Contracts

```typescript
// apps/ui-kit/src/hooks/useAuth.ts
export interface AuthUser { uuid: string; email: string }
```

```python
# backend/.../schemas/caja.py
class SesionCreate(_Base):
    uuid_caja: uuid_lib.UUID
    monto_base: Decimal
    observaciones: str | None = Field(default=None, max_length=500)

# backend/.../models/L_S/sesion.py
class Sesion(Base):
    __tablename__ = "sesion"
    observaciones: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
```

```sql
-- migrations/versions/0034_recreate_mv_ocupacion_diaria_idempotent.py
CREATE OR REPLACE MATERIALIZED VIEW prod.mv_ocupacion_diaria AS
  SELECT ... FROM prod.ingreso ...;            -- canonical definition
DO $$ BEGIN
  IF to_regclass('prod.mv_ocupacion_diaria') IS NULL THEN
    RAISE EXCEPTION 'mv_ocupacion_diaria_missing_post_create';
  END IF; END $$;

-- migrations/versions/0035_add_observaciones_to_sesion.py
ALTER TABLE prod.sesion ADD COLUMN observaciones TEXT NULL;
```

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Frontend (vitest) | Bug 1: `AuthUser.uuid` typed; mocks updated; FormMessage renders | extend `useAuth.test.ts`; new regression in `AbrirTurno.test.tsx` |
| Frontend (vitest) | Bug 2: fetcher invoked with `<UUID>`, not key | NEW `useOcupacion.test.ts::test_fetcher_receives_uuid_not_key` via `vi.mock(getOcupacion)` |
| Backend (pytest) | Bug 3: MV present after `alembic upgrade head` | NEW `tests/integration/test_migration_0034_mv.py`; assert `to_regclass` |
| Backend (pytest) | Bug 4: lowercase-catalog resolution + explicit-uuid precedence | update `tests/unit/test_repo_placa.py` fixture; assert explicit-uuid path in `tests/unit/test_operacion_ingresos_handler.py` |
| Backend (pytest) | Bug 5: `observaciones` round-trip + `log_transaccional` audit | NEW `tests/integration/test_sesion_observaciones.py::test_open_session_persists_observations_and_logs` |
| CI (script) | Bug 3 regression guard | `python openspec/scripts/check_schema_match.py` exits 0 with MV + UNIQUE INDEX verified |
| E2E (manual, post-merge) | F3-F6 happy path with `operador@parkos.local` | re-run the QA script that originally surfaced the 5 bugs |

## Migration / Rollout

- Migration `0034` runs on already-`alembic_head=0024` containers: `CREATE OR REPLACE` heals the missing MV atomically. Migration `0035` adds the column. Both have `downgrade()` that drops cleanly.
- No feature flag — bug-remediation PR; release branch flow per AGENTS.md gitflow.
- Stacked commits: `feat(apps): auth.user.uuid + ocupacion fetcher closure` (FE) · `fix(backend): recreate mv_ocupacion_diaria idempotent + schema gate` (BE-MV) · `fix(backend): detectar_tipo lowercase + sesion.observaciones` (BE-CATALOG-SESION). Partial `git revert <sha>` keeps rollback surgical.
- Post-merge: per AGENTS.md invalidar Vite cache (`.vite/` deps), then re-run the original QA happy path on a fresh container.

## Open Questions

- None — all 5 fixes have file:line-level citations in `exploration.md` and test oracles in `specs/operations/spec.md` (REQ-OPS-131..135).