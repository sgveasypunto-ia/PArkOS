# Plan de pruebas — motor de sincronización

> Alcance de este documento: estrategia real de testing del backend (`backend/`) y del panel administrativo (`apps/web_admin/`) de easypunto_parkos, con énfasis en el motor de sincronización sucursal↔nube (`parkos_core.sync`). Todas las cifras y comportamientos aquí descritos fueron verificados leyendo los archivos reales del repositorio (config de pytest, `conftest.py`, workflow de CI y los propios módulos de prueba) — no incluye casos ni números de ejemplo.

## 1. Alcance

El backend es un monorepo Python (uv workspace, `backend/packages/*`) con dos APIs FastAPI (`api_admin`, `api_sucursal`) sobre PostgreSQL 16. El frontend es una PWA React (`apps/web_admin`). La suite de backend está deliberadamente organizada en **cinco** carpetas bajo `backend/tests/`, no solo las tres capas clásicas de una pirámide (unit/integration/e2e): a las dos capas funcionales se suman `static/` (reglas arquitectónicas ejecutadas como pruebas) y `migrations/` (verificación de DDL), más `bench/` para pruebas de carga.

## 2. Pirámide de pruebas

### 2.1 Backend (pytest)

Conteo real por carpeta (`git ls-files 'backend/tests/<carpeta>/*.py'`):

| Carpeta | Archivos `.py` | Naturaleza |
|---|---:|---|
| `tests/unit/` | 98 | Lógica de un módulo/función, con o sin Postgres real |
| `tests/integration/` | 30 | Flujos multi-componente, API real + Postgres real (a veces 2 contenedores) |
| `tests/static/` | 19 | Reglas arquitectónicas verificadas por AST/OpenAPI, no lógica de negocio |
| `tests/migrations/` | 25 | DDL: triggers, particiones, REVOKE, contra Postgres real post-`alembic upgrade head` |
| `tests/bench/` | 1 | Carga/latencia bajo concurrencia simulada |
| **Total backend** | **173** | |

Notas de precisión sobre el conteo de `unit/` (98): incluye su propio `__init__.py`, un archivo de fixture de datos que no es en sí una prueba (`fixtures/cyclic_dependency_graph_fixture.py`, usado por `test_dependency_graph.py`), y el subpaquete `unit/dian/` completo (7 archivos: `__init__.py`, `conftest.py` y 5 módulos `test_*.py` de despacho DIAN — `test_dispatcher.py`, `test_dispatcher_boundary.py`, `test_dispatcher_hash_chain_branch_not_cloud.py`, `test_factus_provider.py`, `test_ubl_serializer.py`). Igualmente, `static/` y `migrations/` incluyen cada una su propio `__init__.py` y `conftest.py` dentro del conteo de 19 y 25 respectivamente. Ningún conteo presentó discrepancia contra lo reportado antes de esta verificación (ver §9).

La pirámide real, de base a punta, es: **unitarias (98)** → **integración (30)** → **migraciones (25)** → **estáticas (19)** → **carga (1)**. Las capas de `static/` y `migrations/` no compiten por volumen con unit/integration, pero son gate obligatorio en CI (ver §4) porque protegen invariantes que ningún test de negocio cubre (contrato append-only, ausencia de rutas DELETE, forma exacta del esquema).

### 2.2 Frontend (Vitest + Playwright)

Tres archivos, confirmados por `git ls-files`:

- `apps/web_admin/src/App.test.tsx` (Vitest + Testing Library) — 3 pruebas de enrutamiento a nivel de componente: redirección de `/` a `/dashboard` con el encabezado correcto, render de `/login` y render de `/dashboard` (por `data-testid`).
- `apps/web_admin/e2e/branch-selector.spec.ts` (Playwright, T-PR10-13) — 3 pruebas E2E contra un backend mockeado por interceptación de rutas: el selector muestra las sucursales permitidas del token, el cambio de sucursal reenvía `X-Sucursal-Context` en el siguiente fetch del dashboard, y la sucursal elegida persiste en `localStorage` tras recargar.
- `apps/web_admin/e2e/smoke.spec.ts` (Playwright) — smoke test de arranque de la PWA (redirección raíz + marca visible) y un gate de accesibilidad WCAG 2.1 AA con `@axe-core/playwright` contra `/dashboard` (RNF-022), más render de `/login`.

No hay pirámide unitaria amplia en frontend hoy: la cobertura de componente es mínima (un solo archivo) y el grueso de la verificación de UI vive en los 2 specs E2E de Playwright.

## 3. Qué verifica cada categoría

### 3.1 Unitarias (`tests/unit/`)

"Unitaria" aquí no equivale a "sin base de datos": varias pruebas unitarias (p. ej. `test_hash_chain.py::test_hash_chain_append_first_row_uses_genesis`) usan la fixture `pg_engine` contra Postgres real porque el comportamiento que verifican (encadenamiento de hash) no es reproducible de forma significativa con un mock. Lo que define esta capa es que ejercita un módulo o función acotada, no un flujo HTTP completo. Ejemplos reales:

- `test_catalog_counts.py` — invariantes de composición del catálogo de sincronización (46+3+5=54 tablas clasificadas, desglose exacto por clase de auditoría).
- `test_dependency_graph.py` — que las dependencias declaradas coincidan con las FK obligatorias del modelo entidad-relación, y que un ciclo se detecte en tiempo de importación.
- `test_conflict_resolver.py` / `test_resolve_conflict.py` — el punto de entrada y la política de resolución de conflictos por clase de auditoría (ver §6).
- `test_dian_backoff.py` — que la curva de reintentos DIAN esté declarada una sola vez e importada (nunca redeclarada) en catálogo y despachador.
- `unit/dian/` — el despachador DIAN (`test_dispatcher.py`, `test_dispatcher_boundary.py`, etc.) contra un `httpx.MockTransport` que simula la API real de Factus, sin base de datos.

### 3.2 Integración (`tests/integration/`)

Ejercita flujos multi-componente: motor de sincronización + Postgres real +, en varios casos, una app FastAPI real montada vía `httpx.ASGITransport` (sin socket real) o incluso **dos contenedores Postgres independientes** simulando sucursal y nube a la vez (`test_offline_numbering_reconciliation_on_reconnect.py`, `test_e2e_full_catalog_sync.py`). Es la capa que prueba las condiciones de carrera del motor (§6) y los flujos de negocio de punta a punta: emparejamiento de sucursal (`test_pairing_flow.py`), reversa de pagos (`test_reverse_dry_run.py`), backfill topológico de catálogo, etc.

### 3.3 Estáticas (`tests/static/`)

No son pruebas de comportamiento de negocio: son escáneres AST u OpenAPI que hacen cumplir invariantes arquitectónicas en tiempo de CI en vez de depender solo de revisión de código. Ejemplos reales:

- `test_no_raw_dml_on_a_tables.py` — camina el AST de `parkos_core/api/` y `parkos_core/repo/` buscando `session.execute(insert/update/delete(...))` contra clases ORM `[A]` (append-only) fuera de los helpers permitidos (`repo/append_only.py`, `repo/sync_outbox.py`, `repo/versioned.py::close_and_insert`); hay pares equivalentes para tablas `[L-E]`, `[L-S]`, `[L-W]` y `[V]` (`test_no_raw_dml_on_le_tables.py`, etc., y `test_no_raw_upsert_on_v_tables.py`).
- `test_no_delete_routes.py` — además del escaneo AST de rutas `DELETE`, instancia las dos apps FastAPI reales y verifica en el esquema OpenAPI generado en runtime que no exponen ninguna operación `delete` — cubre también el registro dinámico de rutas que un escáner estático podría no ver.
- `test_check_catalog_drift.py`, `test_check_drain_green.py`, `test_check_sync_queue_carveout_green.py` — reutilizan directamente los scripts de guardia que también corren como steps propios de CI (ver §4).

### 3.4 Migraciones (`tests/migrations/`)

Verifican el DDL en sí — triggers, particiones `pg_partman`, `REVOKE` de privilegios — contra una instancia Postgres real después de `alembic upgrade head`, no el ORM ni la capa de servicio. Ejemplo: `test_partman_parents.py` verifica que las 8 tablas `[A]` de alto volumen (`salidas`, `caja`, `arqueo`, `factura_detalle`, `factura_pagos`, `log_transaccional`, `sync_queue`, `sync_log`) estén registradas como padres de partición mensual en `partman.part_config`. **Nota de cobertura real**: sus 3 funciones de prueba están marcadas `xfail(strict=True)` hoy por un defecto de migración documentado y fuera de alcance de este cambio (la migración `0001` registra `parent_table` con un prefijo `parkos.` espurio que rompe el filtro de partman) — es decir, la invariante está *escrita* pero no *pasa* como gate verde; queda como deuda de migración conocida (ver §7).

### 3.5 Rendimiento / carga (`tests/bench/`)

Un único archivo, `test_read_local_seq_load.py`: siembra ~10.010 filas (26 tablas `[V]` × 385) y ejecuta 1.000 lecturas concurrentes (concurrencia acotada a 60) sobre la caché `ReadLocalSeq`, exigiendo p95 ≤ 5 ms y tasa de aciertos ≥ 95 % bajo un patrón de "ráfaga sobre un conjunto caliente" (no una muestra uniforme, que haría el objetivo matemáticamente inalcanzable — documentado explícitamente en el docstring del archivo). El propio archivo documenta que el umbral de latencia se mide, no se relaja, y puede verse afectado por ruido de una máquina de desarrollo compartida frente a un runner de CI dedicado.

### 3.6 Frontend

Ver §2.2 — componente (Vitest) para enrutamiento, E2E (Playwright) para comportamiento funcional contra backend mockeado y accesibilidad (axe-core, WCAG 2.1 AA).

## 4. Política de cobertura

`backend/pyproject.toml` fija, en `[tool.pytest.ini_options].addopts`:

```
addopts = ["-q", "--tb=short", "--cov=parkos_core.sync", "--cov-report=term-missing"]
```

La instrumentación de cobertura local está **acotada a `parkos_core.sync`** — el paquete que es el entregable de este cambio (REQ-OPS-002 / T-PR1-005), no todo el backend.

**El gate `--cov-fail-under=80` vive únicamente en `.github/workflows/ci.yml`, deliberadamente ausente de `addopts`.** La razón está documentada en el propio comentario de `pyproject.toml` y es una desviación consciente de la especificación literal de T-PR1-005 (que sí pedía el umbral en `addopts`): un umbral global ahí rompería cualquier comando de prueba *acotado* de los que la propia tabla "Suggested Work Units" de `tasks.md` designa (p. ej. `uv run pytest tests/unit/test_engine_flag.py tests/integration/test_role_guard.py -q`), porque una invocación angosta casi nunca toca la mayoría de `parkos_core.sync`. El propio archivo cita la evidencia reproducida durante el apply de PR1:

> "19/19 tests green, exit code non-zero solely from `--cov-fail-under=80` against a 3.66% slice."

En consecuencia, el 80 % se exige donde sí tiene sentido medirlo: el step **"Tests + coverage"** de `ci.yml`, que corre la suite completa sin acotar rutas:

```
uv run pytest --cov --cov-report=xml --cov-fail-under=80
```

El comentario de `ci.yml` referencia explícitamente de vuelta el razonamiento de `pyproject.toml` ("a global threshold there would fail every *focused* PR-scoped test command... See the addopts comment for the reproduced evidence"), es decir, ambos archivos se citan mutuamente por diseño.

Ese step de tests es el quinto de seis en el job `test` de CI, en este orden fijo (sin `continue-on-error`, cualquier fallo detiene el job): `uv sync --frozen` → guardia de carve-out de `sync_queue` → guardia de drift de catálogo → `ruff check` → `mypy` → **tests + cobertura** → escaneo Trivy (solo en push a `dev`).

Herramientas de testing declaradas en `[dependency-groups].dev`: `pytest>=8`, `pytest-asyncio>=0.24`, `pytest-cov>=5`, `httpx>=0.27` (cliente ASGI para los tests de API), `factory-boy>=3`, `testcontainers[postgres]>=4`, `faker[es-co]>=40.38.0` (generación de datos sintéticos — RNF-029 prohíbe PII real en fixtures), `pyyaml>=6` (declarado explícitamente porque `test_grafana_alerts.py` parsea `infra/grafana/alerts/sync.yaml`, no solo por dependencia transitiva).

## 5. Fixtures compartidas

`backend/tests/conftest.py` (raíz) es la fuente de las fixtures compartidas por toda la suite. Confirmado leyendo el archivo:

- **`pg_engine` es `session`-scoped** (`@pytest_asyncio.fixture(scope="session") async def pg_engine(...)`): un único engine SQLAlchemy async por sesión de pytest completa, no por test ni por módulo. De ahí que `pyproject.toml` fije también `asyncio_default_fixture_loop_scope = "session"` y `asyncio_default_test_loop_scope = "session"` — sin ese pineo, cada test recibiría su propio event loop mientras las conexiones asyncpg de la fixture de sesión quedan atadas al primero, produciendo `Task ... attached to a different loop` en cuanto corre un segundo test que toca DB.
- `postgres_container` (`session`) — contenedor testcontainers `postgres:16-alpine` por defecto, sustituible vía `TEST_PG_IMAGE` por la imagen propia `parkos-postgres:16-pgpartman` cuando se necesita `pg_partman` real.
- `alembic_upgrade` (`session`) — corre `alembic upgrade head` una vez por sesión vía subproceso; si falla (típicamente porque `postgres:16-alpine` no trae `pg_partman`) hace **skip**, no fail, de toda la sesión de fixtures dependientes, para no inundar de `UndefinedTable` los tests que sí dependen de DB.
- `_bootstrap_global_hash_chain_genesis` (`session`, `autouse=True`) — siembra la fila génesis global (`uuid_sucursal IS NULL`) de la cadena de hash antes de que corra cualquier test, replicando el bootstrap perezoso real de producción, para que pruebas de migración que aseveran la cadena directamente no dependan del orden de recolección de otros archivos.
- `pg_session` (`function`) — una sesión por test que hace **rollback** al final (no trunca tablas), a propósito: varios tests de migración escriben en tablas `[A]` para comprobar que la mutación posterior es rechazada, y un truncate destruiría esa evidencia.
- `make_spec` (`function`, T-PR4-010) — helper fluido que toma una entrada real de `SYNC_CATALOG`/`LOCAL_ONLY_CATALOG` por nombre y devuelve una copia con hooks sobreescritos (p. ej. `hook_validate_parent`), evitando tener que implementar los ~46 hooks reales solo para forzar una rama de prueba. Es el mecanismo que hace posible casi toda la sección de concurrencia (§6).
- `VFixtureFactory` / `v_fixture_factory` — un único builder genérico de filas `[V]` (no 26 factorías `factory-boy` casi idénticas), porque las 26 tablas `[V]` comparten el mismo mixin `VersionedBase`.
- `seeded_sucursal_uuid` / `seeded_usuario_uuid` (`function`) — insertan una fila real padre para que los tests con FK real (`fk_sync_queue_uuid_sucursal`, etc.) no dependan de un `uuid4()` sin respaldo.
- `table_set_a` (11 tablas: `salidas`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `revocacion_factura`, `caja`, `arqueo`, `sync_log`, `sync_conflict`, `log_transaccional` — `sync_queue` queda fuera por el carve-out de columnas mutables del diseño §12) y `table_set_ls` (2: `login`, `sesion`).
- Minters de JWT (`mint_admin_jwt`, `mint_operador_jwt`, `mint_sync_agent_jwt`) y `client` (httpx `AsyncClient` sobre transporte ASGI, parametrizable a la app `admin` o `sucursal`).
- Un workaround documentado para Windows al inicio del archivo: fuerza `WindowsSelectorEventLoopPolicy` porque `psycopg` v3 no puede usar `ProactorEventLoop` para async — relevante porque el entorno de desarrollo de este equipo es Windows.
- `os.environ.setdefault("PARKOS_DEPLOY", "branch")` a nivel de conftest raíz: cierra una condición de orden de import real (no de runtime) — si un módulo en un directorio recolectado alfabéticamente antes que `tests/static/` importa `parkos_core.api.v1` sin este default, el router DIAN de nube queda montado en caché para el resto de la sesión y rompe `test_openapi_branch_excludes_cloud`.

**Conftests de directorio que extienden (nunca contradicen) el raíz:**

- `tests/static/conftest.py` — fuerza `PARKOS_DEPLOY=branch` para todo `static/`, porque sus pruebas validan el límite de despliegue sucursal/nube.
- `tests/unit/dian/conftest.py` — a la inversa, fuerza `PARKOS_DEPLOY=cloud` solo durante la ventana de import del despachador (y la restaura después), y centraliza los dobles de prueba (`token_path`, `factura_row`, `mock_session_with_factura`, helpers de transporte de rechazo y de sleep) que reutiliza toda la suite de `unit/dian/`.
- `tests/migrations/conftest.py` — una fixture `autouse` que exige explícitamente `alembic_upgrade`, convirtiendo en dependencia local y explícita lo que antes era un accidente de orden de recolección entre archivos.

## 6. Concurrencia y condiciones de carrera

El motor de sincronización tiene condiciones de carrera reales como parte de su dominio (filas hijas que llegan antes que el padre, dos sesiones de sync corriendo a la vez, escrituras concurrentes sobre la misma fila versionada, numeración offline que debe reconciliar sin colisión). Esta sección documenta la cobertura real — **dos de las pruebas listadas son regresiones de incidentes reales confirmados en una verificación reciente en contenedor Docker**, y una tercera (`test_verify_chain.py`) documenta otro incidente real ya corregido; no son escenarios hipotéticos.

1. **`tests/integration/test_parent_missing_buffer_drain.py`** — una fila hija (`factura_detalle`) llega antes que su padre declarado (`facturas`). Verifica que `apply_row` devuelva `RETRY/parent_missing`, que la fila se almacene en el buffer de dependencias (`sync_queue_lw_buffer`, `estado='pendiente'`) mientras el **emisor** se marca como entregado (`estado='exitoso'`, `intentos` sin cambio) — una espera de dependencia no es, por diseño (decisión D18), una falla de transporte — y que al llegar el padre, `drain_dependency_buffer` aplique exactamente esa fila y la deje `estado='aplicado'`.

2. **`tests/integration/test_buffer_ttl_escalation.py`** — el lado de expiración de la misma carrera: una fila bufferizada cuyo TTL ya venció (`ttl_hours=-1`) es barrida por `_lw_buffer_sweep`, que debe emitir **exactamente una** alerta `tipo_alerta='orphan_workflow_chain'`, cero reencolados en `sync_queue` (de nuevo por D18: un timeout de dependencia no es falla de transporte) y dejar la fila `estado='fallido'` / `ultimo_error='parent_missing_timeout'` **sin borrarla nunca** (contrato append-only). Una segunda prueba en el mismo archivo confirma que una fila aún dentro del TTL queda intacta tras el barrido.

3. **`tests/unit/test_conflict_resolver.py`** — el punto de entrada (shim) de resolución de conflictos: entradas malformadas → `ERROR`; tabla fuera de catálogo → `APPLIED` incondicional; `[A]`/`[L-E]`/`[L-W]` → `APPLIED` (sin hook de validación de padre implementado aún); `[L-S]` → `APPLIED` dentro de una ventana de gracia de 24 h, `CONFLICT_LS` fuera de ella; `[V]` sin llave natural (`documentos`) → `APPLIED` en primera escritura, `CONFLICT_V` cuando la secuencia remota no es estrictamente más nueva que la local (conflicto de escritura concurrente real); también verifica que una falla de DB durante la resolución devuelva `ERROR` (el llamador reintenta) en vez de propagar la excepción.

4. **`tests/unit/test_resolve_conflict.py`** — la política de despacho por clase de auditoría en la que delega el shim anterior. Para `[V]` sin llave natural, una escritura remota con secuencia igual o sin campo comparable resuelve `MANUAL/seq_tiebreak` y escribe una fila real en `sync_conflict`. La prueba más notable del archivo, `test_ls_applies_when_timestamp_evento_is_wire_string`, es una **regresión de un defecto real de producción**: el resolutor de sesión (`[L-S]`) debía aceptar la marca de tiempo tanto si llega como objeto `datetime` como si llega en formato de red real (cadena ISO-8601) — antes fallaba con `TypeError: unsupported operand type(s) for -: 'datetime.datetime' and 'str'` en un despliegue Docker real pese a que toda la suite estaba en verde, porque ningún otro test del archivo ejercitaba jamás el formato de cadena.

5. **`tests/unit/test_verify_chain.py`** — prueba que el **caminador** de verificación de cadena (no solo el trigger de base de datos) detecte una rotura por sí mismo: escribe una cadena correcta, deshabilita el trigger (`session_replication_role = replica`) para insertar una fila con `hash_anterior` deliberadamente incorrecto, y confirma que `verify_chain` reporta exactamente una anomalía, no aborta el recorrido (una fila correctamente encadenada *después* de la rota se acepta igual) y no contamina la otra tabla con cadena (`revocacion_factura`). Su prueba `test_colliding_timestamp_evento_does_not_false_positive` es la **regresión de un incidente real**: eventos concurrentes con la misma `timestamp_evento` de negocio hacían que el desempate `ORDER BY ... uuid DESC` eligiera el predecesor incorrecto y bifurcara la cadena — confirmado como un `hash_chain_break` falso positivo real en producción; la prueba reproduce el escenario con UUIDs fijados deliberadamente no-monótonos para forzar el caso determinísticamente, y confirma que el orden real de inserción (`created_at`, no la marca de negocio) evita el falso positivo.

6. **`tests/unit/test_hash_chain.py`** — la primitiva de encadenamiento SHA-256: determinismo del JSON canónico, ancla génesis por sucursal, y que cada fila enlace con el `hash_actual` de la inmediatamente anterior (contra Postgres real). Documenta además, vía `pytest.skip` explícito en `test_out_of_order_payload_raises`, una **condición de carrera hoy sin corregir**: dos escritores concurrentes cuya segunda escritura llega con una `timestamp_evento` anterior a la primera pueden bifurcar la cadena en silencio, porque `append` ordena por `timestamp_evento DESC` sin validar monotonicidad — backlog explícito para PR10+, no una garantía vigente.

7. **`tests/integration/test_sync_cloud_concurrent_sessions.py`** — **regresión de un defecto real** confirmado en logs de Docker en una verificación reciente (`This session is provisioning a new connection; concurrent operations are not permitted`). Causa raíz real: `SyncCloudWorker` compartía una única `AsyncSession` entre dos tareas `asyncio` concurrentes (aplicar pendientes y verificar cadena de hash), y `AsyncSession` de SQLAlchemy no admite uso concurrente entre corrutinas. La prueba corre una iteración de cada tarea genuinamente en paralelo (`asyncio.gather`) contra el mismo Postgres real, en 3 rondas, y confirma que ninguna lanza excepción tras el fix (sesión propia por iteración vía `session_factory`).

8. **`tests/integration/test_offline_numbering_reconciliation_on_reconnect.py`** — con la nube probadamente inalcanzable (intento de conexión real rechazado), numera 3 facturas electrónicas localmente en la sucursal (secuencial, sin huecos: `[1,2,3]`); al "reconectar", un `SyncSucursalWorker` real empuja lo pendiente a través de una app FastAPI real hacia un **segundo contenedor Postgres físicamente independiente** que hace de nube, y confirma que las 3 facturas llegan con su consecutivo y `uuid` originales exactos — sin colisión, sin hueco y sin reescritura del documento (inserción nueva de la misma identidad, nunca un update).

9. **`tests/integration/test_apply_pending_no_self_duplicate.py`** — **regresión de un defecto real** detectado en una sesión de QA e2e reciente: otorgar un permiso vía la capa de servicio real producía dos filas activas por una sola fila en `sync_queue`, porque `SyncCloudWorker._apply_pending_batch_once` reaplicaba en silencio su propia fila recién encolada (todo INSERT en tabla `[V]` dispara el trigger de encolado, incluso para escrituras ya "cloud-authored"). La prueba crea una fila real de `impuestos` por la vía de servicio, confirma que el trigger encoló una sola vez, corre el batch de aplicación y verifica que queda **una sola** fila activa (no dos) y que la cola sí liquida como `exitoso`.

**Runbooks operativos relacionados** (ya existentes en `../runbooks/sync/`, no modificados por esta tarea): [`chain_break.md`](../runbooks/sync/chain_break.md) para el punto 5-6, [`conflict_rate.md`](../runbooks/sync/conflict_rate.md) para los puntos 3-4, [`dependency_wait.md`](../runbooks/sync/dependency_wait.md) para el punto 1 y [`orphan_workflow.md`](../runbooks/sync/orphan_workflow.md) para el punto 2 (su alerta `orphan_workflow_chain` es literalmente la que dispara `test_buffer_ttl_escalation.py`).

## 7. Brechas de cobertura documentadas

La suite es explícita sobre lo que **no** garantiza hoy, en vez de ocultarlo — vale la pena listarlo como deuda conocida en vez de asumir cobertura total:

- **`test_hash_chain.py::test_out_of_order_payload_raises`** — `pytest.skip` explícito: no hay detección de escrituras fuera de orden en `repo/hash_chain.py::append`; backlog PR10+ (ver §6.6).
- **`test_partman_parents.py`** (las 3 funciones) — `xfail(strict=True)` por un defecto de migración conocido (prefijo `parkos.` espurio en `parent_table`), fuera de alcance de este cambio.
- **`tests/integration/test_pairing_flow.py`** — de sus 9 escenarios documentados en el docstring del archivo, varios (`test_pair_happy_path`, `test_pair_token_reuse_rejected`, `test_pair_token_expired_rejected`, `test_pair_token_revoked_rejected`, `test_pair_wrong_sucursal_rejected`) están marcados `xfail(strict=True)` por un gap preexistente de partición de `pairing_tokens` en `partman`; otros dos (`test_pair_env_validator_fails_fast`, `test_pair_persisted_jwt_path_0600`) por un bug preexistente de auth/pairing, ambos documentados como fuera de alcance de este cambio y pendientes de investigación dedicada. `test_pair_revoked_jwt_rejects_subsequent_calls` está `xfail(strict=False)` a la espera de que `sync_router` quede cableado.

## 8. Cómo ejecutar

Suite completa con cobertura de `parkos_core.sync` (equivalente a lo que corre localmente vía `addopts`):

```
cd backend && uv run pytest
```

Suite completa con el gate de cobertura del 80 % (lo que corre en CI, `.github/workflows/ci.yml`):

```
cd backend && uv run pytest --cov --cov-report=xml --cov-fail-under=80
```

Invocación acotada a un work unit (ejemplo real citado en el propio comentario de `pyproject.toml`, por eso el 80 % no vive en `addopts`):

```
uv run pytest tests/unit/test_engine_flag.py tests/integration/test_role_guard.py -q
```

## 9. Reconciliación de cifras

Todas las cifras de este documento fueron reconfirmadas con `git ls-files` sobre el estado real del repositorio en esta sesión. No se encontró ninguna discrepancia contra las cifras de partida: unit=98 (7 de ellos en `unit/dian/`), integration=30, static=19, migrations=25, bench=1, total backend=173; frontend=3 archivos. Ver `../04-qa-testing/casos-prueba.md` para el detalle caso por caso de una muestra representativa de esta suite.

## Referencias

- [`casos-prueba.md`](./casos-prueba.md) — catálogo de casos de prueba reales documentados individualmente.
- [`../02-arquitectura/decisiones-tecnicas.md`](../02-arquitectura/decisiones-tecnicas.md) — decisiones de diseño citadas por los tests (D17, D18, ADR-002, ADR-003) [pendiente de publicación al momento de escribir este documento].
- [`../runbooks/sync/`](../runbooks/sync/) — runbooks operativos de las alertas que estas pruebas ejercitan.
