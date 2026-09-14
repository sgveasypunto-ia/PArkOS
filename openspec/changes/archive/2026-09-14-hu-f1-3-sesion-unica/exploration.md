# Exploration: HU-F1.3 — Constraint sesión única + GET /caja-sesion/sesion/me

> **Change**: `hu-f1-3-sesion-unica`
> **Phase**: explore (orchestrator-compiled after sdd-explore sub-agent returned minimal output)
> **HU**: HU-F1.3 — DB-level partial unique index on `prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL` + custom endpoint `GET /caja-sesion/sesion/me`
> **Date**: 2026-09-14
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `a779b79`)
> **PR target**: `origin/dev`

## 1. Contexto de la HU

HU-F1.3 cierra dos gaps del ciclo de vida de sesión [L-S]:

1. **Constraint DB-level** para que un mismo `uuid_usuario` no pueda tener DOS filas en `prod.sesion` con `timestamp_cierre IS NULL` simultáneamente. Defense in depth: además del check a nivel app en `repo/session_cycle.open_session`, la BD rechaza la segunda inserción.
2. **Endpoint `GET /caja-sesion/sesion/me`** para que el frontend admin/operador consulte la sesión activa del usuario autenticado (extraído del JWT vía `TenantContext.actor_uuid`).

Tamaño estimado: **110 LOC** (70 LOC migración + 25 LOC endpoint + 15 LOC tests + manejo de error 409 + KD-1 doc).

## 2. Migraciones existentes

Listado `backend/packages/parkos_core/migrations/versions/`:

```
0001_initial_schema.py
0002_seed_permisos_canonicos.py
0003_add_idempotency_keys_and_revoked_sync_jwts.py
0004_add_factura_pagos_reverso_trigger.py
0006_add_pairing_tokens_and_normalized_revoked_sync_jwts.py
0007_add_v_resolucion_consecutivo_view.py
0008_add_identity_nk_indexes.py
0009_add_derived_read_views.py
0010_drop_le_vigente_inicial_triggers.py
0011_add_seq_lookup_indexes.py
0012_add_sync_queue_lw_buffer.py
0013_add_alert_types.py
0014_add_catalog_triggers.py
0015_drop_infra_triggers.py
0016_add_sync_apply_guard.py
0017_fix_hash_chain_prior_row_ordering.py
0018_add_default_partitions_pairing_revoked_jwts.py
0019_deterministic_permisos_uuids.py
0020_deterministic_tipo_persona_empresa_uuids.py
0021_least_privilege_and_immutability_contract.py
0022_create_calcular_cotizacion.py   ← HU-F1.8 (precedente PL/pgSQL)
```

**Próximo número disponible: 0023.** El plan original mencionaba "0022" para F1.3 pero F1.8 ya consumió ese número.

## 3. Modelo Sesion (`models/L_S/sesion.py`)

`prod.sesion` (50 LOC) con columnas:
- `valor_inicial_efectivo` NUMERIC(18,4) nullable
- `valor_inicial_datafono` NUMERIC(18,4) nullable
- `uuid_sucursal` UUID nullable
- `uuid_usuario` UUID nullable
- `timestamp_apertura` timestamp nullable
- `timestamp_cierre` timestamp nullable
- `uuid_usuario_cierre` UUID nullable

Hereda `SessionBase` (`created_at`, sin versioning columns). El trigger `ls_session_guard` (migration 0001) bloquea UPDATE sin log_transaccional co-transaccional (REQ-41, SC-42).

**Definición operacional de "sesión activa"**: `prod.sesion WHERE timestamp_cierre IS NULL`.

## 4. Router `caja_sesion.py`

Path: `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` (208 LOC).

```
router = APIRouter(prefix="/caja-sesion", tags=["caja-sesion"])
```

Endpoints existentes:
- `POST /sesiones` → `open_sesion()` → `open_session(...)` (REQ-40)
- `PUT /sesion/{uuid}/cerrar` → `cerrar_sesion()` → `close_session_with_log(...)` (REQ-41)
- `GET /arqueos/{uuid}/diferencias` → `arqueo_diferencias()` (SC-40-S-FULL-SHIFT)
- Read-only mount via `make_router(resource="sesion", write_enabled=False, ...)` → `GET /sesion`, `GET /sesion/{uuid}`, `GET /sesion/{uuid}/history`.

Dep `requires_issuer("operador-", "admin-")` aplicada al handler de cierre.

**Patrón para `GET /sesion/me`**: custom handler en caja_sesion.py. NO usar `make_router` (no soporta filtro `actor_uuid`). Definir ANTES del `include_router` para que FastAPI matchee `/me` antes que `/{uuid}`.

## 5. Auth pattern

`TenantContext` (`auth/tenancy.py`) expone `actor_uuid` extraído del JWT por `get_tenant_ctx()` (HU-F1.2). `requires_issuer("operador-", "admin-")` valida prefijo del issuer.

Para `GET /caja-sesion/sesion/me`:
```python
async def get_my_sesion(
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_sesion_issuer_dep),
):
    stmt = (
        select(Sesion)
        .where(Sesion.uuid_usuario == ctx.actor_uuid)
        .where(Sesion.timestamp_cierre.is_(None))
        .order_by(Sesion.timestamp_apertura.desc().nulls_last())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, detail={"error": "sesion_no_active"})
    return SesionRead.model_validate(row)
```

## 6. Test patterns

- HU-F1.8 patrón establecido: `tests/unit/test_calcular_cotizacion.py` (4 HTTP tests via `httpx.AsyncClient + ASGITransport + JWT operador fixture`).
- HU-F1.2 patrón auth: `tests/unit/test_auth_login_password.py` (bcrypt + lockout).
- Tests integración DB: `tests/integration/test_calcular_cotizacion_db.py` (2 tests contra `parkos-branch-db` con `PARKOS_DOCKER_TEST=1`).
- Tests estáticos: `tests/static/test_no_write_in_calcular_cotizacion.py` (AST walk).

Para F1.3:
- `tests/unit/test_caja_sesion_me.py` — 4 HTTP-level tests:
  - T1: usuario operador con sesión activa → 200 + `SesionRead`.
  - T2: usuario operador sin sesión activa → 404 `sesion_no_active`.
  - T3: JWT issuer `cliente-` (sin permiso) → 403/401.
  - T4: usuario operador con dos sesiones cerradas + una abierta → 200 con la abierta (ORDER BY timestamp_apertura DESC).
- `tests/integration/test_caja_sesion_unique_constraint_db.py` — 2 DB tests:
  - T1: insert dos sesiones abiertas para mismo `uuid_usuario` → segunda INSERT falla con `UniqueViolation`.
  - T2: insert dos sesiones donde la segunda cierra la primera → INSERT segunda pasa.
- `tests/static/test_no_write_in_caja_sesion_me.py` — AST walk rechazando `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` dentro del handler `get_my_sesion` (defense in depth, mismo patrón que F1.8).

## 7. Schema

`backend/packages/parkos_core/src/parkos_core/schemas/caja.py` ya define `SesionRead`, `SesionReadList`, `SesionCreate`, `SesionUpdate`. `SesionRead` se reutiliza para `GET /sesion/me`.

## 8. KD preliminares (a refinar en design)

- **KD-1**: error mapping cuando la BD rechaza el INSERT por partial unique constraint. Postgres `UniqueViolation` (psycopg `pgcode '23505'`) → HTTP 409 con `{"error": "sesion_already_active"}`. NO propagar el `pgcode` al cliente.
- **KD-2**: comportamiento del repo `open_session` cuando ya existe sesión activa. Recomendado: dejar que la BD lance `UniqueViolation` y mapear a 409 en el handler (más simple que doble query previa). Defense in depth: el handler `POST /sesiones` también chequea antes (pre-check opcional KD-3).
- **KD-3**: ¿pre-check opcional en el repo? Decisión abierta — opciones:
  - (a) Solo BD constraint (más simple, defense in depth).
  - (b) Pre-check + BD constraint (más friendly error message, pero doble query).
  - (c) Solo pre-check (menos defense in depth).
  - Recomendación: (a) — patrón consistente con F1.8 AST walk.
- **KD-4**: ¿el endpoint `me` aplica a `admin-` issuer? Sí, pero los admin normalmente no abren sesión de caja. Devolver 404 si no hay sesión activa (consistente con operador).

## 9. Dependencias y bloqueadores

- **Sin dependencia de F1.8** ni del bloqueador KD-IVA.
- **Sin nueva dependencia pip**.
- F1.2 cerró `TenantContext.actor_uuid` extraction — reusable.

## 10. Riesgos

- Si el repo `open_session` actual NO captura `UniqueViolation` específicamente, cualquier intento de doble apertura crashea con 500. KD-1 resuelve esto.
- El partial unique index NO aplica retroactivamente: si ya hay datos con dos sesiones activas, la migración falla. Plan: query previa `SELECT count(*) FROM prod.sesion WHERE timestamp_cierre IS NULL GROUP BY uuid_usuario HAVING count(*) > 1` y raise antes de crear el índice. Owner decide qué hacer si hay datos huérfanos (probablemente: cerrarlas manualmente o abortar).

## 11. Artifacts a crear

```
openspec/changes/hu-f1-3-sesion-unica/exploration.md       ← este archivo
openspec/changes/hu-f1-3-sesion-unica/proposal.md           (sdd-propose)
openspec/changes/hu-f1-3-sesion-unica/specs/operational/spec.md (sdd-spec)
openspec/changes/hu-f1-3-sesion-unica/design.md             (sdd-design)
openspec/changes/hu-f1-3-sesion-unica/tasks.md               (sdd-tasks)
openspec/changes/hu-f1-3-sesion-unica/verify-report.md      (sdd-verify)
openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/archive-report.md (sdd-archive)
```

## 12. Open questions para resolver en propose/design

1. ¿KD-3 pre-check en el repo o solo BD constraint? (Recomendación: solo BD).
2. ¿Migración aborta si hay datos con dos sesiones activas? (Recomendación: abortar + reportar).
3. ¿El endpoint `me` aplica a `admin-`? (Recomendación: sí, con 404 si no hay sesión activa).

---

**Explored by**: orchestrator (sdd-explore sub-agent returned empty; data gathered inline via Read/Grep/Glob).
**Engram**: persisted post-write (topic_key `sdd/hu-f1-3-sesion-unica/explore`, project `easypuinto-parkos-software`).
