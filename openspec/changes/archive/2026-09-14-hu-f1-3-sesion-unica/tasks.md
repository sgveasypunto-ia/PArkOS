# Tasks: hu-f1-3-sesion-unica

> **Change**: `hu-f1-3-sesion-unica`
> **Phase**: apply (sdd-tasks) — checklist only, do NOT implement
> **HU**: HU-F1.3 — DB partial unique index on `prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL` + custom endpoint `GET /api/v1/caja-sesion/sesion/me`
> **Status**: READY — 13/13 tasks planned (4 RED + 5 GREEN + 2 REFACTOR + 2 VERIFICATION), TDD-strict
> **Preflight (this session)**: `pace=auto`, `artifact_store=hybrid`, `delivery_strategy=auto-chain`,
>   `review_budget_lines=400` (vigente en `openspec/config.yaml`)
> **Branch topology**: rama única `feat/fase-1-prerequisites-backend` (HEAD `a779b79`); un único PR directo
>   a `feat/fase-1-prerequisites-backend` por chained-pr policy (cambio chico, ~540 LOC incluido tests).
> **Inputs read**: `exploration.md` (KD-1..KD-4 preliminaries, archivos a tocar §11), `proposal.md`
>   (D-HU-F1.3-1..8, decisiones KD confirmadas §2), `specs/operational/spec.md` (REQ-OPS-026..029 RFC 2119),
>   `design.md` (11 secciones, 4 KD, SQL skeleton §5, endpoint design §6, threat matrix §8, risks §9),
>   precedent `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/tasks.md` (13 tasks T-HU-F1.8-1..13,
>   PL/pgSQL migration + custom handler + AST walk pattern, commit `a3d0c39`).
> **Skills loaded**: `python`, `gentle-sdd-tasks` (paths injected)

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~540 across 1 PR (migración ~70 LOC + endpoint ~25 LOC + repo helper ~20 LOC + exception ~10 LOC + handler modification ~6 LOC + unit tests ~200 LOC + integration tests ~80 LOC + static AST test ~50 LOC + spec delta ~30 LOC) |
| Total tasks | 13 (4 RED + 5 GREEN + 2 REFACTOR + 2 VERIFICATION) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | Low — cambio cohesivo en un módulo `caja_sesion.py` + un helper `sesion_activa.py` + un repo `session_cycle.py` + una migración + tres archivos de tests; sin tocar UI, ORMs ni otros endpoints |
| Chained PRs recommended | No — alcance acotado a un único recurso `[L-S]` con soporte DB-level + handler read-only |
| Chain strategy | n/a (single PR) |
| Suggested split | Un único PR: `feat/fase-1-prerequisites-backend` → `main` |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No |

| Phase | Tasks | LOC est. | Cumulative LOC |
|-------|-------|----------|----------------|
| Phase 1: RED (tests fail) | T-1..T-4 | ~250 LOC (tests) | 250 |
| Phase 2: GREEN (impl passes) | T-5..T-9 | ~110 LOC (impl + migration) | 360 |
| Phase 3: REFACTOR + STATIC | T-10..T-11 | ~70 LOC (AST guard + extract helpers) | 430 |
| Phase 4: VERIFICATION | T-12..T-13 | integration tests + suite | 110 |
| **Total** | **13** | **~540 LOC** (incluyendo tests) | — |

> Tope por commit: <800 LOC. Tests típicamente no cuentan al tope pero los cuento para forecast.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| PR1 (único) | Migración 0023 (pre-flight + partial unique index CONCURRENTLY) + helper `repo/sesion_activa.py` + exception `SesionAlreadyActive` + mapping `IntegrityError → 409` en repo + handler `GET /sesion/me` ANTES del `make_router` + mapping `SesionAlreadyActive → 409` en `open_sesion` + 4 unit HTTP tests + 1 mapping test + 2 DB integration tests + AST walk + delta en spec canonical | `feat/fase-1-prerequisites-backend` → `main` | `uv run pytest backend/tests/unit/test_caja_sesion_me.py backend/tests/unit/test_sesion_already_active_mapping.py backend/tests/integration/test_caja_sesion_unique_constraint_db.py backend/tests/static/test_no_write_in_caja_sesion_me.py -q` | `pg_engine` real (`parkos-branch-db:5433`) para tests integración con `PARKOS_DOCKER_TEST=1`; unit tests sin DB; AST check parsea `caja_sesion.py` | Revert PR; migración se elimina con `alembic downgrade -1` (DROP INDEX CONCURRENTLY); handler se elimina al revertir el router; AST check se elimina con el archivo de test |

## Tareas

### Phase 1: RED — escribir tests que fallan

- [ ] **T-HU-F1.3-1** [RED] — `test_caja_sesion_me.py` con 4 HTTP tests
  - Tests:
    - T1: `operador-` con sesión activa → 200 + `SesionRead`.
    - T2: `operador-` sin sesión activa → 404 `sesion_no_active`.
    - T3: `cliente-` JWT → 403 (issuer no permitido).
    - T4: `operador-` con 2 cerradas + 1 abierta → 200 con la abierta (orden DESC).
  - Patrón F1.8: `httpx.AsyncClient` + `ASGITransport` + JWT operador fixture.
  - **Acción**: parametrizar `pytest` con los 4 escenarios del design.md §7 T1-T4; usar `httpx.AsyncClient(transport=ASGITransport(app))` + fixture `operator_jwt` + `pg_engine` real para sembrar sesiones según cada caso. — **Archivos**: `backend/tests/unit/test_caja_sesion_me.py` (nuevo). — **Validación**: `uv run pytest backend/tests/unit/test_caja_sesion_me.py -q` reporta collection error `404 Not Found` por ruta `/sesion/me` no registrada o `ImportError` de `repo.sesion_activa`.

- [ ] **T-HU-F1.3-2** [RED] — `test_sesion_already_active_mapping.py` con 1 mapping test
  - Tests:
    - T5: `open_session()` con `IntegrityError` simulando `pgcode == "23505"` → raises `SesionAlreadyActive(uuid_usuario=…)`.
    - T6: `open_sesion` handler con `SesionAlreadyActive` forzado → 409 con body `{"error": "sesion_already_active"}` y SIN pgcode en body ni headers.
  - Patrón F1.2 (`MagicMock(exc)` con `orig.pgcode == "23505"`).
  - **Acción**: usar `MagicMock` para simular `IntegrityError` con `orig.pgcode = "23505"`; invocar `open_session()` directamente; asserts sobre tipo de excepción y `uuid_usuario` payload. — **Archivos**: `backend/tests/unit/test_sesion_already_active_mapping.py` (nuevo). — **Validación**: `uv run pytest backend/tests/unit/test_sesion_already_active_mapping.py -q` falla con `ImportError` de `exceptions.SesionAlreadyActive` o con `AttributeError` por método no instrumentado.

- [ ] **T-HU-F1.3-3** [RED] — `test_no_write_in_caja_sesion_me.py` AST guard (defense in depth)
  - Test: AST walk sobre `caja_sesion.py::get_my_sesion` rechaza `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` en el cuerpo.
  - Patrón F1.8: greps sobre la función `get_my_sesion` parseada con `ast.parse()`, rechaza tokens case-insensitive fuera de strings/comentarios.
  - **Acción**: usar `ast` para localizar la función `get_my_sesion` en `caja_sesion.py`; tokenizar identificadores; reportar el primer match ofensivo con línea y número de ocurrencia. — **Archivos**: `backend/tests/static/test_no_write_in_caja_sesion_me.py` (nuevo). — **Validación**: `pytest --collect-only backend/tests/static/test_no_write_in_caja_sesion_me.py -q` reporta `no tests ran` o `file not found`; tras T-HU-F1.3-6 (handler creado), el test debe pasar.

- [ ] **T-HU-F1.3-4** [RED] — CONFIRMAR RED textual — ejecutar `uv run pytest --collect-only backend/tests/unit/test_caja_sesion_me.py backend/tests/unit/test_sesion_already_active_mapping.py backend/tests/static/test_no_write_in_caja_sesion_me.py -q` y capturar log; objetivo: 7 items colectados (4 HTTP + 2 mapping + 1 AST), todos en estado RED (collection error o fallo controlado por ruta no montada).

  RED evidence (esperado tras T-HU-F1.3-1..3):
    - `pytest --collect-only`: 7 items collected (4 HTTP + 2 mapping + 1 AST).
    - Files written and parse-clean:
      - `backend/tests/unit/test_caja_sesion_me.py` (~150 LOC, 4 tests)
      - `backend/tests/unit/test_sesion_already_active_mapping.py` (~80 LOC, 2 tests)
      - `backend/tests/static/test_no_write_in_caja_sesion_me.py` (~50 LOC, 1 test)
    - RED-by-construction verified:
      - The endpoint `GET /api/v1/caja-sesion/sesion/me` is NOT registered → HTTP tests would return 404 (path not found).
      - The exception `SesionAlreadyActive` does NOT exist → mapping tests would raise `ImportError`.
      - The handler `get_my_sesion` does NOT exist → AST test would raise `FileNotFoundError` o `ast.AttributeError`.

### Phase 2: GREEN — implementar lo mínimo para pasar

- [ ] **T-HU-F1.3-5** [GREEN] — `0023_add_sesion_unique_active.py` migration
  - Archivo: `backend/packages/parkos_core/migrations/versions/0023_add_sesion_unique_active.py`
  - Contenido: pre-flight `DO $$ … RAISE EXCEPTION 'unique_active_sesion_preflight_failed: % …' $$` + `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS prod.uq_prod_sesion_one_active_per_user ON prod.sesion (uuid_usuario) WHERE timestamp_cierre IS NULL`. Downgrade: `DROP INDEX CONCURRENTLY IF EXISTS prod.uq_prod_sesion_one_active_per_user`.
  - `revision = "0023_sesion_unique_active"`, `down_revision = "0022_create_calcular_cotizacion"` (F1.8 consumed 0022).
  - **Acción**: pegar exactamente el SQL skeleton del design.md §5 (pre-flight con `SELECT count(*) … HAVING count(*) > 1` + `RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation'` + CREATE INDEX CONCURRENTLY); header `from __future__ import annotations` + `from alembic import op`. — **Archivos**: `backend/packages/parkos_core/migrations/versions/0023_add_sesion_unique_active.py` (nuevo). — **Validación**: `uv run alembic upgrade head` aplica la 0023 sin error contra `parkos-branch-db` con `PARKOS_DOCKER_TEST=1`; `\d prod.sesion` en psql muestra el índice `uq_prod_sesion_one_active_per_user` con predicado `WHERE timestamp_cierre IS NULL`.

- [ ] **T-HU-F1.3-6** [GREEN] — `get_my_sesion` handler en `caja_sesion.py`
  - Agregar handler ANTES del `router.include_router(make_router(...))` (líneas 193-207) para evitar colisión con `/sesion/{uuid}`.
  - Filtros: `Sesion.uuid_usuario == ctx.actor_uuid AND Sesion.timestamp_cierre.is_(None)`.
  - ORDER BY: `Sesion.timestamp_apertura.desc().nulls_last()`.
  - Limit 1, 404 si None con body `{"error": "sesion_no_active"}`.
  - `Cache-Control: no-store` header (consistente con F1.8 R8).
  - Helper `repo/sesion_activa.py::get_sesion_activa(session, *, actor_uuid) -> Sesion | None` (NUEVO, ~20 LOC).
  - **Acción**: importar `get_sesion_activa` desde `repo.sesion_activa`; usar `Response` injection para header `Cache-Control`; docstring con referencia a REQ-OPS-027 + REQ-OPS-029. — **Archivos**: `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` (modificado, handler agregado ANTES de include_router); `backend/packages/parkos_core/src/parkos_core/repo/sesion_activa.py` (nuevo). — **Validación**: T-1, T-2, T-4 pasan; T-3 falla por ahora (mapping pendiente, T-HU-F1.3-8); T-5 mapping test pasa una vez creado `SesionAlreadyActive` exception (T-HU-F1.3-7).

- [ ] **T-HU-F1.3-7** [GREEN] — `SesionAlreadyActive` exception en `exceptions.py`
  - Agregar class `SesionAlreadyActive(Exception)` con atributo `uuid_usuario: UUID` para ops triage.
  - En `repo/session_cycle.py::open_session`: envolver `session.flush()` en `try/except IntegrityError as exc:`; detectar `pgcode == "23505"` vía `getattr(getattr(exc, "orig", None), "pgcode", None)`; raise `SesionAlreadyActive(uuid_usuario=uuid_usuario) from exc`; re-raise otros `IntegrityError` unchanged.
  - **Acción**: importar `IntegrityError` de `sqlalchemy.exc`; usar `UniqueViolation.sqlstate == "23505"` para comparar (precedente F1.8 con `pgcode`). — **Archivos**: `backend/packages/parkos_core/src/parkos_core/exceptions.py` (nuevo, ~10 LOC); `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py` (modificado, +12 LOC en `open_session`). — **Validación**: T-5 (mapping test pgcode) pasa; `python -c "from parkos_core.exceptions import SesionAlreadyActive; print(SesionAlreadyActive.__doc__)"` ejecuta sin error.

- [ ] **T-HU-F1.3-8** [GREEN] — Mapear 409 en `caja_sesion.py::open_sesion` + 403 en `get_my_sesion`
  - En `open_sesion`: envolver la llamada a `open_session(...)` en `try/except SesionAlreadyActive` → `HTTPException(409, detail={"error": "sesion_already_active"})`. Body MUST NOT contain pgcode, raw driver message.
  - En `get_my_sesion`: aplicar `_sesion_issuer_dep` ya existente (`requires_issuer("operador-", "admin-")` línea 35). FastAPI automáticamente rechaza issuers no listados con 403 (T-3 verde).
  - **Acción**: importar `SesionAlreadyActive` desde `exceptions`; usar `try/except` específico por subclase; mantener `await session.commit()` DESPUÉS del try block. — **Archivos**: `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` (modificado, +6 LOC en `open_sesion`, `_sesion_issuer_dep` aplicado en `get_my_sesion`). — **Validación**: T-3 (issuer rechazado) pasa; T-6 (mapping 409) pasa; `pgcode` string nunca aparece en response body ni headers (asserted en T-6).

- [ ] **T-HU-F1.3-9** [GREEN] — CONFIRMAR GREEN — ejecutar `uv run pytest -q backend/tests/unit/test_caja_sesion_me.py backend/tests/unit/test_sesion_already_active_mapping.py backend/tests/static/test_no_write_in_caja_sesion_me.py`; objetivo: 7/7 passed. — **Acción**: capturar log con timestamp; si hay fallo, NO marcar esta task como completada — reabrir T-HU-F1.3-5..8 correspondiente. — **Archivos**: ninguno nuevo (verifica los previos). — **Validación**: log muestra `7 passed` sin warnings; el AST check confirma 0 mutaciones en `get_my_sesion`; los 4 HTTP tests cubren T1-T4; los 2 mapping tests cubren T5-T6.

  Log esperado (post-GREEN):
  ```
  tests\unit\test_caja_sesion_me.py ....                                  [ 50%]
  tests\unit\test_sesion_already_active_mapping.py ..                     [ 75%]
  tests\static\test_no_write_in_caja_sesion_me.py .                       [100%]
  ============================== 7 passed in <TBD>s ==============================
  ```

### Phase 3: REFACTOR + STATIC

- [ ] **T-HU-F1.3-10** [REFACTOR] — Extraer `select_active_sesion_by_usuario()` helper en `repo/session_cycle.py`
  - Si hay duplicación entre `get_sesion_activa` y el mapping test setup, extraer un helper puro `select_active_sesion_by_usuario(session, *, actor_uuid) -> Sesion | None` reusado por tests y por el handler.
  - Aplicar `ruff format` sobre los archivos modificados; revisar `__all__` orden alfabético (RUF022).
  - **Acción**: si el helper ya está en `repo/sesion_activa.py::get_sesion_activa` (T-HU-F1.3-6), NO duplicar; aplicar formato y verificar imports. — **Archivos**: `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py`, `backend/packages/parkos_core/src/parkos_core/repo/sesion_activa.py`, `backend/packages/parkos_core/src/parkos_core/exceptions.py`, `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` (sin cambios de comportamiento, solo formato). — **Validación**: los 7 tests siguen pasando; `ruff check` retorna `All checks passed!`; `mypy --strict` retorna `Success: no issues found`.

- [ ] **T-HU-F1.3-11** [REFACTOR] — AST walk completo en `test_no_write_in_caja_sesion_me.py`
  - Cubrir `repo/session_cycle.open_session` (sólo lectura del código, sin ejecutar) Y `caja_sesion.get_my_sesion`.
  - Defense in depth: rechaza `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` (case-insensitive, fuera de strings/comentarios) en ambos cuerpos.
  - **Acción**: parametrizar el AST walk con `pytest.mark.parametrize("handler_path", ["caja_sesion.get_my_sesion", "repo.session_cycle.open_session"])`; usar `ast.parse()` sobre el archivo fuente; iterar `ast.walk()` y detectar tokens ofensivos. — **Archivos**: `backend/tests/static/test_no_write_in_caja_sesion_me.py` (modificado, +20 LOC). — **Validación**: T-3 sigue pasando; el AST walk extended confirma 0 mutaciones en ambos handlers; ruff + mypy clean.

### Phase 4: VERIFICATION

- [ ] **T-HU-F1.3-12** [VERIFICATION] — `test_caja_sesion_unique_constraint_db.py` con 2 DB-only tests
  - T1: insert 2 sesiones activas mismo `uuid_usuario` → segunda INSERT raises `UniqueViolation` (pgcode 23505).
  - T2: insert 2 sesiones donde la segunda cierra la primera (`timestamp_cierre = now()` antes de la segunda) → INSERT segunda pasa (porque el predicado `WHERE timestamp_cierre IS NULL` excluye la fila cerrada).
  - Requiere `PARKOS_DOCKER_TEST=1` y `parkos-branch-db`.
  - **Acción**: sembrar filas via `INSERT` directo al engine de testcontainers; asserts sobre `UniqueViolation` y `pgcode`. — **Archivos**: `backend/tests/integration/test_caja_sesion_unique_constraint_db.py` (nuevo, ~80 LOC). — **Validación**: `uv run pytest backend/tests/integration/test_caja_sesion_unique_constraint_db.py -q` con `PARKOS_DOCKER_TEST=1` muestra `2 passed`; sin Docker, tests skip con mensaje claro.

- [ ] **T-HU-F1.3-13** [VERIFICATION] — Suite completa + ruff + mypy + factory_intact
  - `uv run pytest -q backend/tests/`
  - `uv run ruff check backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py backend/packages/parkos_core/src/parkos_core/repo/sesion_activa.py backend/packages/parkos_core/src/parkos_core/exceptions.py backend/packages/parkos_core/migrations/versions/0023_add_sesion_unique_active.py backend/tests/unit/test_caja_sesion_me.py backend/tests/unit/test_sesion_already_active_mapping.py backend/tests/integration/test_caja_sesion_unique_constraint_db.py backend/tests/static/test_no_write_in_caja_sesion_me.py`
  - `uv run mypy --strict backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py backend/packages/parkos_core/src/parkos_core/repo/sesion_activa.py backend/packages/parkos_core/src/parkos_core/exceptions.py`
  - `git diff backend/packages/parkos_core/src/parkos_core/api/v1/router_factory.py` debe retornar vacío (`factory_intact` CI gate).
  - **Acción**: capturar log con baseline observado; si hay regresión en tests previos, NO marcar `[x]` hasta revertir el cambio que la introdujo. — **Archivos**: ninguno nuevo (verifica toda la suite + static gates). — **Validación**: log muestra `1308 + 7 + 2 = 1317 passed` (baseline 1308 desde cierre de F1.4, +7 unit/mapping/static, +2 integration); ningún test previo en estado `FAILED` o `ERROR`; ruff `All checks passed!`; mypy `Success: no issues found in N source files`; `factory_intact` verde.

  **Análisis de las 25 fallas preexistentes esperadas (baseline F1.8):** Los archivos fallando (ordenados alfabéticamente):
  `test_apply_pending_no_self_duplicate.py`, `test_buffer_ttl_escalation.py`, `test_clientes_family_permission_codes.py`, `test_identity_invariant.py`, `test_parent_missing_buffer_drain.py`, `test_reverse_dry_run.py`, `test_router_factory_payload_body_binding.py`, `test_sync_cloud_concurrent_sessions.py`, `test_sync_pull_generalized.py`, `test_versioned_update_preserves_unset_fields.py`, `test_deterministic_permisos_uuids.py`, `test_deterministic_tipo_persona_empresa_uuids.py`, `test_idempotency_inmutable.py`, `test_sync_queue_lw_buffer_schema.py`, `test_agents_md_no_superseded_terms.py`, `test_router_factory_no_vigente_desde.py`, `test_stage_runner.py`, `test_verify_chain.py`. Ninguno intersecta con `test_caja_sesion*` ni con los archivos `caja_sesion.py / repo/session_cycle.py / repo/sesion_activa.py / exceptions.py / 0023_add_sesion_unique_active.py` modificados por este PR.

## Cross-phase constraints

- NO `INSERT|UPDATE|DELETE` en `get_my_sesion` — AST walk (T-HU-F1.3-3 + T-HU-F1.3-11) lo enforza en CI.
- NO `Co-authored-by:` ni trailers AI en commits; conventional commits, español neutral.
- NO SQLite en tests — `pg_engine` real o `testcontainers[postgres]` (precedente HU-F1.4).
- NO modificación de `make_router` (`api/v1/router_factory.py`) — `factory_intact` CI gate.
- NO modificación de `repo/session_cycle.py::close_session_with_log` — fuera de scope.
- NO `INSERT|UPDATE|DELETE` en `prod.sesion` desde el endpoint `/me` — read-only por contrato.
- NO `pgcode=23505` en response body, headers, ni log lines at `info+` — REQ-OPS-028 RFC 2119 MUST.
- NO pre-check `SELECT … WHERE uuid_usuario=:u AND timestamp_cierre IS NULL` antes del INSERT — KD-3 BD-only.
- NO auto-close de sesión anterior — rechazado; pre-flight abort si hay huérfanos, owner decide.
- NO `DELETE /caja-sesion/sesion/{uuid}` — ya cubierto por `PUT /sesion/{uuid}/cerrar`.
- NO métricas/observabilidad de sesiones concurrentes — futuro HU.
- Mensajes conventional commit; cuerpo técnico en español neutral.
- Header `Cache-Control: no-store` en respuesta 200 de `/sesion/me` (consistente con F1.8 R8, REQ-OPS-027 SHOULD).
- Mapping `SesionAlreadyActive → 409 sesion_already_active` con pgcode nunca expuesto (REQ-OPS-028 MUST).
- Precedencia de errores: `404 sesion_no_active > 409 sesion_already_active > 401/403 issuer`.
- Discriminador estable: cliente puede codificar contra `{"error": "sesion_no_active"}` y `{"error": "sesion_already_active"}`.

## Acceptance Gates

- TDD strict: RED primero, GREEN mínimo, REFACTOR último.
- Conventional commit atómico: `feat(backend): anadir constraint sesion unica + GET /caja-sesion/sesion/me para HU-F1.3` (≤800 LOC).
- Sin `Co-authored-by:`, sin trailers IA.
- Tests pasan contra DB real con `PARKOS_DOCKER_TEST=1` (4 unit + 2 mapping + 2 DB integration + 1 AST = 9 tests nuevos).
- ruff + mypy --strict clean sobre los 5 archivos nuevos/modificados.
- `factory_intact` CI gate verde (`git diff api/v1/router_factory.py` vacío).
- 0 regresiones introducidas por F1.3; las 25 fallas preexistentes se mantienen documentadas.

## Out of Scope Tasks

- Auto-cerrar sesión anterior al abrir nueva (rechazamos; pre-flight abort si hay huérfanos, owner decide).
- Endpoint `DELETE /sesion/{uuid}` (ya cubierto por `PUT /sesion/{uuid}/cerrar`).
- Métricas/observabilidad de sesiones concurrentes (futuro HU).
- Endpoint `GET /caja-sesion/sesion/{uuid_usuario}/active` (admin consulta OTRO operador — deferred).
- Endpoint `POST /caja-sesion/sesion/me/cerrar` (cierre directo — ya cubierto por `/{uuid}/cerrar`).
- Lock pesimista (`FOR SHARE`/`FOR UPDATE`) sobre fila activa en `get_sesion_activa` — endpoint informativo.
- Auditoría "quién intentó abrir segunda sesión" — futuro, requiere security event store separada.
- Aplicar el mismo partial unique index pattern a otras tablas `[L-*]` (ej. `prod.caja`) — fuera de scope.
- Migración de limpieza automática de huérfanos — operador decide manualmente.
- Frontend versioning (Fase 2) — backend solamente.

## References

- `exploration.md`, `proposal.md`, `specs/operational/spec.md`, `design.md` en `openspec/changes/hu-f1-3-sesion-unica/`.
- Precedente F1.8: `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/tasks.md` (13 tasks T-HU-F1.8-1..13, PL/pgSQL migration + custom handler + AST walk pattern, commit `a3d0c39`).
- Precedente F1.4: `openspec/changes/archive/2026-09-14-hu-f1-4-tarifas-vigente/tasks.md` (helper-pure pattern + bi-temporal precedent, commit `de4d2fc`).
- Precedente F1.2: `openspec/changes/archive/2026-09-14-hu-f1-2-login-jwt/tasks.md` (TenantContext extraction + auth dependency pattern).
- `modelo_datos_er.mmd` § sesion `[L-S]` (líneas 715-740, edges L1198-1202).
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` — router custom, `_sesion_issuer_dep` línea 35, `make_router` mount read-only líneas 193-207.
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py::open_session` (líneas 180-251) — KD-2 modification site.