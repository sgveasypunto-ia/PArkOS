# PRD: sucursal (T11)

> Each branch (parking lot). Major FK target — referenced by 25+ tables. **The anchor of the multi-tenant topology**: every business row is filtered by `uuid_sucursal`, the hash chain partition key, and the pairing/pairing-token entry point for branch onboarding.

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration_plan.md`](../iteration_plan.md)
- **Meta-PRD-00 Scaffold**: [`_meta/00_scaffold.md`](_meta/00_scaffold.md)
- **Meta-PRD-01 Models**: [`_meta/01_models.md`](_meta/01_models.md)
- **Meta-PRD-02 Jobs**: [`_meta/02_jobs_queries.md`](_meta/02_jobs_queries.md)
- **Meta-PRD-03 APIs**: [`_meta/03_apis_queries.md`](_meta/03_apis_queries.md)
- **Use-case generation prompt**: [`_meta/04_use_case_generation_prompt.md`](_meta/04_use_case_generation_prompt.md)

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule I: pairing API is segregated from parametrization push*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.sucursal`
- **SQL name**: `sucursal` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite (legal entity)
- **Origin**: F1 (schema) + IT-2 (writes, pairing flow)
- **PRD status**: Draft
- **PRD version**: 3.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; full onboarding cascade through 7-9 tables per case)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `uuid_tipo_sucursal` is mandatory FK to `tipo_sucursal` (the hardware profile of the branch). Branch boot reads this FK and the parent `tipo_sucursal.caracteristicas` JSON to apply configuration.
- Same UUID travel rules: `sucursal.uuid` is the tenant boundary for `operador-` JWT (multi-tenant admin users can switch branches via `X-Sucursal-Context` header; `operador-` tokens are pinned to one `sucursal.uuid`).
- The `sucursal.uuid` is the hash-chain partition key for both `log_transaccional` and `revocacion_factura` — every audit row written by a branch uses this UUID as its partition.

## 3. SOLID Atomic Breakdown
- **S**: "one parking-lot branch" with local data (`direccion`, `telefono`, `prefijo_nombre`, `ciudad`, `horario`) + classification (`uuid_tipo_sucursal`). Corporate data (NIT, regimen, mensajes, resolución DIAN, prefijo/rango) is NOT here — it's read from `empresa` JOINed at query time.
- **O**: `horario` is a free-form string (consider separate `sucursal_horario_excepcion` table if holiday/maintenance exceptions are needed later).
- **I**: segregated audiences — admin CRUD via `api_admin /sucursales`; branch operator reads own via `api_sucursal /sucursales/me`; cloud worker reads via parametrization; auditor reads via `rol_admin_auditor` (BYPASSRLS).
- **D**: `parkos_core/models/V/sucursal.py` (model); `parkos_core/onboarding/pairing_service.py` (token issuance + verification); `infra/docker/entrypoint.sh` (boot-time characteristics application).
- **Atomic**: INSERT (admin creates branch), UPDATE (creates new version, archive old — `vigente_hasta=NOW()`), archive via state transition. DELETE forbidden by FK RESTRICT (25+ tables depend on it).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_tipo_sucursal` | `prod.tipo_sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the hardware profile (A/B/C) |

### Incoming FKs (heavy — 25+ tables)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `usuarios_sucursal.uuid_sucursal` | `\|\|--o{` | which operators assigned |
| `login.uuid_sucursal` | `\|\|--o{` | login audit per branch |
| `documentos.uuid_sucursal` | `\|\|--o{` | licenses, contracts, permits |
| `tarifas_sucursal.uuid_sucursal` | `\|\|--o{` | branch-specific tariff grid |
| `cantidad_vehiculos_sucursal.uuid_sucursal` | `\|\|--o{` | capacity per vehicle type |
| `subscripciones_cliente.uuid_sucursal` | `\|\|--o{` | where subscription was sold |
| `ingreso.uuid_sucursal` | `\|\|--o{` | every vehicle entry |
| `reimpresion_ticket.uuid_sucursal` | `\|\|--o{` | reprint origin |
| `salidas.uuid_sucursal` | `\|\|--o{` | every vehicle exit |
| `anulaciones.uuid_sucursal` | `\|\|--o{` | annulment requests |
| `reclamos.uuid_sucursal` | `\|\|--o{` | customer claims |
| `facturas.uuid_sucursal` | `\|\|--o{` | business invoices |
| `factura_detalle.uuid_sucursal` | `\|\|--o{` | invoice line items |
| `factura_impuestos.uuid_sucursal` | `\|\|--o{` | tax snapshots |
| `factura_otros_cobros.uuid_sucursal` | `\|\|--o{` | charge snapshots |
| `factura_pagos.uuid_sucursal` | `\|\|--o{` | payment methods |
| `factura_electronica.uuid_sucursal` | `\|\|--o{` | DIAN doc (cloud-only writes) |
| `revocacion_factura.uuid_sucursal` | `\|\|--o{` | DIAN revocations (cloud-only) |
| `caja.uuid_sucursal` | `\|\|--o{` | cash snapshots |
| `sesion.uuid_sucursal` | `\|\|--o{` | shifts |
| `arqueo.uuid_sucursal` | `\|\|--o{` | end-of-shift count |
| `alerta.uuid_sucursal` | `\|\|--o{` | operational alerts |
| `sync_queue.uuid_sucursal` | `\|\|--o{` | outbound queue |
| `sync_conflict.uuid_sucursal` | `\|\|--o{` | conflict log |
| `sync_log.uuid_sucursal` | `\|\|--o{` | cycle metrics |
| `log_transaccional.uuid_sucursal` | `\|\|--o{` | audit log (hash chain key) |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin via `api_admin /sucursales` (admin- JWT); chain anchor pre-check; parametrization seed inserted in same TX |
| UPDATE | YES | Inside TX + `log_transaccional` (creates new version, archives old via `vigente_hasta=NOW()`); new version travels via parametrization pull to all branches |
| DELETE | NO | Archive; FK RESTRICT prevents (`sync_queue/sync_log/sync_conflict` use ON DELETE CASCADE — see fk-naming-convention special case) |

**Special rules**:
- `estado ∈ {activo, inactivo, archivado}`. Archive = new version with `vigente_hasta=NOW() AND estado='archivado'`; old version preserved with `vigente_hasta=archive_timestamp`.
- The pairing token table (`pairing_tokens`) is **NOT modeled yet** — referenced in use cases as "concepto a modelar en sprint 5" (same disclaimer as `SyncBackEvent`).
- Parametrization seed (created on branch INSERT): `tarifas_sucursal` rows (one per `(sucursal, tipos_vehiculo, tipo_tarifa)` triple), `cantidad_vehiculos_sucursal` rows (one per `tipos_vehiculo`), `documentos` row placeholder (`tipo='licencia_comercial'`, empty body), `usuarios_sucursal` row for the `sync_agent`. Seed runs in the same TX as `sucursal` INSERT.
- Tenant scope: every API endpoint MUST scope by `uuid_sucursal` — `operador-` JWT pins `uuid_sucursal`; `admin-` JWT uses `X-Sucursal-Context` header validated against `usuarios_sucursal` rows.

## 6. CodeGraph Dependencies
- `api_admin/routers/sucursales.py::POST /sucursales`, `PATCH /sucursales/{uuid}`, `GET /sucursales`, `POST /sucursales/{uuid}/pairing-token`.
- `api_admin/routers/sync.py::POST /sync/pair` (cloud verifies pairing token, issues sync_agent JWT).
- `api_sucursal/routers/sucursales.py::GET /sucursales/me` (branch operator reads own branch).
- `job_sync_cloud::poll_parametrization_pull` (cloud → branch push of new `sucursal` versions).
- `job_sync_sucursal::drain_outbox_sucursal` (branch → cloud push of any branch-side updates, rare since branches don't modify `sucursal` directly).
- `infra/docker/entrypoint.sh` (reads `tipo_sucursal.caracteristicas` JSON to apply boot config: which DIAN stubs activate, which barriers enable, hardware checks).
- `web_admin/SucursalesList`, `SucursalForm`, `PairingTokenDialog` (cloud admin UI).
- `web_sucursal/PairingWizard` (first-boot flow: operator enters pairing token, receives long-lived JWT, persists to `/var/secrets/parkos-sync-jwt`).

## 7. Use Cases enabled by this table

The `sucursal` table is the **anchor of the entire multi-tenant topology**: every business row is FK-filtered by `sucursal.uuid`, the hash chain partition key for `log_transaccional` and `revocacion_factura`, and the entry point for branch onboarding via the pairing flow. Use cases below describe how real parking-lot operations flow through this anchor, with **manual operator input** (no cameras, no OCR, no QR scanners per the system constraint) and full cross-table cascade.

### 7.1 Use Case: `uc.sucursal.admin-onboarding-pairing-flow`

El admin cloud crea una nueva sucursal desde `web_admin`, hace seed de la parametrización local, emite un pairing token de un solo uso, y el operador de la branch lo canjea en `PairingWizard` para obtener el JWT `sync-agent-` largo (90 días). A partir de ahí empieza el pull de parametrización. El flujo completo toca 9 tablas: `sucursal` (creación), `tipo_sucursal` (FK + lectura de `caracteristicas`), `empresa` (JOIN para datos corporativos), `tarifas_sucursal` (seed), `cantidad_vehiculos_sucursal` (seed), `documentos` (placeholder), `usuarios_sucursal` (sync_agent), `log_transaccional` (auditoría), `pairing_tokens` (concepto), `sync_log` (ciclo de pairing).

**Actor**: admin (creates branch, issues token) + system (entrypoint.sh, applies boot config) + operator (consumes token in PairingWizard)

**Pre-conditions**: cloud has `empresa` configured (NIT, resolución DIAN); admin has `rol_admin`; `tipo_sucursal` seed rows (A/B/C) exist.

**Steps**:
1. Admin opens `web_admin/SucursalesList → SucursalForm`, fills `nombre="Sucursal Norte"`, `direccion="Cra 7 #123-45"`, `telefono="601-555-1234"`, `prefijo_nombre="Sucursal Norte — Bogota"`, `ciudad="Bogotá"`, `horario="L-V 06:00-22:00, S 08:00-20:00"`, selects `uuid_tipo_sucursal='B'` (medium with barriers).
2. Frontend POSTs `api_admin /sucursales` (admin- JWT) with the payload.
3. Backend opens TX; `SELECT last.log_transaccional.hash_actual FROM log_transaccional WHERE uuid_sucursal=$PENDING_BRANCH ORDER BY created_at DESC LIMIT 1` — but `$PENDING_BRANCH` doesn't exist yet, so this is a special case: the chain anchor is `NULL` for the genesis row that will be inserted in step 11.
4. Backend INSERTs `sucursal` row (`vigente_desde=NOW(), vigente_hasta=NULL, estado='activo'`) — generates the new `sucursal.uuid`.
5. Backend INSERTs parametrization seed rows (same TX): one `tarifas_sucursal` per `(sucursal, tipos_vehiculo, tipo_tarifa)` triple (e.g., 4 tipos_vehiculo × 3 tipo_tarifa = 12 rows for `valor=3500, valor_plena=25000` placeholders); one `cantidad_vehiculos_sucursal` per `tipos_vehiculo` (4 rows: `cantidad=50` for autos, `cantidad=20` for motos, etc.); one `documentos` placeholder (`tipo='licencia_comercial', documento_b64=NULL, vigente_desde=NOW()`).
6. Backend reads `tipo_sucursal.caracteristicas` JSON for the chosen `uuid_tipo_sucursal` (e.g., `{sensores:false, barreras:true, capacidad_max:200, dian_habilitado:false}` for type B); persists the JSON into a temporary `entrypoint_config.json` S3-keyed for the future branch pull.
7. Backend INSERTs `usuarios_sucursal` row for the future `sync_agent` system user (`uuid_usuario=usuarios_sync_agent.uuid, uuid_sucursal=$new_branch.uuid, estado='activo'`) — created in deactivated state, will activate on pairing.
8. Backend INSERTs `log_transaccional` (`accion='sucursal_creada'`, `tabla_afectada='sucursal'`, `uuid_registro_afectado=$new_branch.uuid`, `datos_anteriores=null`, `datos_nuevos={...snapshot}, hash_anterior=NULL, hash_actual=SHA256(...)` — **this is the genesis row of the new branch chain**). Both cloud and branch will start their chain from this same row.
9. Backend generates pairing token: random 32-char string, stores in `pairing_tokens` (concepto a modelar en sprint 5; expected payload `{uuid, uuid_sucursal, token_hash=SHA256(token), created_at, expires_at=NOW()+24h, used_at=NULL, rate_limit_remaining=5}`); INSERTs `log_transaccional` (`accion='pairing_token_emitido'`, `tabla_afectada='pairing_tokens'`, `uuid_referencia=$new_branch.uuid`).
10. Frontend receives `{sucursal.uuid, pairing_token_plaintext}` and shows it ONCE in `PairingTokenDialog` with copy-to-clipboard. Admin copies the token and sends it to the branch operator (Slack, SMS, paper — out of system scope).
11. Cloud enqueues parametrization push for the (currently non-existent) branch — held in `sync_queue` with `estado='pendiente'` until the branch pairs and pulls.
12. **Branch boot** (operator runs `docker compose -f docker-compose.branch.yml up` for the first time). `infra/docker/entrypoint.sh` orchestrates: `wait-postgres → rol_app precheck → alembic upgrade head → REVOKE/trigger verifier → exec CMD`. The DB is empty (no parametrization yet) — branch is in "awaiting pairing" mode.
13. Operator opens `web_sucursal/PairingWizard` (first-boot screen), types the 32-char pairing token. Frontend POSTs `api_admin /sync/pair` (no JWT yet — endpoint accepts anonymous with rate-limit IP-based) with `{PAIRING_TOKEN, BRANCH_HARDWARE_FINGERPRINT, BRANCH_DB_URL}`.
14. Cloud `pairing_service.verify_token`: SELECTs `pairing_tokens` WHERE `token_hash=SHA256($token)`; rejects if not found, expired (`expires_at < NOW()`), or already used (`used_at IS NOT NULL`). On success: UPDATE `pairing_tokens SET used_at=NOW(), rate_limit_remaining=0` (single-use enforced).
15. Cloud generates `sync-agent-` JWT (`kid='sync-agent-'`, `ttl=90d`, `scope=sync`, `claims={uuid_sucursal: $new_branch.uuid}`); INSERTs `log_transaccional` (`accion='sync_agent_jwt_emitido'`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$new_branch.uuid`); INSERTs `sync_log` (`operaciones_enviadas=1, operaciones_exitosas=1, operaciones_fallidas=0, conflictos=0, duracion_ms=120`, `timestamp=NOW()`).
16. Cloud returns `{sync_agent_jwt, parametrization_initial_pull_url, dian_endpoint_url:null}` to the branch. (Type B branches don't have DIAN enabled; type A would get the DIAN endpoint.)
17. Branch persists JWT to `/var/secrets/parkos-sync-jwt` (read-only after boot); operator is redirected to the main `web_sucursal` shell.
18. Branch `job_sync_cloud::poll_inbox` starts (every 30s); first pull fetches the parametrization seed (`sucursal`, `tipo_sucursal`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `documentos`, `usuarios_sucursal`); INSERTs each row in branch DB (idempotent by UUID); INSERTs `log_transaccional` (`accion='parametrizacion_pull_recibido'`, `datos_nuevos={tablas_pull_count:6}`).
19. Branch boots fully: `entrypoint.sh` re-runs with parametrization now present; reads `tipo_sucursal.caracteristicas` JSON, applies hardware config (`barreras=true → barrier control module loaded`, `dian_habilitado=false → no DIAN stub`); INSERTs `log_transaccional` (`accion='branch_boot_completed'`).

**Tables touched (writes)**: `sucursal`, `tarifas_sucursal` (12 rows), `cantidad_vehiculos_sucursal` (4 rows), `documentos` (1 placeholder), `usuarios_sucursal` (1 for sync_agent), `log_transaccional` (multiple: sucursal_creada + pairing_token_emitido + sync_agent_jwt_emitido + parametrizacion_pull_recibido + branch_boot_completed), `pairing_tokens` (concept), `sync_log` (cycle metrics).
**Tables touched (reads)**: `tipo_sucursal` (caracteristicas JSON), `empresa` (corporate data for JOIN), `usuarios` (sync_agent system user), `sync_queue` (pending parametrization).
**FKs traversed**: `sucursal.uuid_tipo_sucursal` → `tipo_sucursal.uuid`; `tarifas_sucursal.uuid_sucursal` → `sucursal.uuid`; `cantidad_vehiculos_sucursal.uuid_sucursal` → `sucursal.uuid`; `documentos.uuid_sucursal` → `sucursal.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid` + `usuarios_sucursal.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid` (the chain anchor); `log_transaccional.uuid_usuario` → `usuarios.uuid`.

**Sync behavior**:
- Branch → cloud: NO (the admin creates the branch; the pairing consumes cloud-issued token; the branch only pulls).
- Cloud → branch: YES — parametrization pull delivers the seed (`sucursal`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `documentos`, `usuarios_sucursal`, `log_transaccional` genesis row) within 30s of first sync cycle.
- DIAN trigger: NO for type B/C; type A branches would receive DIAN endpoint config but only write DIAN stubs in cloud.
- Hash chain impact: YES — the genesis row (`hash_anterior=NULL`) is inserted in cloud when the branch is created, then pulled to branch; both sides start their chain from the same seed. The pairing event extends the cloud chain (sync_agent_jwt_emitido), and the branch_boot_completed event extends the branch chain (received via pull).

**Integration with other tables**:
- Reads from: `tipo_sucursal` (caracteristicas JSON drives boot config), `empresa` (corporate data — NIT, resolución DIAN — read via JOIN), `usuarios` (sync_agent system user lookup).
- Writes to: `sucursal` (the new row), `tarifas_sucursal` (12 seed rows), `cantidad_vehiculos_sucursal` (4 seed rows), `documentos` (placeholder), `usuarios_sucursal` (sync_agent assignment), `log_transaccional` (multiple audit rows), `pairing_tokens` (concept), `sync_log` (cycle metrics).
- Cross-cutting: this is the **canonical onboarding cascade** — one operator/admin action creates 25+ rows across 9 tables and establishes the hash chain for the new tenant. After onboarding, every subsequent operation writes to `log_transaccional` keyed by `sucursal.uuid`.

### 7.2 Use Case: `uc.sucursal.pairing-replay-attack`

Un atacante intenta reusar un pairing token que ya fue consumido. Cloud `pairing_service.verify_token` detecta `used_at IS NOT NULL`, rechaza con 401, emite un `alerta tipo_alerta='pairing_replay'` para que el admin investigue (posible intento de compromiso de la branch). El flujo toca 4 tablas: `pairing_tokens` (concept), `alerta` (workflow chain root), `log_transaccional` (auditoría), `sync_log` (métrica del intento).

**Actor**: system (cloud `pairing_service.verify_token`)

**Pre-conditions**: branch operator already paired successfully; `pairing_tokens.used_at IS NOT NULL` for the consumed token; attacker (or naive operator who re-tries) submits the same plaintext token again.

**Steps**:
1. Attacker POSTs `api_admin /sync/pair` with the same 32-char token used in 7.1 step 13, from a different IP (rate-limit IP-based triggers warning).
2. Cloud `pairing_service.verify_token`: SELECTs `pairing_tokens` WHERE `token_hash=SHA256($token)`. Row found, but `used_at IS NOT NULL`.
3. Cloud rejects: returns `401 Unauthorized {detail: 'pairing_token_already_used', uuid_sucursal: $original_branch, used_at: $timestamp}`. **No new `sync_agent` JWT is issued.**
4. Cloud INSERTs `alerta` (`tipo_alerta='pairing_replay'`, `estado='abierta'`, `uuid_sucursal=$original_branch.uuid`, `uuid_alerta_padre=NULL`, `uuid_usuario=NULL` — responsible assigned later, `valor_diferencia_efectivo=0`, `valor_diferencia_datafono=0`, `observaciones='IP:$attacker_ip, token_age_min:$X'`) — workflow chain root.
5. Cloud INSERTs `log_transaccional` (`accion='pairing_replay_detectado'`, `tabla_afectada='pairing_tokens'`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$original_branch.uuid`, `datos_nuevos={attacker_ip, token_age_min, original_used_at}`, `uuid_referencia=$alert.uuid`).
6. Cloud INSERTs `sync_log` (`operaciones_enviadas=0, operaciones_fallidas=1, conflictos=0, duracion_ms=8`).
7. Admin sees the `alerta` in `web_admin/AlertasList` (red badge, top of list). Admin clicks → triage.
8. Admin may: (a) confirm legitimate re-try (operator typed the token twice by mistake) → workflow chain transition `en_revision → resuelta` with `observaciones='false_positive_<operator>'`; or (b) confirm actual attack → `en_revision` then manual revocation of the sync_agent JWT (IT-1 task), escalate to security review.
9. The `alerta` workflow chain (`abierta → en_revision → resuelta`) emits 2-3 additional `log_transaccional` rows via the standard `[L-W]` pattern (each transition = new row).

**Tables touched (writes)**: `alerta` (1 root + 2-3 transitions), `log_transaccional` (1 initial + 2-3 per workflow transitions), `sync_log` (1).
**Tables touched (reads)**: `pairing_tokens` (verify single-use), `usuarios` (SYSTEM lookup for log), `sucursal` (uuid for log partition key).
**FKs traversed**: `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` (assigned during en_revision) → `usuarios.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain self-reference for transitions); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_referencia` (polymorphic) → `alerta.uuid`.

**Sync behavior**:
- Branch → cloud: NO (the rejected attempt doesn't pair; no JWT issued to the attacker).
- Cloud → branch: NO (cloud doesn't push the alerta to the affected branch — alertas are operational; branch sees them only on next parametrization pull, but pairing_replay doesn't need branch awareness).
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (the pairing_replay_detectado audit) plus 2-3 rows for the alerta workflow transitions.

**Integration with other tables**:
- Reads from: `pairing_tokens` (verify single-use), `usuarios` (SYSTEM lookup), `sucursal` (uuid for partition).
- Writes to: `alerta` (workflow root + transitions), `log_transaccional` (audit + per-transition), `sync_log` (cycle metrics).
- Cross-cutting: this is the **security tripwire** for the pairing flow. Without this check, a leaked token would grant attacker a long-lived sync_agent JWT (90 days). The rate-limit + single-use + alert chain is the layered defense.
- Related: the `usuarios_sucursal` row for the original sync_agent is NOT deactivated by the replay attempt — only the original branch's operator can trigger that via admin action.

### 7.3 Use Case: `uc.sucursal.branch-offline-detected`

Una branch dejó de hacer push a cloud (cayó internet, se apagó el equipo, falla de hardware). El cloud worker `branch_health_monitor` corre cada 15 minutos, busca branches sin `sync_log` exitoso en las últimas X horas (configurable, default 6h), emite `alerta tipo_alerta='branch_offline'` con workflow chain root. Admin investiga: puede ser outage temporal o branch comprometida. El flujo toca 5 tablas: `sync_log` (consulta), `sucursal` (tenant boundary), `alerta` (workflow root), `log_transaccional` (auditoría), `sync_log` (ciclo del monitor).

**Actor**: system (cloud `branch_health_monitor` cron worker)

**Pre-conditions**: cloud has at least one branch that was previously paired and pushing successfully. Branch stops pushing (no `sync_log` row with `operaciones_exitosas > 0` in the last X hours). `branch_health_monitor` cron is enabled.

**Steps**:
1. `branch_health_monitor` cron fires every 15 min (cloud). SELECTs DISTINCT `sucursal.uuid` from `sucursal` WHERE `estado='activo'`.
2. For each active branch: SELECTs MAX(`sync_log.timestamp`) FROM `sync_log` WHERE `uuid_sucursal=$branch AND operaciones_exitosas > 0`.
3. If `last_successful_sync IS NULL OR (NOW() - last_successful_sync) > threshold_hours`: branch is offline.
4. Branch is offline. Worker INSERTs `alerta` (`tipo_alerta='branch_offline'`, `estado='abierta'`, `uuid_sucursal=$branch.uuid`, `uuid_alerta_padre=NULL`, `uuid_usuario=NULL`, `observaciones='last_sync_at: $timestamp, hours_offline: $X, threshold: $threshold_hours'`).
5. Worker INSERTs `log_transaccional` (`accion='branch_offline_detected'`, `tabla_afectada='sync_log'`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch.uuid`, `datos_nuevos={last_sync, hours_offline, threshold, alert_uuid}`).
6. Worker INSERTs `sync_log` row for the monitor's own cycle (`operaciones_enviadas=0, operaciones_fallidas=0, conflictos=0, duracion_ms=$X`).
7. Admin sees the `alerta` in `web_admin/AlertasList` (orange badge — offline is not critical, but actionable). Admin clicks → triage.
8. Admin options: (a) call the operator → confirm legitimate outage → `en_revision → resuelta` with `observaciones='ISP_outage_<ticket_id>'`; (b) branch silent → escalate: dispatch field tech, check `sync_queue.depth` on cloud side (should be 0 — nothing queued from a silent branch).
9. When branch comes back online: `job_sync_sucursal::drain_outbox` resumes push; cloud receives `sync_log` with successful entries. A separate worker `alerta_auto_resolver` detects that `last_sync < threshold_hours` again and INSERTs new `alerta` row with `uuid_alerta_padre=$root, estado='resuelta'` (workflow chain extension).
10. The `alerta` workflow chain emits 2-3 `log_transaccional` rows total (root + transitions).

**Tables touched (writes)**: `alerta` (1 root + 2-3 transitions), `log_transaccional` (1 initial + 2-3 per transitions), `sync_log` (1 for monitor cycle).
**Tables touched (reads)**: `sucursal` (active branches), `sync_log` (last successful sync per branch), `usuarios` (SYSTEM lookup), `alerta` (existing chain rows to prevent duplicate alerts).
**FKs traversed**: `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `sync_log.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (the silent branch can't push; the monitor runs cloud-side).
- Cloud → branch: NO (alerta is cloud-only operational; branch doesn't need to know it's flagged as offline until it reconnects and queries).
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (branch_offline_detected) plus 2-3 rows for the alerta workflow transitions.

**Integration with other tables**:
- Reads from: `sucursal` (active branches), `sync_log` (last sync per branch), `usuarios` (SYSTEM), `alerta` (existing rows to dedupe — only one open branch_offline alerta per branch).
- Writes to: `alerta` (workflow root + transitions), `log_transaccional` (audit + per-transition), `sync_log` (monitor cycle).
- Cross-cutting: the threshold is configurable per `configuracion_seguridad` (operational setting; not DIAN-critical). When a branch returns online, the auto-resolver emits the workflow chain transition, preserving the audit trail of "branch was offline from X to Y".
- Related: `branch_offline` alertas are NOT critical (orange, not red) — they don't block operations, just notify admin.

### 7.4 Use Case: `uc.sucursal.operator-uploads-branch-document`

El operador de la branch (no admin — el operador local tiene permiso limitado para subir documentos operativos como fotos de daños, contratos firmados con clientes B2B) carga un PDF a `documentos`. El admin cloud había dejado el placeholder en 7.1 step 5 con `documento_b64=NULL`; ahora el operador sube el contenido real (licencia municipal firmada, contrato B2B, permiso de uso de suelo, fotos de daños). El flujo toca 5 tablas: `documentos` (UPDATE a nueva versión con contenido), `log_transaccional` (auditoría), `sync_queue` (propagación diferida), `usuarios_sucursal` (verificación de scope), `sucursal` (tenant scope).

**Actor**: operator (branch-side; has `permisos_usuario` permission for `subir_documentos_operativos`)

**Pre-conditions**: branch is paired and has sync_agent JWT; operator's `permisos_usuario` includes `subir_documentos_operativos`; placeholder `documentos` row exists for the branch (created during onboarding seed in 7.1 step 5); `documentos` row has `documento_b64=NULL, vigente_hasta=NULL`.

**Steps**:
1. Operator opens `web_sucursal/DocumentosTab`, clicks on the placeholder row (`tipo='licencia_comercial'`, empty body).
2. Frontend shows `DocumentUploadForm` with file input (PDF or JPG). Operator selects file (max 10 MB; PDF for licenses, JPG for photos).
3. Frontend reads file as base64 client-side (manual, no auto-capture); displays preview.
4. Frontend POSTs `api_sucursal /documentos/{uuid_placeholder}/upload` with `{documento_b64=<base64>, formato='pdf', mime_type='application/pdf', file_size_bytes=$X, sha256=$hash}`.
5. Backend verifies operator JWT: SELECTs `permisos_usuario` for `permiso='subir_documentos_operativos'`; rejects 403 if missing.
6. Backend SELECTs `documentos` placeholder; validates `uuid_sucursal = JWT.uuid_sucursal` (tenant scope check); validates file size (<=10 MB) and MIME type.
7. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
8. Backend INSERTs new `documentos` row with NEW uuid (versioning): `vigente_desde=NOW(), vigente_hasta=NULL, documento_b64=$b64, formato='pdf'`. UPDATE old placeholder: `vigente_hasta=NOW()` (archived — version flow).
9. Backend INSERTs `log_transaccional` (`accion='documento_subido'`, `tabla_afectada='documentos'`, `uuid_registro_afectado=$new_version.uuid`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `datos_anteriores={placeholder_summary}`, `datos_nuevos={...new_version snapshot, sha256, file_size}`).
10. `queue_processor.enqueue('documentos', $new_uuid, $snapshot)` → INSERT `sync_queue` row.
11. Backend returns `{uuid, sha256, file_size, uploaded_at}` to frontend.
12. Operator UI shows success with the new file size badge.
13. When branch next syncs (online or after offline period), `job_sync_sucursal::drain_outbox` pushes the `documentos` row + `log_transaccional` row via `POST /sync/push` with sync_agent JWT.
14. Cloud receives; INSERTs both rows (idempotent by UUID); cloud chain extends by 1 row.
15. Cloud admin can now view the document in `web_admin/DocumentosDetail/{uuid}` (read-only — no further edits from cloud side; the operator's version is authoritative).

**Tables touched (writes)**: `documentos` (1 new version + 1 archive update), `log_transaccional` (1 branch + 1 cloud when received), `sync_queue` (1 row).
**Tables touched (reads)**: `permisos_usuario` (permission check), `usuarios_sucursal` (tenant scope), `documentos` (placeholder lookup), `log_transaccional` (chain anchor), `sucursal` (tenant).
**FKs traversed**: `documentos.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `documentos.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid` + `permisos_usuario.uuid_permiso` → `permisos.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the `documentos` row + `log_transaccional` row push via `sync_queue` within 30s of upload. Cloud preserves branch chain verbatim.
- Cloud → branch: NO (no parametrization impact; cloud only receives the operator's upload).
- DIAN trigger: NO (documentos are operational/regulatory, not fiscal).
- Hash chain impact: YES — branch chain extends by 1 row on upload; cloud chain extends by 1 row when received via sync.

**Integration with other tables**:
- Reads from: `permisos_usuario` (RBAC check), `usuarios_sucursal` (tenant scope), `documentos` (placeholder lookup), `log_transaccional` (chain anchor), `sucursal` (tenant).
- Writes to: `documentos` (new version + archive old), `log_transaccional` (audit), `sync_queue` (deferred propagation).
- Cross-cutting: the `[V]` versioning is critical here — uploading a new license file doesn't destroy the old one; both versions exist (with `vigente_hasta` on the old). Cloud admin can audit "what version of the license was active on 2026-01-15" via bi-temporal query.
- Related: large files (>10 MB) should use S3-compatible storage with URL reference instead of base64 (deferred to sprint 5; current placeholder accepts up to 10 MB which covers most licenses/contracts).

### 7.5 Use Case: `uc.sucursal.branch-boot-uses-tipo-sucursal-characteristics`

En cada boot de la branch, `infra/docker/entrypoint.sh` lee `tipo_sucursal.caracteristicas` JSON (ya parametrizada desde cloud en 7.1 step 18) y aplica la configuración de hardware: para tipo A activa el módulo de sensores, para tipo B activa barreras, para tipo C desactiva ambos. También decide qué endpoints DIAN activar (solo tipo A). Esto NO es un caso con INSERT — es READ puro en boot que determina la configuración operativa de la branch. El flujo toca 4 tablas en lectura + 1 en escritura (`log_transaccional` audita el boot).

**Actor**: system (entrypoint.sh on every branch boot)

**Pre-conditions**: branch is paired; parametrization pull completed (includes `tipo_sucursal` and `sucursal` rows); branch has its own `sucursal.uuid_tipo_sucursal` FK populated.

**Steps**:
1. Branch boots (start of shift, after restart, after crash recovery). `infra/docker/entrypoint.sh` orchestrates: `wait-postgres → rol_app precheck → alembic upgrade head → REVOKE/trigger verifier → load_tipo_sucursal_config → exec CMD`.
2. `load_tipo_sucursal_config`: SELECTs `sucursal.uuid_tipo_sucursal` from local `sucursal` WHERE `uuid = $self_branch_uuid`. Then SELECTs `tipo_sucursal.caracteristicas` JSON WHERE `uuid = $tipo_sucursal_uuid`.
3. Parses `caracteristicas` JSON. Examples per type:
   - Type A: `{sensores: true, barreras: true, capacidad_max: 500, dian_habilitado: true, hardware_modules: ['sensor_counter', 'barrier_v2', 'receipt_printer']}`
   - Type B: `{sensores: false, barreras: true, capacidad_max: 200, dian_habilitado: false, hardware_modules: ['barrier_v2', 'receipt_printer']}`
   - Type C: `{sensores: false, barreras: false, capacidad_max: 80, dian_habilitado: false, hardware_modules: ['receipt_printer']}`
4. Writes the parsed config to `/var/etc/parkos/boot_config.json` (read by application modules at startup).
5. Application `api_sucursal` reads `boot_config.json` on first request: if `dian_habilitado=true`, loads the `dian_dispatcher_stub` (sends to cloud for DIAN processing — even for type A, the stub doesn't write `factura_electronica` locally; it always delegates to cloud); if `dian_habilitado=false`, the stub is NOT loaded and the operator sees "DIAN: cloud-only, will assign number async" message in `FacturacionForm`.
6. If `barreras=true`: loads `barrier_control_module` — frontend gains `OpenBarrier` button in `IngresoForm` and `SalidaForm` (operator clicks after system confirms ingreso/salida creation); if `barreras=false`, no button (manual entry only).
7. If `sensores=true`: loads `sensor_counter_module` — `web_sucursal/Dashboard` shows live occupancy by sensor zone; if `sensores=false`, occupancy is computed from `ingreso` count minus `salidas` count (manual count).
8. `entrypoint.sh` INSERTs `log_transaccional` (`accion='branch_boot_config_loaded'`, `tabla_afectada='tipo_sucursal'`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$self_branch_uuid`, `datos_nuevos={tipo_codigo:'B', caracteristicas_resolved: {...}, modules_loaded: ['barrier_v2','receipt_printer']}`).
9. Branch operator sees the configured UI (with or without barrier button, DIAN message, etc.) and can start operating.

**Tables touched (writes)**: `log_transaccional` (1 row).
**Tables touched (reads)**: `sucursal` (self uuid + uuid_tipo_sucursal FK), `tipo_sucursal` (caracteristicas JSON), `log_transaccional` (chain anchor for the new audit row), `usuarios` (SYSTEM lookup).
**FKs traversed**: `sucursal.uuid_tipo_sucursal` → `tipo_sucursal.uuid` (the key resolution); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_registro_afectado` (polymorphic) → `tipo_sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES (the boot_config_loaded audit row pushes via `sync_queue` within 30s).
- Cloud → branch: NO (this is a read-and-apply operation, not a write that triggers parametrization).
- DIAN trigger: NO (the config decision happens locally; DIAN writing happens only when the operator actually invoices — and even then, type B/C delegates to cloud).
- Hash chain impact: YES — branch chain extends by 1 row on every boot. Cloud receives it; cloud chain extends by 1 row. Frequent boots don't break the chain (idempotency by UUID + per-row timestamp).

**Integration with other tables**:
- Reads from: `sucursal` (self uuid + tipo FK), `tipo_sucursal` (caracteristicas JSON), `log_transaccional` (chain anchor), `usuarios` (SYSTEM).
- Writes to: `log_transaccional` (boot audit).
- Cross-cutting: this is the **hardware-driven configuration pattern**. The JSON `caracteristicas` is intentionally extensible — adding a new hardware module means adding a key to the JSON + updating the application module loader; no schema change. Per SOLID O (open/closed), the table schema is closed for modification, open for extension via JSON.
- Related: a branch's `tipo_sucursal` may change over time (a type C branch upgrades to type B by adding barriers); admin updates `sucursal.uuid_tipo_sucursal` via cloud parametrization, branch receives the new row, next boot applies the new config. The `log_transaccional` chain records both the configuration change and the resulting boot.

### 7.6 Use Case: `uc.sucursal.archive-when-decommissioned`

Admin cloud desactiva una branch (cierre de local, venta del negocio, mudanza). Marca `estado='archivado'` via nueva versión `[V]` con `vigente_hasta=NOW()`. Cloud enqueue parametrización push para que la branch remota también archive localmente. Branch que estaba activa continúa operando hasta su próximo sync; si la branch estaba offline, al volver detectará que su `sucursal.estado` cambió y mostrará un banner de "Sucursal archivada — contacte admin". El flujo toca 6 tablas: `sucursal` (nueva versión archivada), `log_transaccional` (auditoría), `sync_queue` (propagación), `usuarios_sucursal` (operadores desactivados), `permisos_usuario` (permisos revocados), `sync_log` (ciclo).

**Actor**: admin

**Pre-conditions**: branch is currently `estado='activo'`; admin wants to decommission (closure, sale, relocation); all FK-dependent rows (ingreso, facturas, log) are preserved per audit; only the branch itself + its `usuarios_sucursal` assignments are archived.

**Steps**:
1. Admin opens `web_admin/SucursalesList`, finds the branch, clicks `Archive`.
2. Frontend shows confirmation modal: "Archivar Sucursal Norte? Los usuarios asignados serán desactivados pero los datos históricos (ingresos, facturas, logs) se preservan. Esta acción no se puede deshacer automáticamente."
3. Admin confirms; frontend PATCHes `api_admin /sucursales/{uuid}` with `{estado: 'archivado', archive_reason: 'cierre_local_<reason>'}`.
4. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
5. Backend SELECTs current `sucursal` row (where `vigente_hasta IS NULL`). INSERTs new row: `vigente_desde=NOW(), vigente_hasta=NOW(), estado='archivado'` (the archived version IS its own row; the old row stays as `vigente_hasta=NOW()` from UPDATE — version flow).
6. Backend SELECTs all `usuarios_sucursal` WHERE `uuid_sucursal=$branch AND vigente_hasta IS NULL`. For each: INSERTs new row with `vigente_desde=NOW(), vigente_hasta=NOW(), estado='inactivo'`.
7. Backend SELECTs all `permisos_usuario` for the affected users WHERE `vigente_hasta IS NULL`. For each: INSERTs new row with `vigente_hasta=NOW(), estado='revocado'`.
8. Backend INSERTs `log_transaccional` (`accion='sucursal_archivada'`, `tabla_afectada='sucursal'`, `uuid_registro_afectado=$new_uuid_archived`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$branch`, `datos_anteriores={old_version_snapshot}`, `datos_nuevos={archived_version_snapshot, archive_reason, operadores_desactivados: $N}`).
9. `queue_processor.enqueue('sucursal', $new_uuid, $snapshot)` + parametrization push enqueued for the affected branch.
10. Backend INSERTs `sync_log` (`operaciones_enviadas=1, exitosas=0, fallidas=0, duracion_ms=$X`).
11. Backend returns `{uuid_new, archived_at, operadores_afectados: $N}` to frontend.
12. Branch (if online) receives parametrization: UPSERTs `sucursal` new version + deactivates its `usuarios_sucursal` rows. UI shows red banner: "Sucursal archivada — contacte admin cloud para reactivar".
13. Branch (if offline): next boot applies the new state; same banner.
14. If branch attempts to operate: backend rejects with `403 Sucursal no activa`. The branch is in "graceful shutdown" mode.
15. `sync_queue` + `sync_log` + `sync_conflict` for this branch are NOT deleted (preserved for audit). When the branch eventually goes offline permanently, those rows remain in cloud's local view (operational data is preserved even after branch death).

**Tables touched (writes)**: `sucursal` (1 new archived version), `usuarios_sucursal` (1 new inactive version per operator), `permisos_usuario` (1 new revoked version per operator permission), `log_transaccional` (1 branch + 1 cloud when received), `sync_queue` (parametrization push + log push), `sync_log` (1 row).
**Tables touched (reads)**: `sucursal` (current version lookup), `usuarios_sucursal` (operators at this branch), `permisos_usuario` (their permissions), `log_transaccional` (chain anchor).
**FKs traversed**: `sucursal.uuid_tipo_sucursal` → `tipo_sucursal.uuid` (preserved on archived version); `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid` + `usuarios_sucursal.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid` + `permisos_usuario.uuid_permiso` → `permisos.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid` (chain anchor preserved even after archive); `log_transaccional.uuid_usuario` → `usuarios.uuid` (admin).

**Sync behavior**:
- Branch → cloud: NO (this write happens in cloud).
- Cloud → branch: YES — parametrization push delivers the archived version + inactive operador versions within 30s. Branch receives and applies locally; sync chain on branch remains intact (the archive is one row in the chain).
- DIAN trigger: NO (archive doesn't affect DIAN; historical facturas remain intact).
- Hash chain impact: YES — cloud chain extends by 1 row (sucursal_archivada) for the admin's action. Branch chain extends by 1 row when it receives the parametrization (and another when it boots and applies the new state).

**Integration with other tables**:
- Reads from: `sucursal` (current version), `usuarios_sucursal` (operators), `permisos_usuario` (their permissions), `log_transaccional` (chain anchor), `tipo_sucursal` (preserved FK), `usuarios` (admin actor).
- Writes to: `sucursal` (new archived version), `usuarios_sucursal` (new inactive versions), `permisos_usuario` (new revoked versions), `log_transaccional` (audit), `sync_queue` (parametrization push), `sync_log` (cycle metrics).
- Cross-cutting: archive is **NOT a delete**. Historical rows (`ingreso`, `facturas`, `log_transaccional`, `factura_electronica`, etc.) are FK RESTRICT — they remain forever, preserving audit. The branch itself becomes inaccessible (operadores deactivated, permisos revoked) but the data lives on.
- Related: if admin wants to "fully decommission" (remove from queries), that requires a separate process (PII pseudonymization, regulatory retention purge) — out of MVP scope; current archive is sufficient for "branch no longer operates".

## 8. Layer-by-Layer Impact
Layers: 1, 4, 6, 7, 10, 11, 13, 14, 15, 16, 17, 24, 28, 31, 35, 38, 40.

## 9. RED Tests
- (RED) Admin POST `/sucursales` → 201; parametrization seed rows exist (tarifas_sucursal, cantidad_vehiculos_sucursal, documentos, usuarios_sucursal).
- (RED) Branch operator reads other branch's `sucursal` → 403 (tenant scope enforced).
- (RED) Pairing token replay attempt → 401 + `alerta tipo_alerta='pairing_replay'` created.
- (RED) Pairing token expired (>24h) → 401.
- (RED) Pairing token rate-limit (5 attempts per IP per hour) → 429.
- (RED) Admin PATCH `/sucursales/{uuid}` with `estado='archivado'` → new version created, old `vigente_hasta=NOW()`, operadores deactivated.
- (RED) ON DELETE RESTRICT: cannot `DELETE FROM sucursal WHERE uuid=?` because `ingreso` rows exist.
- (RED) Hash chain: branch genesis row (`hash_anterior=NULL`) inserted at first sync after pairing; subsequent writes extend chain.
- (RED) Sync queue dedupe: parametrization pull of `sucursal` row received twice → second INSERT is `ON CONFLICT DO NOTHING` (idempotent).
- (RED) Branch offline detection: simulate `sync_log` with no `operaciones_exitosas > 0` for >6h → `alerta tipo_alerta='branch_offline'` created.
- (RED) Boot config: `tipo_sucursal='B'` branch boots with `barrier_v2` module loaded; `tipo_sucursal='C'` branch boots WITHOUT it (UI test: `OpenBarrier` button visible/hidden).
- (RED) Cross-audience sync: branch operator JWT to `api_admin /sucursales` → 401 (admin-only).
- (RED) Documentos upload: operator without `permiso='subir_documentos_operativos'` → 403.

## 10. Implementation Tasks
- [x] F1.x Schema.
- [ ] IT-2.x: `api_admin /sucursales` (POST, PATCH, GET list, GET detail).
- [ ] IT-2.x: parametrization seed on INSERT (12 tarifas_sucursal rows, 4 cantidad_vehiculos_sucursal rows, 1 documentos placeholder, 1 usuarios_sucursal for sync_agent).
- [ ] IT-2.x: `api_admin /sucursales/{uuid}/pairing-token` (POST).
- [ ] IT-2.x: `api_admin /sync/pair` (POST — verify token, issue sync_agent JWT).
- [ ] IT-2.x: `infra/docker/entrypoint.sh` orchestrates `load_tipo_sucursal_config` step + writes `/var/etc/parkos/boot_config.json`.
- [ ] IT-2.x: `web_sucursal/PairingWizard` (operator UI for first-boot token consumption).
- [ ] IT-2.x: `api_sucursal /documentos/{uuid}/upload` (operator upload, version flow).
- [ ] IT-2.x: `workers/branch_health_monitor` (cron, 15min interval).
- [ ] Sprint 5: model `pairing_tokens` as concrete table (current: concepto documentado en use cases 7.1, 7.2).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Pairing token replay | Low | Single-use enforced in `pairing_tokens.used_at`; 24h TTL; rate-limit 5/IP/hour; alerta on replay |
| Pairing token leaked | Low | 90d JWT TTL for sync_agent; admin can revoke via `permisos_usuario` chain |
| Branch silently offline | Med | `branch_health_monitor` cron emits `alerta tipo_alerta='branch_offline'` after 6h silence; threshold configurable in `configuracion_seguridad` |
| Branch decommissioned mid-operation | Low | Archive is graceful — branch shows banner, can finish current `sesion`, but new operations rejected |
| Parametrization seed incomplete | Low | F1 migration seeds A/B/C `tipo_sucursal`; admin POST validates FK; seed runs in same TX as `sucursal` INSERT |
| tipo_sucursal change requires hardware upgrade | Med | Documented in 7.5: type C → B upgrade requires barriers installed; JSON `caracteristicas` drives the check |
| Operator overwrites critical document | Low | `[V]` versioning preserves all versions; admin can bi-temporally query |
| Hash chain break on parametrization pull | Low | `log_writer` verifies chain anchor before INSERT; mismatch → `HASH_CHAIN_BREAK` + `sync_conflict` policy `manual` |
| Branch starts before parametrization pulled | Med | `entrypoint.sh` runs `load_tipo_sucursal_config` BEFORE `exec CMD`; if parametrization missing, branch enters "awaiting pairing" mode and shows PairingWizard |

## 12. Open Questions
- (a) Multiple `tipo_sucursal` per branch over time (e.g., upgrades)? Currently FK is single-valued; upgrade = admin PATCHes `sucursal.uuid_tipo_sucursal` and INSERTs new `[V]` row with `vigente_hasta=NOW()` on old. Next boot applies new config.
- (b) `pairing_tokens` materialization: concrete table vs in-memory cache with persistence? Sprint 5 decision.
- (c) Multi-region branches (latency): does each region have its own `empresa` corporate identity, or one global? Currently one global; revisit if multi-region expansion happens.
- (d) `branch_offline` threshold per branch or global? Currently global (in `configuracion_seguridad`); could be per-branch in `[V]` if operational variability demands it.
- (e) `sucursal.horario` as string vs structured: current free-form string is sufficient; revisit if exception tables (holiday, maintenance) are needed.
- (f) Branch lifecycle states beyond `activo/inactivo/archivado`: e.g., `mantenimiento`, `renovacion`? Currently collapsed into `inactivo`; expand if operational complexity demands.
