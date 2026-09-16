# easypunto_parkos — Changelog

> No hay tags de versión publicados: `git tag` no devuelve resultados. Este
> changelog está **derivado del historial real de `git log`** (82 commits en
> total, `git rev-list --count HEAD`), agrupado por época/tema en lugar de
> por versión. Rango: 2026-08-30 (primer commit) → 2026-09-10 (hoy).
>
> **Convención observada**: Conventional Commits —
> `tipo(alcance): descripción` (`feat`, `fix`, `test`, `docs`, `chore`),
> muchos con referencia a un PR/issue de GitHub entre paréntesis (`(#N)`).
> Ningún commit de los 82 lleva `Co-Authored-By` ni atribución de IA, en
> línea con la regla explícita de `AGENTS.md` ("Conventional Commits (no
> Co-Authored-By / AI attribution)").

## Resumen por época

| Época | Rango de fechas | Tema | Commits |
|---|---|---|---|
| 1 | 2026-08-30 – 2026-09-02 | Bootstrap del repositorio | 2 |
| 2 | 2026-09-02 – 2026-09-04 | `create-49-table-apis`: esquema de 49→50 tablas, ORM, auth/JWT, sync workers, DIAN, primer frontend | 37 |
| 3 | 2026-09-04 | Estabilización previa al corte de sync | 4 |
| 4 | 2026-09-08 | Scaffold previo al nuevo motor de sync | 1 |
| 5 | 2026-09-08 – 2026-09-09 | `sync-overhaul`: motor de sincronización catalog-driven | 17 |
| 6 | 2026-09-09 – 2026-09-10 | Correcciones de integridad post-overhaul (rama actual, sin mergear a `dev`) | 21 |

## Época 1 — Bootstrap del repositorio

| Commit | Fecha | Descripción |
|---|---|---|
| `728d28c` | 2026-08-30 | First commit |
| `0d53e6f` | 2026-09-02 | chore: sincroniza la documentación al nuevo modelo SDD + ratificación de gitflow |

## Época 2 — `create-49-table-apis`: esquema, ORM, auth, sync, DIAN, primer frontend

Cambio grande (PR0 + PR1a/b/c + PR2-11, 9 fases) que entregó el esquema
completo (49 tablas iniciales, luego reconciliadas a 50), el ORM particionado
por nivel de auditoría, autenticación con JWT de tres emisores, el
despachador DIAN, los workers de sync y el primer bootstrap de `web_admin`.

| Commit | Fecha | Descripción |
|---|---|---|
| `01f6aa2` | 2026-09-02 | docs: agrega topología de despliegue, pairing, sync workers, despachador DIAN |
| `4ba7f5c` | 2026-09-03 | docs: agrega gate de coincidencia de esquema al 100% + orquestación por sub-agente y tarea |
| `886c614` | 2026-09-03 | docs: absorbe el bootstrap `0001_initial_schema.py` dentro de PR1 (`size:exception`) |
| `ab1c3c5` | 2026-09-03 | docs: reconcilia el drift de conteo de tablas 45→49 (#1) |
| `e6b729d` | 2026-09-03 | feat: migración inicial de esquema de 49 tablas (`size:exception`) (#2) |
| `e808153` | 2026-09-03 | feat: ORM + schemas + auth + JWT + routers de API (#3) |
| `a9f54bb` | 2026-09-03 | test: tests unitarios + de migración + AST + seed idempotente (#4) |
| `3989d3b` | 2026-09-03 | feat: infraestructura `[A]` + `idempotency_keys` (PR2 + fix de MRO de `Base`) (#5) |
| `5fd6856` | 2026-09-03 | feat: dominio de catálogos `[V]` (9 tablas, 11 commits por unidad de trabajo) (#6) |
| `0b034f1` | 2026-09-03 | feat: `empresa` + `sucursal` + configuración por sucursal (8 tablas `[V]`, frontera DIAN) (#7) |
| `1b1061e` | 2026-09-03 | feat: comercial + `ingreso` (5 `[V]` + 1 `[L-E]`) (#8) |
| `9706280` | 2026-09-03 | feat: operaciones + workflows + frontera DIAN (12 tablas, 22 tareas) (#9) |
| `bf4e239` | 2026-09-03 | feat: `caja` + `sesion` + idempotencia (4 tablas + 50.ª tabla `[A]`) (#10) |
| `fd6ad56` | 2026-09-03 | feat: agrega validador de `runtime/env` + 13 tests (#11) |
| `a152c63` | 2026-09-03 | feat: `jobs/runner.py` + `sync/transport.py` + 16 tests unitarios (#12) |
| `1450bdc` | 2026-09-03 | feat: vistas de admin (3 endpoints) + helper `apply_admin_scope` + 21 tests (#13) |
| `99da167` | 2026-09-03 | feat: módulo DIAN cloud (`ubl_serializer` + proveedor Factus + esqueleto de despachador) (#14) |
| `d96aabc` | 2026-09-03 | fix: exporta la API pública de `L_E` (`FacturaElectronica`, `Facturas`) |
| `4a26674` | 2026-09-03 | feat: máquina de estados del despachador DIAN + wiring de `cloud_router` (#15) |
| `6cb9f85` | 2026-09-03 | feat: suite de tests DIAN + bundle XSD + `.dockerignore` (#16) |
| `9dc48c9` | 2026-09-03 | fix: desbloqueo de cadena en migración 0003 — predicado `IMMUTABLE` + `version_num` ampliado (#17) |
| `894af33` | 2026-09-03 | fix: `cwd` del subproceso de alembic en `conftest.py` (un nivel arriba) (#18) |
| `4441e76` | 2026-09-03 | feat: PR8a — wiring de entorno + clock + ORM de `pairing_tokens`/`revoked_sync_jwts` + migración 0006 (#19) |
| `580831e` | 2026-09-03 | feat: PR8b — runtime de pairing (repos + endpoints admin + rate limiter + CLIs) (#20) |
| `ccc7ebc` | 2026-09-03 | feat: PR8c — cierre del transporte de sync (router + helpers + mount) — PR8 completo (#21) |
| `58fcda6` | 2026-09-03 | feat: PR2 retroactivos — schemas de `sync_infra` + tests de `sync_outbox`/whitelist (#22) |
| `8510dbd` | 2026-09-03 | test: PR1c retroactivos — escaneo openapi de no-delete + tests de tenancy (#23) |
| `0d6ac06` | 2026-09-03 | fix: PR11c — 5 bugs documentados (serializador UBL, cadena de hash, timeout del despachador, `fecha_retencion_hasta` en el ORM, vista `V_RESOLUCION_CONSECUTIVO`) (#25) |
| `755bc7b` | 2026-09-03 | feat: PR9a — helpers de sync (`conflict_resolver` + `jwt_manager`) + Dockerfiles cloud/sucursal (#26) |
| `8e0b74c` | 2026-09-03 | feat: PR9b — workers de sync (sucursal + cloud) + `auto_discovery` + docker-compose (#27) |
| `2c3fcb9` | 2026-09-03 | fix: PR9b post-merge — orden 207 + escalares de tenant (#28) |
| `d9f93b3` | 2026-09-03 | feat: PR9c — verificación Docker + cierre de riesgos #20-22 y #24 — PR9 completo (#29) |
| `a77dd24` | 2026-09-04 | test: PR10a — verificación de admin revoke-sync + tests de `me`/dashboard/tenancy (#30) |
| `f7738e9` | 2026-09-04 | feat: PR10b — bootstrap de la PWA de `web_admin` (Vite + React 18 + shadcn + Tailwind + PWA) (#31) |
| `3a8fb02` | 2026-09-04 | feat: PR10c — UI de `BranchSelector` + Playwright — PR10 completo (#32) |
| `b397c5e` | 2026-09-04 | fix: cierra 3 brechas conocidas — mocks de test + JWT 401 + limpieza de trailer + CI de `web_admin` (#33) |
| `4cea0b0` | 2026-09-04 | fix: `test_admin_me` + `test_dashboard_aggregation` (contaminación de módulos) + reset de cache del motor de idempotencia (#34) |

## Época 3 — Estabilización previa al corte de sync

| Commit | Fecha | Descripción |
|---|---|---|
| `d4efa40` | 2026-09-04 | fix(tests): restaura `__dict__` del paquete padre en fixtures de contaminación de módulos (#35) |
| `74bd0f2` | 2026-09-04 | fix(deploy): `app_factory.create_app` + alias `SessionLocal` + `DATABASE_URL` + `uv` 0.11.32 + volumen de secretos (#36) |
| `ef4ce9c` | 2026-09-04 | fix(branch-sync): detección de prefijo de emisor JWT + script de pairing de bootstrap + compose local combinado (#37) |
| `c275bef` | 2026-09-04 | fix(auth): incluye el emisor completo en el mensaje de `CrossIssuerError` (compatibilidad de tests) (#38) |

## Época 4 — Scaffold previo al nuevo motor de sync

| Commit | Fecha | Descripción |
|---|---|---|
| `9f8f20b` | 2026-09-08 | Limpieza del árbol de trabajo y scaffold previo a `sync-overhaul`: descarta `table_registry.py` legado, agrega pruebas/cobertura, parser de `PARKOS_SYNC_ENGINE`, guard de rol y verificación de carve-out de `sync_queue` (#39) |

## Época 5 — `sync-overhaul`: motor de sincronización catalog-driven

Cambio SDD completo (PR2-PR14), archivado en
`openspec/changes/archive/2026-09-09-sync-overhaul/`. Reemplaza el motor de
sync original por uno genérico, dirigido por un catálogo declarativo.

| Commit | Fecha | Descripción |
|---|---|---|
| `8e6b855` | 2026-09-08 | feat: catálogo declarativo de sincronización (PR2) (#40) |
| `7e0913e` | 2026-09-08 | feat: grafo de dependencias y `DependencyOrderer` (PR3), corrige 3 `depends_on` desalineados del ER (#41) |
| `2bef349` | 2026-09-08 | feat: esqueleto de `SyncMotor` y ciclo de vida de hooks (PR4) (#42) |
| `7058e17` | 2026-09-09 | feat: hooks de identidad, suscripción, cascada de placa y compensación bi-temporal (PR5) (#43) |
| `b0ff5e0` | 2026-09-09 | feat: hooks de cadena de hash y `verify_chain` (PR6), bootstrap real de la fila génesis (#44) |
| `e98cc37` | 2026-09-09 | feat: materializa `read_local_seq` y `resolve_conflict` (PR7), convierte `ConflictResolver` en shim (#45) |
| `df5b742` | 2026-09-09 | feat: buffer de dependencias y `alert_types` con escalamiento único (PR8) (#46) |
| `3266301` | 2026-09-09 | feat: numeración DIAN local en sucursal, `envio_dian` y backoff dedicado (PR9) (#47) |
| `29c4b14` | 2026-09-09 | feat: triggers de catálogo en 18 tablas `[V]`, actualiza el canon ER a 51/54 (PR10) (#48) |
| `0e4a989` | 2026-09-09 | feat: corte del worker cloud al motor catalog-driven, agrega `/sync/hello` y protocolo dual (PR11) (#49) |
| `66dcb36` | 2026-09-09 | feat: corte del worker de sucursal al motor catalog-driven y backfill topológico (PR12) (#50) |
| `abdc5cd` | 2026-09-09 | feat: métricas, logs estructurados, redacción de PII en el sink y alertas Grafana (PR13) (#51) |
| `73492e4` | 2026-09-09 | feat: evaluador de stage-gates y script de reversión idempotente (PR14, cierre de la cadena) (#52) |
| `5ee5bca` | 2026-09-09 | fix: ejercicio E2E de las 46 tablas de catálogo, corrige 6 bugs reales de sincronización y un flake de JWT (#53) |
| `971ec21` | 2026-09-09 | chore: agrega `PARKOS_SYNC_ENGINE` al compose local combinado (cloud + sucursal) |
| `5b41fdf` | 2026-09-09 | fix: corrige 3 bugs críticos confirmados en despliegue real de Docker (workers sin commit, orden de dependencias en `/sync/events`, eco de trigger duplicando la cadena de hash) (#54) |
| `d89a41a` | 2026-09-09 | chore: archiva el change y fusiona sus specs al canon del proyecto, corrige el guard R21 tras el archivado (#55) |

## Época 6 — Correcciones de integridad post-overhaul (rama actual)

Rama `feature/motor_sync_correcciones_integridad` — **todavía no mergeada a
`dev`** al momento de este documento. Serie de correcciones sobre el motor
de sync recién reescrito, encontradas en pruebas de integración y en
despliegue real con Docker.

| Commit | Fecha | Descripción |
|---|---|---|
| `ba5065e` | 2026-09-09 | fix: ordena la cadena de hash por `created_at` en vez de `timestamp_evento`, evita bifurcaciones falsas |
| `998e15e` | 2026-09-09 | fix: parsea `timestamp_evento` como ISO-8601 en vez de fallar al restar contra un string |
| `eff15fa` | 2026-09-09 | fix: evita reaplicar una fila cuyo uuid ya existe en destino |
| `9b379cf` | 2026-09-09 | feat: implementa `/sync/pull` real y genérico por JWT de la sucursal (deja de ser stub) |
| `dd500c2` | 2026-09-09 | fix: corrige el binding del body JSON en `create`/`update`, roto por PEP 563 en `router_factory` |
| `234f379` | 2026-09-09 | fix: agrega partición `DEFAULT` a `pairing_tokens` y `revoked_sync_jwts`, retira los `xfail` que tapaban el gap |
| `6c7947c` | 2026-09-09 | fix: usa el permiso canónico `gestionar_clientes` en vez de códigos nunca sembrados que bloqueaban todo el módulo |
| `db413f5` | 2026-09-09 | fix: `SyncMotor.apply_row` ahora resuelve `open_version`; `identity_reconciler` nunca reconciliaba en producción |
| `e8106bf` | 2026-09-09 | fix: UUIDs determinísticos para los 16 permisos canónicos, antes divergían entre cloud y sucursal |
| `91bbb5e` | 2026-09-09 | feat: extiende la reconciliación de identidad a las 20 tablas de catálogo restantes con clave natural real |
| `d5afd8f` | 2026-09-09 | fix: `SyncCloudWorker` abre una sesión propia por iteración, corrige una carrera real confirmada en Docker |
| `57024bd` | 2026-09-09 | test: confirma la reconciliación de numeración offline y la inmutabilidad de columnas snapshot |
| `32cf320` | 2026-09-09 | fix: `close_and_insert` conserva las columnas no enviadas en un PUT parcial |
| `ed4991a` | 2026-09-09 | fix: `record_event` hace flush antes de leer el uuid para el `log_transaccional` |
| `d901a43` | 2026-09-09 | fix: envuelve el estado del heartbeat en `{"state": ...}`, el endpoint lo rechazaba con 422 |
| `752a6a3` | 2026-09-10 | fix: UUIDs determinísticos para `tipo_persona` y `empresa`, mismo defecto que en `234f379` |
| `a6f550e` | 2026-09-10 | test: aísla fixtures compartidas para evitar colisiones al correr la suite completa |
| `bab394b` | 2026-09-10 | test: acota el conteo de `sync_conflict` a la fila propia del test |
| `5a93cea` | 2026-09-10 | test: acota por `known_uuids` el `fetch_page` duplicado de `offline_numbering` |
| `59d7cc0` | 2026-09-10 | test: deja de crear `tipo_persona="natural"` literal en 6 tests que comparten `pg_engine` |
| `5edb317` | 2026-09-10 | fix(db): la app deja de conectarse como superusuario, ahora usa un rol de mínimo privilegio real |

## Fuera de este historial

Al momento de este documento hay 4 scripts sin commitear en el árbol de
trabajo (`backend/scripts/insert_null_genesis.py`,
`backend/scripts/replicate_catalogs_to_branch.py`,
`backend/scripts/verify_branch_catalogs.py`,
`infra/scripts/seed_catalogs.py`) — no forman parte de este changelog porque
`git log` no los incluye; quedan como trabajo en curso no versionado.
