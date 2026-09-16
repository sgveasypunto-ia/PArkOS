# Decisiones técnicas

> Arquitectura del motor de sincronización bidireccional — easypunto_parkos
> Fuente primaria: `openspec/changes/archive/2026-09-09-sync-overhaul/` (ADRs 001-003 y `design.md`) y `AGENTS.md` (raíz del repo). Este documento transcribe y resume decisiones ya ratificadas; no introduce decisiones nuevas. Para el detalle línea por línea, remitirse siempre al ADR original citado en cada sección.

Este documento cubre las decisiones arquitectónicas del motor de sincronización cloud-sucursal (cambio `sync-overhaul`, archivado 2026-09-09) y las mitigaciones de concurrencia que ese motor implementa y prueba contra Postgres real. Para el modelo de datos completo ver [`./modelo-datos.md`](./modelo-datos.md); para el modelo de seguridad ver [`./seguridad.md`](./seguridad.md).

## Índice

- ADR-001: enum `PARKOS_SYNC_ENGINE`
- ADR-002: el canon ER crece de 49 a 51 entidades (54 tablas físicas)
- ADR-003: `depends_on` y un único camino de escalación
- Concurrencia y condiciones de carrera

---

## ADR-001: enum PARKOS_SYNC_ENGINE

**Fuente**: `openspec/changes/archive/2026-09-09-sync-overhaul/adr/001-parkos-sync-engine-enum.md`
**Estado**: Aceptada (la decisión original de nombrar el enum por comportamiento fue revertida por enmienda del 2026-09-08; el enum vigente es el descrito abajo).

### Contexto

`PARKOS_SYNC_ENGINE` es el único feature flag que gobierna el *cutover* del motor de sincronización. Lo lee `parkos_core/runtime/engine_flag.py::get_engine()` al inicio de cada ciclo de 60 s de cada worker Python; se valida contra el enum en la primera lectura y se cachea después. `infra/docker/entrypoint.sh` solo reenvía la variable de entorno, sin lógica propia. El valor `legacy` es el interruptor de apagado (*kill switch*) de todo el cambio.

El cutover se escalona **por servicio**, no por comportamiento observable:

| Etapa | Servicio | Valor |
|---|---|---|
| 0 | todos | `legacy` |
| 1 | `api_admin` | `catalog_admin` |
| 2 | `dian/cloud/dispatcher` | `catalog_dian` |
| 3 | `jobs/sync_cloud` | `catalog` |
| 4-5 | workers de sucursal | `catalog_branch` |

Durante el diseño coexistieron dos candidatos: uno orientado a servicio (el de las specs) y uno orientado a comportamiento (`catalog_read`/`catalog_dual`/`catalog_only`/`catalog_lite`, el del diseño original). La revisión de conformidad ER detectó el conflicto (hallazgo A5) y esta ADR lo resuelve reteniendo un único enum.

### Decisión

`PARKOS_SYNC_ENGINE` acepta exactamente cinco valores: **`legacy | catalog_admin | catalog_dian | catalog | catalog_branch`** — el enum orientado a servicio, ya presente en las specs (`sync-motor.md` REQ-MOT-011, `cutover-migration.md` REQ-CUT-001). El enum orientado a comportamiento queda retirado y no puede reaparecer en ningún artefacto, módulo, runbook o test.

Razonamiento clave: si el *cutover* ya se escalona por servicio, el valor del flag debe nombrar la etapa directamente, así un operador respondiendo un incidente no necesita una tabla de mapeo adicional para saber "qué etapa está viva". El motor (`SyncMotor.__init__(engine=...)`) sigue sin importar identidad de servicio: recibe el modo como argumento de constructor y despacha sobre él.

### Consecuencias

**Positivas**: cero *drift* entre specs y diseño; el valor del flag ubica la etapa directamente en logs y runbooks; el rollback sigue siendo un único cambio de variable de entorno a `legacy`.

**Negativas**: el diseño y esta misma ADR llevaban los valores retirados y debieron enmendarse; cualquier artefacto que los usara debe corregirse — mitigado con un guard AST (`check_engine_flag_values.py`) que falla el build ante un literal retirado. El valor `catalog` es prefijo de `catalog_admin`, `catalog_dian` y `catalog_branch`; el parser hace *match* exacto contra el enum, nunca `startswith`.

**Validación**: `tests/unit/test_engine_flag.py` (`test_parse_all_5_values`, `test_rejects_withdrawn_values`, `test_exact_match_not_prefix`, `test_legacy_is_kill_switch`).

---

## ADR-002: el canon ER crece de 49 a 51 entidades (54 tablas físicas)

**Fuente**: `openspec/changes/archive/2026-09-09-sync-overhaul/adr/002-50-table-canon.md` (el nombre del archivo es histórico y no refleja la aritmética vigente; la propia ADR lo advierte en su título y en una nota de encabezado).
**Estado**: Aceptada, enmendada 2026-09-08.

### Contexto

El canon del proyecto (`AGENTS.md`, sección *Architectural Principles*) declaraba un modelo AUDIT-FIRST de 49 tablas ER, verificado por `openspec/scripts/check_table_counts.py` y `check_schema_match.py`. `sync-overhaul` necesita dos tablas `[A]` operacionales nuevas:

- **`prod.sync_queue_lw_buffer`** — el buffer de dependencias (ver ADR-003): una fila por cada entrada con un padre `depends_on` declarado y ausente, indexada por `(tabla_padre, uuid_padre)`, TTL de 24 h configurable.
- **`prod.alert_types`** — registro del catálogo de tipos de alerta del proyecto, sembrado de forma idempotente tanto en la nube como en cada sucursal.

### Decisión

El canon ER crece de **49 a 51 entidades**; el total de tablas físicas en producción pasa a **54** (51 ER + 3 tablas operacionales no-ER ya existentes desde `create-49-table-apis`: `idempotency_keys`, `pairing_tokens`, `revoked_sync_jwts`). Ambas tablas nuevas quedan **fuera del catálogo de sincronización** (`OUT_OF_CATALOG`): bufferizar el propio buffer no tiene sentido, y el registro de alertas se siembra en el despliegue en vez de replicarse. El criterio explícito para esta última decisión es *quién autoriza los valores*: un catálogo editable por el operador debe replicarse porque un valor nuevo debe llegar a la sucursal sin un despliegue; los identificadores de `alert_types` se referencian en código Python, así que añadir uno ya implica un despliegue.

Conteo canónico completo (fuente única de verdad: `check_table_counts.py`):

| Magnitud | Valor |
|---|---|
| Entidades ER | 51 (26 `[V]` + 3 `[L-E]` + 6 `[L-W]` + 2 `[L-S]` + 14 `[A]`) |
| Tablas operacionales no-ER | 3 |
| **Total tablas físicas** | **54** |
| `SYNC_CATALOG` | 46 |
| `LOCAL_ONLY_CATALOG` | 3 |
| `OUT_OF_CATALOG` | 5 (`sync_queue`, `sync_log`, `sync_conflict`, `sync_queue_lw_buffer`, `alert_types`) |

### Consecuencias

**Positivas**: `sync_queue` mantiene su propósito acotado (drenar rápido, reintentar con backoff); el buffer obtiene su propio `pg_partman` parent con TTL y particionado independientes; `alert_types` le da a `repo/alert_types.py::validate` un registro contra el cual rechazar identificadores desconocidos.

**Negativas**: los scripts de conteo y `modelo_datos_er.mmd` deben actualizarse en el mismo cambio — la propia enmienda documenta que en el primer intento nadie tocó el `.mmd`, dejando el gate de CI imposible de pasar. Mantener dos cifras (entidades ER vs. tablas físicas) exige disciplina: confundirlas fue precisamente el defecto que esta enmienda corrige.

**Validación**: `check_table_counts.py`, `check_schema_match.py`, `check_catalog_drift.py` (exit 0); `tests/migrations/test_sync_queue_lw_buffer_schema.py`, `test_alert_types_schema.py`.

---

## ADR-003: depends_on y un único camino de escalación

**Fuente**: `openspec/changes/archive/2026-09-09-sync-overhaul/adr/003-dependency-ordering-and-single-escalation.md`
**Estado**: Aceptada.

### Contexto

La revisión de conformidad ER (hallazgo C4) constató que no existía ningún orden de aplicación por FK para el tráfico `branch_to_cloud`: nueve pares padre/hijo de la ruta de facturación (`salidas→ingreso`; `facturas→ingreso,salidas`; `factura_detalle/factura_impuestos/factura_otros_cobros/factura_pagos→facturas`; `factura_pagos→sesion`; `arqueo→sesion`; `revocacion_factura→factura_electronica`) no tenían protección alguna; las clases `[L-E]`/`[A]` se aplicaban siempre como "APPLIED" sin ningún camino `RETRY(parent_missing)`, así que un hijo llegado antes que su padre producía una violación de FK cruda — justo en la ruta crítica DIAN, donde los hijos llegan primero con más frecuencia. Además, `priority` (heredado del orden de inserción de los triggers legados) llegaba a ordenar hijos *antes* que sus padres, y coexistían dos caminos de escalación sin reconciliar (reencolado en `sync_queue` a `intentos>=6` y el barrido de TTL del buffer).

### Decisión

**Parte 1 — `depends_on` es el único mecanismo de orden entre tablas.** Cada entrada del catálogo declara `depends_on`: las tablas a las que tiene una FK **obligatoria** (NOT NULL) que a su vez es una entrada del catálogo. Los batches se aplican en **orden topológico** sobre `depends_on`; cualquier padre declarado y ausente produce `RETRY(parent_missing)`. `depends_on` se deriva por CI desde el bloque de relaciones del ER (`check_catalog_drift.py`) y nunca se mantiene a mano; las FKs opcionales quedan excluidas estructuralmente (una FK opcional en `depends_on` rompe el build); los siete self-chains se excluyen del ordenamiento topológico y se resuelven aparte por `ValidateParentChain`; y `priority` queda degradado a un simple desempate FIFO dentro de un mismo nivel topológico — usarlo para ordenar entre tablas queda prohibido y un guard de CI lo verifica.

**Parte 2 — `RETRY(parent_missing)` es "entregado y diferido"; un único camino de escalación.** Quien recibe la fila (la nube para `branch_to_cloud`, la sucursal para `cloud_to_branch`) es quien bufferiza, porque es quien puede ver si el padre existe:

| `ApplyResult.status` | Estado por fila en `/sync/events` | Acción del emisor |
|---|---|---|
| `APPLIED` | `applied` | `mark_success` |
| `CONFLICT` | `conflict` | `mark_success` (ya entregada; existe una fila en `sync_conflict`) |
| `RETRY(parent_missing)` | `retry_parent_missing` | **`mark_success`** — entregada; la espera pasa a ser responsabilidad del buffer del receptor |
| fallo de transporte/HTTP | — | `mark_failed` → backoff |

En consecuencia, `sync_queue` **nunca** se reencola por una espera de dependencia y `intentos` **nunca** se incrementa por eso — el buffer es dueño de la espera y su barrido de TTL es dueño del *timeout*. El drenado es una **cola de trabajo iterativa acotada**, no recursión dentro de la transacción que aplica: cuando un padre se aplica, se drenan los hijos bufferizados con esa clave, con tope por ciclo (tamaño de batch) y por fila (profundidad del DAG).

### Consecuencias

**Positivas**: los nueve pares desprotegidos de la ruta de facturación quedan cubiertos por el mismo mecanismo que ya protegía los seis self-chains `[L-W]`; la métrica de tasa de fallos de transporte vuelve a ser honesta (antes, una espera de dependencia contaba como fallo de transporte, lo que podía bloquear o aprobar falsamente el *gate* de la etapa 3 del cutover); el mismo mecanismo ordena tanto la réplica en régimen estable como el *backfill* inicial de una sucursal recién emparejada.

**Negativas**: el contrato de red gana un estado adicional por fila (`retry_parent_missing`) que ambas versiones del protocolo deben entender durante la ventana de gracia de 14 días. Hacer `mark_success` sobre una fila que no se aplicó "parece un bug" a primera vista — mitigado con nomenclatura explícita en el punto de llamada, una métrica (`sync_deferred_total`) que cuenta estos casos separados de `applied`, y un test dedicado que confirma que `intentos` no cambia tras un diferimiento.

**Validación**: `tests/unit/test_dependency_graph.py`, `test_dependency_orderer.py`; `tests/integration/test_parent_missing_buffer_drain.py`, `test_r22_non_selling_branch.py`, `test_buffer_ttl_escalation.py`; `check_catalog_drift.py`.

---

## Concurrencia y condiciones de carrera

Las siguientes mitigaciones ya están implementadas y probadas contra Postgres real (`testcontainers`); se documentan aquí como decisiones arquitectónicas vigentes, no como riesgos hipotéticos.

### 1. Fila hija sincronizada antes que su padre

Cuando el validador de dependencias no encuentra el padre declarado de una fila (ni localmente ni antes en el mismo batch), `motor/dependency_buffer.py::handle_parent_missing` (`backend/packages/parkos_core/src/parkos_core/sync/motor/dependency_buffer.py:178`) inserta la fila en `prod.sync_queue_lw_buffer` vía `buffer_row` (línea 123), indexada por `(tabla_padre, uuid_padre)`, con TTL configurable (`DEFAULT_TTL_HOURS = 24`, línea 75). Cuando el padre se aplica, `drain_dependency_buffer` (línea 238) drena las filas en espera con una cola FIFO iterativa (`deque`, no recursión), con un guard de reentrada (`contextvars.ContextVar`) y un tope de profundidad calculado desde los niveles topológicos reales del catálogo (`_MAX_DRAIN_DEPTH`, línea 81). Si el TTL expira antes de que el padre llegue, `_lw_buffer_sweep` (línea 332) marca la fila `fallido` y emite exactamente una alerta `orphan_workflow_chain` — nunca la reencola en `sync_queue`.

**Test real**: `backend/tests/integration/test_parent_missing_buffer_drain.py::test_parent_missing_buffer_drain` (línea 35); `backend/tests/integration/test_buffer_ttl_escalation.py::test_buffer_ttl_escalation_emits_one_alert_no_requeue` (línea 24) y `test_buffer_ttl_sweep_ignores_non_expired_rows` (línea 93).

### 2. Conflictos de escritura concurrente cloud/sucursal

`motor/resolve_conflict.py::resolve_conflict` (`backend/packages/parkos_core/src/parkos_core/sync/motor/resolve_conflict.py:183`) aplica la política de conflicto según la clase de auditoría de la entrada: las `[V]` con `natural_key` (identidad maestra: `clientes`, `clientes_b2b`, `vehiculos`) delegan en `IdentityReconciler` y nunca bloquean; las `[V]` sin `natural_key` comparan la secuencia local (`ReadLocalSeq`) contra la remota — si la remota es mayor, aplica; si no, escala a `MANUAL` y persiste ambas versiones en `prod.sync_conflict` (`_write_seq_tiebreak_conflict`, línea 144); las `[L-E]`/`[A]`/`[L-W]` resuelven cada padre declarado en `depends_on` o devuelven `RETRY(parent_missing)`; las `[L-S]` usan una ventana de gracia configurable (24 h por defecto).

**Test real**: `backend/tests/unit/test_resolve_conflict.py` (p. ej. `test_v_without_natural_key_manual_on_stale_remote_seq` línea 144, `test_v_without_natural_key_applies_when_remote_seq_is_newer` línea 123); `backend/tests/unit/test_conflict_resolver.py` (fachada `ConflictResolver`, p. ej. `test_versioned_table_rejects_stale_seq` línea 135, `test_versioned_table_accepts_newer_seq` línea 149).

### 3. Integridad de la cadena hash bajo escritura concurrente

`motor/verify_chain.py::verify_chain_for_spec` (`backend/packages/parkos_core/src/parkos_core/sync/motor/verify_chain.py:72`) recorre cada tabla con cadena (`log_transaccional`, `revocacion_factura`) en orden `(created_at, uuid)` — deliberadamente nunca por `timestamp_evento`, que es de negocio y puede colisionar en una ráfaga de eventos — comparando el `hash_anterior` de cada fila contra el `hash_actual` esperado desde el ancla de génesis (`_genesis_hash`, línea 62: `sha256("genesis:" + uuid_sucursal)`). Un desajuste no aborta el recorrido: cada fila se valida contra su propio predecesor inmediato, de modo que una única ruptura produce exactamente una anomalía y no una cascada de falsos positivos. `verify_chain` (línea 131) recorre ambas tablas en una sola llamada.

**Test real**: `backend/tests/unit/test_verify_chain.py` (`test_walks_both_chain_bearing_tables` línea 80, `test_mismatch_does_not_abort_the_walk` línea 154, `test_colliding_timestamp_evento_does_not_false_positive` línea 215); `backend/tests/unit/test_hash_chain.py` (`test_hash_chain_append_second_row_links_to_prior` línea 104, `test_out_of_order_payload_raises` línea 174).

### 4. Múltiples sesiones de sync cloud simultáneas

Defecto real confirmado en arranque de contenedor (2026-09-09, logs de `docker logs`): `SyncCloudWorker` guardaba una única `AsyncSession` compartida entre dos tareas `asyncio` concurrentes (el loop de aplicación y el verificador de cadena hash); SQLAlchemy rechaza el uso concurrente de una misma sesión ("concurrent operations are not permitted"), y el `try/except` de cada loop silenciaba el error — con el riesgo de que el verificador de cadena, "la capa defensiva más importante para el cumplimiento DIAN" según su propio docstring, se saltara un barrido completo sin que nadie lo notara. Corrección: `SyncCloudWorker` acepta un `session_factory` opcional; cada iteración de cada loop abre y confirma su **propia** sesión en vez de compartir `self._session`.

**Test real**: `backend/tests/integration/test_sync_cloud_concurrent_sessions.py::test_apply_and_verify_iterations_run_concurrently_without_session_conflict` (línea 57) — reproduce la carrera real con `asyncio.gather` sobre sesiones independientes contra el mismo contenedor Postgres, en varias rondas para maximizar la probabilidad de colisión en el mismo tick del event loop.

### 5. Numeración offline reconciliada al reconectar

Cada sucursal numera localmente dentro de su propio rango autorizado y disjunto (`resolucion_facturacion.rango_desde`/`rango_hasta`); la asignación es transaccional e idempotente por evento de origen (`repo/resolucion_facturacion.py::assign_consecutivo`), de forma que dos sucursales offline nunca pueden asignar el mismo número oficial — los rangos ya son disjuntos por construcción, no se reconcilian números a posteriori. Al reconectar, cada fila se empuja tal cual (mismo `uuid`, mismo `consecutivo`); en la nube, `dian/cloud/dispatcher.py::validate_consecutivo_range` (`backend/packages/parkos_core/src/parkos_core/dian/cloud/dispatcher.py:315`) valida que el `consecutivo` recibido caiga dentro del rango autorizado de su resolución antes de reenviarlo al proveedor DIAN, y emite `alerta tipo_alerta='fe_numbering_exhausted'` si no.

**Test real**: `backend/tests/integration/test_offline_numbering_reconciliation_on_reconnect.py::test_offline_numbering_reconciles_without_collision_on_reconnect` (línea 349) — extremo a extremo con dos Postgres reales (sucursal y nube): prueba con un fallo de socket real que la nube es inalcanzable, emite 3 facturas electrónicas offline, reconecta con un worker real contra una app FastAPI real, y verifica en la nube 0 colisiones, 0 huecos, y que cada fila es un INSERT nuevo de la misma identidad de origen — nunca una reescritura de un documento ya existente en el nodo central.

### 6. Reaplicación idempotente / evitar auto-duplicado al reprocesar un batch

`jobs/sync_cloud.py::_apply_pending_batch_once` (`backend/packages/parkos_core/src/parkos_core/jobs/sync_cloud.py:390`) incluye una guarda de auto-origen: para una entrada `[V]`, si el `uuid` de la fila ya existe localmente (`_row_already_applied`), la fila se marca `mark_dispatched` sin reaplicarse. Esto cierra un defecto real confirmado en Docker: una tabla `[V]` sin *hook* `IdentityReconciler` (p. ej. `impuestos`, a diferencia de `clientes`/`vehiculos`) terminaba con dos filas activas a partir de una única fila de `sync_queue`, porque el payload sin `uuid` fluía igual hacia un `close_and_insert` que generaba una fila nueva en vez de fallar. Además, la migración `0016_add_sync_apply_guard` junto con `sync.motor.apply_guard.enable_echo_suppression` evita que el propio trigger `AFTER INSERT` reencole un "eco" de la fila mientras este loop la está aplicando.

**Test real**: `backend/tests/integration/test_apply_pending_no_self_duplicate.py::test_apply_pending_batch_once_does_not_duplicate_self_originated_row` (línea 52).

---

## Ver también

- [`./modelo-datos.md`](./modelo-datos.md) — modelo de datos completo, ER y clases de auditoría (`[V]`/`[L-E]`/`[L-W]`/`[L-S]`/`[A]`).
- [`./seguridad.md`](./seguridad.md) — autenticación, autorización, pairing, revocación y roles de base de datos.
- [`../runbooks/sync/dependency_wait.md`](../runbooks/sync/dependency_wait.md), [`../runbooks/sync/orphan_workflow.md`](../runbooks/sync/orphan_workflow.md), [`../runbooks/sync/chain_break.md`](../runbooks/sync/chain_break.md), [`../runbooks/sync/conflict_rate.md`](../runbooks/sync/conflict_rate.md), [`../runbooks/sync/backfill_stalled.md`](../runbooks/sync/backfill_stalled.md) — procedimientos operativos para las alertas que estas mismas mitigaciones emiten.
- [`../04-qa-testing/plan-pruebas.md`](../04-qa-testing/plan-pruebas.md) — estrategia de pruebas completa (unitarias, integración, invariantes, AST/CI).
