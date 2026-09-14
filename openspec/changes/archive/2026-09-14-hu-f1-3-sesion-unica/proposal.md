# Proposal: HU-F1.3 — Sesión única + GET /caja-sesion/sesion/me

> **Change**: `hu-f1-3-sesion-unica`
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F1.3 (Fase-1 prerequisites — backend)
> **Inputs**: `openspec/changes/hu-f1-3-sesion-unica/exploration.md` (this change),
> `plan.md` (HU-F1.3 contrato único, GAP-BE-LS-04 rationale), `modelo_datos_er.mmd`
> (`prod.sesion` tabla `[L-S]`, columnas `timestamp_cierre`, `uuid_usuario`),
> `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/` (precedente más reciente: PL/pgSQL
> migration + custom handler + AST walk pattern, commit `a3d0c39`),
> `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` (router custom,
> `_sesion_issuer_dep` línea 35, `make_router` mount read-only líneas 193–207).

## 1. Why

`POST /caja-sesion/sesiones` (REQ-40) hoy solo valida "no hay sesión abierta" en el repo
`session_cycle.open_session`. Es una validación a nivel aplicación: si dos operadores
disparan el endpoint simultáneamente con JWTs distintos pero mismo `uuid_usuario`, ambas
inserciones pasan antes de que el repo pueda detectar la condición. Sin un veto DB-level,
el modelo permite DOS filas en `prod.sesion` con `timestamp_cierre IS NULL` para un mismo
`uuid_usuario` — el cierre posterior solo cierra una y deja la otra huérfana, rompiendo
la definición operacional de "sesión activa" (1:1 con el cajero). Defense in depth: la BD
debe rechazar el segundo INSERT aun cuando el check app falle o sea evadido.

`GET /caja-sesion/sesion/me` no existe hoy. El frontend admin/operador necesita consultar
"¿cuál es mi sesión activa ahora mismo?" sin filtrar a mano por `uuid_usuario` y
`timestamp_cierre IS NULL`. La consulta directa a `GET /sesion` devuelve la lista
completa paginada sin filtro de actor — útil para auditoría pero ruidoso para el caso
"mi turno actual". El endpoint dedicado devuelve una sola fila o 404.

Esta HU aterriza dos cosas mínimas y de bajo riesgo:

1. **Partial unique index** en `prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL`
   vía migración Alembic `0023_add_sesion_unique_active.py`. Garantiza 1:1 con el cajero.
2. **Handler `GET /caja-sesion/sesion/me`** registrado ANTES del `make_router` de `sesion`
   para que FastAPI matchee `/me` antes que `/{uuid}`. Lee la sesión activa del actor
   vía `TenantContext.actor_uuid`. Sin joins costosos, sin paginación, sin lock.

Tamaño estimado: **110 LOC** (70 LOC migración con guard previo + 25 LOC endpoint + 15 LOC
tests unit + manejo de `UniqueViolation` → 409 + KD-1 doc).

## 2. Decision Summary

| # | Decisión | Rationale |
|---|---|---|
| **D-HU-F1.3-1 (KD-1)** | Mapear `psycopg2.errors.UniqueViolation` con `pgcode '23505'` a HTTP 409 con `{"error": "sesion_already_active"}`. NO propagar el `pgcode` ni el mensaje crudo de Postgres al cliente | Defensa en profundidad: BD rechaza el segundo INSERT, repo propaga la `UniqueViolation`, handler HTTP la convierte a error tipado estable. El pgcode es detalle de implementación de psycopg2 — exponerlo acopla el contrato del cliente a la versión del driver |
| **D-HU-F1.3-2 (KD-2)** | `repo/session_cycle.py::open_session` deja que la BD lance `UniqueViolation` y re-emite una excepción tipada de dominio (`SesionAlreadyActive`). El handler HTTP captura y mapea a 409. NO doble query previa | Defense in depth consistente: la BD es la fuente de verdad. El check app actual sigue como fast-path para mensajes friendly cuando hay carrera entre dos requests del mismo operador en ms, pero no es la línea primaria de defensa |
| **D-HU-F1.3-3 (KD-3)** | Sin pre-check en repo (`SELECT … WHERE uuid_usuario=:u AND timestamp_cierre IS NULL` antes de INSERT). Solo BD constraint | Patrón consistente con HU-F1.8 (`STABLE` + AST walk rechaza `INSERT\|UPDATE\|DELETE` en PL/pgSQL). Pre-check + BD constraint duplica round-trips y abre ventana TOCTOU. El handler HTTP puede opcionalmente emitir 422 con mensaje más legible si detecta la condición con `count(*)` antes del INSERT — KD-3 queda ABIERTO hasta design, recomendación: NO |
| **D-HU-F1.3-4 (KD-4)** | `GET /caja-sesion/sesion/me` aplica a `operador-` y `admin-`. Devuelve 404 `sesion_no_active` si no hay fila con `timestamp_cierre IS NULL` para `ctx.actor_uuid` | El admin consulta la misma forma que el operador; la BD es la fuente de verdad sobre si tiene sesión de caja abierta. 404 (no 403) para "no tienes sesión" es coherente con el contrato REST canónico |
| **D-HU-F1.3-5** | Helper puro `repo/sesion_activa.py::get_sesion_activa(session, *, actor_uuid) -> Sesion | None` con `ORDER BY timestamp_apertura DESC NULLS LAST LIMIT 1` | Encapsula la query, testeable sin HTTP, consistente con el patrón de `resolve_active_subscription_for_exit` (HU-F1.4, archive `2026-09-14-hu-f1-4-tarifas-vigente`) |
| **D-HU-F1.3-6** | Handler dedicado registrado ANTES del `_mount_sesion` (líneas 193–207 de `caja_sesion.py`). FastAPI matchea `/me` por especificidad de path antes que `/{uuid}` | El factory de HU-F1.1 no soporta filtro `actor_uuid`; un handler dedicado evita tocar `make_router` (commit `f7cb37a` estabilizado, no se toca) |
| **D-HU-F1.3-7** | Pre-flight en la migración: `SELECT count(*) FROM prod.sesion WHERE timestamp_cierre IS NULL GROUP BY uuid_usuario HAVING count(*) > 1` y abortar con error explícito si retorna > 0 filas | El partial unique index NO aplica retroactivamente: si ya hay datos huérfanos (dos sesiones activas para un mismo usuario), `CREATE UNIQUE INDEX` falla con mensaje críptico. Detectar ANTES y reportar al operador con la lista de `uuid_usuario` afectados |
| **D-HU-F1.3-8** | AST walk test `tests/static/test_no_write_in_caja_sesion_me.py` rechaza `INSERT\|UPDATE\|DELETE\|TRUNCATE\|MERGE` dentro del handler `get_my_sesion` | Mismo patrón que F1.8. El endpoint es read-only por contrato; defensa contra un dev futuro que agregue side-effects por error |

## 3. Goals & Non-Goals

### 3.1 Goals

1. Garantizar a nivel BD que un mismo `uuid_usuario` no tenga DOS filas en `prod.sesion`
   con `timestamp_cierre IS NULL` simultáneamente, vía partial unique index.
2. Mapear el `UniqueViolation` resultante a HTTP 409 con código de error tipado
   `sesion_already_active` (sin propagar `pgcode`).
3. Exponer `GET /api/v1/caja-sesion/sesion/me` que devuelve la sesión activa del actor
   autenticado, o 404 `sesion_no_active` si no existe.
4. Definir pre-flight en la migración que detecte datos huérfanos pre-existentes y aborte
   la migración con reporte explícito si los encuentra.
5. Aplicar a `operador-` y `admin-` issuers (ambos pueden abrir sesión de caja).
6. Mantener `make_router` intacto (HU-F1.1 GAP-BE-02, commit `f7cb37a`); el handler
   dedicado se registra antes del mount genérico y solo aplica a `/me`.
7. Reusar `TenantContext.actor_uuid` de HU-F1.2 (sin agregar dependencias nuevas).
8. Cubrir el flujo con tests RED-then-GREEN: 4 HTTP unit, 2 DB integration, 1 AST walk.

### 3.2 Non-Goals

1. NO se siembra el constraint con `NOT VALID` + `VALIDATE CONSTRAINT` por separado —
   pre-flight + `CREATE UNIQUE INDEX` en una sola TX Alembic.
2. NO se modifica `make_router` (HU-F1.1 GAP-BE-02, commit `f7cb37a`).
3. NO se modifica `repo/session_cycle.py::open_session` en su semántica de fast-path
   check; solo agrega captura explícita de `UniqueViolation` y re-emisión tipada.
4. NO se crea path `POST /caja-sesion/sesion/me` — solo GET (idempotente, sin side-effects).
5. NO se crea endpoint `DELETE /caja-sesion/sesion/me` — el cierre va por
   `PUT /caja-sesion/sesion/{uuid}/cerrar` (precedente REQ-41).
6. NO se cambia `SesionCreate` ni `SesionRead` — se reutilizan tal cual.
7. NO se introduce lock sobre `prod.sesion` en lectura — el endpoint es read-only sin
   `FOR UPDATE/SHARE`. La atomicidad la garantiza el partial unique index para INSERT.
8. NO se agrega tenant scoping adicional más allá de `actor_uuid` del JWT — el partial
   index es por `uuid_usuario`, no por sucursal.
9. NO se reescribe la lógica de `close_session_with_log` — sale del scope.
10. NO se introduce lock pesimista en `get_sesion_activa` — el endpoint es informativo,
    no coordina mutaciones.

## 4. Architecture Overview

```
          ┌──────────────────────────────────────────────────────────────────────┐
          │  MIGRACIÓN Alembic 0023 (defense in depth DB-level)                 │
          │                                                                      │
          │  pre_upgrade:                                                         │
          │    SELECT uuid_usuario, count(*) AS n                                  │
          │    FROM   prod.sesion                                                 │
          │    WHERE  timestamp_cierre IS NULL                                    │
          │    GROUP  BY uuid_usuario                                              │
          │    HAVING count(*) > 1                                                │
          │    → si rows: raise RuntimeError con lista de uuid_usuario            │
          │                                                                      │
          │  upgrade:                                                             │
          │    CREATE UNIQUE INDEX CONCURRENTLY                                   │
          │      uq_prod_sesion_one_active_per_user                              │
          │    ON prod.sesion(uuid_usuario)                                       │
          │    WHERE timestamp_cierre IS NULL;                                   │
          │                                                                      │
          │  downgrade:                                                           │
          │    DROP INDEX IF EXISTS prod.uq_prod_sesion_one_active_per_user;     │
          └──────────────────────────────────────────────────────────────────────┘

   HTTPS POST /caja-sesion/sesiones            (path existente, comportamiento extendido)
        │  requires_issuer("operador-", "admin-")
        ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ api/v1/caja_sesion.py  (open_sesion handler, sin tocar)            │
   │                                                                      │
   │   repo/session_cycle.py::open_session(...)                          │
   │       INSERT INTO prod.sesion (...)                                 │
   │       │                                                              │
   │       │  si UniqueViolation (pgcode 23505) ← RACE con otra TX:     │
   │       │    raise SesionAlreadyActive(...)        ◄── KD-2 typed     │
   │       │                                                              │
   │       └─► HTTPException(409, {"error": "sesion_already_active"})   │
   │                                       ◄── KD-1 mapping              │
   └──────────────────────────────────────────────────────────────────────┘

   HTTPS GET /caja-sesion/sesion/me           (path NUEVO)
        │  requires_issuer("operador-", "admin-")
        ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ api/v1/caja_sesion.py                                                │
   │ @router.get("/sesion/me")  (NUEVO handler get_my_sesion)            │
   │   registrado ANTES del include_router(make_router(...))             │
   │                                                                      │
   │   repo/sesion_activa.py::get_sesion_activa(                         │
   │       session, actor_uuid=ctx.actor_uuid)                            │
   │       │                                                              │
   │       │  SELECT * FROM prod.sesion                                  │
   │       │  WHERE  uuid_usuario = :actor_uuid                          │
   │       │    AND  timestamp_cierre IS NULL                            │
   │       │  ORDER BY timestamp_apertura DESC NULLS LAST                │
   │       │  LIMIT 1                                                    │
   │       │                                                              │
   │       └─► SesionRead (model_validate) o None                        │
   │              │                                                       │
   │              └─► None → HTTPException(404,                          │
   │                       {"error": "sesion_no_active"})                │
   └──────────────────────────────────────────────────────────────────────┘
```

## 5. Capabilities

### New

- **`prod-sesion-unicidad-activa`** — cubre el partial unique index
  `uq_prod_sesion_one_active_per_user` sobre `prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL`
  + el mapeo de `UniqueViolation` a 409 `sesion_already_active` + el pre-flight de datos
  huérfanos. Spec en `openspec/changes/hu-f1-3-sesion-unica/specs/operational/spec.md`,
  archivada en `openspec/specs/operations/spec.md` como REQ-OPS-026, REQ-OPS-027.
- **`operador-me-sesion-activa`** — cubre el endpoint `GET /caja-sesion/sesion/me` con
  helper `repo/sesion_activa.py::get_sesion_activa` y respuesta `SesionRead` o 404
  `sesion_no_active`. Spec REQ-OPS-028, REQ-OPS-029 en el mismo archivo de spec.

### Modified

- **`operations`** — la skill canónica agrega la regla "máximo una sesión activa por
  `uuid_usuario`" como invariante de `prod.sesion`. Sin cambio contractual sobre
  REQ-OPS-001..025; sólo delta. Spec deltada en
  `openspec/changes/hu-f1-3-sesion-unica/specs/operations/spec.md`.
- **`repo/session_cycle.py`** — captura explícita de `UniqueViolation` (pgcode 23505)
  en `open_session`, re-emisión como `SesionAlreadyActive` (excepción de dominio). Sin
  cambio en la lógica del fast-path check previo al INSERT.

## 6. Data Model

`modelo_datos_er.mmd` tabla `prod.sesion` (`[L-S]`) — **sin cambios de esquema**. La
migración `0023` sólo crea el partial unique index.

**Columnas leídas** (todas existentes):

| Tabla | Columna | Lectura |
|---|---|---|
| `prod.sesion` | `uuid_usuario` | PK del partial unique index; filtro en `get_sesion_activa` |
| `prod.sesion` | `timestamp_cierre` | predicado del partial index (`WHERE ... IS NULL`); filtro en `get_sesion_activa` |
| `prod.sesion` | `timestamp_apertura` | `ORDER BY DESC NULLS LAST` en `get_sesion_activa` |
| `prod.sesion` | (todas) | SELECT en `get_sesion_activa` para `SesionRead.model_validate` |

**DDL nuevo** (migración `0023_add_sesion_unique_active.py`):

```sql
-- Pre-flight (dentro de upgrade(), antes del CREATE INDEX):
SELECT uuid_usuario, count(*) AS n
INTO   _huérfanos
FROM   prod.sesion
WHERE  timestamp_cierre IS NULL
GROUP  BY uuid_usuario
HAVING count(*) > 1;

IF FOUND THEN
    RAISE EXCEPTION
      'sesion_unique_active_preflight_failed: % uuid_usuario con >1 sesión activa',
      (SELECT count(*) FROM _huérfanos)
      USING ERRCODE = 'integrity_constraint_violation';
END IF;

-- Index:
CREATE UNIQUE INDEX CONCURRENTLY uq_prod_sesion_one_active_per_user
    ON prod.sesion (uuid_usuario)
    WHERE timestamp_cierre IS NULL;
```

**Downgrade** (`downgrade()`):

```sql
DROP INDEX CONCURRENTLY IF EXISTS prod.uq_prod_sesion_one_active_per_user;
```

`CONCURRENTLY` permite crear/borrar el índice sin tomar `AccessExclusiveLock` sobre
`prod.sesion` — crítico porque la tabla está activa en operaciones (turnos de cajero).

## 7. API Surface

| Path | Method | Cambio | Issuer / rol |
|---|---|---|---|
| `/api/v1/caja-sesion/sesion/me` | GET | NUEVO endpoint — devuelve sesión activa del actor o 404 | `operador-`, `admin-` |
| `/api/v1/caja-sesion/sesiones` | POST | Comportamiento extendido: si BD rechaza por unique constraint, devuelve 409 `sesion_already_active` | `operador-`, `admin-` |

**Request signature** para `GET /caja-sesion/sesion/me`:

```python
async def get_my_sesion(
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_sesion_issuer_dep),
) -> SesionRead:
```

**Response shape** (sin cambios): `SesionRead` (12 campos: `uuid`, `uuid_sucursal`,
`uuid_usuario`, `valor_inicial_efectivo`, `valor_inicial_datafono`, `timestamp_apertura`,
`timestamp_cierre`, `uuid_usuario_cierre`, `created_at`, `created_by`, `sync_status`,
`sync_timestamp`).

**Errores tipados**:

| HTTP | Body | Cuándo |
|---|---|---|
| 404 | `{"error": "sesion_no_active"}` | `actor_uuid` no tiene fila con `timestamp_cierre IS NULL` |
| 409 | `{"error": "sesion_already_active"}` | `POST /sesiones` con `uuid_usuario` que ya tiene sesión abierta (KD-1, KD-2) |
| 401/403 | sin cambios | issuer inválido / falta token (precedente) |

**Sin cambios sobre**:

- `POST /caja-sesion/sesiones` (comportamiento base; solo agrega 409)
- `PUT /caja-sesion/sesion/{uuid}/cerrar` (cierre)
- `GET /caja-sesion/arqueos/{uuid}/diferencias` (arqueo)
- `GET /caja-sesion/sesion` (lista read-only del factory)
- `GET /caja-sesion/sesion/{uuid}` (single read)
- `GET /caja-sesion/sesion/{uuid}/history` (history read)

**Requirements planificados** (escritos en spec.md por `sdd-spec`):

- `REQ-OPS-026` — partial unique index `uq_prod_sesion_one_active_per_user` + pre-flight
- `REQ-OPS-027` — mapping `UniqueViolation → 409 sesion_already_active`
- `REQ-OPS-028` — endpoint `GET /caja-sesion/sesion/me` con helper `get_sesion_activa`
- `REQ-OPS-029` — respuesta 404 `sesion_no_active` cuando no hay sesión activa

## 8. Risks & Mitigations

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| **R1** | Datos huérfanos pre-existentes (dos sesiones activas para mismo `uuid_usuario`) hacen fallar `CREATE UNIQUE INDEX` con mensaje críptico de Postgres | Media | Pre-flight en `upgrade()` ejecuta `GROUP BY … HAVING count(*) > 1` antes del `CREATE INDEX`. Si hay filas, aborta con error explícito listando los `uuid_usuario` afectados. Operador decide: cerrar manualmente las duplicadas o abortar el deploy |
| **R2** | Repo `open_session` actual NO captura `UniqueViolation` específicamente — segundo intento crashea con 500 genérico | Media | KD-1 + KD-2: `open_session` captura `UniqueViolation` (pgcode 23505) y re-emite `SesionAlreadyActive`. Handler HTTP mapea a 409. Defense in depth: el partial unique index existe, así que la primera barrera es la BD |
| **R3** | El handler dedicado `get_my_sesion` se registra antes del `make_router` — si un futuro dev lo registra después, FastAPI matchea `/{uuid}` y devuelve 422 ("uuid inválido: 'me'") | Baja | Comentario explícito en `caja_sesion.py` líneas 70–71 sobre el orden de registro. KD documentado en design.md. Test verifica que `/me` se resuelve ANTES que `/{uuid}` |
| **R4** | `admin-` issuer no suele abrir sesión de caja — endpoint `me` siempre devuelve 404 para admin. ¿Es útil? | Baja | KD-4: respuesta 404 coherente con la realidad (admin no tiene sesión de caja). Si en el futuro admin necesita ver "sesión activa del actor X", eso es otro endpoint con `?actor_uuid=` explícito. Sale del scope |
| **R5** | `CREATE INDEX CONCURRENTLY` puede tardar minutos en tablas grandes — deploy bloqueado | Baja | `prod.sesion` tiene cardinalidad esperada < 100 filas/sede × N sedes = pocos miles de filas. Index trivialmente rápido (< 1s). Documentado en design.md |
| **R6** | Race entre `get_sesion_activa` (read) y `close_session_with_log` (write) — el endpoint podría devolver una fila que se cierra milisegundos después | Baja | El endpoint es informativo, no coordina mutaciones. Sin lock. Coherente con el contrato REST: "la sesión activa AHORA es esta; si la cierras inmediatamente, una siguiente llamada puede devolver 404" |
| **R7** | Un dev futuro agrega un `INSERT|UPDATE|DELETE` accidental dentro de `get_my_sesion` — rompe read-only | Baja | AST walk `tests/static/test_no_write_in_caja_sesion_me.py` rechaza mutaciones en el cuerpo del handler (patrón F1.8). CI gate |
| **R8** | `TenantContext.actor_uuid` puede ser None si el JWT no incluye `sub` o el preproceso falla — la query retorna 0 filas, no error | Baja | Defensa en profundidad: HU-F1.2 garantiza `actor_uuid` no-None en claims válidos. Si llegara None, la query `WHERE uuid_usuario = NULL` retorna 0 filas → 404 `sesion_no_active` (consistente con "no hay sesión") |
| **R9** | `make_router` (HU-F1.1) tiene un GET `GET /sesion/{uuid}` registrado — colisión de ruta con `GET /sesion/me` | Baja | FastAPI matchea por especificidad de path estático: `/me` es literal, gana sobre `/{uuid}` paramétrico. Test verifica match order |

## 9. Success Criteria

1. `pytest backend/tests/unit/test_caja_sesion_me.py` verde — 4 tests HTTP-level:
   - T1: operador con sesión activa → 200 + `SesionRead` con campos correctos.
   - T2: operador sin sesión activa → 404 `{"error":"sesion_no_active"}`.
   - T3: JWT issuer `cliente-` → 403/401 (issuer_dep rechaza).
   - T4: operador con dos sesiones cerradas + una abierta → 200 con la abierta
     (`ORDER BY timestamp_apertura DESC NULLS LAST`).
2. `pytest backend/tests/integration/test_caja_sesion_unique_constraint_db.py` verde — 2 tests DB:
   - T1: insert dos sesiones abiertas para mismo `uuid_usuario` → segunda INSERT falla
     con `UniqueViolation` (pgcode 23505).
   - T2: insert dos sesiones donde la segunda cierra la primera (`timestamp_cierre`
     seteado antes de la segunda) → INSERT segunda pasa (porque el predicado
     `WHERE timestamp_cierre IS NULL` excluye la fila cerrada).
3. `pytest backend/tests/static/test_no_write_in_caja_sesion_me.py` verde — AST walk
   rechaza `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` en el cuerpo de `get_my_sesion`.
4. Migración `0023_add_sesion_unique_active.py` aplica limpia en BD de tests; downgrade
   sin errores.
5. Pre-flight detecta datos huérfanos correctamente (test de integración con siembra
   manual de 2 filas activas para mismo `uuid_usuario` → migración aborta).
6. `GET /caja-sesion/sesion/me` registrado ANTES del `make_router` — el orden está
   documentado y verificado por test de path resolution.
7. `repo/session_cycle.py::open_session` captura `UniqueViolation` y re-emite
   `SesionAlreadyActive`; test unitario verifica el mapping.
8. Handler `POST /caja-sesion/sesiones` devuelve 409 `sesion_already_active` cuando la
   BD rechaza (test unitario + test de integración).
9. `ruff check`, `ruff format --check`, `mypy --strict` verde sobre los archivos
   nuevos/modificados (5 nuevos + 1 modificado).
10. Ningún cambio en `openspec/specs/operations/spec.md`破坏 REQ-OPS-001..025; sólo
    delta en REQ-OPS-026..029.
11. `make_router` intacto: `git diff backend/packages/parkos_core/src/parkos_core/api/v1/router_factory.py`
    retorna vacío.

## 10. Out of Scope (deferred)

1. Endpoint `GET /caja-sesion/sesion/{uuid_usuario}/active` (consultar sesión activa de
   OTRO usuario con `admin-` issuer) — futuro, KD-4 deja la puerta abierta pero este
   change solo cubre `/me`.
2. Endpoint `POST /caja-sesion/sesion/me/cerrar` (cierre directo de "mi sesión"
   sin pasar por `/{uuid}/cerrar`) — futuro, la ruta existente cubre el caso
   (`PUT /sesion/{uuid}/cerrar` con uuid conocido).
3. Notificación WebSocket cuando un segundo operador intenta abrir sesión con un
   `uuid_usuario` ya activo — futuro, fuera del MVP backend.
4. Lock pesimista sobre la fila activa en `get_sesion_activa` (`FOR SHARE`) — el
   endpoint es informativo, sin coordinación de mutaciones.
5. Auditoría "quién intentó abrir segunda sesión" — futuro, requiere tabla de
   eventos de seguridad separada.
6. Aplicar el mismo partial unique index a otras tablas `[L-*]` con invariante
   "una fila activa por actor" (ej: `prod.caja` si existe). Sale del scope.
7. Migración de limpieza (`DELETE FROM prod.sesion WHERE timestamp_cierre IS NULL AND
   uuid_usuario IN (...)`) automática cuando el pre-flight detecta huérfanos. El
   operador decide manualmente.
8. Versionado de UI cliente (Fase 2 frontend) — la HU aterriza backend solamente.
9. Métricas/observabilidad (contador de 409, latencia de `/me`). Sale del scope;
   alineado con HU-F1.X de observabilidad (futuro).

## 11. Relevant Files

- `backend/packages/parkos_core/migrations/versions/0023_add_sesion_unique_active.py`
  (NUEVO) — Alembic: pre-flight `GROUP BY HAVING count(*) > 1` + `CREATE UNIQUE INDEX
  CONCURRENTLY` + downgrade `DROP INDEX CONCURRENTLY`.
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` (MODIFICAR) —
  agregar handler `get_my_sesion` ANTES del `include_router(make_router(...))` (líneas
  193–207) y agregar mapeo `UniqueViolation → 409` en `open_sesion`.
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py` (MODIFICAR) —
  agregar captura de `UniqueViolation` en `open_session`, re-emitir `SesionAlreadyActive`.
- `backend/packages/parkos_core/src/parkos_core/repo/sesion_activa.py` (NUEVO) — helper
  puro `get_sesion_activa(session, *, actor_uuid) -> Sesion | None` con SQL parametrizado.
- `backend/tests/unit/test_caja_sesion_me.py` (NUEVO) — 4 HTTP-level tests.
- `backend/tests/integration/test_caja_sesion_unique_constraint_db.py` (NUEVO) — 2
  DB-backed tests contra `parkos-branch-db`.
- `backend/tests/static/test_no_write_in_caja_sesion_me.py` (NUEVO) — AST walk.
- `openspec/specs/operations/spec.md` (MODIFICAR) — `REQ-OPS-026..029` + entrada en
  `## Modified Capabilities`.
- `openspec/changes/hu-f1-3-sesion-unica/{proposal,specs/operations/spec.md,design.md,
  tasks.md,exploration.md}` (NUEVOS, este change) — 5 archivos.

**Archivos NO tocados (deliberado)**:

- `api/v1/router_factory.py` (factory HU-F1.1, commit `f7cb37a`).
- `models/L_S/sesion.py` (sin cambios de esquema, solo índice nuevo).
- `schemas/caja.py` (`SesionRead`, `SesionCreate`, etc. se reutilizan tal cual).
- `repo/session_cycle.py::close_session_with_log` (sin cambio).
- `repo/tarifas_vigencia.py` (helper F1.4, no relacionado).

## 12. Open Questions

**Ninguna abierta**. Las 4 KD (KD-1 error mapping, KD-2 captura `UniqueViolation`,
KD-3 pre-check vs BD-only, KD-4 admin issuer) están recomendadas en la exploration con
fecha 2026-09-14 y se adoptan sin disputa:

- **KD-1**: mapping `UniqueViolation → 409 sesion_already_active` (D-HU-F1.3-1).
- **KD-2**: repo re-emite `SesionAlreadyActive`, handler HTTP mapea (D-HU-F1.3-2).
- **KD-3**: solo BD constraint, sin pre-check en repo (D-HU-F1.3-3). Consistente con
  el patrón F1.8 (`STABLE` + AST walk).
- **KD-4**: `admin-` accepted, 404 si no hay sesión activa (D-HU-F1.3-4).

Si durante `sdd-design` surge evidencia técnica fuerte para revisar alguna KD (ej: el
pre-flight de huérfanos revela > X filas esperadas), se reabre en `design.md` con
evidencia. Caso base: el plan original está completo y es ejecutable tal cual.
