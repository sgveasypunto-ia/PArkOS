# Exploration: qa-2026-09-17-bug-remediation

> **Change**: `qa-2026-09-17-bug-remediation`
> **Phase**: explore (sdd-explore)
> **Branch**: `dev` (HEAD `251dba8`)
> **Date**: 2026-09-17
> **Working dir**: `E:/easypunto_parkos`
> **PR target**: `origin/dev`
> **Scope**: 5 confirmed end-to-end blockers + 1 cosmetic warning, discovered during manual QA of the 6 already-implemented phases (F3 login + lockout + turno, F4.2 tarifas, F4.3 ocupación en vivo, F5.x impresión, F6.1/F6.2 ingreso vehicular + tiquete). All five bugs are blocking the canonical F3-F6 happy path.

## 1. Current state — bug-by-bug evidence

### Bug 1 — AbrirTurno Zod silent reject (frontend)
- **`apps/electron-sucursal/src/features/caja/pages/AbrirTurno.tsx:50-51`**:
  ```ts
  defaultValues: {
    uuid_sucursal: sucursal?.uuid ?? '',
    uuid_usuario:  user?.id     ?? '',   // ← undefined at runtime
  ```
- **`apps/ui-kit/src/hooks/useAuth.ts:33-36`** (interface) vs **`backend/.../schemas/auth.py:279`** (backend returns `uuid`):
  ```ts
  interface AuthUser { id: string; email: string }   // frontend
  class UserItem(_Base):
      uuid: uuid_lib.UUID                           // backend
  ```
- **`apps/ui-kit/src/hooks/useAuth.test.ts:43-56`** mocks the WRONG shape (`{ id: 'u-1', ... }`) — masks the bug end-to-end.
- `abrirTurnoSchema.uuid_usuario = z.string().uuid()` rejects `""` silently because the form has no `<FormMessage>` for `uuid_*` (only `valor_*` show inline errors).

### Bug 2 — useOcupacion URL duplication (frontend)
- **`apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.ts:73-77`**:
  ```ts
  const key = buildKey(uuid_sucursal, accessToken);   // "/operacion/ocupacion?uuid_sucursal=<UUID>"
  const { data, error, mutate } = useSWR<OcupacionResponse>(
    key, getOcupacion,                                // ← SWR passes `key` as fetcher arg
    ...
  );
  ```
- **`apps/electron-sucursal/src/features/operacion/api/ocupacionApi.ts:71-77`**:
  ```ts
  export async function getOcupacion(uuid_sucursal: string) {
    const params = new URLSearchParams({ uuid_sucursal }); // ← re-encodes the FULL key
    return parkosFetch(`${OCUPACION_PATH}?${params.toString()}`);
  }
  ```
- Result: `?uuid_sucursal=%2Foperacion%2Focupacion%3Fuuid_sucursal%3D<UUID>` → FastAPI 422.
- **Correct precedent (`useSesionActiva.ts:55-57`)** uses `() => getSesionActiva()` (no args) — fetcher closure ignores the key. Same correct pattern in `useIngresoActivo.ts:67-69`.

### Bug 3 — Branch DB MV `prod.mv_ocupacion_diaria` missing (backend/infra)
- **`backend/.../migrations/versions/0024_add_mv_ocupacion_diaria.py:89`** uses `CREATE MATERIALIZED VIEW prod.mv_ocupacion_diaria` WITHOUT `IF NOT EXISTS` (line 89). The UNIQUE INDEX (line 118) uses `IF NOT EXISTS`, but the view itself does not.
- Branch DB state confirmed via session #1795: `alembic_version = 0024_mv_ocupacion_diaria` BUT `to_regclass('prod.mv_ocupacion_diaria') IS NULL`. Subsequent migrations 0025-0033 applied cleanly → partial-commit state.
- **`backend/.../src/parkos_core/repo/ocupacion.py:106-110`** JOINs `prod.mv_ocupacion_diaria` → backend 500 every 10s for any operador with active polling.
- **`openspec/scripts/check_schema_match.py`** does NOT verify materialized-view existence (only tables, columns, UK, FK, REVOKE, triggers, partman). A re-application of `0024` would NOT recreate the MV — the gap that allowed the silent failure.

### Bug 4 — `detectar_tipo_vehiculo` vs catalog seed (backend, F6.1 blocker)
- **`backend/.../src/parkos_core/repo/placa.py:48-60`**:
  ```python
  if FORMATO_AUTO.match(placa):   tipo_nombre = "Auto"
  elif FORMATO_MOTO.match(placa): tipo_nombre = "Moto"
  ...
  stmt = select(TiposVehiculo.uuid).where(TiposVehiculo.tipo == tipo_nombre, ...)
  ```
- **`backend/scripts/replicate_catalogs_to_branch.py:20`** seeds branch with `('carro', 'moto', 'bicicleta', 'patineta')` (lowercase). No `Auto`/`Moto` row exists.
- **`backend/.../models/V/tipos_vehiculo.py:16`** docstring: `carro | moto | bicicleta`.
- **`backend/.../api/v1/operacion.py:177-186`** uses `detectar_tipo_vehiculo` BEFORE honouring the client's explicit `uuid_tipo_vehiculo` (which is in `IngresoCreate`, ignored). Helper returns `None` → 422 `placa_formato_invalido` for EVERY plate.
- **`backend/tests/unit/test_repo_placa.py:140-151`** asserts the current (buggy) behavior: `regex matches + catalog missing → None`. Fixing the lookup requires updating this test to seed the right `tipo` string.

### Bug 5 — `POST /caja-sesion/sesiones` rejects `observaciones`
- **`backend/.../schemas/caja.py:201-215`** `class SesionCreate(_Base)` does NOT declare `observaciones`. `_Base` has `extra="forbid"` (`schemas/common.py:28`) → 422 `extra_forbidden` on every POST with the field.
- **`backend/.../models/L_S/sesion.py:34-40`** ORM `Sesion` has no `observaciones` column.
- **`backend/.../repo/session_cycle.py:188-241`** `open_session` does not accept `observaciones`; `Sesion(...)` constructor does not pass it.
- **`apps/.../features/caja/api/schemas/turnoSchema.ts:37-51`** Zod schema has `observaciones: z.string().optional()`.
- **`openspec/specs/operations/spec.md:4907`** (REQ-OPS-119) MANDATES `observaciones` as part of the payload. The backend drift is the bug, not the FE.

### Cosmetic — `configuracion_seguridad_missing_fallback_to_defaults`
- **`backend/.../src/parkos_core/api/v1/auth.py:106-111`** warns when both per-branch row and global-default row are absent, then falls back to hardcoded `(5, 15)`. Branch DB has neither → repeated warning per login attempt.
- Mitigation is OUT OF SCOPE of this remediation (1-line warning, no UX impact, fix is a seed row); tracked as follow-up per orchestrator instruction.

## 2. Affected areas

| Path | Why affected |
|---|---|
| `apps/ui-kit/src/hooks/useAuth.ts:33-36` | `AuthUser.id` field declaration diverges from API `user.uuid` — root cause of bug 1 |
| `apps/ui-kit/src/hooks/useAuth.test.ts:43-56` | Mocks wrong shape; needs `uuid` instead of `id` |
| `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.tsx:51` | Reads `user?.id` (undefined) — needs `user?.uuid` |
| `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.tsx` (FormMessage for uuid_*) | Silent reject UX — needs inline error visibility |
| `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.test.tsx:131-135` | Mocks `user: { id: ... }` — must change to `uuid` to lock in fix |
| `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.ts:77` | `useSWR(key, getOcupacion, ...)` — fetcher must be a closure that captures `uuid_sucursal` only |
| `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.test.ts` | New U-O10 regression: fetcher invoked with `<UUID>` not `<key>` |
| `apps/electron-sucursal/src/features/operacion/hooks/useIngresoActivo.ts:67` | Already correct — reference pattern |
| `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts:55-57` | Already correct — reference pattern |
| `backend/.../migrations/versions/0024_add_mv_ocupacion_diaria.py:89` | Missing `IF NOT EXISTS` on `CREATE MATERIALIZED VIEW` |
| `backend/.../migrations/versions/0034_recreate_mv_ocupacion_diaria_idempotent.py` (NEW) | Idempotent view rebuild; `CREATE OR REPLACE` + post-check `to_regclass` |
| `openspec/scripts/check_schema_match.py` | Add `prod.mv_ocupacion_diaria` to the schema-conformance scan (CI gate) |
| `backend/.../src/parkos_core/repo/placa.py:48-60` | Look up `tipo='carro'`/`tipo='moto'` (lowercase) matching the catalog seed |
| `backend/.../api/v1/operacion.py:177` | Honour explicit `payload.uuid_tipo_vehiculo` first, fall back to regex detection |
| `backend/tests/unit/test_repo_placa.py:30-41` | Fixture must seed lowercase `carro`/`moto` rows; tests assert against lowercase |
| `backend/.../migrations/versions/0035_add_observaciones_to_sesion.py` (NEW) | `ALTER TABLE prod.sesion ADD COLUMN observaciones TEXT NULL` |
| `backend/.../models/L_S/sesion.py` | Add `observaciones: Mapped[str \| None]` |
| `backend/.../schemas/caja.py:201-215` | Add `observaciones: str \| None = Field(default=None, max_length=500)` |
| `backend/.../repo/session_cycle.py:188-241` | `open_session` accepts `observaciones: str \| None = None` |
| `backend/.../src/parkos_core/api/v1/auth.py:106-117` (cosmetic, optional) | Seed global default `configuracion_seguridad` row OR suppress warning |

## 3. Approaches — per bug

### Bug 1 — `AuthUser.id` ↔ API `uuid`
| Approach | Pros | Cons | Effort |
|---|---|---|---|
| **A. Rename `AuthUser.id` → `AuthUser.uuid` in useAuth.ts** | One-line shape fix at the source; matches backend; tests need one update each | Touches 3 consumers (`AbrirTurno`, `useAuth.test.ts`, downstream TS code using `user.id`) | **Low** |
| B. Add alias `id = uuid` in useAuth.ts return | No consumer changes; keeps `user.id` working | Lying type — drift risk; H1/H2 tests stay green but mock still wrong | Low |
| C. Backend renames `UserItem.uuid` → `UserItem.id` | Matches frontend | Breaks every other consumer of `/auth/me` (already wired via uuid) | High |

**Pick A** — cleanest, one-file rename + 2 test updates. `sucursal?.uuid` is already consistent, so `user?.uuid` is the analogous fix.

### Bug 2 — `useOcupacion` fetcher signature
| Approach | Pros | Cons | Effort |
|---|---|---|---|
| **A. `useSWR(key, () => getOcupacion(uuid_sucursal), ...)`** | Mirrors `useSesionActiva` and `useIngresoActivo` verbatim | One-line change | **Low** |
| B. Make `getOcupacion` parse the SWR key | Hidden parsing logic; ties API to SWR-internal shape | Smell; future SWR-shape changes break the API | Low |
| C. Drop the SWR key suffix; use only the UUID as the key | Dedupe across branches; loses per-branch cache | Operador- pinned — moot for v1, but blocks admin multi-branch later | Low |

**Pick A** — exactly the precedent (`useSesionActiva.ts:55-57`, `useIngresoActivo.ts:67-69`). Also add a new U-O10 test asserting `getOcupacion` is called with the raw UUID string.

### Bug 3 — Missing MV on branch DB
| Approach | Pros | Cons | Effort |
|---|---|---|---|
| **A. New migration `0034_recreate_mv_ocupacion_diaria_idempotent.py` that `CREATE OR REPLACE VIEW` + post-check `to_regclass`** | Idempotent; fixes existing prod state; `alembic upgrade head` re-runs it once to heal | The MV already has data — `CREATE OR REPLACE` recreates it (empty until first refresh) | **Low** |
| B. Manual `CREATE MATERIALIZED VIEW ... WITH NO DATA` from ops script | No new migration | Out of band; not in migration head; future branches with same drift must re-do | Low |
| C. Patch 0024 in-place to add `IF NOT EXISTS` | No new migration | `alembic upgrade head` won't re-run 0024 — same problem | Low |

**Pick A** plus **add `prod.mv_ocupacion_diaria` to `check_schema_match.py`'s mandatory-table list** (CI gate so this can't happen again). Also: edit 0024 in-place to add `IF NOT EXISTS` for FUTURE re-application safety — separate concern, not required for the immediate fix.

### Bug 4 — catalog seed mismatch
| Approach | Pros | Cons | Effort |
|---|---|---|---|
| **A. Change `detectar_tipo_vehiculo` to lowercase `tipo_nombre = "carro"/"moto"`** | One-line fix; aligns to seeded catalog; aligns to model docstring | `test_repo_placa.py` fixture must update from `tipo='Auto'` to `tipo='carro'`; `SAMPLE_OK` in `useOcupacion.test.ts:111` uses `tipo: 'Auto'` too | **Low** |
| B. Add `Auto`/`Moto` rows via migration seed | Mirrors existing `replicate_catalogs_to_branch.py` data | Two synonyms for the same class — bi-temporal close-and-insert required to remove duplicates; touches 5+ tests | High |
| C. Honour `payload.uuid_tipo_vehiculo` first, detect second | Lets client explicitly choose (REQ-OPS-119 already carries `uuid_tipo_vehiculo`) | Doesn't fix the implicit detection; F6.1 frontend may not always send the explicit UUID | Medium |

**Pick A** — minimal, correct, matches the canonical catalog (`replicate_catalogs_to_branch.py` is the source of truth for branch seeding). Also add Scenario 4 in `operacion.py` to honour explicit `payload.uuid_tipo_vehiculo` (defense in depth — but only if the field is populated; current F6.1 doesn't always send it, so this is forward-friendly, not blocking).

### Bug 5 — `observaciones` rejected by `extra='forbid'`
| Approach | Pros | Cons | Effort |
|---|---|---|---|
| **A. Migration `0035_add_observaciones_to_sesion.py` + ORM + schema + `open_session` accept kwarg** | Spec-compliant (REQ-OPS-119 mandates `observaciones`); bi-temporal `log_transaccional` captures the value; future `SesionRead` exposes it | 4 files + 1 migration; test for `observaciones_cierre` precedent (`F1.13`) may need re-check | **Medium** |
| B. Drop the field from frontend schema | No backend change | Spec violation; loses audit trail; REQ-OPS-119 already ratified the field | Medium (frontend rework + i18n key removal) |
| C. Backend reads `observaciones` from `model_extra` (defeat `extra='forbid'`) | No schema/migration change | Defeats defense-in-depth XR6 (extra='forbid' is canon per `_Base`); one-off exception propagates badly | Low |

**Pick A** — spec is canonical, schema/ORM/migration are the missing pieces. Note: `Sesion` is `[L-S]` (no versioning) but it carries an audit baseline (`created_at`, `created_by`). The `observaciones` value should also be recorded in the co-transactional `log_transaccional.datos_nuevos` (consistent with the existing log row in `open_session`).

### Cosmetic — `configuracion_seguridad` warnings
| Approach | Pros | Cons | Effort |
|---|---|---|---|
| Suppress (mark as out of scope per orchestrator) | Zero scope creep | Warning noise persists | Zero |
| Seed a global-default row via migration | One-time fix | Touches DB; needs `vigente_hasta=NULL` + bi-temporal insert | Low |

**Pick "suppress"** per orchestrator instruction; the warning is informational and the hardcoded `(5, 15)` default matches the plan.md contract.

## 4. Recommendation

**Three chained PRs** for review focus (each < 800 LOC, each ~200-400):

1. **PR-FE — `fix(frontend): AuthUser.id → uuid + useOcupacion fetcher closure`**
   Touches: `useAuth.ts`, `AbrirTurno.tsx`, `useOcupacion.ts`, their 3 test files. ~120 LOC. Closes bugs 1 & 2.
2. **PR-BE-MV — `fix(backend+infra): recreate mv_ocupacion_diaria + schema_match gate`**
   New migration `0034_recreate_mv_ocupacion_diaria_idempotent.py`, edit `0024` to add `IF NOT EXISTS`, add MV check to `check_schema_match.py`. ~60 LOC. Closes bug 3.
3. **PR-BE-CATALOG-SESION — `fix(backend): detectar_tipo_vehiculo lowercase + sesion.observaciones`**
   New migration `0035_add_observaciones_to_sesion.py`, edits in `repo/placa.py`, `models/L_S/sesion.py`, `schemas/caja.py`, `repo/session_cycle.py`, `api/v1/operacion.py`, test updates in `test_repo_placa.py`. ~150 LOC. Closes bugs 4 & 5.

PR-FE and PR-BE-CATALOG-SESION can land in either order (different layers, no git conflict). PR-BE-MV is independent — it can land first to unblock the F4.3 polling loop.

**Out of scope** (suppress per orchestrator): `configuracion_seguridad_missing_fallback_to_defaults` warning. Cosmetic, plan-aligned hardcoded fallback already documented.

## 5. Risks

- **R1 (High, Bug 4)**: Changing `detectar_tipo_vehiculo` from `'Auto'`/`'Moto'` to `'carro'`/`'moto'` is a one-way contract change. Any external consumer (admin UI, future mobile) that calls `detectar_tipo_vehiculo` and branches on the string will break. Mitigate: keep the return type as `uuid_lib.UUID | None` (no string return — `open_session` and `operacion.py` callers consume UUIDs, not labels). Verify via grep: only `repo/placa.py:48-60` returns the string internally; consumers consume UUID. **The string is internal — safe.**
- **R2 (Medium, Bug 5)**: Adding `observaciones` to `prod.sesion` causes `alembic upgrade head` to rewrite `prod.sesion` rows on a populated DB. Mitigation: `ALTER TABLE … ADD COLUMN TEXT NULL` is **instant in PostgreSQL 11+** (no table rewrite, no lock). Verify with `alembic upgrade --sql` pre-flight.
- **R3 (Medium, Bug 5)**: `extra='forbid'` is the canon (defense in depth XR6). Adding a new schema field is fine, but the `_Base` rule still rejects unknown fields — make sure the field is declared in `SesionCreate` AND `SesionRead` (so reads don't 422 either).
- **R4 (High, Bug 3)**: The branch DB is the only known instance with the missing MV. After PR-BE-MV lands, we MUST run `alembic upgrade head` against the live branch container before F4.3 polling can resume; otherwise the migration will be a no-op (`alembic_version` already at 0034) and operators still see 500s. Mitigate: include a one-line psql verification in the PR description: `SELECT to_regclass('prod.mv_ocupacion_diaria');` after upgrade.
- **R5 (Medium, Bug 1)**: Renaming `AuthUser.id` → `AuthUser.uuid` may break ANY FE code that destructures `user.id` outside the 5 known files. Mitigate: `git grep -rn "user?.id\|user\.id" apps/ electron-sucursal` BEFORE the rename; only 3 sites (`AbrirTurno.tsx`, `AbrirTurno.test.tsx`, the `useAuth.test.ts` mock) are known. Add a `tsc --noEmit` CI gate.
- **R6 (Low, Bug 2)**: `useOcupacion.ts` change is small but the SWR pattern is wrong in two more places if any other hook passes the fetcher reference directly. Mitigate: `git grep -n "useSWR<.*>(.*, [a-zA-Z]*, {" apps/electron-sucursal` — only `useOcupacion.ts` matches the antipattern today; `useIngresoActivo` and `useSesionActiva` already correct.
- **R7 (Low, Bug 5)**: The F1.13 close-session test (`test_cierre_turno`) sends `observaciones_cierre` in the PUT body — verify that schema also accepts it (separate `SesionUpdate` vs `SesionCreate`). Audit: `grep -n "observaciones_cierre\|observaciones" backend/.../schemas/caja.py`.
- **R8 (Low, cross-cutting)**: The OpenAPI JSON files under `packages/api_admin/openapi.json` and `packages/api_sucursal/openapi.json` are auto-generated. PR-BE-CATALOG-SESION must regenerate them or the docs drift.

## 6. Open questions

- Q1 (Bug 4): Does `replicate_catalogs_to_branch.py` need to be updated too? Right now it seeds `('carro', 'moto', 'bicicleta', 'patineta')`. Lowercase matches the corrected repo lookup — no script change needed. **Answer: no.**
- Q2 (Bug 4): Should `F6.1` frontend be allowed to pass `uuid_tipo_vehiculo` explicitly going forward (REQ-OPS-119 mentions it)? The frontend schema `abrirTurnoSchema` doesn't have it. The current `operacion.py:177` ignores it. **Answer: keep current behavior (regex detection) for v1; surface explicit-UUID support as a follow-up.**
- Q3 (Bug 3): Should `check_schema_match.py` also assert the existence of the UNIQUE INDEX on the MV? **Answer: yes — add as part of the same PR-BE-MV change; the UNIQUE INDEX is what enables `REFRESH CONCURRENTLY` and is part of REQ-OPS-032's "MUST".**

## 7. Ready for proposal

**Yes.** All 5 bugs have:
- Confirmed root cause (matches prior memory observations #1792, #1793, #1794, #1795)
- Confirmed test files that need extension (not replacement)
- Affected files mapped to 1-3 LOC each
- Precedent pattern identified for the 2 frontend fixes (`useSesionActiva`, `useIngresoActivo`)
- Spec reference (REQ-OPS-119 for `observaciones`; REQ-OPS-032 for MV)
- Migration head confirmed (`0033_login_historic_index` → next is `0034`)

The change naturally splits into 3 chained PRs (frontend / backend+infra MV / backend catalog+sesion) — recommend `delivery_strategy=auto-chain` per AGENTS.md hard rule.

**Next phase**: `sdd-propose` to formalize the scope, approach, and rollback plan for each of the 3 PRs.

## 8. Engram

Persisted post-write to topic_key `sdd/qa-2026-09-17-bug-remediation/explore` (type=architecture, scope=project, capture_prompt=false).
