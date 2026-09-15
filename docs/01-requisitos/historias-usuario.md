# Historias de Usuario — easypunto_parkos

[Índice general](../README.md) · [Requisitos funcionales](funcionales.md) · [Requisitos no funcionales](no-funcionales.md) · [Decisiones técnicas](../02-arquitectura/decisiones-tecnicas.md) · [Modelo de datos](../02-arquitectura/modelo-datos.md) · [Referencia de API](../03-desarrollo/api-reference.md)

> Historias derivadas de funcionalidad **ya implementada** en el código real (no aspiracional).
> Cada una cita el endpoint y/o el test que la respalda. Formato: *Como &lt;rol&gt;, quiero
> &lt;acción&gt;, para &lt;objetivo&gt;*, con criterios de aceptación verificables. La sección
> final agrupa historias de **Roadmap** (no implementadas), marcadas explícitamente con su fuente
> en `openspec/_meta/iteration-plan.md`. Ver también
> [`funcionales.md`](funcionales.md) para el catálogo completo de requisitos y
> [`no-funcionales.md`](no-funcionales.md) para SLA/seguridad/rendimiento.

## Roles reales del sistema

| Rol | Issuer JWT | Dónde opera |
|---|---|---|
| Administrador | `admin-` | `web_admin` + `api_admin` |
| Operador de sucursal | `operador-` | `web_sucursal` (planeado) + `api_sucursal` |
| Agente de sincronización (proceso, no humano) | `sync-agent-` | `job_sync_cloud` / `job_sync_sucursal` |

---

## Autenticación y sesión

### HU-01 — Login con JWT por rol
Como **administrador u operador de sucursal**, quiero iniciar sesión con mis credenciales, para
obtener un token que me autorice solo dentro de mi ámbito (admin global vs. una sucursal).

**Criterios de aceptación**
- El token emitido lleva el prefijo `kid` del issuer correspondiente (`admin-`/`operador-`).
- Un token de un issuer no sirve en el API del otro rol (rechazo 401 cruzado).

**Evidencia**: `POST /api/v1/auth/login` (`api/v1/auth.py:44`); AGENTS.md §"JWT (three issuers)".

### HU-02 — Renovar sesión sin volver a autenticar
Como **usuario autenticado**, quiero renovar mi token antes de que expire, para no perder mi
sesión de trabajo a mitad de un turno.

**Evidencia**: `POST /api/v1/auth/refresh` (`api/v1/auth.py:133`).

### HU-03 — Cerrar sesión
Como **usuario autenticado**, quiero cerrar sesión explícitamente, para invalidar mi token actual.

**Evidencia**: `POST /api/v1/auth/logout` (`api/v1/auth.py:175`).

---

## Onboarding de sucursal

### HU-04 — Emitir un token de pairing de un solo uso
Como **administrador**, quiero generar un token temporal para una sucursal nueva, para que su
equipo pueda emparejarse una única vez sin compartir credenciales permanentes.

**Criterios de aceptación**
- El token expira a las 24 horas.
- Un segundo intento de uso del mismo token es rechazado (`410 Gone`).
- No puedo generar más de 5 tokens por hora.

**Evidencia**: router admin `admin/pairing-tokens`; `repo/pairing.py::generate_pairing_token`;
`api/rate_limit_pairing.py`; `backend/tests/integration/test_pairing_flow.py` (9 escenarios).

### HU-05 — Sucursal se empareja con el cloud
Como **agente de sincronización de una sucursal nueva**, quiero canjear el token de pairing por un
JWT de larga duración, para poder sincronizar de forma continua sin repetir el proceso manual.

**Evidencia**: `POST /api/v1/sync/pair` (`api/v1/sync_router.py:432`); `POST /api/v1/sync/hello`
para negociar versión de protocolo (`sync_router.py:402`).

### HU-06 — Revocar el acceso de una sucursal
Como **administrador**, quiero revocar el pairing o el JWT de sincronización de una sucursal, para
cortar su acceso si el equipo se da de baja o hay sospecha de compromiso.

**Evidencia**: `POST /api/v1/admin/pairing-tokens/{uuid}/revoke`,
`POST /api/v1/admin/sucursales/{uuid}/revoke-sync`; `repo/revoked_sync_jwt.py::revoke_jwt`.

---

## Gestión de catálogos

### HU-07 — Mantener catálogos operativos desde el admin
Como **administrador**, quiero crear y versionar catálogos (tipos de vehículo, tarifas, impuestos,
tipos de arqueo, etc.), para que cada sucursal opere con las mismas reglas de negocio sin
redeploy.

**Criterios de aceptación**
- Puedo consultar, insertar y actualizar cada uno de los 9 catálogos (nunca eliminar).
- Una actualización no borra el valor anterior: cierra la versión vigente e inserta una nueva.

**Evidencia**: `api/v1/catalogos.py:1-130` (9 catálogos); `backend/tests/unit/test_tipo_arqueo_crud.py`
(patrón representativo de los 9).

### HU-08 — Los catálogos llegan a la sucursal aunque esté sin conexión
Como **operador de sucursal**, quiero que los catálogos configurados en el admin (tarifas, tipos
de vehículo, impuestos) estén disponibles localmente, para poder cobrar y clasificar ingresos aun
sin conexión a internet.

**Evidencia**: `openspec/specs/sync-catalog/spec.md` REQ-CAT-004 (18 tablas `[V]` corregidas para
replicar `cloud_to_branch`/`all_branches`, entre ellas `tipos_vehiculo`, `impuestos`,
`tarifas_sucursal`).

---

## Operación diaria de parqueadero

### HU-09 — Registrar el ingreso de un vehículo
Como **operador de sucursal**, quiero registrar la entrada de un vehículo con su placa y tipo,
para llevar el control de ocupación y poder facturar la salida más tarde.

**Evidencia**: `POST /api/v1/ingresos` (`api/v1/operacion.py:73`).

### HU-10 — Consultar el estado de un ingreso
Como **operador de sucursal**, quiero ver si un ingreso sigue activo o ya se cerró, para decidir
si puedo facturar la salida.

**Evidencia**: `GET /api/v1/ingresos/{uuid}/estado` (`api/v1/operacion.py:121`).

### HU-11 — Ver la lista de ingresos activos de mi sucursal
Como **operador de sucursal**, quiero listar los ingresos de mi sucursal, para tener visión del
parqueadero en el turno.

**Evidencia**: `GET /api/v1/ingresos` (`api/v1/operacion.py:168`).

### HU-12 — Abrir y cerrar una sesión de caja
Como **operador de sucursal**, quiero abrir mi caja al iniciar turno y cerrarla al terminar, para
que el sistema registre el ciclo de mi turno con auditoría (log-first).

**Evidencia**: `POST /api/v1/sesiones`, `PUT /api/v1/sesion/{uuid}/cerrar`
(`api/v1/caja_sesion.py:70-145`).

### HU-13 — Ver diferencias de un arqueo
Como **operador o administrador**, quiero ver la diferencia entre lo esperado y lo reportado en un
arqueo, para detectar faltantes o sobrantes de caja.

**Evidencia**: `GET /api/v1/arqueos/{uuid}/diferencias` (`api/v1/caja_sesion.py:145`).

---

## Clientes, vehículos y suscripciones

### HU-14 — Registrar un cliente con suscripción
Como **administrador**, quiero registrar un cliente (natural o B2B) y venderle una suscripción
ligada a una sucursal, para que sus vehículos asociados usen tarifas de plan en lugar de tarifa
ocasional.

**Evidencia**: recursos `clientes`, `clientes-b2b`, `subscripciones-cliente`, `vehiculos`,
`subscripcion-vehiculos` bajo `/api/v1/clientes` (`api/v1/clientes.py:40-120`).

### HU-15 — Dos sucursales registran el mismo cliente estando ambas sin conexión
Como **sistema de sincronización**, quiero reconciliar automáticamente dos versiones del mismo
cliente o vehículo (identificados por documento o placa) creadas por sucursales distintas mientras
ambas estaban offline, para que no se dupliquen entidades ni se bloquee la operación.

**Criterios de aceptación**
- La reconciliación nunca bloquea (no puede frenar una factura por este motivo).
- Si los datos difieren de forma material, se registra un `sync_conflict` informativo, sin
  detener la aplicación.

**Evidencia**: `openspec/specs/sync-catalog/spec.md` REQ-CAT-018 (D17,
`IdentityReconciler`).

---

## Facturación electrónica DIAN

### HU-16 — Emitir factura electrónica sin depender de la conexión a cloud
Como **operador de sucursal**, quiero emitir una factura electrónica con la numeración de mi
propia resolución, esté o no conectado a cloud, para no detener la operación por una caída de
red.

**Criterios de aceptación**
- La numeración es idéntica en línea o sin conexión (mismo comportamiento).
- El documento queda como final desde la emisión; lo único pendiente puede ser el acuse DIAN.

**Evidencia**: `POST /api/v1/factura-electronica`; `openspec/changes/archive/2026-09-09-sync-overhaul/adr/001-parkos-sync-engine-enum.md`
(contexto de D1-rev); AGENTS.md §"DIAN".

### HU-17 — Reintentar el envío a DIAN ante fallas del proveedor
Como **sistema (dispatcher DIAN)**, quiero reintentar el envío de una factura con una curva de
espera creciente y detenerme con una alerta crítica tras 6 intentos, para no perder de vista un
documento que ya consumió un número consecutivo irrepetible.

**Evidencia**: `dian/backoff.py::DIAN_BACKOFF_SCHEDULE` (1m→5m→15m→1h→6h→24h);
`backend/tests/unit/test_dian_backoff.py`.

### HU-18 — Reimprimir un ticket sin esperar al acuse DIAN
Como **operador de sucursal**, quiero reimprimir un ticket ya emitido en cualquier momento, para
atender al cliente sin que una demora de DIAN me bloquee.

**Estado real (corregido tras verificación directa)**: el modelo de datos (`reimpresion_ticket`,
`[L-W]`) y la regla de negocio (nunca condicionada a un round-trip a cloud) están definidos, y el
recurso es **consultable** vía `GET /workflows/reimpresion-ticket`. Pero el router se monta con
`write_enabled=False` (`api/v1/workflows.py:81-108`, confirmado leyendo el archivo completo): **no
existe un `POST` para crear una reimpresión vía API** — el propio docstring del módulo lo dice
explícitamente: *"Custom transition endpoints ship in PR7. PR6 only exposes reads."* Ver HU-R03bis
en Roadmap.

**Evidencia**: `api/v1/workflows.py:1-41` (docstring), `:111-118` (montaje `reimpresion-ticket`);
AGENTS.md §"Frontend" (la regla de negocio en sí sí está confirmada, solo falta el endpoint de
creación).

### HU-19 — Revocar una factura electrónica
Como **sistema (webhook DIAN)**, quiero registrar la revocación de una factura y extender la
cadena de hash correspondiente, para mantener evidencia probatoria íntegra ante una anulación
fiscal.

**Evidencia**: `POST /api/v1/revocacion-factura-webhook` (`dian/cloud_router.py:294-346`).

### HU-20 — Reversar un pago sin borrar el original
Como **operador de sucursal**, quiero reversar un pago registrado por error, para corregirlo sin
que el registro original desaparezca del historial auditable.

**Evidencia**: índice único parcial `uq_factura_pagos_reverso`;
`backend/tests/unit/test_factura_pagos_reverse.py`, `test_bi_temporal_compensation.py`.

---

## Integridad y auditoría (roles de sistema)

### HU-21 — Verificar periódicamente que la cadena de hash no se rompió
Como **job de sincronización en cloud**, quiero recorrer la cadena de hash de `log_transaccional`
y `revocacion_factura` por sucursal, para detectar manipulación o corrupción antes de que se
acumule.

**Evidencia**: `SyncMotor.verify_chain` (`openspec/specs/sync-motor/spec.md` REQ-MOT-006);
runbook [`../runbooks/sync/chain_break.md`](../runbooks/sync/chain_break.md).

### HU-22 — La aplicación nunca debe operar con privilegios de superusuario
Como **responsable de seguridad**, quiero que la aplicación se conecte a la base de datos con un
rol de mínimo privilegio real (no el superusuario), para que los `REVOKE` declarados en el esquema
efectivamente restrinjan lo que el código puede hacer.

**Criterios de aceptación**
- Existe un rol `parkos_app` con `LOGIN`, que hereda de `rol_app` (sin `LOGIN` propio).
- Los 4 contenedores de aplicación se conectan con `parkos_app`, no con el superusuario.

**Evidencia**: commit `5edb317`; migración
`0021_least_privilege_and_immutability_contract.py` (2026-09-10).

### HU-23 — Un lote de sincronización no se pierde por una fila con dependencia pendiente
Como **sistema de sincronización**, quiero aplicar un lote en orden de dependencias y diferir solo
la fila cuyo padre no ha llegado (nunca abortar el lote completo), para que un pico de tráfico no
bloquee filas que sí podían aplicarse.

**Evidencia**: `openspec/specs/sync-motor/spec.md` REQ-MOT-015 (D18); corrección real aplicada en
el cierre de `sync-overhaul` — `openspec/changes/archive/2026-09-09-sync-overhaul/archive-report.md`
§5.2, punto 2.

---

## Roadmap — historias no implementadas

> Marcadas explícitamente como planeación, no como funcionalidad actual. Fuente:
> `openspec/_meta/iteration-plan.md` salvo que se indique otra.

### HU-R01 — Registrar la salida de un vehículo (IT-4)
Como operador de sucursal, quiero registrar la salida de un vehículo para cerrar su ingreso y
calcular el cobro. No existe `POST` sobre `salidas` en ningún router — confirmado **textualmente**
en el propio código (`api/v1/operacion.py:15-17`): *"the exit ('salida') HTTP endpoint itself is
not built by any PR up to and including this one (no `salidas` CRUD route exists yet in this
router or elsewhere in `api/v1/`)"*. Fuente de planeación: IT-4.

### HU-R02 — Dar de alta usuarios y asignarlos a una sucursal (IT-1.4/IT-1.5)
Como administrador, quiero crear usuarios operadores y asignarlos a una sucursal. El login ya
existe (HU-01); la gestión de usuarios en sí no tiene endpoint confirmado.

### HU-R03 — Aprobar y ejecutar una anulación (IT-6)
Como administrador, quiero aprobar y luego ejecutar una anulación solicitada por un operador,
avanzando la cadena `solicitada → aprobada → ejecutada`. Hoy `anulaciones` es de solo lectura vía
API (`api/v1/workflows.py`).

### HU-R04 — Resolver un reclamo (IT-8)
Como administrador, quiero marcar un reclamo como `en_revision` y luego `resuelto`/`rechazado`.
Mismo estado que HU-R03: solo lectura hoy.

### HU-R03bis — Crear y transicionar una reimpresión de ticket vía API
Como operador, quiero registrar una reimpresión de ticket (y su eventual anulación) desde la
interfaz, sin depender de que llegue por sincronización desde otro nodo. Confirmado por lectura
completa de `api/v1/workflows.py`: los 4 recursos que monta (`reimpresion-ticket`, `anulaciones`,
`reclamos`, `alerta`) usan `write_enabled=False` — ninguno tiene `POST`/`PUT` propio; la única vía
de escritura real hoy es `repo/workflow.py::append_transition`, invocada desde el motor de sync
(`sync/motor/apply_row.py`), no desde un endpoint HTTP interactivo. Fuente: `api/v1/workflows.py:26-34`
(docstring: "Custom transition endpoints ship in PR7").

### HU-R05 — Revisar y descartar una alerta operacional (IT-7)
Como administrador, quiero marcar una alerta como revisada o descartarla. La emisión automática
de alertas (arqueo, sync) ya funciona; la gestión manual vía API no tiene endpoint confirmado.

### HU-R06 — Ver reportes administrativos multi-sucursal (IT-11)
Como administrador, quiero ver agregaciones diarias/semanales de facturación, arqueo y alertas
entre sucursales, para tomar decisiones sin revisar sucursal por sucursal.

### HU-R07 — Panel de auditoría de la cadena de hash (IT-12)
Como administrador, quiero un panel en `web_admin` que muestre el estado de la cadena de hash por
sucursal/tabla/usuario, filtrable, para auditar sin acceso directo a la base de datos.

### HU-R08 — Operar desde `web_sucursal` (frontend de sucursal)
Como operador de sucursal, quiero una interfaz web para todo lo anterior (ingreso, caja,
facturación). Hoy `web_sucursal` no existe como aplicación — fuente: AGENTS.md §"Frontend",
verificado con `apps/**/package.json` (solo existe `apps/web_admin`).

### HU-R09 — Ver un banner de modo degradado ante partición de red
Como operador de sucursal, quiero un aviso visual claro cuando mi sucursal no puede alcanzar el
cloud, para saber que ciertas funciones (visibilidad del acuse DIAN) están temporalmente
degradadas. Fuente: `openspec/specs/sync-catalog/spec.md` §"Out of Scope" (D16).

### HU-R10 — Bloquear una cuenta tras varios intentos fallidos de login (REQ-43)
Como responsable de seguridad, quiero que una cuenta se bloquee temporalmente tras N intentos de
login fallidos, para mitigar ataques de fuerza bruta contra credenciales de operadores o
administradores. Hoy toda falla de autenticación responde `401` genérico (anti-enumeración) sin
incrementar ningún contador ni bloquear la cuenta — confirmado en el propio docstring del módulo:
*"PR1b ships the login + logout skeleton. The full failure-path (counter increment + lockout after
N failed attempts, REQ-43) lands in PR7."* Fuente: `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:6-8,51`.
