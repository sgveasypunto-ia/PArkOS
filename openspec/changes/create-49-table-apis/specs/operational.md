# Spec: Operational Requirements (Resolved Open Questions)

## Capability

Capture the **12 open questions deferred from propose** and resolve them with concrete API/ORM/DB requirements; also document the **Idempotency-Key 50th-table contract**, the **OpenAPI TS client SDK strategy**, the **RBAC permission matrix framework**, and the **uniform pagination shape**. Every requirement here is **testable** and either powers an endpoint of one of the per-class specs (bi-temporal-crud, append-only-events, etc.) or stands alone as an infrastructure module under `parkos_core/`. Together these close the last ambiguity that prevented implementation.

---

## Requirements

### REQ-OP-01-PAGINATION-CURSOR: Uniform opaque-base64 next_cursor (Q1)
**Given** any list endpoint that returns multiple rows (across `[V]`, `[L-E]`, `[L-W]`, `[L-S]`, `[A]` classes — every spec uses the same scheme)
**When** the client supplies `cursor=<opaque>` from a prior `next_cursor` response
**Then** the system MUST (a) treat `next_cursor` as an opaque base64-encoded JSON `{"vigente_desde": "<iso8601>", "uuid": "<uuid>", "resource": "<table-name>"}` for `[V]` (canonical AD-1 contract); analog for `[L-E]` uses `timestamp_evento, uuid`; for `[L-W]` uses `timestamp_evento, uuid`; for `[A]` `created_at, uuid`; (b) reject malformed cursors with 400 `{"error": "invalid_cursor"}`; (c) `limit` is bounded 1..200 inclusive; (d) emit RFC 5988 `Link: <url>; rel="next"` header as a non-normative convenience in addition to the body field; (e) `next_cursor = null` (or empty string) signals end of result set; (f) `X-Total-Estimate` MUST NOT be emitted (counting would defeat cursor pagination)

### REQ-OP-02-OPENAPI-SDK: Committed OpenAPI artifacts + TypeScript codegen (Q2)
**Given** the FastAPI app boots in CI for both `api_admin` and `api_sucursal`
**When** `uv run python -m parkos_core.openapi --output backend/packages/api_admin/openapi.json` runs (one per deploy context)
**Then** the system MUST (a) generate an OpenAPI 3.1 JSON artifact; (b) split by audience via `openapi_tags`: `admin`, `operador`, `sync` — each PWA only consumes its tag set; (c) set `info.version` to the git SHA of the change that shipped the contract; (d) commit the JSON file as an artifact (NOT generated at consumer runtime) — frontend pins a specific SHA via `git checkout` of the artifact; (e) the frontend uses `openapi-typescript-codegen` (zero runtime dep, deterministic, tree-shakable) to produce `apps/ui-kit/src/api/{admin,branch}/generated/`. The git SHA pinned in `info.version` is a deliberate break-glass — when the contract changes, the consumer PR must update its pin. Codegen runs in `apps/ui-kit/package.json` script `gen:api:admin` / `gen:api:branch`

### REQ-OP-03-SYNC-ENDPOINTS: Mounted on both services, sync-agent token only (Q3)
**Given** the four sync endpoints `/api/v1/sync/{pair, push, pull, events}`
**When** the routers are mounted
**Then** the system MUST (a) mount on BOTH `api_admin` (cloud-side receiver) and `api_sucursal` (branch-side receiver) — NOT a separate `api_sync` service (keeps the topology simple); (b) require a `sync-agent-` JWT scoped to the relevant `uuid_sucursal` (Q3 resolution; see `cross-cutting.md` REQ-X8); (c) the `/events` route is the cloud → branch push channel (`SyncBackEvent` for offline-preliminary `factura_electronica`, ID resolution, etc.); (d) Admin and operador tokens are rejected with 401 on any `/sync/*` path; (e) the topology remains: `web_admin ↔ api_admin ↔ job_sync_cloud ↔ many(job_sync_sucursal) ↔ many(api_sucursal) ↔ web_sucursal`

### REQ-OP-04-IDEMPOTENCY-KEY: Required POST header, 50th `[A]`-class table (AD-3, Q5 deferred)
**Given** any POST endpoint under `/api/v1/*` that is a write (CREATE / append / transition / open)
**When** the client requests without an `Idempotency-Key` header
**Then** the system MUST reject with 400 `{"error": "idempotency_key_required", "detail": "POST requires Idempotency-Key header (RFC 7234-style)"}`. With a header, the helper `parkos_core/repo/idempotency.py::guard()` MUST (a) UPSERT into `prod.idempotency_keys` table (`uuid PK`, `key_hash` index, `endpoint`, `request_payload_hash`, `response_status`, `response_body JSONB`, `created_at`, `expires_at = NOW() + 24 hours`, `created_by`); (b) if a row with the same `(endpoint, key_hash)` exists and `expires_at > NOW()`, return the cached response with `Idempotent-Replay: true` header instead of executing the write; (c) if expired, the helper deletes the row (TTL worker — nightly) and the new request proceeds. The `idempotency_keys` table is `[A]`-class: `REVOKE UPDATE, DELETE FROM rol_app` + `BEFORE UPDATE OR DELETE` trigger — created by migration `0002_add_idempotency_keys.py` in PR7. The 24-hour TTL matches Stripe's default and absorbs every realistic retry window

### REQ-OP-05-DOCUMENTOS-UPLOAD: multipart/form-data for new uploads, base64 stays for legacy (Q5)
**Given** the `documentos` table's `documento_b64` TEXT column historically inlined binary; new uploads prefer streaming
**When** the operator POSTs a binary file
**Then** the system MUST (a) accept both `application/json` with `documento_b64` field (size cap 5MB enforced by Pydantic `String(max_length=7_000_000)` — base64-encoded 5MB binary ≈ 6.67M chars, cap at 7M to be safe) AND `multipart/form-data` upload via `POST /api/v1/documentos/upload` (`file: <binary>`, `uuid_sucursal`, `tipo`, `formato`, `metadata`) — server stores base64 internally but accepts the streamed representation client-side; (b) for `multipart/form-data`, the server emits a 201 with the new row's `uuid`; (c) for legacy `application/json`, Pydantic validates the base64 size cap; (d) the `documento_b64` column is readable in full (no truncation), writes are managed through `versioned.close_and_insert()` (it's `[V]`); (e) `documentos` size cap is configurable via `configuracion_seguridad` future extension (out of scope now)

### REQ-OP-06-BULK-OPS: Defer to separate change (Q6)
**Given** the canonical 49-table surface
**When** the question of bulk operations like `POST /catalogos/<x>:batch` CSV arises
**Then** the system MUST NOT expose any bulk endpoint in this change — Q6 deferred to a separate change after operators validate the per-row idempotency machinery (REQ-OP-04). Rationale: per-row idempotency composes; bulk would need a separate `bulk_operation_id` mechanism (Stripe-style) and a different sync replication story. Documented in this spec as out-of-scope; no router may be added without an ADR

### REQ-OP-07-PERMISOS-USUARIO-REVOKE: Bi-temporal close (Q7)
**Given** a `permisos_usuario` row R with `estado='activo'`, `vigente_hasta IS NULL`
**When** the admin calls `PUT /api/v1/permisos-usuario/{R.uuid}` with the same body (to revoke) and an `Idempotency-Key`
**Then** the system MUST (a) close R via `versioned.close_and_insert()`: R UPDATE SET `vigente_hasta = NOW()`, `estado = 'inactivo'`; INSERT new row R' with `uuid_permiso` cleared (`null` is not allowed by the schema — instead, R' carries the same `uuid_permiso` but a different `vigente_desde` and an explicit `datos_nuevos.motivo='revocado'` snapshot in `log_transaccional`); (b) only `admin-` token allowed; (c) NO explicit `revocado` boolean exists on the table — the historical `vigente_hasta` IS the revoke marker; (d) the audit row in `log_transaccional` carries `accion='revocar'`. The read API (`GET /api/v1/permisos-usuario?uuid_usuario=X`) returns only `vigente_hasta IS NULL` rows by default; the history endpoint surfaces the full chain

### REQ-OP-08-RECLAMOS-POLYMORPHIC-FK-VALIDATION: Strict Pydantic + Redis cache (Q8)
**Given** a `POST /api/v1/reclamos` with `tipo_reclamable` and `uuid_reclamable`
**When** the validator runs
**Then** see `workflow-transitions.md` REQ-23-W-POLYMORPHIC-FK — repeated here for visibility: Pydantic `model_validator(mode='after')` confirms a row exists in `tipo_reclamable`'s named table with `uuid_reclamable`; cloud-side validator consults a Redis cache (60s TTL, populated by sync worker when `ingreso`, `salidas`, `facturas`, `subscripciones_cliente` rows arrive) to avoid cross-network synchronous DB validation; on cache miss, falls back to direct DB read; no polymorphic physical FK exists (the FK is replaced by application-level validation per `modelo_datos_er.mmd` row comment)

### REQ-OP-09-FACTURA-PAGOS-REVERSO-1TO1: Partial unique index + ORM helper (Q9)
**Given** a successful `factura_pagos` `tipo_movimiento='pago'` row P
**When** an operator posts a reverso: `POST /api/v1/factura-pagos {tipo_movimiento:'reverso', uuid_pago_revertido:P.uuid, ...}`
**Then** see `append-only-events.md` REQ-15-A-COMPENSATION — repeated here for visibility: the migration adds `CREATE UNIQUE INDEX IF NOT EXISTS uq_factura_pagos_reverso ON prod.factura_pagos (uuid_pago_revertido) WHERE tipo_movimiento = 'reverso' AND uuid_pago_revertido IS NOT NULL;` (Postgres allows multiple NULLs on partial index). The ORM helper `parkos_core/repo/factura_pagos.py::reverse_payment()` raises `DuplicateReversoError` (mapped to 409) on second attempt. `uuid_pago_revertido` is required by Pydantic when `tipo_movimiento='reverso'` (422 otherwise); forbidden (must be null) when `tipo_movimiento='pago'`

### REQ-OP-10-ALERTA-DESCARTADA: Admin-only rejection branch (Q10)
**Given** an `alerta` chain in `estado='en_revision'` with assigned `uuid_usuario=U1`
**When** a transition to `descartada` is attempted
**Then** see `workflow-transitions.md` REQ-26-W-ALERTA-DESCARTADA — repeated here: only `admin-` tokens may transition to `descartada`; U1 is forbidden even with `permisos.descartar_alerta` granularity (defense in depth). The transition writes a `log_transaccional` row (`accion='rechazar'`) for audit

### REQ-OP-11-LOGIN-LOCKOUT-SLIDING-WINDOW: 3 fails / 15 min / 30 min (Q11)
**Given** the auth service's lockout machinery
**When** a login attempt fails (or succeeds)
**Then** see `session-cycles.md` REQ-43-S-LOGIN-FAILURE — repeated here with concrete numerics: (a) sliding 15-minute window (default; overrides via `configuracion_seguridad.minutos_ventana_login` if present in the row); (b) 3 failure threshold (default `configuracion_seguridad.max_intentos_login`); (c) 30-minute lockout (`configuracion_seguridad.minutos_bloqueo_login`); (d) counter is reset bi-temporally on successful login (close+insert on `usuarios`); (e) the user is suspended via a `usuarios` close+insert on exceeding attempts, restored either manually by admin or auto after lockout elapses + correct password (admin-restored path is the canonical)

### REQ-OP-12-V-RESOLUCION-CONSECUTIVO-LIVE: Materialized view choice (Q12)
**Given** the `V_RESOLUCION_CONSECUTIVO` view that exposes `MAX(consecutivo)` per `uuid_resolucion_facturacion`
**When** the `factura_electronica` insert path needs the next `consecutivo`
**Then** the system MUST treat `V_RESOLUCION_CONSECUTIVO` as a LIVE `VIEW` (not materialized) — the DDL is `CREATE VIEW prod.v_resolucion_consecutivo AS SELECT uuid_resolucion_facturacion, MAX(consecutivo) AS consecutivo FROM prod.factura_electronica GROUP BY uuid_resolucion_facturacion`. Rationale (Q12 resolution): per resolution the row set is small (typically < 10k rows), live query perf is acceptable; the atomic mutation in REQ-34 (`SELECT ... FOR UPDATE` on the `resolucion_facturacion` row + read of view + INSERT in same TX) is the serialization point — two concurrent emissions on the same branch serialized by the resolucion row's lock. The online path takes < 5ms on the bench; offline path is preliminary row + sync queue (REQ-34 + REQ-OP-04)

### REQ-OP-13-RBAC-FRAMEWORK: FastAPI dependency `require_permission()` (AD-2)
**Given** the framework needs to expose RBAC at the API layer (defense in depth, alongside DB REVOKE + triggers)
**When** any router needs a permission check
**Then** the system MUST (a) ship a FastAPI dependency `require_permission(codigo: str)` in `parkos_core/auth/permissions.py` that (a1) parses the JWT (issuer auto-resolved), (a2) reads `permisos_usuario` for the JWT subject, (a3) returns 403 `{"error": "permission_denied", "detail": "<codigo>"}` if not in the active set; (b) the dependency is wired to every router that mutates state — for example `anulaciones.aprobar` requires `require_permission("aprobar_anulacion")`; (c) the matrix population is DEFERRED (matrix authoring is a separate change) — for v1, the canonical permissions are seeded by an Alembic migration `0003_seed_permisos_canonicos.py` with permissions like `aprobar_anulacion`, `ejecutar_anulacion`, `crear_arqueo`, `solicitar_reverso`, `cerrar_sesion`, `descartar_alerta`, etc. The DB REVOKE + trigger on `permisos_usuario` (e.g. a `BEFORE INSERT OR UPDATE OR DELETE` trigger that ensures only admin- token rows are allowed via `current_setting('jwt.claim.iss')` GUC) prevents non-admin writes — token check at DB layer is a final defense if API is bypassed

### REQ-OP-14-OPENAPI-RUNTIME: Per-audience tag split artifact
**Given** the OpenAPI generator runs at PR time
**When** the artifact is emitted
**Then** the system MUST emit TWO separate JSON files: `api_admin/openapi.json` (tags: `admin`, `operador`, `sync`, `cloud-only`) and `api_sucursal/openapi.json` (tags: `operador`, `sync` — NO `admin` mutations, NO `cloud-only`). Each tag is the AUDIENCE the PWA consumes; the PWAs do not load the full JSON. CI test asserts that `api_sucursal/openapi.json` contains no paths under the `admin` tag, no `cloud-only` paths, and no DELETE operations

### REQ-OP-15-SUCURSAL-SELF-REGISTRATION: Operador may self-register with admin pre-approval
**Given** the rubric in the exploration note (`usuarios` straddles the catalog/branch-originated boundary)
**When** an operador at branch B with `admin-` pre-approval token attempts to register a new operador
**Then** the system MUST (a) require a `permite_crear_operador` claim in the bearer admin- token (issued by an `admin-` token holder); (b) insert the `usuarios` row with `rol='operador'`, `created_by = <admin-issuer uuid>`; (c) send a JWT activation link to the new user's email (link generation out of scope here); (d) without the admin- token, return 403 `permission_denied`. The Operator registration flow is fully bi-temporal like any other `usuarios` close+insert

---

## Scenarios

### SC-OP-01-PAGINATION-CURSOR-ITERATION: Walk full catalog
1. Client `GET /api/v1/tipo-persona?limit=50`. Response: `{items: [...50 rows...], next_cursor: "eyJ2aWdlbnRlX2Rlc2RlIjogIjIwMjYtMDktMDJUMDA6MDA6MDAiLCAidXVpZCI6ICJhYWFhYWFhLWJiYmItY2NjYy1kZGRkLWVlZWVlZWVlZWVlZWUiLCAicmVzb3VyY2UiOiAidGlwb19wZXJzb25hIn0="}`.
2. Client decodes: `{ vigente_desde: "...", uuid: "aaaaaaa-...", resource: "tipo_persona" }`.
3. Client `GET /api/v1/tipo-persona?limit=50&cursor=<opaque>`. Service applies `WHERE (vigente_desde, uuid) < (decoded.vigente_desde, decoded.uuid)`. Returns next page.
4. Final response has `next_cursor: null` (or empty). Iteration ends.

### SC-OP-02-IDEMPOTENCY-REPLAY: Double-submit returns same response
1. Client POSTs `POST /api/v1/auth/login ...` with `Idempotency-Key: 11111111-1111-1111-1111-111111111111`. `idempotency_keys` row inserted with `endpoint='auth/login'`, `key_hash=...`, `response_status=200`, `response_body={...}`. Response: 200 + tokens.
2. Network blip; client retries the SAME POST with the SAME `Idempotency-Key`. Helper sees existing row, `expires_at > NOW()`, returns the cached response with header `Idempotent-Replay: true` and same status/body. NO new `login` row is inserted; NO new tokens are issued. The internal `actor_real_id` of the cached login reflects the original subject only.
3. After 24h, the row's `expires_at` is past. Nightly TTL worker deletes the row. New POST proceeds normally with a new write.

### SC-OP-03-PERMISOS-USUARIO-REVOKE: Bi-temporal revoke with history
1. Admin grants P: `POST /api/v1/permisos-usuario {uuid_usuario: U, uuid_permiso: P1}`. Row G1 created (root, vigente_desde = T0).
2. Admin revokes via PUT (same body, no new fields): close+insert on G1 → G2 (vigente_desde = T1, vigente_hasta = NULL, audit log with motivo='revocado').
3. `GET /api/v1/permisos-usuario/{U}` (read-active endpoint) returns empty (G1 is now `vigente_hasta=T1`).
4. `GET /api/v1/permisos-usuario/{U}/historial` returns `[G1 (estado=inactivo, motivo=...), G2]`.
5. No `revocado` flag exists in any row's columns; the historical close IS the marker.

### SC-OP-04-RBAC-DEPENDENCY: Permission check rejects unauthorized role
1. Operador O1 calls `POST /api/v1/anulaciones {estado:'aprobada', ...}` on branch B's data.
2. `require_permission('aprobar_anulacion')` runs: looks up `permisos_usuario` for O1 with `vigente_hasta IS NULL` AND joins `permisos.codigo='aprobar_anulacion'`.
3. Returns 0 rows → 403 `{"error": "permission_denied", "detail": "aprobar_anulacion"}`. No DB INSERT.
4. Admin A1 retries same → granted (admin has all permissions by default; `permisos_usuario` is the canonical store). Succeeds.

### SC-OP-05-DOCUMENTOS-MULTIPART: Streamed upload
1. Operator POSTs `POST /api/v1/documentos/upload` with `multipart/form-data` body containing `<file>` (2MB PNG).
2. Server reads the streaming body, base64-encodes in memory (cap check: 5MB), INSERT into `documentos` via `versioned.close_and_insert()` (new row if first version).
3. Response 201 with `Read` payload including `documento_b64` field (echo of the stored canonical form). Subsequent GETs return the same row.

### SC-OP-06-CONFIG-OVERRIDE-FALLBACK: Default global when no override
1. Cloud-admin writes `POST /api/v1/configuracion-seguridad {uuid_sucursal: null, max_intentos_login: 5, minutos_bloqueo_login: 30, minutos_ventana_login: 15}`. Expect 201 (global default).
2. Branch A reads via `GET /api/v1/configuracion-seguridad/efectiva?uuid_sucursal=A`. Helper: no override row exists for A → fall back to global default (uuid_sucursal IS NULL row).
3. Admin writes override for A: max_intentos_login=10. Subsequent read at A returns 10; at B returns 5.
4. The override pattern is documented in `bi-temporal-crud.md` SC-03.

---

## Constraints

- **C-OP1**: No bulk-operation endpoint may be added without an ADR (REQ-OP-06).
- **C-OP2**: `idempotency_keys` is the 50th `[A]`-class table; follows the same REVOKE + trigger pattern as the other 12 `[A]`s. Added by migration `0002_add_idempotency_keys.py` in PR7.
- **C-OP3**: `V_RESOLUCION_CONSECUTIVO` is a LIVE view (not materialized). REQ-34 in `lifecycle-events.md` explains the concurrent-emission serialization.
- **C-OP4**: Cursor stability: order key MUST be `(vigente_desde DESC, uuid ASC)` for `[V]`; equivalent for other classes. Different ordering breaks cursor stability under concurrent writes.
- **C-OP5**: OpenAPI artifacts are committed as JSON, pinned by git SHA. Codegen is offline (CI), not consumer-runtime.
- **C-OP6**: The DIAN `consecutivo_actual` mutation is atomic per resolution (not just per branch). Cloud and branches both serialize on the same `resolucion_facturacion` row lock.

## Out of scope

- `multipart/form-data` size > 5MB (object storage or S3-style out of band — separate change).
- WebAuthn / passkeys (v2).
- BFF (v2).
- WebSocket sync (v2).
- Bulk CSV import (separate change).
- Factus / DIAN provider HTTP (separate change).

## Dependencies

- `parkos_core/repo/idempotency.py` — `guard()` helper (depends on migration `0002_add_idempotency_keys.py`).
- `parkos_core/repo/versioned.py` — `close_and_insert()` for `permisos_usuario` revoke and `configuracion_seguridad` overrides.
- `parkos_core/repo/factura_pagos.py::reverse_payment()` — compensating row helper.
- `parkos_core/auth/permissions.py::require_permission()` — RBAC framework dependency.
- ADR references: AD-1, AD-2, AD-3, AD-4. Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q9, Q10, Q11, Q12 ALL closed in this spec.
- Engram topic: `sdd/create-49-table-apis/spec`.
