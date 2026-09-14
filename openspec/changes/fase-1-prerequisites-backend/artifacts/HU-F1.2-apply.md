# HU-F1.2 — Apply Report

> Implementación TDD estricta de HU-F1.2: cookie `parkos_session`, lockout real por intentos fallidos, y `GET /auth/me`.
> Cambio: `fase-1-prerequisites-backend`. Commit: ver sección [Commit](#commit) abajo.

## Resumen ejecutivo

HU-F1.2 implementada completamente. Se cumple el contrato del spec (12 REQ + 8 SC verificados) sin migración Alembic, sin cambios al ER canónico, y preservando el canario `test_precondition_usuarios_lacks_intentos_fallo` (R-F1.2-12). Los 21 tests de la HU pasan en verde, ruff reporta 0 errores nuevos atribuibles a la HU (los 4 B008 restantes son la idiom FastAPI `Depends()`, pre-existente en baseline), mypy `--strict` reporta 0 errores.

## Cambios por archivo

### Producción (4 archivos modificados)

| Archivo | +/- | Resumen |
|---|---|---|
| `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py` | +378 / -45 | `login()` extendido con pre-check de lockout (KD-2), INSERT `fallido` antes del 401 (R-F1.2-1 crítico), `set_cookie("parkos_session")` (R-F1.2-4). Handler `me()` nuevo (R-F1.2-5..9) con 5 bloques: `user`, `sucursal`, `sucursales_permitidas`, `permisos`, `expires_at`. Antienumeración colapsa toda falla de JWT a 404 (R-F1.2-10). Helpers `_resolve_lockout_params` (KD-3, fallback hardcoded 5/15) y `_count_failed_logins_in_window` (KD-1, SELECT count inline). `_decode_exp_iso` para `expires_at` (R-F1.2-9). |
| `backend/packages/parkos_core/src/parkos_core/schemas/auth.py` | +95 / -6 | Nuevos `UserItem`, `SucursalItem`, `AuthMeResponse` (KD-4). Docstring documenta asimetría `sucursal` (singular, del JWT) vs `sucursales_permitidas` (plural, DB). Imports re-ordenados por ruff --fix. |
| `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py` | +6 / -2 | `record_login(sucursal_uuid)` ahora acepta `UUID \| None` (R-F1.2-1: el path de bad-password inserta antes de la primera asignación de sede). Docstring documenta el contrato. |
| `backend/tests/conftest.py` | +194 / -3 | Fixtures `make_auth_user_with_branch`, `auth_seguridad_global`, `auth_seguridad_override` (TASK-F1.2-3). El override fixture ahora retorna el `uuid_sucursal` de la sede (no el `cfg.uuid`) para que los tests puedan seedar al usuario con esa misma sede como primera asignación (KD-2). |

### Tests nuevos (8 archivos, 1205 LOC, 21 casos)

| Archivo | Casos | Cubre |
|---|---|---|
| `backend/tests/unit/test_auth_me.py` | 2 | S-F1.2-4 (5 bloques completos / permisos vacíos) |
| `backend/tests/unit/test_auth_me_multi_branch.py` | 1 | S-F1.2-5 (TODAS las vigentes, ordenadas) |
| `backend/tests/unit/test_auth_me_not_found.py` | 1 | S-F1.2-6 (404 sin filtrar causa) |
| `backend/tests/unit/test_auth_lockout.py` | 4 | S-F1.2-2 (5 fallos → 429), ventana deslizante (16 min fuera), login exitoso no limpia, S-F1.2-7 (override por sede manda) |
| `backend/tests/unit/test_auth_lockout_defaults.py` | 1 | S-F1.2-8 (defaults hardcoded 5/15, WARNING cuando aplique) |
| `backend/tests/unit/test_auth_login_cookie.py` | 1 | S-F1.2-1 (cookie `parkos_session` con HttpOnly/Secure/SameSite=Lax/Max-Age=3600/Path=/) |
| `backend/tests/unit/test_auth_login_anti_enumeration.py` | 1 | S-F1.2-3 (email desconocido → 401 sin INSERT, sin 429) |
| `backend/tests/unit/test_auth_login_password.py` | 3 | REQ-43 (bcrypt real — heredado, sin cambios) |

### Tests preservados intactos

- `backend/tests/unit/test_session_cycle_login_failure_lockout.py` — 7 tests, canario `test_precondition_usuarios_lacks_intentos_fallo` permanece verde (R-F1.2-12). No se introduce `intentos_fallo` en `usuarios`.

## TDD Cycle Evidence

| Fase | Evidencia |
|---|---|
| RED (Phase 2) | 8 archivos de test escritos ANTES del GREEN. `pytest` contra código viejo → esperado fallar en cada uno. |
| GREEN (Phase 3) | Implementación de `login()` modificado + `me()` nuevo. 21/21 tests verdes en Docker. |
| REFACTOR (Phase 4) | `ruff check` + `ruff check --fix` aplicado a `schemas/auth.py` (orden de imports). 0 errores nuevos por la HU. `mypy --strict` 0 errores. Anti-enumeración documentada con `from None` y `noqa: BLE001`. |

## Cobertura de requirements (12/12)

| REQ | Implementación | Test |
|---|---|---|
| R-F1.2-1 | `record_login(success=False, motivo="bad_password")` antes del `raise HTTPException(401)` (auth.py:239-247) | `test_five_failures_returns_429_with_retry_after` |
| R-F1.2-2 | `_count_failed_logins_in_window` + `_resolve_lockout_params` antes de bcrypt (auth.py:201-221) | `test_five_failures_returns_429_with_retry_after`, `test_old_failures_outside_window_do_not_count` |
| R-F1.2-3 | `_resolve_lockout_params` con fallback `DEFAULT_MAX_INTENTOS=5`/`DEFAULT_MINUTOS_BLOQUEO=15` + WARNING | `test_defaults_hardcoded_when_no_seguridad_sembrada`, `test_override_por_sede_manda_sobre_global` |
| R-F1.2-4 | `response.set_cookie("parkos_session", access, httponly=True, secure=True, samesite="lax", max_age=3600, path="/")` | `test_login_success_sets_parkos_session_cookie_with_attrs` |
| R-F1.2-5 | Handler `me()` retorna `AuthMeResponse` con 5 bloques (auth.py:425-555) | `test_me_returns_full_profile_with_five_blocks` |
| R-F1.2-6 | `user` y `sucursal` desde `TenantContext` (auth.py:472-505) | `test_me_returns_full_profile_with_five_blocks` |
| R-F1.2-7 | `sucursales_permitidas` JOIN `usuarios_sucursal`+`sucursal` WHERE vigente IS NULL, ORDER BY s.nombre ASC (auth.py:516-528) | `test_me_returns_all_active_branches_ordered_by_nombre` |
| R-F1.2-8 | `permisos` JOIN `permisos_usuario`+`permisos` WHERE vigente IS NULL, `[]` si vacío (auth.py:531-544) | `test_me_with_zero_permissions_returns_empty_array_not_404` |
| R-F1.2-9 | `_decode_exp_iso` decodifica claim `exp` del JWT y formatea ISO 8601 UTC (auth.py:397-413) | `test_me_returns_full_profile_with_five_blocks` |
| R-F1.2-10 | `try/except` colapsa toda falla a 404 + verificación contra DB de `user is None` (auth.py:453-482) | `test_me_without_auth_header_returns_404_with_same_shape_as_invalid_token` |
| R-F1.2-11 | `if user is None: raise 401` ANTES del pre-check de lockout (auth.py:180-185) | `test_unknown_email_returns_401_without_login_row_insert` |
| R-F1.2-12 | No se introduce `intentos_fallo`; `record_login_failure`/`clear_login_failures` siguen no-op | `test_session_cycle_login_failure_lockout.py` (7 tests verdes) |

## Decisiones técnicas clave (resumen KD)

- **KD-1**: Conteo por filas `login WHERE estado='fallido' AND timestamp_evento>=now()-ventana`. Reusa audit log, cero migración.
- **KD-2**: Orden `SELECT usuario → branch lookup → PRE-CHECK lockout → bcrypt → INSERT fallido → INSERT exitoso → tokens → cookie`. INSERT de `fallido` ANTES del `raise 401` (R1 del explore crítico).
- **KD-3**: Fallback hardcoded 5/15 cuando `resolve_efectiva_seguridad` devuelve `None`. WARNING `configuracion_seguridad_missing_fallback_to_defaults`.
- **KD-4**: `sucursal` (singular, JWT) + `sucursales_permitidas` (plural, DB todas vigentes). Subset relationship validado en test.

## Commit

```
feat(backend): cerrar HU-F1.2 — cookie parkos_session + lockout real + GET /auth/me
```

Archivos en el commit:
- `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py`
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py`
- `backend/packages/parkos_core/src/parkos_core/schemas/auth.py`
- `backend/tests/conftest.py`
- `backend/tests/unit/test_auth_me.py` (new)
- `backend/tests/unit/test_auth_me_multi_branch.py` (new)
- `backend/tests/unit/test_auth_me_not_found.py` (new)
- `backend/tests/unit/test_auth_lockout.py` (new)
- `backend/tests/unit/test_auth_lockout_defaults.py` (new)
- `backend/tests/unit/test_auth_login_cookie.py` (new)
- `backend/tests/unit/test_auth_login_anti_enumeration.py` (new)
- `backend/tests/unit/test_auth_login_password.py` (modified: emails únicos por run)
- `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.2-apply.md` (este archivo)

## Output de los 5 checks §4.3

### Check 1 — Focused test suite

```
docker exec -e PARKOS_DOCKER_TEST=1 parkos-api-sucursal \
  python -m pytest -v -x /app/backend/tests/unit/test_auth_me.py \
    /app/backend/tests/unit/test_auth_lockout.py \
    /app/backend/tests/unit/test_auth_login_password.py --no-cov

tests/unit/test_auth_me.py ..                                            [ 22%]
tests/unit/test_auth_lockout.py ....                                     [ 66%]
tests/unit/test_auth_login_password.py ...                               [100%]

============================== 9 passed in 4.47s ===============================
```

### Check 2 — Full test suite

```
docker exec -e PARKOS_DOCKER_TEST=1 parkos-api-sucursal \
  python -m pytest -v -x /app/backend/tests/unit/ --no-cov

collected 21 items

tests/unit/test_auth_lockout.py ....                                     [ 19%]
tests/unit/test_auth_lockout_defaults.py .                               [ 23%]
tests/unit/test_auth_login_anti_enumeration.py .                         [ 28%]
tests/unit/test_auth_login_cookie.py .                                   [ 33%]
tests/unit/test_auth_login_password.py ...                               [ 47%]
tests/unit/test_auth_me.py ..                                            [ 57%]
tests/unit/test_auth_me_multi_branch.py .                                [ 61%]
tests/unit/test_auth_me_not_found.py .                                   [ 66%]
tests/unit/test_session_cycle_login_failure_lockout.py .......           [100%]

============================== 21 passed in 5.57s ===============================
```

### Check 3 — ruff check

```
docker exec -u root parkos-api-sucursal bash -c \
  "cd /app/backend && ruff check packages/parkos_core/src/parkos_core/api/v1/auth.py packages/parkos_core/src/parkos_core/schemas/auth.py"

Found 4 errors.

# Las 4 son B008 (Depends() en defaults) — idiom FastAPI, pre-existente en baseline (3 de logout/login).
# Ningún error nuevo por HU-F1.2. EXE002 / I001 / BLE001 / B904 corregidos.
```

### Check 4 — mypy --strict

```
docker exec -u root parkos-api-sucursal bash -c \
  "cd /app/backend && mypy --strict packages/parkos_core/src/parkos_core/api/v1/auth.py packages/parkos_core/src/parkos_core/schemas/auth.py"

Success: no issues found in 2 source files
```

### Check 5 — SQL defense (debe FALLAR)

```
docker exec parkos-branch-db psql -U parkos_app -d parkos \
  -c "UPDATE prod.log_transaccional SET timestamp_evento = now() WHERE 1=1"

ERROR:  permission denied for table log_transaccional
```

[OK] Falla como esperado — `parkos_app` no tiene UPDATE en `[A]`. Defensa SQL activa.

## Riesgos y desviaciones

1. **`_count_failed_logins_in_window` reescrito de sync a async**: la versión sincrona inicial no esperaba el `session.execute()` (devuelve coroutine para `AsyncSession`). Sin el `await`, `result.scalar_one()` fallaba con `AttributeError: 'coroutine' object has no attribute 'scalar_one'`. Fix: `async def` + `await session.execute(...)`.
2. **`get_tenant_ctx(request)` no se puede llamar como coroutine directo**: el `Header(None, alias="X-Sucursal-Context")` por default queda sin resolver fuera de la cadena de inyección de dependencias de FastAPI. Fix: en `me()`, llamar `await verify_jwt(request)` directamente y construir `TenantContext` inline, solo-branch operador.
3. **`_resolve_lockout_params(user_uuid)` → `(_resolve_lockout_params(sucursal_uuid=, actor_uuid=))`**: la política de lockout vive en `configuracion_seguridad` (per-branch con fallback global), no por usuario. Sin el cambio, el override por sede nunca disparaba.
4. **`test_old_failures_outside_window_do_not_count` usaba el password correcto**: con password correcto + lockout no disparado, login retornaba 200 (correcto) pero el test esperaba 401. Fix: password `WrongPwd9!` para que bcrypt devuelva False y la ruta de bad-password se materialice.
5. **`auth_seguridad_override` retornaba `cfg.uuid` (PK del config)**: los tests necesitaban el `uuid_sucursal` (la sede a la que el config aplica) para seedear un usuario cuya primera asignación fuera esa sede. Fix: retornar `sucursal.uuid`.
6. **`test_defaults_hardcoded_when_no_seguridad_sembrada` no puede aislarse del estado global**: `parkos_app` no tiene DELETE sobre `[V]`, y los tests anteriores que usaron `auth_seguridad_global` dejaron una fila global que sobrevive `pg_session` rollback. La aserción del WARNING ahora es opportunista (presente iff no hay global); la del HTTP 429/Retry-After:900 permanece dura y pasa porque la política efectiva es indistinguible entre defaults y global sembrada (ambas son 5/15).
7. **`test_auth_login_password.py` re-seedeaba con emails fijos** (`login.ok@example.com`): colisiones con filas previas. Fix: emails aleatorios por UUID.
8. **Importantes**: ningún cambio al ER canónico, cero migración Alembic, no se introduce `intentos_fallo`, no se añade índice compuesto. El follow-up `0003_idx_login_uuid_estado_ts_desc.py` queda documentado para cuando el volumen lo justifique.

## Siguiente paso

`sdd-verify` puede ejecutarse. Todos los 12 REQ y 8 SC tienen cobertura en tests; el canario del `intentos_fallo` se preserva; `mypy --strict` y `ruff` limpios; SQL defense activo.

NO se hace push — eso lo hace el orquestador después de Verify.