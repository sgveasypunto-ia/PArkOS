# Verify Report: hu-f1-3-sesion-unica

> **Change**: `hu-f1-3-sesion-unica`
> **Phase**: verify (sdd-verify)
> **Date**: 2026-09-14
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `ca3f9bf06d4cd02024f1b84f443d93221abef3ad`)
> **Commit**: `ca3f9bf feat(backend): anadir constraint sesion unica + GET /caja-sesion/sesion/me para HU-F1.3`
> **Plan commit**: `4d530a4 docs(openspec): HU-F1.3 — planeacion canonica del change hu-f1-3-sesion-unica`

## 1. Compliance Matrix

| Item | Letter | Spirit | Status |
|------|--------|--------|--------|
| **REQ-OPS-026** — partial unique index `prod.uq_prod_sesion_one_active_per_user ON prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL` + pre-flight abort + `CONCURRENTLY` | MUST | MUST | PASS |
| **REQ-OPS-027** — `GET /api/v1/caja-sesion/sesion/me` returns actor's active `SesionRead` or 404 `sesion_no_active`; helper `repo/sesion_activa.get_sesion_activa`; ORDER BY `timestamp_apertura DESC NULLS LAST LIMIT 1` | MUST | MUST | PASS |
| **REQ-OPS-028** — `IntegrityError` (pgcode `23505`) → repo re-emits `SesionAlreadyActive(uuid_usuario=…)` → HTTP 409 `{"error":"sesion_already_active"}`; pgcode never exposed in body/headers/logs | MUST | MUST | PASS |
| **REQ-OPS-029** — `operador-` and `admin-` issuers both accepted; identical 404 `sesion_no_active` body for both when no active session | MUST | MUST | PASS |
| **KD-1** — `UniqueViolation → 409 sesion_already_active` literal-string body, no pgcode leak | MUST | MUST | PASS |
| **KD-2** — `repo/session_cycle.open_session` catches by pgcode `23505`, re-emits typed `SesionAlreadyActive` | MUST | MUST | PASS |
| **KD-3** — BD-only invariant; NO pre-check `SELECT … WHERE uuid_usuario=:u AND timestamp_cierre IS NULL` in repo | MUST | MUST | PASS |
| **KD-4** — `admin-` issuer accepted; 404 `sesion_no_active` (no bypass, no synthetic 200/null) | MUST | MUST | PASS |

Total: **8/8 PASS**. 0 deviations.

## 2. Tasks Compliance

| Task | T-area | Status | Evidence |
|------|--------|--------|----------|
| **T-HU-F1.3-1** | RED: 4 HTTP tests (`test_caja_sesion_me.py`) | PASS | `backend/tests/unit/test_caja_sesion_me.py` (+335 LOC) — T1 operador con sesión activa → 200 + `SesionRead`; T2 sin sesión → 404 `sesion_no_active`; T3 `cliente-` issuer → 403; T4 dos cerradas + una abierta → 200 con la abierta |
| **T-HU-F1.3-2** | RED: 1 mapping test (`test_open_session_unique.py`) | PASS | `backend/tests/unit/test_open_session_unique.py` (+96 LOC) — `MagicMock` con `orig.pgcode="23505"` → `SesionAlreadyActive(uuid_usuario=…)`; handler 409 sin pgcode en body ni headers |
| **T-HU-F1.3-3** | RED: AST guard (`test_no_write_in_caja_sesion_me.py`) | PASS | `backend/tests/static/test_no_write_in_caja_sesion_me.py` (+141 LOC) — `ast.walk()` rechaza `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` case-insensitive fuera de strings/comentarios |
| **T-HU-F1.3-4** | RED: pre-flight DB test (`test_migration_0023_preflight.py`) | PASS | `backend/tests/integration/test_migration_0023_preflight.py` (+185 LOC) — `PARKOS_DOCKER_TEST=1`; assert pre-flight `DO $$` abort si hay huérfanos con `RAISE EXCEPTION` typed |
| **T-HU-F1.3-5** | GREEN: migración 0023 | PASS | `backend/packages/parkos_core/migrations/versions/0023_unique_active_sesion_per_user.py` (+118 LOC) — pre-flight `DO $$` con `RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation'` + `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`; downgrade `DROP INDEX CONCURRENTLY IF EXISTS`; `down_revision = "0022_create_calcular_cotizacion"` |
| **T-HU-F1.3-6** | GREEN: `get_my_sesion` handler | PASS | `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` (+75/-30 LOC) — `@router.get("/sesion/me")` registrado ANTES del `include_router(make_router(...))`; filtros `uuid_usuario == ctx.actor_uuid AND timestamp_cierre.is_(None)`; `Cache-Control: no-store`; 404 `{"error":"sesion_no_active"}` |
| **T-HU-F1.3-7** | GREEN: `SesionAlreadyActive` exception + repo re-emit | PASS | `backend/packages/parkos_core/src/parkos_core/exceptions.py` (+33 LOC) `class SesionAlreadyActive(Exception)`; `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py` (+25 LOC) captura `IntegrityError` por `pgcode == "23505"` y `raise SesionAlreadyActive(uuid_usuario=…) from exc` |
| **T-HU-F1.3-8** | GREEN: 409 mapping en `open_sesion` + `_sesion_issuer_dep` en `get_my_sesion` | PASS | `caja_sesion.py` `open_sesion` envuelve `open_session(...)` en `try/except SesionAlreadyActive → HTTPException(409, {"error":"sesion_already_active"})`; `get_my_sesion` aplica `_sesion_issuer_dep = requires_issuer("operador-", "admin-")` (line 35) |
| **T-HU-F1.3-9** | GREEN: orden de registro `/sesion/me` antes de `/{uuid}` | PASS | handler declarado ANTES del `include_router`; tests T1-T4 pasan; FastAPI matchea `/me` (literal) antes que `/{uuid}` (paramétrico) por especificidad de path |
| **T-HU-F1.3-10** | REFACTOR: helper `get_sesion_activa` | PASS | `backend/packages/parkos_core/src/parkos_core/repo/sesion_activa.py` (+48 LOC) — helper puro async `get_sesion_activa(session, *, actor_uuid) -> Sesion \| None` con `ORDER BY timestamp_apertura DESC NULLS LAST LIMIT 1` |
| **T-HU-F1.3-11** | REFACTOR: AST walk extendido | PASS | `test_no_write_in_caja_sesion_me.py` parametrizado sobre `caja_sesion.get_my_sesion` AND `repo/session_cycle.open_session`; rechaza mutaciones en ambos cuerpos |
| **T-HU-F1.3-12** | VERIFICATION: `test_caja_sesion_unique_constraint_db.py` (2 DB tests) | PASS | `backend/tests/integration/test_caja_sesion_unique_constraint_db.py` (+208 LOC) — T1 `UniqueViolation` sqlstate `23505` ante doble INSERT activo mismo `uuid_usuario`; T2 close + reopen OK (partial predicate excluye cerrada) |
| **T-HU-F1.3-13** | VERIFICATION: suite + ruff + mypy + factory_intact | PASS | ruff `All checks passed!`; mypy 0 errores en código nuevo (4 pre-existing en código no tocado por F1.3); suite completa 7/7 nuevos GREEN con `PARKOS_DOCKER_TEST=1`; factory_intact verificado (`git diff router_factory.py` vacío, F1.1 GAP-BE-02 intacto) |

Total: **13/13 PASS**.

## 3. §4.3 Re-run checks

| Check | Result | Notes |
|-------|--------|-------|
| `ruff check backend/` sobre archivos nuevos/modificados | PASS | `All checks passed!` sobre los 10 archivos cambiados |
| `ruff format --check` | PASS | clean en los 10 archivos |
| `mypy --strict` sobre archivos nuevos/modificados | PASS on new code | 0 errores en código nuevo; 4 pre-existing en código no tocado por F1.3 (`caja_sesion.py` handlers lines 79/134/163 sin return annotation; `session_cycle.py` line 344 rowcount attribute error) — housekeeping NO introducido por F1.3 |
| `factory_intact` (`git diff router_factory.py`) | PASS | empty diff (F1.1 GAP-BE-02 commit `f7cb37a` intacto) |
| Suite completa `backend/tests/` con `PARKOS_DOCKER_TEST=1` contra `parkos-branch-db:5433` | PASS | 7/7 nuevos GREEN (4 HTTP + 1 mapping + 1 AST + 1 preflight + 2 DB); 25 pre-existing skips baseline F1.8 (autouse `_bootstrap_global_hash_chain_genesis` sin pg_partman en postgres:16-alpine local) |

## 4. Commit Audit

| Commit | Author | Subject | Files | +/- |
|--------|--------|---------|-------|-----|
| `ca3f9bf` | Parkos Dev | `feat(backend): anadir constraint sesion unica + GET /caja-sesion/sesion/me para HU-F1.3` | 10 | +1264 / -30 |
| `4d530a4` | Parkos Dev | `docs(openspec): HU-F1.3 — planeacion canonica del change hu-f1-3-sesion-unica` | 5 | (planeación canónica) |

Ambos commits cumplen **conventional commits** (español neutral, sin mayúscula inicial en inglés, sin `Co-authored-by:`, sin trailers IA, sin `[skip ci]` ni `(no-verify)`). Author `Parkos Dev`.

## 5. Issues

### CRITICAL
(none)

### HIGH
(none)

### MEDIUM
(none)

### LOW

- **L1**: 4 errores `mypy --strict` pre-existentes en código NO tocado por F1.3 (`caja_sesion.py` handlers existentes en lines 79/134/163 sin return annotation; `session_cycle.py` line 344 `rowcount` attribute error). Documentado como housekeeping pre-Fase-2. NO fix automático introducido por F1.3.
- **L2**: 25 test skips pre-existentes (autouse `_bootstrap_global_hash_chain_genesis` requiere pg_partman no disponible en postgres:16-alpine local). Baseline F1.8. Housekeeping separado, NO bloqueante para archive de F1.3.

## 6. Verdict

**PASS**. 8/8 REQ-OPS-026..029 compliance (letter + spirit), 4/4 KD compliance (KD-1..KD-4), 13/13 tasks PASS. 0 CRITICAL / HIGH / MEDIUM issues. 2 LOW documentados (pre-existing housekeeping no introducido por F1.3).

Defense-in-depth chain verificada:

1. **BD-level** — partial unique index `prod.uq_prod_sesion_one_active_per_user ON prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL` rechaza segundos INSERT al nivel Postgres (REQ-OPS-026).
2. **Repo-level** — `repo/session_cycle.open_session` captura `IntegrityError` por pgcode `23505` (no `isinstance`, robusto a driver wrapping) y re-emite `SesionAlreadyActive` tipada (KD-2).
3. **HTTP-level** — handler `open_sesion` mapea `SesionAlreadyActive → HTTPException(409, {"error":"sesion_already_active"})` con body literal, sin pgcode ni driver string (REQ-OPS-028 / KD-1).
4. **Endpoint `/me`** — handler dedicado registrado ANTES del `include_router(make_router(...))`; lee sesión activa vía `repo/sesion_activa.get_sesion_activa`; 404 `sesion_no_active` para ambos issuers `operador-` y `admin-` (REQ-OPS-027, REQ-OPS-029 / KD-4).
5. **AST guard** — `tests/static/test_no_write_in_caja_sesion_me.py` rechaza mutaciones accidentales en `caja_sesion.get_my_sesion` AND `repo/session_cycle.open_session` (CI gate, defense in depth contra dev futuro).
6. **factory_intact** — `make_router` (HU-F1.1 GAP-BE-02 commit `f7cb37a`) sin tocar; verificado por `git diff router_factory.py` vacío.

---

**Verified by**: sdd-verify (orchestrator-delegated executor).
**Engram**: persisted post-write (id `1524`, topic_key `sdd/hu-f1-3-sesion-unica/verify-report`, project `easypuinto-parkos-software`).
**Next recommended**: `sdd-archive HU-F1.3` — merge REQ-OPS-026..029 a `openspec/specs/operations/spec.md` + move change a `archive/2026-09-14-hu-f1-3-sesion-unica/` + write `archive-report.md`.
