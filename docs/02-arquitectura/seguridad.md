# Seguridad

> Modelo de autenticación, autorización y protección de datos — easypunto_parkos
> Fuentes: código verificado en `backend/packages/parkos_core/src/parkos_core/{auth,repo,api}/`, migraciones en `backend/packages/parkos_core/migrations/versions/`, y `AGENTS.md` (raíz del repo). Cada afirmación cita archivo y línea; donde el código y `AGENTS.md` difieren (p. ej. el algoritmo JWT vigente frente al objetivo de diseño), ambos estados se documentan explícitamente en vez de presentarlos como uno solo.

Este documento cubre el modelo de autenticación (JWT con tres *issuers*), la autorización (contexto de tenant + permisos granulares), el flujo de emparejamiento (*pairing*) de una sucursal nueva, la revocación de tokens, la protección de las tablas `[A]` (append-only) y los roles de base de datos. Para el modelo de datos completo ver [`./modelo-datos.md`](./modelo-datos.md); para las decisiones del motor de sincronización ver [`./decisiones-tecnicas.md`](./decisiones-tecnicas.md).

## Índice

- 1. Modelo de autenticación: JWT con tres issuers
- 2. Autorización: tenancy y permisos
- 3. Flujo de pairing de sucursal
- 4. Revocación de tokens
- 5. Protección de tablas [A]: REVOKE y triggers
- 6. Roles de base de datos

---

## 1. Modelo de autenticación: JWT con tres issuers

El sistema define tres emisores de JWT mutuamente excluyentes — no existe jerarquía implícita entre ellos; el mismo código que rechaza un token `operador-` en una ruta de administración rechaza también un token `admin-` en una ruta de sincronización:

```python
# backend/packages/parkos_core/src/parkos_core/auth/jwt_issuer_guard.py:21
ISSUER_PREFIXES = ("admin-", "operador-", "sync-agent-")
```

| Issuer | Uso | Alcance (`AGENTS.md:180-187`) |
|---|---|---|
| `admin-` | usuarios de administración | vida larga, alcance amplio |
| `operador-` | operadores de sucursal | vida media, fijado a una sucursal vía `uuid_sucursal` |
| `sync-agent-` | agentes de sincronización (workers) | vida larga, alcance de sync |

**Emisión** (`issue_token`, `backend/packages/parkos_core/src/parkos_core/auth/tokens.py:61`): construye el payload estándar (`iss`, `sub`, `iat`, `exp`, `aud`, `jti`) y rechaza cualquier `issuer` que no empiece por uno de los tres prefijos (`JWTIssuerPrefixError`). La audiencia (`aud`) se deriva del *issuer* (`_audience_for`, línea 144: `admin-` → `parkos-admin`, `operador-` → `parkos-branch`, `sync-agent-` → `parkos-sync`), y el header lleva un `kid` con el mismo prefijo del *issuer* (`kid = f"{issuer}{_kid_suffix(issuer)}"`, línea 96).

**Verificación** (`verify_token`, `tokens.py:105`): valida la firma con comparación de tiempo constante (`hmac.compare_digest`), la expiración, que el prefijo de `iss` esté entre los tres válidos, y que el `kid` del header comparta el mismo prefijo que `iss`. Esta última comprobación es la defensa explícita contra una clave de un *issuer* usada para firmar o aceptar un token de otro.

**Estado actual del algoritmo — nota importante.** El código vigente firma con **HS256 y un secreto compartido** (`tokens.py:68`, comentario explícito "dev mode"); `AGENTS.md:99` documenta el objetivo de diseño como **RS256** con tres juegos de claves, uno por *issuer*. El propio código marca la migración a RS256 + JWKS como pendiente ("Production RS256 + JWKS lands in PR7", `jwt_issuer_guard.py:8`). La rotación con solape (`JWT_OVERLAP_HOURS=24`, `AGENTS.md:187`, ambas claves convivientes en el JWKS durante la ventana) pertenece a ese mismo diseño objetivo RS256 y aún no tiene contraparte funcional en el HS256 actual: `_kid_suffix` siempre devuelve `"current"` (`tokens.py:155-162`), con un comentario en el propio código que anticipa el sufijo `-prior-<n>` para cuando exista rotación real.

**Estado actual de la verificación de contraseña — nota importante.** `POST /auth/login` (`backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:70-74`) todavía no invoca `bcrypt.checkpw`: acepta cualquier valor no vacío de `password_hash` como comprobación interina, según el propio comentario del archivo ("PR1b accepts any password... PR7 wires the real bcrypt.checkpw"). `bcrypt` está declarado como dependencia de *hashing* en `AGENTS.md:98`, pero la verificación real en el endpoint de login es trabajo pendiente explícito, no una decisión de seguridad definitiva.

## 2. Autorización: tenancy y permisos

### 2.1 Contexto de tenant (TenantContext)

`backend/packages/parkos_core/src/parkos_core/auth/tenancy.py:29` define el contexto por-request:

```python
@dataclass(frozen=True)
class TenantContext:
    actor_uuid: uuid_lib.UUID
    actor_rol: str
    issuer_prefix: str  # 'admin-' | 'operador-' | 'sync-agent-'
    sucursal_uuid: uuid_lib.UUID | None
```

La dependencia FastAPI `get_tenant_ctx` (`tenancy.py:68`) resuelve `sucursal_uuid` con una regla distinta por *issuer*:

- **`operador-`**: la sucursal viene fijada en el claim `sucursal` del propio JWT. El header `X-Sucursal-Context` es opcional; si se envía, debe coincidir exactamente con el claim, o se responde 403 `unauthorized_sucursal_context` (líneas 99-106).
- **`admin-`**: exige el header `X-Sucursal-Context` (400 `missing_sucursal_context` si falta, línea 117) y lo valida contra el claim `sucursales_permitidas` del token (403 `unauthorized_sucursal_context` si el UUID no está en esa lista, líneas 122-124). Esta es la mitigación documentada en `AGENTS.md:252` contra fuga de alcance de tenant en un JWT de administración.
- **`sync-agent-`**: el claim `scope` decide — `branch` fija `sucursal_uuid` a la sucursal del claim; `cloud` no aplica ningún filtro de tenant (el receptor de sincronización en la nube debe poder ver todas las sucursales).

El `TenantContext` resuelto se enlaza al *listener* de SQLAlchemy (`db.tenancy.set_tenant_context`, invocado en las tres ramas) para que cada `SELECT`/`UPDATE`/`DELETE` posterior sobre una tabla con `uuid_sucursal` quede auto-filtrado. Es un filtrado de **aplicación/ORM**, no de PostgreSQL.

> **Nota — hueco encontrado.** `rol_admin_auditor` tiene el atributo nativo `BYPASSRLS` (ver §6), que solo tiene efecto si existen políticas de Row-Level Security activas. No se encontró ninguna sentencia `CREATE POLICY` ni `ENABLE ROW LEVEL SECURITY` en el repositorio (ni en migraciones ni en scripts). El aislamiento de tenant hoy se hace exclusivamente a nivel de aplicación (`get_tenant_ctx` + el *listener* de SQLAlchemy); `BYPASSRLS` está aprovisionado pero no anula ninguna política existente.

### 2.2 Permisos granulares (require_permission)

`backend/packages/parkos_core/src/parkos_core/auth/permissions.py:25` implementa una segunda capa de dependencia, **posterior** al guard de *issuer*:

```python
def require_permission(codigo: str):
    async def _dep(request, session=Depends(get_session)) -> dict:
        claims = ... await verify_jwt(request)
        actor_uuid = uuid_lib.UUID(claims["sub"])
        result = await session.execute(
            select(PermisosUsuario)
            .join(Permisos, Permisos.uuid == PermisosUsuario.uuid_permiso)
            .where(
                PermisosUsuario.uuid_usuario == actor_uuid,
                PermisosUsuario.vigente_hasta.is_(None),   # bi-temporal: permiso vigente
                Permisos.permiso == codigo,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(403, {"error": "permission_denied", "detail": codigo})
```

Decisión de diseño explícita, documentada en el propio módulo (`permissions.py:6-8`): **los permisos no viajan en el JWT** — se consultan en vivo contra `permisos_usuario`/`permisos` en cada request, exigiendo que la fila de asignación esté vigente (`vigente_hasta IS NULL`, el mismo patrón bi-temporal del resto del modelo). Esto garantiza que revocar un permiso surte efecto en la siguiente petición, sin ventana de caché de token que retrase la revocación.

Los routers de catálogo y configuración (`api/v1/catalogos.py`, `api/v1/configuracion.py`) componen ambas capas sobre el mismo *router factory* (`api/router_factory.py::make_router`): `issuer_required` (p. ej. `"admin-,operador-"`) + `permission_required` (p. ej. `"config_catalogo"`, `"config_seguridad"`, `"config_tolerancias"`).

## 3. Flujo de pairing de sucursal

**Emisión** — `create_pairing_token` (`backend/packages/parkos_core/src/parkos_core/repo/pairing.py:100`): un administrador genera un token de un solo uso; el texto plano se genera y se hashea con SHA-256 (`hash_pairing_token`, línea 95) y **solo el hash se persiste** en `prod.pairing_tokens` (`used=False`, `expires_at = now + ttl_hours`; 24 h por defecto, hasta 168 h según el endpoint administrativo, `pairing.py:119`). El texto plano nunca llega a la capa de repositorio más allá de la variable local que lo devuelve una única vez al administrador en la respuesta HTTP — comentario explícito en el código (líneas 142-147): *"the repo layer is the wrong place to carry the plaintext across the API surface"*.

**Consumo atómico de un solo uso** — `consume_pairing_token` (`repo/pairing.py:210`), en cinco pasos:

1. Busca por hash la fila más reciente; si no existe ninguna fila con ese hash, rechaza con `PairingTokenNotFoundError`; si la fila ya está `used`, con `PairingTokenConsumedError`; si expiró, con `PairingTokenExpiredError`.
2. **Compuerta cross-sucursal**: si la fila encontrada tiene `uuid_sucursal` fijado y no coincide con quien intenta consumirla, se responde con el mismo `PairingTokenConsumedError` genérico (no un error distinto de "sucursal incorrecta") — para que un token válido perteneciente a otra sucursal no se distinga de uno ya usado.
3. **Compuerta de revocación**: consulta `revoked_sync_jwt.is_revoked` con `kid=f"pairing_token:{uuid}"` — un administrador puede revocar un token de pairing antes de que se use.
4. **Reclamo atómico**: `SELECT ... FOR UPDATE SKIP LOCKED`. Si dos consumidores intentan el mismo token en paralelo, solo uno obtiene la fila con `FOR UPDATE`; el otro recibe `SKIP LOCKED` vacío y se le responde también como token ya consumido — esta es la mitigación real de una condición de carrera de doble consumo del mismo pairing token.
5. **INSERT de una fila hermana** con `used=True` — `pairing_tokens` es `[A]` (append-only): el consumo nunca es un `UPDATE` de la fila de emisión, sino una fila nueva. Las búsquedas de token activo filtran por `used=False`, de modo que la hermana insertada en este paso desactiva el token para cualquier verificación futura.

**En el lado del cliente**, `cli/pair.py` (`AGENTS.md:259`) toma el token de la variable de entorno `PARKOS_PAIRING_TOKEN`, lo intercambia por el JWT `sync-agent-`, y ejecuta `os.environ.pop("PARKOS_PAIRING_TOKEN", None)` para borrar el texto plano del entorno del proceso — nunca se escribe a disco ni a log. El transporte va cifrado con **TLS 1.3** obligatorio entre sucursal y nube (terminación `nginx` a nivel de contenedor + gate `PARKOS_TLS=required`, `AGENTS.md:259`). El emparejamiento está además protegido por *rate limiting* (5 solicitudes/hora por administrador, `parkos_core/api/rate_limit_pairing.py` según `AGENTS.md:261`).

**Test real**: `backend/tests/integration/test_pairing_flow.py` (9 escenarios, `AGENTS.md:261`).

## 4. Revocación de tokens

`prod.revoked_sync_jwts` es una tabla `[A]` (append-only): la revocación **no** es un blocklist mutable, es un registro de inserciones.

**Revocar** — `revoke_jwt` (`backend/packages/parkos_core/src/parkos_core/repo/revoked_sync_jwt.py:44`): INSERT de una fila con `jwt_kid`, `jwt_uuid`, `motivo`, `revoked_by`, `expires_at`. La clave única `(jwt_kid, jwt_uuid, vigente_desde, fecha_retencion_hasta)` hace que revocar dos veces el mismo par sea idempotente: la `IntegrityError` de la segunda inserción se atrapa y se interpreta como una operación exitosa sin efecto (204), nunca como un error.

**Comprobar** — `is_revoked` (línea 99):

```sql
SELECT 1 FROM prod.revoked_sync_jwts
WHERE jwt_kid = :k AND jwt_uuid = :j
  AND expires_at IS NOT NULL AND expires_at > NOW()
```

El mismo mecanismo protege dos tipos de identidad distintos con la misma tabla: un JWT de `sync-agent-` revocado (por `jti`) y un *pairing token* revocado antes de usarse (convención `kid=f"pairing_token:{uuid}"`, ver §3 paso 3). El middleware de `sync_router.py` llama a `is_revoked` para rechazar con 401 cualquier request firmado con un JWT revocado.

## 5. Protección de tablas [A]: REVOKE y triggers

El modelo AUDIT-FIRST del proyecto (`AGENTS.md`, sección *Architectural Principles*) exige defensa en profundidad en tres capas para que ninguna tabla `[A]` (fuente de verdad append-only: `log_transaccional`, `revocacion_factura`, `revoked_sync_jwts`, etc.) pueda mutar fuera de los caminos permitidos: **API** (sin endpoint DELETE), **ORM** (solo *helpers* de cierre+inserción), **DB** (`REVOKE` + trigger).

**Migración inicial** (`backend/packages/parkos_core/migrations/versions/0001_initial_schema.py`): de las **12** entidades ER `[A]` originales, **11** reciben `REVOKE UPDATE, DELETE ... FROM rol_app` más un trigger `BEFORE UPDATE OR DELETE` por tabla (`fn_<table>_inmutable()`, que levanta `ERRCODE 42501` ante cualquier intento de mutación) — según el resumen de las propias migraciones (`migrations/versions/README.md:31,35,86-88`). `sync_queue` es la excepción deliberada: conserva un carve-out operativo de `UPDATE` acotado a cuatro columnas (`estado`, `intentos`, `next_retry_at`, `ultimo_error`), documentado y probado en `repo/sync_queue.py`.

**Crecimiento del canon (ADR-002, ver [`./decisiones-tecnicas.md`](./decisiones-tecnicas.md)).** `sync-overhaul` eleva las entidades ER `[A]` de 12 a **14** (`+prod.sync_queue_lw_buffer`, `+prod.alert_types`), cada una con su propio `REVOKE` + trigger en la **misma** migración que la crea (`0012_add_sync_queue_lw_buffer.py`, `0013_add_alert_types.py`) — la convención que `AGENTS.md:169` exige explícitamente ("Every migration that touches `[A]` tables MUST include the REVOKE statement AND the BEFORE UPDATE OR DELETE trigger in the SAME migration").

> **Nota — hueco encontrado.** La sección *Architectural Principles* de `AGENTS.md` (líneas 34-36 y 110) todavía documenta *"REVOKE UPDATE, DELETE on 11 `[A]` tables"* — la cifra previa a la enmienda de ADR-002. Las migraciones 0012/0013 ya reflejan 14 entidades `[A]` en el canon ER (13 con REVOKE + trigger propio, más `sync_queue` con su carve-out); `AGENTS.md` no se actualizó tras esa enmienda.

**Verificación en arranque.** `infra/docker/entrypoint.sh` corre un verificador de REVOKE/trigger antes de exponer el servicio (`wait-postgres → rol_app precheck → alembic upgrade head → REVOKE/trigger verifier → exec CMD`, `AGENTS.md:176`) y aborta con código distinto de cero si detecta *drift* (`AGENTS.md:250`): la protección de esquema no depende solo de que la migración se haya aplicado alguna vez, se revalida en cada arranque de contenedor.

**Ampliación reciente más allá de `[A]`** (migración `0021`, 2026-09-10) — ver el detalle completo en §6, porque su hallazgo principal es sobre el rol de conexión, no sobre las tablas `[A]` en sí.

## 6. Roles de base de datos

| Rol | LOGIN | Atributos | Propósito |
|---|---|---|---|
| `rol_app` | no | — | rol de "grupo de privilegio" puro; ningún proceso se conecta como él directamente |
| `rol_admin_auditor` | no | `BYPASSRLS` | solo lectura (`GRANT SELECT ON ALL TABLES`) para auditoría/reporting |
| `parkos_app` | **sí** | `INHERIT` de `rol_app` | identidad real de conexión de las 4 aplicaciones de contenedor (desde la migración `0021`) |

`rol_app` y `rol_admin_auditor` se crean en la migración inicial (`0001_initial_schema.py:2911-2919`): `rol_app` recibía originalmente `SELECT, INSERT, UPDATE, DELETE` amplio sobre todo `prod.*`, acotado después tabla por tabla; `rol_admin_auditor` solo `SELECT` sobre todo el esquema, con el atributo `BYPASSRLS` (ver la nota de §2.1 sobre la ausencia actual de políticas RLS activas).

### 6.1 Hallazgo: el rol de aplicación real solo existe desde hoy (migración 0021)

Este es el cambio de seguridad más reciente del repositorio (commit `5edb317`, rama actual) y se documenta con detalle porque invalida retroactivamente el sentido de todo `REVOKE` anterior:

> **Causa raíz.** `rol_app` es `NOLOGIN` desde `0001` — pensado para ser heredado por un rol de conexión real, que nunca llegó a existir. El único rol con `LOGIN` en ambos nodos era `parkos`, que además es **superusuario** de PostgreSQL (`POSTGRES_USER=parkos`, usado tal cual en `DATABASE_URL`/`PARKOS_DB_URL` por los cuatro contenedores de aplicación, confirmado en vivo vía `pg_roles`). Un superusuario ignora todo `GRANT`/`REVOKE` por definición: **cada `REVOKE` escrito por cualquier migración anterior fue inerte desde el día en que se escribió.**

La migración `0021_least_privilege_and_immutability_contract.py`:

1. Crea `parkos_app LOGIN INHERIT` (línea 227) y lo agrega a `rol_app` (línea 232), con una contraseña dev-only inyectable vía la variable `PARKOS_APP_DB_PASSWORD` — marcada explícitamente en el código como pendiente de gestión de secretos real para producción — y actualiza `docker-compose.cloud.yml`/`docker-compose.local.yml` para que los 4 contenedores de aplicación conecten con `parkos_app` en vez de con `parkos`.
2. Con `rol_app` ya en uso real, quedaron expuestos privilegios reales que antes no se podían ni detectar: 8 tablas `[L-W]`/`[L-E]` (`alerta`, `anulaciones`, `reclamos`, `reimpresion_ticket`, `validacion_evento`, `facturas`, `ingreso`, `factura_electronica`) y 26 tablas `[V]` más `login`/`sesion` tenían `UPDATE` y `DELETE` completamente abiertos para la aplicación.
3. Se cerraron con `REVOKE UPDATE, DELETE` + `GRANT UPDATE` acotado a columnas concretas — **nunca con un trigger nuevo**: un primer intento con un trigger genérico bloqueaba incluso al superusuario y rompió 30 tests reales (duplicaba triggers ya existentes en las tablas `[A]`, contradecía el carve-out ya probado de `sync_queue`, y chocaba con *fixtures* de test que hacen limpieza como superusuario). El propio archivo de migración documenta este giro de diseño en su docstring (líneas 29-105) como una corrección hecha dentro de la misma sesión de trabajo, no oculta después del hecho.

Columnas concedidas por excepción, con su justificación verificada en el código:

| Tabla(s) | Columnas con UPDATE permitido | Motivo verificado |
|---|---|---|
| `envio_dian` | `payload` | `dian/cloud/dispatcher.py` hace un `UPDATE` legítimo de ese campo a mitad del *round-trip* con el proveedor DIAN (fusiona el `track_id`) |
| 26 tablas `[V]` | `vigente_hasta`, `estado` | cierre bi-temporal de versión |
| `login` | `timestamp_cierre`, `estado` | cierre de sesión |
| `sesion` | `timestamp_cierre`, `uuid_usuario_cierre`, `estado` | cierre de sesión; `estado` está además guardado por el trigger preexistente `fn_sesion_ls_session_guard()` |
| 8 tablas `[L-W]`/`[L-E]` restantes | ninguna (`REVOKE UPDATE, DELETE` sin `GRANT` de vuelta) | sin caso de uso legítimo de actualización |

**Asimetría residual — documentada explícitamente por la propia migración, no un hallazgo independiente de este documento:** para las tablas restringidas en `0021`, la protección es solo `GRANT`/`REVOKE` (que un rol superusuario puede seguir saltándose); solo las tablas `[A]` originales (protegidas desde `0001`) y `idempotency_keys`/`pairing_tokens`/`revoked_sync_jwts`/`sync_queue_lw_buffer` mantienen además el trigger que bloquea incluso a un superusuario. `sync_queue` conserva su `DELETE` (carve-out para un futuro *worker* de purga, aún no implementado). Verificado en vivo contra Docker real, según el propio mensaje de commit: `rol_app` ya no puede tocar columnas de negocio ni borrar filas, y los 4 contenedores corrieron tráfico real de sincronización sin errores tras el cambio de rol.

---

## Ver también

- [`./decisiones-tecnicas.md`](./decisiones-tecnicas.md) — ADRs del motor de sincronización y mitigaciones de concurrencia.
- [`./modelo-datos.md`](./modelo-datos.md) — modelo de datos, clases de auditoría y el ER completo.
- [`../01-requisitos/no-funcionales.md`](../01-requisitos/no-funcionales.md) — requisitos no funcionales (incluye seguridad y cumplimiento DIAN).
- [`../04-qa-testing/plan-pruebas.md`](../04-qa-testing/plan-pruebas.md) — estrategia de pruebas, incluida `test_pairing_flow.py` y la suite de autenticación.
- [`../runbooks/sync/`](../runbooks/sync/) — procedimientos operativos de sincronización.
