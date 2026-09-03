# Design: create-49-table-apis

> **Change**: `create-49-table-apis`
> **Phase**: design (sdd-design)
> **Status**: ready for `sdd-tasks`
> **Preflight cached**: `pace=auto`, `artifact=hybrid`, `delivery=auto-chain`, `chain=gitflow`, `review_budget=800 lines/PR`
> **Inputs read**: `proposal.md` (644 lines), `exploration.md` (345 lines), all 7 specs (`bi-temporal-crud.md` 100, `append-only-events.md` 109, `workflow-transitions.md` 113, `lifecycle-events.md` 107, `session-cycles.md` 90, `cross-cutting.md` 114, `operational.md` 152), `modelo_datos_er.mmd` (1178 lines, 49 tables), `AGENTS.md`, `bootstrap-monorepo-foundation/design.md` (monorepo skeleton commitments), `bootstrap-monorepo-foundation/tasks.md` (F1 walking skeleton). Engram #1264 (explore), #1265 (propose), #1266 (spec).

## 1. Architecture overview

The change layers on top of `bootstrap-monorepo-foundation` (PR1–PR6 already shipped on `dev`) and converts the 49 entities in `modelo_datos_er.mmd` into a typed, tenant-scoped, DIAN-aware API surface. The bootstrap change owns the monorepo skeleton, `parkos_core` package layout, `dian/{common,cloud,branch}/` split, the 49-table Alembic `0001_initial_schema.py` with REVOKE + triggers + `pg_partman` partitions + hash-chain genesis, and the `entrypoint.sh` verifier. This change adds the application code on top.

```
+-----------------------------------------------------------------------------+
| web_admin (PWA)            web_sucursal (PWA, offline-first, branch-pinned) |
|  Zustand, RHF, Zod         indexedDB, service-worker, preliminar badge     |
+------------+--------------------+--------------------------------------------+
             | HTTPS              | HTTPS (X-Sucursal-Context for admin)
             v                    v
+-------------------------+   +-----------------------------------+
| api_admin (cloud)       |   | api_sucursal (branch)             |
| FastAPI + parkos_core   |   | FastAPI + parkos_core             |
| JWT: admin- | sync-     |   | JWT: operador- | sync-agent-       |
| tags: admin,operador,   |   | tags: operador, sync              |
|        sync, cloud-only |   | NO cloud-only routers mounted     |
+-------------------------+   +-----------------------------------+
             |                          |
             | /sync/{pair,push,pull,events} over HTTPS (HTTP polling)
             |                          |
+-------------------------+   +-----------------------------------+
| job_sync_cloud          |   | job_sync_sucursal                 |
| - applies branch rows   |   | - bundles local inserts          |
| - extends hash chain    |   | - stamps per-branch monotonic seq |
| - emits SyncBackEvent   |   | - retries on transient failures   |
+-------------------------+   +-----------------------------------+
             |                          |
             v                          v
+-------------------------------------------------------+
| PostgreSQL 16+ (cloud)            PostgreSQL 16+ (branch)
| schema prod.* (49 tables)          schema prod.* (49 tables)
| rol_app + REVOKE on 11 [A] tables  same REVOKE pattern
| pg_partman 8 partitions            same partition parents
| hash chain per uuid_sucursal       chain extends branch-side
| AFTER INSERT trigger -> sync_queue AFTER INSERT trigger -> sync_queue
|                                  (local-only, no propagation)
+-------------------------------------------------------+
```

The three layers of defense in depth (per AGENTS.md §1 and §3):

1. **API layer**: zero `DELETE` routes (CI grep on `openapi.json`); `require_permission()` dependency; `Idempotency-Key` middleware; tenant-scope guard.
2. **ORM layer**: `parkos_core/repo/{versioned,workflow,session_cycle,append_only,event,hash_chain,idempotency,factura_pagos}.py` are the ONLY writers for state-changing operations; AST test rejects `session.execute(update/delete)` against `[V]/[L-E]/[L-W]/[A]` class names outside those modules.
3. **DB layer**: `REVOKE UPDATE, DELETE FROM rol_app` on 11 `[A]` tables (sync_queue excluded — carve-out); `BEFORE UPDATE OR DELETE` trigger `prod.fn_<table>_inmutable()`; `BEFORE UPDATE` trigger on `[L-S]` requiring co-transactional `log_transaccional` row.

The cloud / branch asymmetry is captured at four boundaries:

- **Image-level**: the branch image does NOT include `parkos_core/dian/cloud_router.py` and `parkos_core/dian/cloud/` (factus_dispatcher, atomic_next_consecutivo). The cloud image does. The branch Dockerfile's `.dockerignore` excludes `**/dian/cloud/**`; a `Dockerfile.cloud`-only multi-stage target `COPY`s `parkos_core/dian/cloud/`.
- **Module-level**: `parkos_core/api/v1/__init__.py` performs a lazy import of `dian.cloud_router` only when `os.environ.get("PARKOS_DEPLOY") == "cloud"`; importing on branch raises `ImportError("cloud_router_unavailable_on_branch")`.
- **Router-level**: even if a branch image accidentally imported the module, the JWT scope guard REQ-X7 (REQ-X8 for sync) rejects `operador-` tokens on cloud-only paths.
- **OpenAPI-level**: the build-time generator emits TWO artifacts (`api_admin/openapi.json` includes `cloud-only` tag paths; `api_sucursal/openapi.json` does not); the branch artifact is CI-grepped for `/factura-electronica/`, `/revocacion-factura/`, `/envio-dian/`, `/validacion-evento/` paths.

## 2. Module layout

The layout extends the `bootstrap-monorepo-foundation` skeleton (which already places models partitioned by audit level under `backend/packages/parkos_core/models/`). This change fills in the schemas, helpers, auth, routers, and tests.

```
backend/
├── pyproject.toml                              # uv workspace marker (PR1 of bootstrap)
├── packages/
│   ├── parkos_core/                            # The shared library. Built first.
│   │   ├── pyproject.toml
│   │   ├── migrations/
│   │   │   ├── env.py                          # include_schemas=True (bootstrap)
│   │   │   ├── script.py.mako
│   │   │   └── versions/
│   │   │       ├── 0001_initial_schema.py      # bootstrap (49 tables + REVOKE + triggers + partitions + genesis)
│   │   │       ├── 0002_add_idempotency_keys.py  # NEW (PR7, AD-3)
│   │   │       ├── 0003_seed_permisos_canonicos.py  # NEW (PR1, REQ-OP-13)
│   │   │       ├── 0004_add_factura_pagos_reverso_index.py  # NEW (PR6, REQ-OP-09)
│   │   │       └── ...
│   │   ├── config.py                           # pydantic-settings (bootstrap)
│   │   ├── db/
│   │   │   ├── base.py                         # DeclarativeBase (bootstrap)
│   │   │   ├── engine.py                       # async engine + sessionmaker (bootstrap)
│   │   │   ├── tenancy.py                      # ContextVar for uuid_sucursal (bootstrap; extended in PR1)
│   │   │   └── triggers.py                     # NEW Alembic helper: create_a_table_with_trigger()
│   │   ├── models/                             # 49 tables, partitioned by enforcement class
│   │   │   ├── V/                              # 26 files, one per [V] table (PR1, PR3, PR4, PR5)
│   │   │   │   ├── __init__.py                 # re-exports for Alembic discovery
│   │   │   │   ├── usuarios.py
│   │   │   │   ├── permisos.py
│   │   │   │   ├── permisos_usuario.py
│   │   │   │   ├── ...
│   │   │   │   └── sub.py                      # sub-package helper: shared mixins (V mixin applied)
│   │   │   ├── L_E/                            # 3 files (PR5, PR6)
│   │   │   ├── L_W/                            # 6 files (PR6, PR7)
│   │   │   ├── L_S/                            # 2 files (PR1, PR7)
│   │   │   ├── A/                              # 12 files + 1 idempotency_keys (PR2, PR6, PR7)
│   │   │   └── base.py                        # NEW: shared abstract bases (see §3.2)
│   │   ├── schemas/                            # Pydantic v2 (PR1–PR7)
│   │   │   ├── auth.py
│   │   │   ├── catalogos.py
│   │   │   ├── clientes.py
│   │   │   ├── operacion.py
│   │   │   ├── caja.py
│   │   │   ├── workflows.py
│   │   │   ├── empresa.py
│   │   │   ├── configuracion.py
│   │   │   ├── dian.py                         # cloud-only schema subset (REQs from lifecycle-events + workflow-transitions)
│   │   │   ├── sync_infra.py                   # local-only sync endpoints schemas
│   │   │   ├── common.py                       # NEW: Filter/ReadList/cursor base models
│   │   │   └── idempotency.py                  # NEW: AD-3 schemas
│   │   ├── repo/                               # NEW: All state-changing logic lives here (defense in depth, REQ cross-cutting)
│   │   │   ├── versioned.py                    # [V] close_and_insert() (PR1)
│   │   │   ├── event.py                        # [L-E] record_event() (PR5)
│   │   │   ├── workflow.py                     # [L-W] append_transition(), read_chain_tip() (PR6)
│   │   │   ├── session_cycle.py                # [L-S] open_session(), close_session_with_log() (PR1, PR7)
│   │   │   ├── append_only.py                  # [A] append_event() (PR2)
│   │   │   ├── hash_chain.py                   # log_transaccional + revocacion_factura chain (PR2)
│   │   │   ├── factura_pagos.py                # NEW: reverse_payment() compensating-row helper (PR6, REQ-OP-09)
│   │   │   ├── idempotency.py                  # NEW: guard() middleware helper (PR7, AD-3)
│   │   │   ├── sync_outbox.py                  # NEW: no-op facade; confirms DB trigger is doing enqueue (PR2)
│   │   │   └── pagination.py                   # NEW: encode/decode opaque cursor (PR1, REQ-OP-01)
│   │   ├── auth/                               # NEW (extends bootstrap's stub)
│   │   │   ├── jwt_issuer_guard.py             # NEW: three-issuer verification, requires_issuer() dep (PR1)
│   │   │   ├── permissions.py                  # NEW: require_permission(codigo) (PR1, REQ-OP-13)
│   │   │   ├── passwords.py                    # bootstrap (bcrypt 12+)
│   │   │   ├── tenancy.py                      # NEW: enforce_operador_scope + admin_ctx (PR1, REQ-X1/X2)
│   │   │   └── tokens.py                       # NEW: issue/verify/rotate for admin-/operador-/sync-agent-
│   │   ├── api/                                # NEW: shared router building blocks (PR1)
│   │   │   ├── router_factory.py               # NEW: make_router() — generic C/Q/U surface
│   │   │   ├── deps.py                         # NEW: get_session, get_current_actor, get_tenant_ctx
│   │   │   ├── middleware.py                   # NEW: IdempotencyKeyMiddleware
│   │   │   └── v1/                             # NEW: per-domain routers
│   │   │       ├── __init__.py                 # lazy import of dian.cloud_router (DIAN boundary)
│   │   │       ├── auth.py                     # /auth/login, /auth/refresh, /auth/logout
│   │   │       ├── catalogos.py                # 9 catalog routers
│   │   │       ├── empresa.py
│   │   │       ├── sucursal.py
│   │   │       ├── configuracion.py
│   │   │       ├── clientes.py
│   │   │       ├── operacion.py                # ingreso, salidas
│   │   │       ├── facturacion.py              # facturas + (cloud-only: factura-electronica via import)
│   │   │       ├── caja.py
│   │   │       ├── caja_sesion.py              # sesion open/close
│   │   │       ├── workflows.py                # anulaciones, reclamos, alerta, reimpresion_ticket
│   │   │       ├── arqueo.py
│   │   │       └── sync.py                     # POST /sync/{pair,push,pull,events}
│   │   ├── dian/                               # Cloud-only branch of the boundary
│   │   │   ├── common/                         # bootstrap: ProvisionalNumber, SyncBackEvent, NumerationMode
│   │   │   ├── cloud/                          # bootstrap: FacturaElectronicaBuilder, dian_dispatcher
│   │   │   │                                  # (out of scope here; this change imports but does NOT implement)
│   │   │   ├── cloud_router.py                 # NEW (PR6): routers for factura-electronica, envio-dian, validacion-evento, revocacion-factura-webhook
│   │   │   └── branch/                         # bootstrap: ProvisionalNumber consumer
│   │   ├── sync/                               # bootstrap: sync transport/queue_processor/conflict_policy/sync_back (out of scope here)
│   │   ├── workers/                            # bootstrap: hash_chain_verifier, dian_dispatcher entrypoints (out of scope here)
│   │   ├── openapi.py                          # NEW: generator CLI (uv run python -m parkos_core.openapi)
│   │   └── structlog_config.py                 # NEW: log binding for actor_real_id, actor_impersonado_id, request_id
│   ├── api_admin/                              # Cloud-only deployable
│   │   ├── pyproject.toml                      # deps: parkos_core, fastapi, uvicorn
│   │   ├── src/api_admin_main/
│   │   │   ├── __main__.py                     # uvicorn entrypoint
│   │   │   └── app.py                          # FastAPI app factory; mounts all routers
│   │   └── openapi.json                        # NEW (committed artifact)
│   ├── api_sucursal/                           # Branch-side deployable
│   │   ├── pyproject.toml
│   │   ├── src/api_sucursal_main/
│   │   │   ├── __main__.py
│   │   │   └── app.py                          # mounts operador + sync routers only
│   │   └── openapi.json                        # NEW (committed artifact)
│   ├── job_sync_cloud/                         # bootstrap (out of scope here)
│   └── job_sync_sucursal/                      # bootstrap (out of scope here)
├── tests/                                      # NEW
│   ├── conftest.py                             # testcontainers Postgres + Redis + admin/operador/sync-agent JWT mint helpers
│   ├── migrations/
│   │   ├── test_a_inmutable.py                 # NEW (PR1): 12 fixtures, one per [A] table — INSERT then UPDATE/DELETE expects <TABLE>_INMUTABLE
│   │   ├── test_ls_session_guard.py            # NEW (PR1): 2 fixtures — UPDATE on sesion/login without prior log row raises LOG_TRANSACCIONAL_REQUIRED
│   │   ├── test_revokes_active.py              # NEW (PR1): has_table_privilege('rol_app', ..., 'UPDATE') = f on the 11 [A] tables
│   │   ├── test_partman_parents.py             # NEW (PR1): 8 partman.part_config rows present
│   │   ├── test_hash_chain_genesis.py          # NEW (PR2): per uuid_sucursal, first log_transaccional has hash_anterior = sha256(b"genesis:" + uuid_sucursal_bytes)
│   │   ├── test_idempotency_keys_inmutable.py  # NEW (PR7): 50th table has REVOKE + trigger
│   │   └── test_factura_pagos_reverso_index.py # NEW (PR6): partial unique index rejects duplicate reverso
│   ├── static/
│   │   ├── test_no_delete_routes.py            # NEW (PR1): grep generated openapi.json for `delete:` operations
│   │   ├── test_no_raw_upsert_on_v_tables.py   # NEW (PR1): AST scan rejects session.execute(update(...)) against [V] class names outside versioned.close_and_insert
│   │   ├── test_no_raw_dml_on_a_tables.py      # NEW (PR1): AST scan rejects session.execute(update/delete) against [A] class names outside append_only.append_event / sync_queue carve-outs
│   │   ├── test_no_raw_dml_on_lw_tables.py     # NEW (PR6): AST scan rejects session.execute(update/delete) against [L-W] class names outside workflow.append_transition
│   │   ├── test_no_raw_dml_on_le_tables.py     # NEW (PR5): AST scan rejects session.execute(update/delete) against [L-E] class names outside event.record_event
│   │   ├── test_no_raw_dml_on_ls_tables.py     # NEW (PR1): AST scan rejects session.execute(update) against [L-S] class names outside session_cycle helpers
│   │   ├── test_dian_boundary_branch.py        # NEW (PR6): ImportError when branch image imports parkos_core.dian.cloud_router
│   │   ├── test_openapi_branch_excludes_cloud.py  # NEW (PR1): jq check on api_sucursal/openapi.json — zero paths under cloud-only tags
│   │   └── test_openapi_no_delete_operations.py   # NEW (PR1): jq check on both openapi.json files — zero delete operations
│   ├── unit/
│   │   ├── test_versioned_close_and_insert.py  # PR1
│   │   ├── test_event_record.py                # PR5
│   │   ├── test_workflow_append_transition.py  # PR6
│   │   ├── test_workflow_read_chain_tip.py     # PR6 (REQ-X9 tie-break deterministic)
│   │   ├── test_append_only.py                 # PR2
│   │   ├── test_hash_chain_append.py           # PR2 (REQ-OP-12 + REQ-X4)
│   │   ├── test_hash_chain_break.py            # PR2 (SC-X3 out-of-order)
│   │   ├── test_factura_pagos_reverse.py       # PR6 (REQ-OP-09)
│   │   ├── test_idempotency_guard.py           # PR7 (REQ-OP-04 + SC-OP-02)
│   │   ├── test_idempotency_ttl.py             # PR7
│   │   ├── test_session_cycle_open_close.py    # PR7 (REQ-41-S-CLOSE)
│   │   ├── test_session_cycle_login_failure_lockout.py  # PR7 (REQ-43-S-LOGIN-FAILURE)
│   │   ├── test_jwt_issuer_guard.py            # PR1 (cross-audience)
│   │   ├── test_permissions_dependency.py      # PR1 (REQ-OP-13)
│   │   ├── test_tenancy_operador.py            # PR1 (REQ-X1)
│   │   ├── test_tenancy_admin.py               # PR1 (REQ-X2)
│   │   ├── test_pagination_cursor.py           # PR1 (REQ-OP-01)
│   │   ├── test_reclamos_polymorphic_validator.py  # PR6 (REQ-OP-08)
│   │   └── test_config_override_resolution.py # PR4 (SC-OP-06)
│   └── integration/
│       ├── test_crud_happy_path.py             # full create → read → update → list → history per class
│       ├── test_sync_flow.py                   # bootstrap concern (smoke only here)
│       └── test_branch_offline_flow.py         # SC-33 + SC-34 (preliminar + SyncBackEvent)
└── ...
apps/
└── ui-kit/                                     # bootstrap (PWA — out of scope here; this change ships openapi.json only)
    └── src/api/
        ├── admin/                              # git-pin to api_admin/openapi.json
        └── branch/                             # git-pin to api_sucursal/openapi.json
```

**Justification per folder**:

- `models/{V,L_E,L_W,L_S,A}/` mirrors the 5 enforcement classes (AGENTS.md "Python conventions"); one file per table keeps PR diffs small and reviewable.
- `schemas/` is grouped by **domain** (`catalogos`, `clientes`, `operacion`, `caja`, `empresa`, `dian`), not by enforcement class, because one domain (e.g. `operacion`) spans `[V]` (`clientes`, `vehiculos`), `[L-E]` (`ingreso`), `[A]` (`salidas`). Cross-class domain grouping matches the user's mental model and reduces router sprawl.
- `repo/` is a single directory because all five helpers share concerns: cursor pagination, hash chain, tenant context, idempotency. They are NOT written per-class — they ARE the only writer layer.
- `auth/` is separate from `repo/` because auth has no DB writes of its own (it reads `permisos_usuario`, `usuarios`, `login` via `repo/*`).
- `dian/cloud_router.py` is the SINGLE mount point for cloud-only routes — making it the IMAGE-LEVEL boundary (see §10).
- `tests/migrations/` is separate from `tests/unit/` because the migration tests need a real `testcontainers` Postgres with REVOKE/triggers active; they are not hermetic.
- `tests/static/` houses the AST-scan enforcement tests. These are the third-layer automation of "no DELETE", "no raw UPDATE on `[A]`", etc. — running them in CI is what makes the architectural promise executable.
- `api_admin/openapi.json` and `api_sucursal/openapi.json` are committed artifacts (REQ-OP-02, AD-1 contract surface is uniform); git-pinned by SHA.

## 3. ORM models (49 tables)

### 3.1 Folder structure

`parkos_core/models/` follows the project's hard rule of partitioning by audit level:

| Subfolder | Count | Tables |
|---|---:|---|
| `models/V/` | 26 | `usuarios`, `permisos`, `permisos_usuario`, `usuarios_sucursal`, `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `tipo_sucursal`, `tipo_arqueo`, `impuestos`, `otros_cobros`, `costos_servicios`, `configuracion_tolerancias`, `configuracion_seguridad`, `empresa`, `resolucion_facturacion`, `sucursal`, `documentos`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos` |
| `models/L_E/` | 3 | `ingreso`, `facturas`, `factura_electronica` |
| `models/L_W/` | 6 | `anulaciones`, `reclamos`, `alerta`, `reimpresion_ticket`, `envio_dian`, `validacion_evento` |
| `models/L_S/` | 2 | `login`, `sesion` |
| `models/A/` | 13 | `salidas`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `revocacion_factura`, `caja`, `arqueo`, `log_transaccional`, `sync_queue`, `sync_conflict`, `sync_log`, `idempotency_keys` (50th, PR7) |
| **TOTAL** | **50** | (49 + `idempotency_keys` per AD-3) |

The `models/base.py` module ships the five abstract declarative bases that the audit-level subfolders subclass (see §3.2).

### 3.2 Base class per class

`models/base.py` defines five abstract bases. Each table file subclasses exactly one:

```python
# backend/packages/parkos_core/src/parkos_core/models/base.py
from __future__ import annotations
import uuid as uuid_lib
from datetime import datetime
from sqlalchemy import CHAR, DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

# Universal id_columns: every table has `uuid` PK (CHAR(36) for portability; uuid v4 generated server-side)
class IdMixin:
    uuid: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),  # pgcrypto extension (bootstrap installs it)
        nullable=False,
    )

# Universal audit_columns: created_at, created_by (also mandatory for defense in depth)
class AuditMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
        # Note: NOT a FK to usuarios — usuarios can be closed; the dissolution must survive.
        # The audit layer holds a snapshot of the actor's uuid at write time.
    )

# Universal sync_columns: every replicated table carries them
class SyncMixin:
    sync_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pendiente"
    )  # 'pendiente' | 'sincronizado' | 'error'
    sync_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sync_attempts: Mapped[int] = mapped_column(
        nullable=False, server_default="0"
    )

# [V]: bi-temporal versioning (vigente_desde, vigente_hasta, estado)
class VersionedMixin:
    vigente_desde: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    vigente_hasta: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    estado: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="activo"
    )  # 'activo' | 'inactivo'

# [A] DIAN retention column
class RetentionMixin:
    fecha_retencion_hasta: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
        # DIAN tables set this to NOW() + INTERVAL '5 years' on insert (enforced in helper)
    )

# [A] Hash chain columns — ONLY on log_transaccional + revocacion_factura
class HashChainMixin:
    hash_anterior: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    hash_actual: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    # Server-computed by parkos_core.repo.hash_chain.append(); NEVER client-supplied (Pydantic rejects)

# The five bases combine mixins by class
class Base(DeclarativeBase):
    pass

class VersionedBase(IdMixin, AuditMixin, SyncMixin, VersionedMixin):  # [V]
    __abstract__ = True

class LifecycleEventBase(IdMixin, AuditMixin, SyncMixin):  # [L-E]
    __abstract__ = True

class WorkflowBase(IdMixin, AuditMixin, SyncMixin):  # [L-W] — carries uuid_*_padre FK to self or to a parent event
    __abstract__ = True

class SessionBase(IdMixin, AuditMixin, SyncMixin):  # [L-S]
    __abstract__ = True

class AppendOnlyBase(IdMixin, AuditMixin, SyncMixin, RetentionMixin):  # [A]
    __abstract__ = True
```

### 3.3 Inheritance and mixins

Each audit-level subfolder exports a single concrete base per enforcement class. The mixin composition is fixed per class — `[A]` always has `RetentionMixin` (even when the column is NULL for non-DIAN `[A]`s like `sync_queue`), `[L-E]` and `[L-W]` do not. This way the AST test can statically verify class membership by walking `__mro__`.

`AppendOnlyBase` adds a class-level `__write_only__ = True` marker that the AST scan in `tests/static/test_no_raw_dml_on_a_tables.py` reads:

```python
class AppendOnlyBase(...):
    __abstract__ = True
    __write_only__ = True  # marker consumed by AST tests
```

`VersionedBase` adds `__close_and_insert_only__ = True`. `WorkflowBase` adds `__workflow_only__ = True`. `LifecycleEventBase` adds `__record_only__ = True`. `SessionBase` adds `__session_only__ = True`. The markers carry zero runtime cost; they are metadata.

### 3.4 Per-table file naming

`<table_name>.py` per table, e.g. `models/V/usuarios.py` for `usuarios`. Each file exports exactly one ORM class named in PascalCase matching the snake_case file. Example:

```python
# backend/packages/parkos_core/src/parkos_core/models/V/usuarios.py
from sqlalchemy import BigInteger, String, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from ..base import VersionedBase

class Usuarios(VersionedBase):
    __tablename__ = "usuarios"
    # business-key columns (per modelo_datos_er.mmd row comment + actual columns)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[str] = mapped_column(String(32), nullable=False)  # 'admin' | 'operador'
    # No requiere_totp here — see operational.md REQ-OP-15 for the future flag

    __table_args__ = (
        Index("ix_usuarios_email", "email"),
        {"schema": "prod", "extend_existing": True},
    )
```

`extend_existing=True` is critical because the bootstrap Alembic `0001_initial_schema.py` creates the table first; ORM models must not fight it. The bootstrap migration owns the column types verbatim; this change re-asserts the column types for SQLAlchemy introspection but does NOT generate new DDL. `alembic check` exits 0 because the model metadata matches the live schema.

`models/__init__.py` performs `from .V import *` (and the other four) so Alembic's `env.py` `target_metadata = Base.metadata` sees all 50 tables. Each subfolder has its own `__init__.py` that re-exports the classes for direct import (`from parkos_core.models.V.usuarios import Usuarios`).

`models/A/idempotency_keys.py` is the 50th table (AD-3). It is `[A]`-class: `REVOKE UPDATE, DELETE FROM rol_app` + `BEFORE UPDATE OR DELETE` trigger per `openspec/config.yaml` `rules.tasks`. Migration `0002_add_idempotency_keys.py` (PR7) ships both in the SAME migration script.

## 4. Repository helpers (5 patterns + 3 cross-cutting)

The `repo/` package is the single allowed writer layer. The API routers (`api/v1/*.py`) MUST NOT call `session.add(...)` or `session.execute(...)` for INSERT/UPDATE/DELETE on `[V]/[L-E]/[L-W]/[L-S]/[A]` tables — they call helpers. The AST tests in `tests/static/` enforce this.

### 4.1 versioned.py — close + insert for [V]

```python
# backend/packages/parkos_core/src/parkos_core/repo/versioned.py
from __future__ import annotations
from datetime import datetime
from typing import Type, TypeVar
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.base import VersionedBase

T = TypeVar("T", bound=VersionedBase)

class VersioningError(Exception): ...
class BusinessKeyConflictError(VersioningError): ...

async def close_and_insert(
    session: AsyncSession,
    model_cls: Type[T],
    current_uuid: uuid.UUID,        # the row to close
    new_attrs: dict,                # business-key + payload for the new row
    actor_uuid: uuid.UUID,          # JWT subject
    log_tx: bool = True,            # write a log_transaccional row (default True)
) -> T:
    """Bi-temporal Actualización: close current version + insert new version.

    1. UPDATE current SET vigente_hasta = NOW(), estado = 'inactivo' WHERE uuid = :cu.
       (NOTE: this UPDATE is allowed because it's part of the documented
       close+insert pattern; [V] tables do NOT carry REVOKE. [A] tables DO carry
       REVOKE — see append_only.py below which has no such UPDATE.)
    2. INSERT new row with vigente_desde = NOW(), vigente_hasta = NULL, estado = 'activo',
       created_by = :actor.
    3. If log_tx: insert a log_transaccional row in the SAME TX (via hash_chain.append or
       append_only.append_event for log_transaccional).
    4. Return the new row instance (await session.refresh(new_row) at caller's discretion).

    Raises:
        RowNotFound:     current_uuid doesn't match any row.
        BusinessKeyConflictError: a UK collision is detected (Pydantic-validated upstream).
    """
    ...

async def current_version(
    session: AsyncSession, model_cls: Type[T], uuid: uuid.UUID
) -> T | None:
    """SELECT ... WHERE uuid = :uuid AND vigente_hasta IS NULL LIMIT 1."""
    result = await session.execute(
        select(model_cls).where(
            model_cls.uuid == uuid,
            model_cls.vigente_hasta.is_(None),
        )
    )
    return result.scalar_one_or_none()

async def history(
    session: AsyncSession, model_cls: Type[T], uuid: uuid.UUID, *,
    limit: int = 200, cursor: Cursor | None = None,
) -> list[T]:
    """Order by vigente_desde DESC, uuid ASC. Same cursor pagination as list_with_cursor."""
    ...

async def list_with_cursor(
    session: AsyncSession, model_cls: Type[T], *,
    filters: dict, cursor: Cursor | None, limit: int,
    base_query: Select | None = None,  # tenant scoping starts here
) -> tuple[list[T], Cursor | None]:
    """Generic cursor pagination ordered by (vigente_desde DESC, uuid ASC).
    Cursor is opaque base64({vigente_desde, uuid, resource})."""
    ...
```

**Side effects on commit**: `log_transaccional` row written via `append_only.append_event(session, log_transaccional, payload, actor)` in the same TX. The DB `AFTER INSERT` trigger on `[A]` enqueues a `sync_queue` row automatically — no manual enqueue.

**Exception classes**:
- `RowNotFound`: mapped to HTTP 404 by the router.
- `BusinessKeyConflictError`: raised by the partial unique index OR by the ORM UK check; mapped to 409.
- `TenantScopeViolation`: tenant middleware raises this directly, not `versioned.py`.

### 4.2 workflow.py — transition + chain for [L-W]

```python
# backend/packages/parkos_core/src/parkos_core/repo/workflow.py
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.base import WorkflowBase

class WorkflowTransitionError(Exception): ...
class IllegalTransitionError(WorkflowTransitionError): ...

# State machines per table (REQ-X9 + REQ-21-W-TRANSITION)
STATE_MACHINES: dict[str, dict[str, frozenset[str]]] = {
    "anulaciones":      {"solicitada":   frozenset({"aprobada", "rechazada"}),
                         "aprobada":     frozenset({"ejecutada", "rechazada"}),
                         "ejecutada":    frozenset(),
                         "rechazada":    frozenset()},
    "reclamos":         {"abierto":      frozenset({"en_revision"}),
                         "en_revision":  frozenset({"resuelto", "rechazado"}),
                         "resuelto":     frozenset(),
                         "rechazado":    frozenset()},
    "alerta":           {"abierta":      frozenset({"en_revision"}),
                         "en_revision":  frozenset({"resuelta", "descartada"}),
                         "resuelta":     frozenset(),
                         "descartada":   frozenset()},
    "reimpresion_ticket": {"cobrada":     frozenset({"anulada"}),
                           "anulada":     frozenset()},
    "envio_dian":       {"pendiente":    frozenset({"enviado", "rechazado"}),
                         "enviado":      frozenset({"aceptado", "rechazado", "pendiente"}),  # may re-loop
                         "aceptado":     frozenset(),
                         "rechazado":    frozenset({"pendiente"})},                          # re-loop
    "validacion_evento":{"recibido":     frozenset({"validado", "observado", "rechazado"}),
                         "observado":    frozenset({"validado", "rechazado"}),
                         "validado":     frozenset(),
                         "rechazado":    frozenset()},
}

async def append_transition(
    session: AsyncSession,
    table: str,            # e.g. "anulaciones"
    parent_uuid: uuid.UUID | None,  # None = chain root (REQ-22-W-INITIAL)
    new_estado: str,
    actor_uuid: uuid.UUID,
    motivo: str | None,
    payload: dict,         # table-specific fields beyond uuid_*_padre + estado + motivo
) -> WorkflowRow:
    """1. If parent_uuid: read parent.estado, validate transition in STATE_MACHINES[table].
       2. INSERT new row with uuid_*_padre = parent_uuid (or NULL for root), estado = new_estado,
          timestamp_evento = NOW(), created_by = actor_uuid.
       3. Write log_transaccional row (accion='actualizar', uuid_registro_afectado = root_uuid,
          i.e. the chain's root, NOT the new row).
       4. Return new row."""
    ...

async def read_chain_tip(
    session: AsyncSession,
    table: str,
    root_uuid: uuid.UUID,
) -> dict:
    """REQ-X9 deterministic tie-break:
       (a) most recent timestamp_evento
       (b) on tie: longest chain length
       (c) on tie: lexicographic uuid ASC.

       Returns {uuid_root, uuid_actual, estado, timestamp_evento, chain_length}.
       Algorithm walks the chain via uuid_*_padre FKs; collects all leaves; applies tie-break.
    """
    ...
```

**Side effects on commit**: `log_transaccional` row written via `append_only.append_event`. For `[L-W]` tables whose transitions cross the cloud/branch boundary (`envio_dian`, `validacion_evento`), the row is written via the cloud-only router path (`dian/cloud_router.py`).

**Exception classes**:
- `IllegalTransitionError`: mapped to 422 `{"error": "illegal_transition", "detail": "..."}`.
- `ParentNotFoundError`: mapped to 404.
- `AdminScopeRequiredError`: raised by the JWT guard BEFORE this function runs; mapped to 403.
- `SelfDiscardForbiddenError`: REQ-26-W-ALERTA-DESCARTADA — when `alerta.estado='descartada'` is attempted by the user assigned to the alert.

### 4.3 session_cycle.py — close_with_log for [L-S]

```python
# backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py
from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from .append_only import append_event  # the log_transaccional writer

class SessionGuardError(Exception): ...

async def open_session(
    session: AsyncSession,
    user_uuid: uuid.UUID,
    sucursal_uuid: uuid.UUID,
    valor_inicial_efectivo: Decimal,
    valor_inicial_datafono: Decimal,
) -> SesionRow:
    """REQ-40-S-OPEN: INSERT sesion row with estado='abierta', timestamp_apertura=NOW().
    Mirror INSERT into login table with estado='exitoso'.
    Log row in SAME TX (accion='crear').
    Returns the new sesion row."""
    ...

async def close_session_with_log(
    session: AsyncSession,
    sesion_uuid: uuid.UUID,
    actor_uuid: uuid.UUID,
    valor_final_efectivo: Decimal,
    valor_final_datafono: Decimal,
) -> SesionRow:
    """REQ-41-S-CLOSE: log_transaccional INSERT FIRST, then UPDATE sesion — same TX.

    1. Read current sesion row (for datos_anteriores snapshot).
    2. INSERT log_transaccional row with accion='actualizar',
       tabla_afectada='sesion', uuid_registro_afectado=sesion_uuid,
       datos_anteriores=json(current), datos_nuevos=json(current+changes).
       The hash_chain.append() helper computes hash_anterior/actual.
    3. UPDATE sesion SET estado='cerrada', timestamp_cierre=NOW(),
       uuid_usuario_cierre=actor_uuid, valor_final_efectivo=:ve,
       valor_final_datafono=:vd WHERE uuid = :sesion_uuid AND estado='abierta'.

    The DB trigger prod.ls_session_update_guard() verifies that a log_transaccional
    row was inserted in the SAME TX (it reads pg_stat_activity or a CTE of xid-local
    temp tables). If the trigger fires RAISE EXCEPTION 'LOG_TRANSACCIONAL_REQUIRED',
    the AsyncSession raises and the close aborts — defense in depth layer 3.
    """
    ...

async def record_login(
    session: AsyncSession,
    user_uuid: uuid.UUID,
    sucursal_uuid: uuid.UUID,
    success: bool,
    motivo: str | None = None,
) -> LoginRow:
    """REQ-42-S-LOGIN / REQ-43-S-LOGIN-FAILURE: INSERT login row estado='exitoso' or 'fallido'.
    No UPDATE on usuarios here — counter reset is a separate bi-temporal close+insert
    via versioned.close_and_insert."""
    ...

async def close_login_with_log(
    session: AsyncSession,
    login_uuid: uuid.UUID,
    actor_uuid: uuid.UUID,
) -> LoginRow:
    """REQ-45-S-LOGOUT: log_transaccional INSERT first, then UPDATE login SET estado='cerrado'."""
    ...
```

**Side effects on commit**: `log_transaccional` row written via `append_event(session, log_transaccional, payload, actor_uuid)`. The DB trigger on `[A]` enqueues a `sync_queue` row.

**Exception classes**:
- `SessionAlreadyClosedError`: state-machine violation; mapped to 409.
- `SessionGuardViolation`: bubbles up from the DB trigger as `psycopg2.errors.RaiseException: LOG_TRANSACCIONAL_REQUIRED`; mapped to 500 with structured detail (NOT silently swallowed).

### 4.4 append_only.py — append + compensate for [A]

```python
# backend/packages/parkos_core/src/parkos_core/repo/append_only.py
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.base import AppendOnlyBase

class AppendOnlyError(Exception): ...

async def append_event(
    session: AsyncSession,
    model_cls: type[AppendOnlyBase],
    payload: dict[str, Any],
    actor_uuid: uuid.UUID,
    *,
    chain_hash: bool = False,  # set True for log_transaccional + revocacion_factura
) -> AppendOnlyBase:
    """REQ-10-A-INSERCION: single INSERT, no UPDATE, no DELETE.

    1. If chain_hash: call hash_chain.append(session, model_cls, payload, actor_uuid) to compute
       hash_anterior / hash_actual columns server-side.
    2. INSERT row with created_at = NOW(), created_by = actor_uuid, sync_status = 'pendiente'.
    3. For DIAN tables: set fecha_retencion_hasta = NOW() + INTERVAL '5 years'.
    4. Return the new row.

    Caller MUST NOT perform any further session.execute(update/delete) on this row.
    The DB trigger prod.fn_<table>_inmutable() will reject any such attempt.

    The DB trigger prod.fn_enqueue_sync() fires AFTER INSERT and creates a sync_queue row
    (filtered by WHEN TG_TABLE_NAME <> 'sync_queue').
    """
    ...

# Whitelisted-column sync_queue update paths
class SyncQueueStateError(Exception): ...

ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS = frozenset({"estado", "intentos", "next_retry_at", "ultimo_error"})

async def mark_dispatched(
    session: AsyncSession, sync_queue_uuid: uuid.UUID, intentos: int
) -> None:
    """SC-13-A-SYNC-QUEUE-MARK-DISPATCHED: UPDATE sync_queue SET estado='despachado',
    intentos=:intentos, next_retry_at=NULL WHERE uuid=:u.
    Trigger fn_sync_queue_mark_dispatched() permits only the four whitelisted columns.
    A fuzz test asserts any other column name in the helper input raises ValueError."""
    ...

async def mark_failed(
    session: AsyncSession, sync_queue_uuid: uuid.UUID, ultimo_error: str
) -> None:
    """UPDATE sync_queue SET estado='error', ultimo_error=:e WHERE uuid=:u."""
    ...

async def schedule_retry(
    session: AsyncSession, sync_queue_uuid: uuid.UUID,
    next_retry_at: datetime, ultimo_error: str | None,
) -> None:
    """UPDATE sync_queue SET estado='pendiente', next_retry_at=:t, ultimo_error=:e WHERE uuid=:u."""
    ...
```

**Compensation pattern** (REQ-15-A-COMPENSATION) lives in `repo/factura_pagos.py`:

```python
# backend/packages/parkos_core/src/parkos_core/repo/factura_pagos.py
class DuplicateReversoError(AppendOnlyError): ...

async def reverse_payment(
    session: AsyncSession,
    original_pago_uuid: uuid.UUID,
    actor_uuid: uuid.UUID,
    motivo: str,
    valor: Decimal,
    medio_pago: str,
) -> FacturaPagosRow:
    """REQ-OP-09: INSERT a new row with tipo_movimiento='reverso', uuid_pago_revertido=:original_pago_uuid.

    Pydantic validates: tipo_movimiento='reverso' requires uuid_pago_revertido (422 otherwise);
    tipo_movimiento='pago' requires uuid_pago_revertido IS NULL (422 otherwise).

    The DB has a partial unique index:
      CREATE UNIQUE INDEX uq_factura_pagos_reverso ON prod.factura_pagos (uuid_pago_revertido)
        WHERE tipo_movimiento = 'reverso' AND uuid_pago_revertido IS NOT NULL;

    A second reversal attempt fails at the DB layer with UniqueViolation; the helper maps
    that to DuplicateReversoError → HTTP 409. V_FACTURA_PAGOS_NETOS subtracts reversos
    from pagos for net reporting.
    """
    ...
```

**Side effects on commit**: hash chain extends if `chain_hash=True`. `sync_queue` row enqueued by the DB trigger.

### 4.5 event.py — insert-only for [L-E]

```python
# backend/packages/parkos_core/src/parkos_core/repo/event.py
from __future__ import annotations
import uuid
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from .append_only import append_event  # reused for hash chain + sync enqueue

class ConscutivoExhaustedError(Exception): ...
class ResolucionNotFoundError(Exception): ...

async def record_event(
    session: AsyncSession,
    model_cls: type[LifecycleEventBase],
    payload: dict,
    actor_uuid: uuid.UUID,
) -> LifecycleEventBase:
    """REQ-30-E-INSERCION: single INSERT with timestamp_evento=NOW(), created_by=actor_uuid.
    For [L-E] tables only (ingreso, facturas). For factura_electronica, see
    dian/cloud_router.factura_electronica_create() instead — it adds the SELECT FOR UPDATE
    on resolucion_facturacion and the atomic consecutivo assignment."""
    ...

# CLOUD-ONLY — imported only on cloud images
async def record_factura_electronica_online(
    session: AsyncSession,
    uuid_factura: uuid.UUID,           # the internal facturas row uuid
    uuid_resolucion_facturacion: uuid.UUID,
    payload: dict,
    actor_uuid: uuid.UUID,
) -> FacturaElectronicaRow:
    """REQ-34-E-FACTURA-ELECTRONICA-CONSECUTIVO: atomic cloud-side consecutivo assignment.

    1. BEGIN; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
    2. SELECT ... FOR UPDATE on resolucion_facturacion row WHERE uuid = :r AND vigente_hasta IS NULL.
       Raises ResolucionNotFoundError if no active resolution.
    3. Compute new_consecutivo = (SELECT COALESCE(MAX(consecutivo), 0) FROM factura_electronica
                                  WHERE uuid_resolucion_facturacion = :r) + 1.
    4. If new_consecutivo > resolucion_facturacion.rango_hasta: raise ConscutivoExhaustedError.
    5. INSERT factura_electronica with prefijo=R.prefijo, consecutivo=new_consecutivo,
       uuid_factura=:f, fecha_retencion_hasta=NOW() + INTERVAL '5 years'.
    6. COMMIT.

    Returns the new row with numero_oficial = prefijo + consecutivo.
    """
    ...
```

**Side effects on commit**: hash chain NOT extended (L-E rows do not carry `hash_*` columns; only `log_transaccional` and `revocacion_factura` do — those are `[A]`). `sync_queue` row enqueued by the DB trigger.

### 4.6 (cross-cutting) hash_chain.py

```python
# backend/packages/parkos_core/src/parkos_core/repo/hash_chain.py
import hashlib
import json
import uuid
from datetime import datetime
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.A.log_transaccional import LogTransaccional
from ..models.A.revocacion_factura import RevocacionFactura

GENESIS_PREFIX = b"genesis:"

class HashChainIntegrityViolation(Exception): ...

def _canonical_json(payload: dict) -> bytes:
    """Deterministic JSON encoding (sort_keys + ensure_ascii=False + compact separators).
    The same payload MUST hash to the same bytes regardless of dict insertion order."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

async def append(
    session: AsyncSession,
    model_cls: type,  # LogTransaccional or RevocacionFactura
    payload: dict,
    actor_uuid: uuid.UUID,
) -> None:
    """REQ-X4 + REQ-16-A-HASH-CHAIN + REQ-OP-12.

    1. Read MAX(timestamp_evento) row for uuid_sucursal = :s from the target table.
       If none: hash_anterior = sha256(GENESIS_PREFIX + uuid_sucursal_bytes).hexdigest().
    2. Compute payload_with_audit = {**payload, 'created_at': NOW(), 'created_by': actor_uuid,
       'uuid_sucursal': payload['uuid_sucursal']}.
    3. hash_actual = sha256(_canonical_json(payload_with_audit) + bytes.fromhex(hash_anterior)).hexdigest().
    4. Caller (append_only.append_event with chain_hash=True) performs the INSERT in the same TX.

    On mismatch (e.g. external sync delivered out of order, and the previous row's hash_actual
    doesn't match what we'd compute): raise HashChainIntegrityViolation → mapped to 500.
    The cloud-side verifier (out of scope here) writes sync_conflict + opens an alerta workflow.
    """
    ...
```

### 4.7 (cross-cutting) idempotency.py

```python
# backend/packages/parkos_core/src/parkos_core/repo/idempotency.py
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, insert, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.A.idempotency_keys import IdempotencyKeys

TTL_HOURS = 24

class IdempotencyKeyRequiredError(Exception): ...
class IdempotencyConflictError(Exception): ...

def hash_request(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()

async def guard(
    session: AsyncSession,
    *,
    endpoint: str,           # e.g. "POST /api/v1/auth/login"
    idempotency_key: str | None,
    request_body: bytes,
    actor_uuid: uuid.UUID,
) -> tuple[int, dict, bool] | None:
    """REQ-OP-04: returns (status_code, response_body, is_replay) if cached;
    returns None if first time; raises on missing key or duplicate-with-different-body."""
    if not idempotency_key:
        raise IdempotencyKeyRequiredError(
            "POST requires Idempotency-Key header (RFC 7234-style)"
        )
    key_hash = hashlib.sha256(f"{endpoint}|{idempotency_key}|{hash_request(request_body)}".encode()).hexdigest()

    # Try to read existing
    existing = await session.execute(
        select(IdempotencyKeys).where(
            IdempotencyKeys.key_hash == key_hash,
            IdempotencyKeys.expires_at > datetime.now(timezone.utc),
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        if row.request_payload_hash != hash_request(request_body):
            raise IdempotencyConflictError(
                "Idempotency-Key reused with different request body"
            )
        return (row.response_status, row.response_body, True)

    # First-time write will happen AFTER the route handler succeeds;
    # the helper returns None and the route calls store_response() on commit.
    return None

async def store_response(
    session: AsyncSession,
    *,
    endpoint: str,
    idempotency_key: str,
    request_body: bytes,
    actor_uuid: uuid.UUID,
    response_status: int,
    response_body: dict,
) -> None:
    """INSERT INTO idempotency_keys ... in the same TX as the write."""
    ...
```

### 4.8 (cross-cutting) pagination.py — cursor encode/decode

```python
# backend/packages/parkos_core/src/parkos_core/repo/pagination.py
import base64
import json
import uuid
from datetime import datetime

class InvalidCursorError(Exception): ...

class Cursor:
    def __init__(self, *, vigente_desde: str | None, timestamp_evento: str | None,
                 created_at: str | None, uuid: str, resource: str):
        ...

def encode(cursor: Cursor) -> str:
    """REQ-OP-01: opaque base64-encoded JSON."""
    raw = json.dumps(cursor.__dict__, sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")

def decode(opaque: str, expected_resource: str) -> Cursor:
    """Strict: malformed JSON, missing fields, wrong resource → InvalidCursorError → 400."""
    ...
```

## 5. FastAPI router patterns

The shared router factory generates the uniform C/Q/U surface for every table. AD-1 says all 49 tables get a list endpoint; this section shows how that contract is realized.

```python
# backend/packages/parkos_core/src/parkos_core/api/router_factory.py
from __future__ import annotations
import uuid
from typing import Type, TypeVar
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.engine import get_session
from ..auth.tenancy import TenantContext, get_tenant_ctx
from ..auth.jwt_issuer_guard import requires_issuer
from ..auth.permissions import require_permission
from ..api.middleware import IdempotencyKeyMiddleware
from ..models.base import VersionedBase, AppendOnlyBase, LifecycleEventBase, WorkflowBase, SessionBase
from ..repo.versioned import close_and_insert, current_version, history, list_with_cursor
from ..repo.append_only import append_event
from ..repo.event import record_event
from ..repo.workflow import append_transition
from ..repo.session_cycle import close_session_with_log
from ..repo.idempotency import guard as idempotency_guard
from ..repo.pagination import Cursor, encode as cursor_encode, decode as cursor_decode

T = TypeVar("T")

def make_router(
    *,
    resource: str,                    # e.g. "tipo-persona" (URL slug)
    model_cls: Type,                   # ORM class
    schema_module,                     # Pydantic module with Read/Create/Update/Filter
    repo_kind: str,                    # "versioned" | "append_only" | "event" | "workflow" | "session"
    derived_view: str | None = None,   # "V_FACTURA_ESTADO" etc. for nested /estado
    issuer_required: str,              # "admin-" | "operador-" | "sync-agent-" or comma-list
    permission_required: str | None = None,
    write_enabled: bool = True,        # False for [A] where only POST exists, True for [V]/[L-S]
    transition_states: list[str] | None = None,  # for [L-W]
) -> APIRouter:
    """Generates:
       GET    /<resource>                 — list (REQ-02-V-CONSULTA / -A-CONSULTA / etc.)
       GET    /<resource>/{uuid}          — current read (REQ-01 / REQ-12)
       GET    /<resource>/{uuid}/estado   — derived state (REQ-32-E-DERIVED-ESTADO; only if derived_view)
       GET    /<resource>/{uuid}/historial — full history (REQ-05)
       POST   /<resource>                 — insert (REQ-03 / REQ-10 / REQ-21-W-TRANSITION / REQ-22 / REQ-30 / REQ-40)
       PUT    /<resource>/{uuid}          — close+insert for [V]/[L-S] close (REQ-04 / REQ-41)
                                              OR for [L-W] parent_uuid + estado + motivo (REQ-21)
       NO DELETE — enforced at the static test layer.
    """
    router = APIRouter(prefix=f"/{resource}", tags=[resource])

    # JWT scope guard (single dependency reused for every route)
    issuers = [s.strip() for s in issuer_required.split(",")]
    issuer_dep = requires_issuer(*issuers)
    perm_dep = (Depends(require_permission(permission_required))
                if permission_required else None)

    # READ routes
    @router.get("", response_model=schema_module.ReadList)
    async def list_endpoint(
        cursor: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
        ctx: TenantContext = Depends(get_tenant_ctx),
        _issuer: None = Depends(issuer_dep),
    ):
        try:
            decoded = cursor_decode(cursor, expected_resource=resource) if cursor else None
        except InvalidCursorError:
            raise HTTPException(400, {"error": "invalid_cursor"})
        items, next_cursor = await list_with_cursor(
            session, model_cls,
            filters={},  # tenant scoping injected by get_tenant_ctx via event listener
            cursor=decoded, limit=limit,
        )
        return {"items": items, "next_cursor": cursor_encode(next_cursor) if next_cursor else None}

    @router.get("/{uuid}", response_model=schema_module.Read)
    async def get_endpoint(uuid: uuid.UUID = Path(...), ...): ...

    if derived_view:
        @router.get("/{uuid}/estado", response_model=schema_module.ReadEstado)
        async def estado_endpoint(uuid: uuid.UUID = Path(...), ...):
            return await _query_derived_view(session, derived_view, uuid)

    if write_enabled:
        if repo_kind == "versioned":
            @router.post("", response_model=schema_module.Read, status_code=201)
            async def post_endpoint(
                payload: schema_module.Create,
                idem_key: str | None = Header(None, alias="Idempotency-Key"),
                session: AsyncSession = Depends(get_session),
                ctx: TenantContext = Depends(get_tenant_ctx),
                _issuer: None = Depends(issuer_dep),
                _perm: None = Depends(perm_dep) if perm_dep else None,
            ):
                cached = await idempotency_guard(
                    session, endpoint=f"POST /{resource}", idempotency_key=idem_key,
                    request_body=payload.model_dump_json().encode(),
                    actor_uuid=ctx.actor_uuid,
                )
                if cached:
                    raise HTTPException(cached[0], cached[1], headers={"Idempotent-Replay": "true"})
                new_row = await close_and_insert(  # special-cased to INSERT-only when vigente_hasta IS NOT NULL in body
                    session, model_cls,
                    current_uuid=None,  # INSERT path
                    new_attrs=payload.model_dump(),
                    actor_uuid=ctx.actor_uuid,
                )
                await session.commit()
                # store_response() — best-effort; if it fails, log and continue
                try:
                    await store_response(
                        session, endpoint=f"POST /{resource}", idempotency_key=idem_key,
                        request_body=payload.model_dump_json().encode(),
                        actor_uuid=ctx.actor_uuid,
                        response_status=201,
                        response_body=schema_module.Read.model_validate(new_row).model_dump(mode="json"),
                    )
                    await session.commit()
                except IdempotencyConflictError:
                    raise HTTPException(409, {"error": "idempotency_conflict"})
                return schema_module.Read.model_validate(new_row)

            @router.put("/{uuid}", response_model=schema_module.Read)
            async def put_endpoint(...):
                # Same idempotency dance, then close_and_insert(current_uuid=uuid, ...)
                ...

        elif repo_kind == "append_only":
            @router.post("", response_model=schema_module.Read, status_code=201)
            async def post_endpoint(...):
                # append_event(session, model_cls, payload, actor)
                ...

        elif repo_kind == "event":
            @router.post("", response_model=schema_module.Read, status_code=201)
            # record_event(session, model_cls, payload, actor)
            ...

        elif repo_kind == "workflow":
            @router.post("", response_model=schema_module.Read, status_code=201)
            # append_transition(session, table=model_cls.__tablename__, parent_uuid=payload.uuid_*_padre,
            #                   new_estado=payload.estado, actor, motivo, payload=rest)
            ...

        elif repo_kind == "session":
            # /sesion/{uuid}/cerrar is a sub-resource action endpoint
            @router.put("/{uuid}/cerrar", response_model=schema_module.Read)
            # close_session_with_log(session, sesion_uuid, actor, ...)
            ...

    return router
```

Each domain router file (`api/v1/catalogos.py`, `api/v1/operacion.py`, etc.) calls `make_router(...)` once per table it owns and combines them under a single `APIRouter(prefix="/api/v1")`. The factory is shared across PRs, which is the leverage point — once it exists, adding 8 more tables in PR6 is mechanical.

```python
# backend/packages/parkos_core/src/parkos_core/api/v1/catalogos.py (PR3)
from ..router_factory import make_router
from ...schemas import catalogos as schemas
from ...models.V.tipo_persona import TipoPersona
from ...models.V.tipos_vehiculo import TiposVehiculo
# ... etc.

router = APIRouter(prefix="/api/v1")
router.include_router(make_router(
    resource="tipo-persona", model_cls=TipoPersona,
    schema_module=schemas, repo_kind="versioned",
    issuer_required="admin-,operador-",
    permission_required="config_catalogo",
))
# ... 8 more times for the catalogs
```

## 6. Pydantic schemas

Schemas live in `parkos_core/schemas/`, grouped by domain per §2. Per table: `Read`, `Create`, `Update`, `Filter`, `ReadEstado` (when nested derived endpoint exists).

```python
# backend/packages/parkos_core/src/parkos_core/schemas/catalogos.py
from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated

class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

class TipoPersonaRead(_Base):
    uuid: uuid.UUID
    tipo: str
    descripcion: str | None
    vigente_desde: datetime
    vigente_hasta: datetime | None
    estado: str
    created_at: datetime
    created_by: uuid.UUID
    sync_status: str

class TipoPersonaCreate(_Base):
    """REQ-03-V-INSERCION. Clients MUST NOT supply vigente_desde (C-6 in bi-temporal-crud.md).
    Pydantic 'extra=forbid' rejects it with 422."""
    tipo: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    descripcion: Annotated[str | None, StringConstraints(max_length=512)] = None

class TipoPersonaUpdate(_Base):
    """REQ-04-V-ACTUALIZACION. Same shape as Create (the new version's payload);
    vigente_hasta is set server-side by close_and_insert, not accepted from the client."""
    tipo: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    descripcion: Annotated[str | None, StringConstraints(max_length=512)] = None

class TipoPersonaFilter(_Base):
    estado: str | None = None
    vigente_desde__gte: datetime | None = None
    vigente_desde__lte: datetime | None = None
    vigente_hasta__isnull: bool | None = None

class TipoPersonaReadList(BaseModel):
    items: list[TipoPersonaRead]
    next_cursor: str | None = None
```

Naming discipline: **field names match ORM column names exactly** so `model_validate(row)` is the only mapping (`from_attributes=True`). Aliases are forbidden — they introduce drift. C-3 in `bi-temporal-crud.md` enforces this with a sample row per table.

For `[A]` tables, the schema reflects the no-UPDATE invariant:

```python
# schemas/facturacion.py (PR6) — ejemplo para factura_pagos
class FacturaPagosCreate(_Base):
    """REQ-15-A-COMPENSATION. tipo_movimiento discriminator.
    Pydantic model_validator(mode='after') enforces:
      - tipo_movimiento='reverso'  → uuid_pago_revertido is REQUIRED (422 otherwise)
      - tipo_movimiento='pago'     → uuid_pago_revertido MUST BE NULL (422 otherwise)
    """
    uuid_factura: uuid.UUID
    medio_pago: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    valor: Decimal = Field(..., decimal_places=2, max_digits=18)
    tipo_movimiento: Literal["pago", "reverso"]
    uuid_pago_revertido: uuid.UUID | None = None
    motivo: Annotated[str | None, StringConstraints(max_length=512)] = None
    fecha_retencion_hasta: datetime | None = None  # server sets NOW()+5y; client may omit

    @model_validator(mode="after")
    def _check_reverso_or_pago(self):
        if self.tipo_movimiento == "reverso" and self.uuid_pago_revertido is None:
            raise ValueError("tipo_movimiento='reverso' requires uuid_pago_revertido")
        if self.tipo_movimiento == "pago" and self.uuid_pago_revertido is not None:
            raise ValueError("tipo_movimiento='pago' must NOT set uuid_pago_revertido")
        return self

# There is NO Update / PUT for [A] tables — only POST + GET. The router factory respects
# repo_kind='append_only' and omits the PUT endpoint entirely.
```

For `[L-W]` polymorphic FK (REQ-23-W-POLYMORPHIC-FK):

```python
# schemas/workflows.py (PR6) — reclamos
class ReclamoCreate(_Base):
    """REQ-23-W-POLYMORPHIC-FK: tipo_reclamable + uuid_reclamable polymorphic pair."""
    tipo_reclamable: Literal["ingreso", "salida", "factura", "subscripcion"]
    uuid_reclamable: uuid.UUID
    uuid_reclamo_padre: uuid.UUID | None = None  # None for chain root
    estado: Literal["abierto", "en_revision", "resuelto", "rechazado"]
    motivo: Annotated[str, StringConstraints(min_length=1, max_length=1024)]

    @model_validator(mode="after")
    async def _check_polymorphic_fk(self):
        """REQ-OP-08 + REQ-23: verify a row exists in the named table.
        Cloud-side consults Redis cache (60s TTL); branch-side reads local DB.
        On miss, falls back to direct read."""
        from parkos_core.repo.polymorphic_validator import polymorphic_row_exists
        from parkos_core.cache.poly_cache import get_poly_cache
        cache = get_poly_cache()
        cached = await cache.get(self.tipo_reclamable, self.uuid_reclamable)
        if not cached:
            ok = await polymorphic_row_exists(self.tipo_reclamable, self.uuid_reclamable)
            if not ok:
                raise ValueError(f"polymorphic_fk_not_found: no row in {self.tipo_reclamable} with uuid {self.uuid_reclamable}")
            await cache.set(self.tipo_reclaimable, self.uuid_reclamable, ttl=60)
        return self
```

For `[L-E]` `factura_electronica` (cloud-only, REQ-34):

```python
# schemas/dian.py (PR6) — cloud-only module
class FacturaElectronicaCreate(_Base):
    """Server-assigns prefijo + consecutivo (REQ-34). client never sets them."""
    uuid_factura: uuid.UUID
    uuid_resolucion_facturacion: uuid.UUID
    # ... payload fields from modelo_datos_er.mmd ...
```

## 7. JWT three-issuer enforcement

Each request to `/api/v1/*` runs through a layered auth pipeline. The three issuers (AGENTS.md "JWT (three issuers)") are mutually exclusive; the same code path that rejects `operador-` on admin routes also rejects `admin-` on sync routes.

```python
# backend/packages/parkos_core/src/parkos_core/auth/jwt_issuer_guard.py
from __future__ import annotations
import jwt
from fastapi import Depends, HTTPException, Request, status
from .jwks_cache import get_jwks  # reads from /var/secrets/jwt_*_*.pem or /.well-known/jwks.json
from .tenancy import TenantContext

ISSUER_PREFIXES = ("admin-", "operador-", "sync-agent-")

class InvalidTokenError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=401, detail={"error": "invalid_token", "detail": detail})

class CrossIssuerError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=401, detail={"error": "wrong_issuer", "detail": detail})

async def verify_jwt(request: Request) -> dict:
    """Verifies signature against the issuer's JWKS, with grace rotation (JWT_OVERLAP_HOURS=24).
    Caches the decoded claims in request.state.jwt_claims for downstream dependencies."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise InvalidTokenError("missing bearer token")
    token = auth[7:]
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid", "")
    except jwt.PyJWTError as e:
        raise InvalidTokenError(f"malformed token: {e}")
    # kid prefix identifies the issuer
    if not kid.startswith(ISSUER_PREFIXES):
        raise CrossIssuerError(f"kid prefix must be one of {ISSUER_PREFIXES}")
    issuer_prefix = kid.split("-", 1)[0] + "-"
    try:
        jwks = await get_jwks(issuer_prefix)
        claims = jwt.decode(
            token, jwks,
            algorithms=["RS256"],
            audience=f"parkos-{ 'admin' if issuer_prefix == 'admin-' else ('branch' if issuer_prefix == 'operador-' else 'sync') }",
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.InvalidIssuerError as e:
        raise InvalidTokenError(f"issuer mismatch: {e}")
    except jwt.ExpiredSignatureError as e:
        raise InvalidTokenError(f"expired: {e}")
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(f"invalid: {e}")
    if not claims["iss"].startswith(issuer_prefix):
        raise CrossIssuerError(f"iss claim {claims['iss']} doesn't match kid prefix {issuer_prefix}")
    request.state.jwt_claims = claims
    return claims

def requires_issuer(*allowed: str):
    """FastAPI dependency factory. REQ-X7."""
    allowed_set = set(allowed)
    async def _dep(request: Request) -> dict:
        claims = await verify_jwt(request)
        issuer_prefix = claims["iss"].split("-")[0] + "-"
        if issuer_prefix not in allowed_set:
            raise CrossIssuerError(
                f"issuer {issuer_prefix} not in allowed {sorted(allowed_set)}"
            )
        return claims
    return _dep
```

The `require_permission()` dependency (`auth/permissions.py`) is layered AFTER the issuer guard. It queries `permisos_usuario` (REQ-OP-13):

```python
# backend/packages/parkos_core/src/parkos_core/auth/permissions.py
async def require_permission(codigo: str):
    async def _dep(
        request: Request,
        session: AsyncSession = Depends(get_session),
    ) -> dict:
        claims = getattr(request.state, "jwt_claims", None) or await verify_jwt(request)
        actor_uuid = uuid.UUID(claims["sub"])
        result = await session.execute(
            select(PermisosUsuario)
            .join(Permisos, Permisos.uuid == PermisosUsuario.uuid_permiso)
            .where(
                PermisosUsuario.uuid_usuario == actor_uuid,
                PermisosUsuario.vigente_hasta.is_(None),
                Permisos.codigo == codigo,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(403, {"error": "permission_denied", "detail": codigo})
        return claims
    return _dep
```

Per-router scope mapping (table → required issuers). This table is the single source of truth consulted by every `make_router(...)` call:

| Resource class | Tables | Issuers | Permission required |
|---|---|---|---|
| Auth (`/auth/login`, `/auth/refresh`, `/auth/logout`) | (none) | none (pre-auth) | none |
| `[V]` catalog | `tipo-persona`, `tipos-vehiculo`, `tipo-subscripciones`, `tipo-tarifa`, `tipo-sucursal`, `tipo-arqueo`, `impuestos`, `otros-cobros`, `costos-servicios` | `admin-,operador-` (operador = read only) | `config_catalogo` for write |
| `[V]` config | `configuracion-tolerancias`, `configuracion-seguridad` | `admin-` (write), `operador-` (read of /efectiva) | `config_sistema` |
| `[V]` empresa/sucursal | `empresa`, `sucursal`, `documentos`, `resolucion-facturacion`, `tarifas-sucursal`, `cantidad-vehiculos-sucursal` | `admin-` | `config_sucursal` |
| `[V]` auth | `usuarios`, `permisos`, `permisos-usuario`, `usuarios-sucursal` | `admin-` (write), `operador-` (self-read) | `admin_usuarios` for write |
| `[V]` clientes | `clientes`, `clientes-b2b`, `subscripciones-cliente`, `vehiculos`, `subscripcion-vehiculos` | `operador-` (write at branch), `admin-` (cross-branch read) | `gestionar_clientes` |
| `[L-E]` operacion | `ingreso`, `facturas` | `operador-` (write), `admin-` (read) | `emitir_factura` for facturas |
| `[L-E]` cloud-only | `factura-electronica` | `operador-` (online path proxies via cloud), `admin-` (manual correction) | `emitir_factura_electronica` |
| `[L-W]` workflows | `anulaciones`, `reclamos`, `alerta`, `reimpresion-ticket` | branch-originated transitions: `operador-`; `aprobada/ejecutada` on anulaciones: `admin-` only (REQ-24-W-ADMIN-ONLY) | per transition (e.g. `aprobar_anulacion`) |
| `[L-W]` cloud-only | `envio-dian`, `validacion-evento` | `admin-` + `cloud-only` deploy context (REQ-25-W-CLOUD-ONLY) | `gestionar_dian` |
| `[A]` local-only infra | `sync-queue`, `sync-log`, `sync-conflict` | `sync-agent-` only (REQ-X8) | n/a |
| `[A]` session | `caja`, `arqueo` | `operador-` (write), `admin-` (read) | `cerrar_arqueo` |
| `[A]` audit | `log-transaccional` | `admin-` (read), `admin-` (write from helper only) | `audit_read` for SELECT |
| `[A]` DIAN | `revocacion-factura` | `admin-` (cloud-only) | `revocar_factura` |
| `[A]` billing | `salidas`, `factura-detalle`, `factura-impuestos`, `factura-otros-cobros`, `factura-pagos` | `operador-` | `emitir_factura` |
| `[A]` idempotency | `idempotency-keys` | (no direct API; written by middleware) | n/a |
| `[L-S]` | `login`, `sesion` | `operador-` | n/a (operador self-service) |
| `/sync/*` | all four sync endpoints | `sync-agent-` only (REQ-OP-03 + REQ-X8) | n/a |

`X-Sucursal-Context` enforcement is in `auth/tenancy.py` and runs alongside the issuer guard. See §9.

## 8. Idempotency-Key middleware

REQ-OP-04 (AD-3) requires every POST to carry `Idempotency-Key`. The middleware is implemented in two layers: a thin FastAPI middleware that extracts the header and the per-route guard in §4.7.

```python
# backend/packages/parkos_core/src/parkos_core/api/middleware.py
from __future__ import annotations
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class IdempotencyKeyMiddleware(BaseHTTPMiddleware):
    """Reads the Idempotency-Key header and stashes it on request.state.idempotency_key
    for downstream handlers. Does NOT enforce presence — the per-route helper does,
    so that GET endpoints and OPTIONS preflights are unaffected."""

    async def dispatch(self, request, call_next):
        request.state.idempotency_key = request.headers.get("Idempotency-Key")
        return await call_next(request)
```

The `idempotency_keys` table (50th, AD-3) is `[A]`-class. Schema:

```sql
CREATE TABLE prod.idempotency_keys (
    uuid              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash          CHAR(64)     NOT NULL,
    endpoint          VARCHAR(255) NOT NULL,
    request_payload_hash  CHAR(64) NOT NULL,
    response_status   INT          NOT NULL,
    response_body     JSONB        NOT NULL,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at        TIMESTAMPTZ  NOT NULL DEFAULT (NOW() + INTERVAL '24 hours'),
    created_by        UUID         NOT NULL
);
CREATE UNIQUE INDEX uq_idempotency_keys_key_hash_endpoint
    ON prod.idempotency_keys (key_hash, endpoint)
    WHERE expires_at > NOW();
REVOKE UPDATE, DELETE ON prod.idempotency_keys FROM rol_app;
CREATE TRIGGER idempotency_keys_inmutable
    BEFORE UPDATE OR DELETE ON prod.idempotency_keys
    FOR EACH ROW EXECUTE FUNCTION prod.fn_idempotency_keys_inmutable();
```

Migration `0002_add_idempotency_keys.py` (PR7) ships the table + REVOKE + trigger in the SAME script per `openspec/config.yaml` `rules.tasks`.

The TTL worker (out of scope for this change, owned by the sync-infra or a future batch) runs nightly:
```sql
DELETE FROM prod.idempotency_keys WHERE expires_at < NOW();
```
This is one of the two carve-out DELETEs in the whole system; the trigger blocks all OTHER DELETEs. The DELETE is owner-only (`postgres` role), not `rol_app`.

**Failure case — duplicate key with different body**: REQ-OP-04 says `IdempotencyConflictError → 409`. The helper computes `key_hash = sha256(endpoint + idempotency_key + sha256(request_body))`; two POSTs with the same key but different bodies produce the same `key_hash` but different `request_payload_hash`, and the helper raises.

## 9. Tenant scoping

```python
# backend/packages/parkos_core/src/parkos_core/auth/tenancy.py
from __future__ import annotations
import uuid
from dataclasses import dataclass
from fastapi import Depends, HTTPException, Request, Header
from .jwt_issuer_guard import verify_jwt

@dataclass
class TenantContext:
    actor_uuid: uuid.UUID
    actor_rol: str
    issuer_prefix: str           # 'admin-' | 'operador-' | 'sync-agent-'
    sucursal_uuid: uuid.UUID | None  # operador- pins; admin- reads from X-Sucursal-Context

class MissingSucursalContextError(HTTPException):
    def __init__(self):
        super().__init__(status_code=400, detail={"error": "missing_sucursal_context"})

class UnauthorizedSucursalContextError(HTTPException):
    def __init__(self):
        super().__init__(status_code=403, detail={"error": "unauthorized_sucursal_context"})

class TenantScopeViolationError(HTTPException):
    def __init__(self):
        super().__init__(status_code=403, detail={"error": "tenant_scope_violation"})

async def get_tenant_ctx(
    request: Request,
    x_sucursal_context: str | None = Header(None, alias="X-Sucursal-Context"),
) -> TenantContext:
    """REQ-X1 + REQ-X2: enforce X-Sucursal-Context against sucursales_permitidas for admin-."""
    claims = getattr(request.state, "jwt_claims", None) or await verify_jwt(request)
    actor_uuid = uuid.UUID(claims["sub"])
    actor_rol = claims.get("rol", "operador" if claims["iss"].startswith("operador-") else "admin")
    issuer_prefix = claims["iss"].split("-")[0] + "-"

    if issuer_prefix == "operador-":
        # operador- is pinned to a single sucursal
        sucursal_uuid = uuid.UUID(claims["sucursal"])
        # The X-Sucursal-Context header is OPTIONAL and, if present, MUST match the JWT claim.
        if x_sucursal_context is not None and uuid.UUID(x_sucursal_context) != sucursal_uuid:
            raise UnauthorizedSucursalContextError()
        ctx = TenantContext(
            actor_uuid=actor_uuid, actor_rol=actor_rol,
            issuer_prefix=issuer_prefix, sucursal_uuid=sucursal_uuid,
        )
        _set_tenant_context_var(sucursal_uuid)
        return ctx

    if issuer_prefix == "admin-":
        # admin- requires X-Sucursal-Context header
        if x_sucursal_context is None:
            raise MissingSucursalContextError()
        header_uuid = uuid.UUID(x_sucursal_context)
        permitidas = claims.get("sucursales_permitidas", [])
        if str(header_uuid) not in permitidas:
            raise UnauthorizedSucursalContextError()
        ctx = TenantContext(
            actor_uuid=actor_uuid, actor_rol=actor_rol,
            issuer_prefix=issuer_prefix, sucursal_uuid=header_uuid,
        )
        _set_tenant_context_var(header_uuid)
        return ctx

    if issuer_prefix == "sync-agent-":
        # sync-agent- is scoped to a single sucursal (the branch it represents)
        # OR to 'cloud' for the cloud-side sync receiver
        scope = claims.get("scope", "branch")
        if scope == "branch":
            sucursal_uuid = uuid.UUID(claims["sucursal"])
        else:
            sucursal_uuid = None  # cloud scope — no tenant filter on sync receivers
        ctx = TenantContext(
            actor_uuid=actor_uuid, actor_rol="sync-agent",
            issuer_prefix=issuer_prefix, sucursal_uuid=sucursal_uuid,
        )
        return ctx

    raise HTTPException(401, {"error": "unknown_issuer"})


# SQLAlchemy event listener (in db/tenancy.py, bootstrap-extended)
# Injects `WHERE uuid_sucursal = :ctx_sucursal` into every SELECT/UPDATE/DELETE
# for operation-bearing tables that have a uuid_sucursal column.
@event.listens_for(AsyncSession, "do_orm_execute")
def _filter_by_sucursal(state):
    if not (state.is_select or state.is_update or state.is_delete):
        return
    ctx_uuid = _ctx_sucursal.get()
    if ctx_uuid is None:
        return
    for tbl in state.statement.column_descriptions:
        entity = tbl.get("entity")
        if entity is None:
            continue
        if hasattr(entity, "uuid_sucursal"):
            state.statement = state.statement.where(entity.uuid_sucursal == ctx_uuid)
```

For tables WITHOUT `uuid_sucursal` (catalogs like `tipo_persona`, `usuarios`, `permisos`), the listener is a no-op. For `permisos_usuario` (no `uuid_sucursal`, joins through `usuarios`), the listener's column scan is the canonical gate — and the absence of `uuid_sucursal` means cross-branch reads are allowed (which is what the spec requires).

For tenant-scoped queries against the operational tables (`ingreso`, `facturas`, `clientes`, etc.), the SQL becomes `SELECT ... WHERE uuid_sucursal = :ctx` automatically. The router code doesn't write `WHERE uuid_sucursal = ...` manually — the listener does. AST tests catch accidental direct filters in routers.

## 10. DIAN-only boundary (image-level)

This is the single most important boundary to get right. Three layers of defense:

### Layer 1: Filesystem exclusion (Docker)

The branch Dockerfile's `.dockerignore` (already shipped by bootstrap) excludes:

```dockerignore
**/dian/cloud/**
**/api/v1/cloud_dian_router.py
```

The branch image simply does not contain the cloud-only module on disk. The cloud image's multi-stage build `COPY`s `parkos_core/dian/cloud/` separately:

```dockerfile
# Dockerfile (already in bootstrap PR1)
ARG BUILD_TARGET=api_admin

# ... builder stage ...
COPY packages/parkos_core/src/parkos_core/ /app/parkos_core/

# Conditional COPY for cloud-only files
RUN if [ "${BUILD_TARGET}" = "api_admin" ]; then \
      echo "Including DIAN cloud-only code"; \
      cp -r /build/dian_cloud/. /app/parkos_core/dian/cloud/; \
    else \
      echo "Excluding DIAN cloud-only code for branch image"; \
    fi
```

`/build/dian_cloud/` is a separate build-arg source directory populated by the CI image build pipeline for cloud targets only.

### Layer 2: Module import guard

`parkos_core/api/v1/__init__.py`:

```python
# backend/packages/parkos_core/src/parkos_core/api/v1/__init__.py
import os
from fastapi import APIRouter
from .auth import router as auth_router
from .catalogos import router as catalogos_router
# ... other domain routers

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(catalogos_router)
# ... other includes

# Lazy + conditional DIAN router import. The branch image's process never reaches this line.
if os.environ.get("PARKOS_DEPLOY") == "cloud":
    try:
        from parkos_core.dian.cloud_router import router as dian_router
        router.include_router(dian_router)
    except ImportError as e:
        # Cloud image MUST have the module; ImportError here is a build defect.
        raise RuntimeError(f"cloud_router_unavailable_in_cloud_image: {e}") from e
```

The RED test `tests/static/test_dian_boundary_branch.py`:

```python
import os, importlib, pytest

def test_branch_image_cannot_import_cloud_router(monkeypatch):
    monkeypatch.setenv("PARKOS_DEPLOY", "branch")
    # Re-import to pick up the env var
    if "parkos_core.api.v1" in sys.modules:
        del sys.modules["parkos_core.api.v1"]
    with pytest.raises(RuntimeError, match="cloud_router_unavailable_in_cloud_image"):
        # On branch image the cloud_router doesn't exist; the except branch fires.
        importlib.import_module("parkos_core.api.v1")
```

Actually, the cleaner formulation: on a branch image, `from parkos_core.dian.cloud_router import router` raises `ImportError` because the file is not on disk. The test imports that module directly:

```python
def test_branch_image_cannot_import_cloud_router():
    # On branch image the file is not on disk — ImportError is the EXPECTED outcome.
    with pytest.raises(ImportError):
        from parkos_core.dian import cloud_router  # noqa: F401
```

### Layer 3: OpenAPI tag check

The CI step that emits `api_sucursal/openapi.json` runs:

```bash
# backend/tests/static/test_openapi_branch_excludes_cloud.py — pytest version
import json
def test_branch_openapi_excludes_cloud_paths():
    with open("backend/packages/api_sucursal/openapi.json") as f:
        spec = json.load(f)
    cloud_only_paths = [
        "/api/v1/factura-electronica",
        "/api/v1/revocacion-factura",
        "/api/v1/envio-dian",
        "/api/v1/validacion-evento",
    ]
    for path in cloud_only_paths:
        assert path not in spec["paths"], (
            f"DIAN-only path {path} leaked into api_sucursal/openapi.json"
        )
        # Also assert no prefix matches
        assert not any(p.startswith(path) for p in spec["paths"])
```

The OpenAPI generator (`parkos_core.openapi`):

```python
# backend/packages/parkos_core/src/parkos_core/openapi.py
import os, json, importlib
from pathlib import Path

def generate_openapi(deploy_context: str, output_path: str) -> None:
    """REQ-OP-02 + REQ-OP-14: emit per-audience OpenAPI artifact.

    Sets PARKOS_DEPLOY env var BEFORE importing the app, so the dian router
    import-guard at api/v1/__init__.py does the right thing per context."""
    os.environ["PARKOS_DEPLOY"] = deploy_context
    if deploy_context == "cloud":
        from parkos_core.api_admin_main.app import app
    else:
        from parkos_core.api_sucursal_main.app import app
    spec = app.openapi()
    spec["info"]["version"] = _git_sha()  # traceable contract pin
    Path(output_path).write_text(json.dumps(spec, indent=2))
```

CI runs:
```bash
uv run python -m parkos_core.openapi --deploy cloud --output backend/packages/api_admin/openapi.json
uv run python -m parkos_core.openapi --deploy branch --output backend/packages/api_sucursal/openapi.json
```

Both files are committed. The frontend pins a specific SHA via `git checkout` of the artifact.

## 11. Hash chain (log_transaccional + revocacion_factura)

REQ-X4 + REQ-16-A-HASH-CHAIN require server-computed SHA-256 chains per `uuid_sucursal`. The chain is per-uuid_sucursal (per branch) — multiple branches coexist in cloud with separate chains.

Implementation in `parkos_core.repo.hash_chain` (§4.6):

1. **Genesis**: the FIRST row for a `(table, uuid_sucursal)` pair carries `hash_anterior = sha256(b"genesis:" + str(uuid_sucursal).encode()).hexdigest()`. Deterministic, identical for both branches and cloud.

2. **Extension**: read the row with `MAX(timestamp_evento)` for the same `uuid_sucursal` in the same table; its `hash_actual` becomes the new row's `hash_anterior`. Then `hash_actual = sha256(canonical_json(payload + audit_cols) + bytes.fromhex(hash_anterior)).hexdigest()`.

3. **Canonical JSON** (`_canonical_json`): `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` — deterministic across Python versions and dict insertion orders.

4. **Client rejection**: Pydantic schemas for `log_transaccional` and `revocacion_factura` exclude `hash_anterior` and `hash_actual` from `Create` / `Update` models entirely. The DB column-level GRANT also omits these columns from `rol_app` SELECT privilege (out of scope here; bootstrap migration does the GRANT).

5. **Cloud preservation**: when the cloud sync worker applies a batch from a branch, it processes rows in `MAX(timestamp_evento)` order stamped in the row's `datos` JSON (the per-branch monotonic seq). Each row's `hash_actual` arrives pre-computed from the branch; the cloud verifier (worker owned by bootstrap PR5) checks that `hash_actual == sha256(canonical_json(payload) + bytes.fromhex(hash_anterior))`. Cloud-originated rows append at the head of the same chain.

6. **Break detection**: when the verifier detects a mismatch, it raises `HashChainIntegrityViolation` → HTTP 500 returned to the sync worker. The worker writes a `sync_conflict` row (cloud-side, §6 in cross-cutting SC-X3) with both `datos_local` and `datos_cloud` snapshots. An `alerta` chain opens on the affected `uuid_sucursal` with `tipo_alerta='sync_failure'`.

The verifier itself (a worker process) is out of scope for this change — bootstrap PR5 owns it. This change ships the helper and the unit tests (PR2).

## 12. Sync triggers and outbox

The DB-side `AFTER INSERT` trigger is the canonical outbox enqueue path. The API does NOT enqueue manually — the trigger does, on every replicated `[A]` row's commit.

The trigger is created by bootstrap migration `0001_initial_schema.py`:

```sql
CREATE OR REPLACE FUNCTION prod.fn_enqueue_sync() RETURNS trigger AS $$
BEGIN
    IF TG_TABLE_NAME = 'sync_queue' THEN
        RETURN NULL;  -- recursion guard
    END IF;
    INSERT INTO prod.sync_queue (
        uuid, tabla, uuid_registro, datos, estado, prioridad,
        created_at, sync_status, sync_attempts
    ) VALUES (
        gen_random_uuid(),
        TG_TABLE_NAME,
        NEW.uuid,
        to_jsonb(NEW),
        'pendiente',
        CASE TG_TABLE_NAME
            WHEN 'factura_electronica' THEN 10
            WHEN 'revocacion_factura'  THEN 10
            WHEN 'ingreso'             THEN 5
            WHEN 'salidas'             THEN 5
            WHEN 'factura_pagos'       THEN 5
            ELSE 1
        END,
        NOW(),
        'pendiente',
        0
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all replicated [A] tables EXCEPT sync_queue itself
CREATE TRIGGER enqueue_sync_after_insert
    AFTER INSERT ON prod.salidas             FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
CREATE TRIGGER enqueue_sync_after_insert
    AFTER INSERT ON prod.factura_detalle    FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
-- ... (10 more triggers, one per replicated [A] table)
-- sync_queue itself has NO trigger (the IF branch handles the guard)
```

The API-side `parkos_core.repo.sync_outbox` is a no-op facade:

```python
# backend/packages/parkos_core/src/parkos_core/repo/sync_outbox.py
"""REQ: confirms that the DB trigger is doing the enqueue, not the API.

If you ever feel tempted to enqueue a sync_queue row from Python, DON'T.
The DB trigger guarantees atomicity (no orphan inserts) and consistency
(filter on TG_TABLE_NAME)."""
def enqueue_sync_row(*args, **kwargs):
    raise RuntimeError(
        "parkos_core.repo.sync_outbox.enqueue_sync_row is a no-op by design. "
        "The DB trigger prod.fn_enqueue_sync() handles enqueue. "
        "See bootstrap-monorepo-foundation/design.md §Data Flow."
    )
```

Test (PR2):

```python
# tests/migrations/test_sync_outbox_recursion.py
async def test_sync_queue_insert_does_not_recurse(db_session):
    initial_count = await db_session.scalar(select(func.count()).select_from(SyncQueue))
    await append_event(db_session, SyncQueue, {
        "tabla": "factura_pagos",  # arbitrary; the trigger fires regardless
        "uuid_registro": uuid.uuid4(),
        "datos": {},
        "estado": "pendiente",
        "prioridad": 1,
    }, actor_uuid=uuid.uuid4())
    await db_session.commit()
    new_count = await db_session.scalar(select(func.count()).select_from(SyncQueue))
    assert new_count == initial_count + 1  # exactly ONE new row, not two (no recursion)

async def test_other_a_table_insert_creates_sync_row(db_session):
    initial_count = await db_session.scalar(select(func.count()).select_from(SyncQueue))
    await append_event(db_session, FacturaPagos, {
        "uuid_factura": uuid.uuid4(),
        "medio_pago": "efectivo",
        "valor": Decimal("100.00"),
        "tipo_movimiento": "pago",
    }, actor_uuid=uuid.uuid4())
    await db_session.commit()
    new_count = await db_session.scalar(select(func.count()).select_from(SyncQueue))
    assert new_count == initial_count + 1
    row = (await db_session.execute(select(SyncQueue).order_by(SyncQueue.created_at.desc()).limit(1))).scalar()
    assert row.tabla == "factura_pagos"
```

## 13. Alembic migration strategy

Bootstrap ships `0001_initial_schema.py` in F1 (one big file, `size:exception`). This change adds migrations per the 800-line PR budget.

### Per-PR migration rule

Each PR adds AT MOST one migration. The migration may include multiple DDL operations but must be one revision. The migration filename follows bootstrap's convention: `YYYY_MM_DD_NNNN_<slug>.py` (`script.py.mako` template).

### Per-PR migration table

| PR | Migration | What | REVOKE+trigger? |
|---|---|---|---|
| PR0 (docs) | none | doc drift reconciliation | n/a |
| PR1 | none | uses bootstrap's `0001_initial_schema.py` | already done by bootstrap |
| PR1 | `0003_seed_permisos_canonicos.py` | INSERT canonical permission codes (REQ-OP-13) | n/a |
| PR2 | (none — uses bootstrap's partitions + REVOKE) | PR2 ships only the ORM + helpers for sync infra | already done by bootstrap |
| PR3–PR5 | none | ORM-only changes (no DDL) | n/a |
| PR6 | `0004_add_factura_pagos_reverso_index.py` | partial unique index for reverso (REQ-OP-09) | not an `[A]` table mod (index only) |
| PR7 | `0002_add_idempotency_keys.py` | 50th table + REVOKE + trigger | YES — same migration, per `config.yaml` `rules.tasks` |

If a future PR must touch an `[A]` table's column structure (e.g., `caja` adds a new audit column), the migration MUST include the REVOKE + trigger re-assertion in the SAME migration, even though they're unchanged. This is the project's hard rule (`openspec/config.yaml` `rules.tasks`).

### Pre-flight `alembic upgrade --sql` check

Every migration applied via:
```bash
cd backend/packages/parkos_core
uv run alembic upgrade --sql head 2>&1 | head -500
```
followed by visual inspection. The check fires in CI via `tests/migrations/test_alembic_drift.py`:
```python
def test_alembic_drift():
    """Runs `alembic check` and asserts exit 0."""
    result = subprocess.run(
        ["uv", "run", "alembic", "check"],
        cwd="backend/packages/parkos_core", capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic drift detected:\n{result.stdout}\n{result.stderr}"
```

### Trigger + REVOKE packaging rule

For ANY migration that:
- Creates a new `[A]` table: include `REVOKE UPDATE, DELETE ...` AND the `BEFORE UPDATE OR DELETE` trigger creation in the SAME migration.
- Drops an `[A]` table: include `GRANT UPDATE, DELETE ...` to allow downgrade to succeed.
- Alters an `[A]` table's columns: re-assert REVOKE (defensive — if a previous migration accidentally GRANTed, this recovers).

```python
# Example skeleton: 0002_add_idempotency_keys.py
def upgrade():
    op.create_table(
        "idempotency_keys",
        sa.Column("uuid", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("key_hash", sa.CHAR(64), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("request_payload_hash", sa.CHAR(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=False),
        sa.Column("response_body", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW() + INTERVAL '24 hours'")),
        sa.Column("created_by", PG_UUID(as_uuid=True), nullable=False),
        schema="prod",
    )
    op.create_index(
        "uq_idempotency_keys_key_hash_endpoint",
        "idempotency_keys", ["key_hash", "endpoint"],
        unique=True, postgresql_where=sa.text("expires_at > NOW()"),
        schema="prod",
    )
    # REVOKE + TRIGGER in the SAME migration (config.yaml rules.tasks)
    op.execute("REVOKE UPDATE, DELETE ON prod.idempotency_keys FROM rol_app")
    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_idempotency_keys_inmutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'IDEMPOTENCY_KEYS_INMUTABLE' USING ERRCODE = '42501';
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER idempotency_keys_inmutable
        BEFORE UPDATE OR DELETE ON prod.idempotency_keys
        FOR EACH ROW EXECUTE FUNCTION prod.fn_idempotency_keys_inmutable();
    """)

def downgrade():
    op.execute("DROP TRIGGER IF EXISTS idempotency_keys_inmutable ON prod.idempotency_keys")
    op.execute("DROP FUNCTION IF EXISTS prod.fn_idempotency_keys_inmutable()")
    op.execute("GRANT UPDATE, DELETE ON prod.idempotency_keys TO rol_app")  # downgrade succeeds
    op.drop_table("idempotency_keys", schema="prod")
```

`env.py` (bootstrap-extended):
```python
# include_schemas=True (bootstrap)
# include_object callback to keep prod.* objects in autogenerate:
def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and object.schema != "prod":
        return False
    return True
```

## 14. File-by-file deliverable plan

The 8-PR slicing is ratified in `proposal.md` §"PR slicing". Per PR:

| PR | Branch | Files touched (new / modified) | LOC | Tables added (ORM) | Migration # | New helpers | New tests |
|---|---|---|---|---|---|---|---|
| **PR0** | `docs/create-49-table-apis-pr0-doc-reconcile` | `openspec/PROJECT_CONTEXT.md`, `openspec/_meta/roadmap.md`, `openspec/_meta/iteration-plan.md`, `openspec/config.yaml`, `openspec/scripts/check_table_counts.py` | ~40 | none | none | n/a | script self-test |
| **PR1** | `feat/create-49-table-apis-pr1-orm-auth` | `backend/packages/parkos_core/src/parkos_core/models/{V,L_S,A}/<table>.py` × 9 (usuarios, permisos, permisos_usuario, usuarios_sucursal via V; login via L_S; sync_queue, log_transaccional via A — but no helpers yet), `models/base.py`, `schemas/{auth,common}.py`, `repo/{versioned,session_cycle,append_only,event,workflow,pagination,idempotency}.py` (stubs full for versioned+session_cycle, stubs for others), `auth/{jwt_issuer_guard,permissions,tenancy,tokens}.py`, `api/{router_factory,deps,middleware}.py`, `api/v1/{auth,__init__}.py`, `api/v1/catalogos.py` (1 table mounted for smoke), `api/v1/caja_sesion.py` (login only), `tests/migrations/{test_a_inmutable,test_ls_session_guard,test_revokes_active,test_partman_parents}.py`, `tests/static/{test_no_delete_routes,test_no_raw_upsert_on_v_tables,test_no_raw_dml_on_a_tables,test_no_raw_dml_on_ls_tables,test_openapi_branch_excludes_cloud,test_openapi_no_delete_operations}.py`, `tests/unit/{test_versioned_close_and_insert,test_jwt_issuer_guard,test_permissions_dependency,test_tenancy_operador,test_tenancy_admin,test_pagination_cursor,test_session_cycle_open_close}.py`, `conftest.py`, `backend/packages/parkos_core/migrations/versions/0003_seed_permisos_canonicos.py`, `openspec/scripts/preflight_table_counts.sh` | ~700 | 7 (5 V + 1 L_S + 1 A for log_transaccional OR) | 0003_seed_permisos_canonicos | `close_and_insert`, `current_version`, `history`, `list_with_cursor`, `verify_jwt`, `requires_issuer`, `require_permission`, `get_tenant_ctx`, `append_event` (stub) | 12 migration fixtures + 6 static + 7 unit |
| **PR2** | `feat/create-49-table-apis-pr2-a-infra` | `models/A/{sync_queue,sync_log,sync_conflict,log_transaccional,caja,arqueo,revocacion_factura}.py` × 7, `repo/{append_only,hash_chain,sync_outbox}.py` (full), `schemas/sync_infra.py`, `tests/migrations/{test_hash_chain_genesis,test_sync_outbox_recursion}.py`, `tests/unit/{test_append_only,test_hash_chain_append,test_hash_chain_break}.py` | ~700 | 7 `[A]` | none | `append_event`, `hash_chain.append`, `mark_dispatched`, `mark_failed`, `schedule_retry` | 2 migration + 3 unit |
| **PR3** | `feat/create-49-table-apis-pr3-catalogs` | `models/V/{tipo_persona,tipos_vehiculo,tipo_subscripciones,tipo_tarifa,tipo_sucursal,tipo_arqueo,impuestos,otros_cobros,costos_servicios}.py` × 9, `schemas/catalogos.py`, `api/v1/catalogos.py` (full — 9 tables mounted) | ~600 | 9 `[V]` | none | n/a | unit per table (≈ 27 cases, shared scaffolding) |
| **PR4** | `feat/create-49-table-apis-pr4-empresa-sucursal` | `models/V/{empresa,sucursal,documentos,resolucion_facturacion,tarifas_sucursal,cantidad_vehiculos_sucursal,configuracion_tolerancias,configuracion_seguridad}.py` × 8, `schemas/{empresa,configuracion}.py`, `api/v1/{empresa,sucursal,configuracion}.py`, `tests/unit/test_config_override_resolution.py` | ~750 | 8 `[V]` | none | n/a | config override scenario |
| **PR5** | `feat/create-49-table-apis-pr5-commercial-ingreso` | `models/{V,L_E}/{clientes,clientes_b2b,subscripciones_cliente,vehiculos,subscripcion_vehiculos,ingreso,salidas}.py` × 7, `schemas/{clientes,operacion}.py`, `repo/event.py` (full), `api/v1/{clientes,operacion}.py`, `tests/unit/test_event_record.py` | ~800 | 7 (5 V + 1 L_E + 1 A) | none | `record_event` | unit per table + derived estado |
| **PR6** | `feat/create-49-table-apis-pr6-operations-workflows` | `models/{L_E,L_W,A}/{facturas,factura_electronica,factura_detalle,factura_impuestos,factura_otros_cobros,factura_pagos,anulaciones,reclamos,alerta,reimpresion_ticket,envio_dian,validacion_evento}.py` × 12, `schemas/{facturacion,workflows,dian}.py`, `repo/{workflow,factura_pagos}.py` (full), `dian/cloud_router.py` (DIAN-only), `api/v1/{facturacion,workflows}.py`, `tests/static/{test_no_raw_dml_on_lw_tables,test_dian_boundary_branch,test_reclamos_polymorphic_validator}.py`, `tests/migrations/{test_factura_pagos_reverso_index}.py`, `tests/unit/{test_workflow_append_transition,test_workflow_read_chain_tip,test_factura_pagos_reverse}.py`, `backend/packages/parkos_core/migrations/versions/0004_add_factura_pagos_reverso_index.py` | ~800 | 12 (2 L_E + 6 L_W + 4 A billing) | 0004_add_factura_pagos_reverso_index | `append_transition`, `read_chain_tip`, `reverse_payment` | 6 |
| **PR7** | `feat/create-49-table-apis-pr7-caja-sesion` | `models/{L_S,A}/{sesion,caja,arqueo,idempotency_keys}.py` × 4, `schemas/{caja,idempotency}.py`, `repo/{session_cycle,idempotency}.py` (full), `api/v1/caja.py`, `tests/migrations/{test_idempotency_keys_inmutable}.py`, `tests/unit/{test_idempotency_guard,test_idempotency_ttl,test_session_cycle_login_failure_lockout,test_session_cycle_logout}.py`, `backend/packages/parkos_core/migrations/versions/0002_add_idempotency_keys.py` | ~600 | 4 (1 L_S + 2 A + 1 idempotency 50th) | 0002_add_idempotency_keys | `open_session`, `close_session_with_log`, `record_login`, `close_login_with_log`, `idempotency_guard`, `idempotency_store_response` | 5 |

Total: 49 [V]/[L]/[A] tables + 1 idempotency_keys = 50 ORM models across 7 code PRs.

PR6 is the budget-edge PR (12 tables + ~800 LOC). The conditional split into PR6a + PR6b is documented in `proposal.md` PR6 description; apply-time triggers if `git diff --stat` exceeds 800 LOC.

PR7 carries the `idempotency_keys` migration — that table is the 50th `[A]` and is created by PR7, NOT by bootstrap. This is documented in `proposal.md` "NEW — MED" risk.

## 15. Testing strategy

The change inherits `openspec/config.yaml` testing config (strict_tdd: false). Pytest infrastructure lands in PR1; thereafter every PR adds fixtures for its own helpers and integration tests for its routers.

### pytest fixtures per class (PR1)

```python
# backend/tests/conftest.py
import pytest, asyncio, uuid
from testcontainers.postgres import PostgresContainer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from parkos_core.db.base import Base
import parkos_core.models  # noqa: F401 — register all ORM classes

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg

@pytest_asyncio.fixture(scope="session")
async def engine(postgres_container):
    raw = postgres_container.get_connection_url()
    url = raw.replace("postgresql+psycopg", "postgresql+asyncpg")
    eng = create_async_engine(url)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS prod"))
        # Bootstrap migration applies the full schema; here we just create_all for unit tests.
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()

@pytest_asyncio.fixture
async def db_session(engine):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
        await session.rollback()  # each test starts fresh

# JWT mint helpers
@pytest.fixture
def mint_admin_jwt():
    from parkos_core.auth.tokens import issue_token
    def _mint(uuid=None, sucursales_permitidas=None):
        return issue_token(
            scope="admin",
            claims={
                "sub": str(uuid or uuid.uuid4()),
                "sucursales_permitidas": sucursales_permitidas or [str(uuid.uuid4())],
                "iss": "admin-test",
            },
            ttl_seconds=3600,
        )
    return _mint
# Similar for operador_jwt, sync_agent_jwt
```

### The 12 immutability fixtures (one per [A] table)

`tests/migrations/test_a_inmutable.py` (PR1, runs once the `[A]` schema exists from bootstrap):

```python
@pytest.mark.parametrize("table_name,table_cls", [
    ("salidas",              Salidas),
    ("factura_detalle",      FacturaDetalle),
    ("factura_impuestos",    FacturaImpuestos),
    ("factura_otros_cobros", FacturaOtrosCobros),
    ("factura_pagos",        FacturaPagos),
    ("revocacion_factura",   RevocacionFactura),
    ("caja",                 Caja),
    ("arqueo",               Arqueo),
    ("sync_queue",           SyncQueue),
    ("sync_conflict",        SyncConflict),
    ("sync_log",             SyncLog),
    ("log_transaccional",    LogTransaccional),
])
async def test_a_table_inmutable(db_session, table_name, table_cls):
    """INSERT succeeds; UPDATE raises <TABLE>_INMUTABLE; DELETE raises same."""
    # ... insert a minimal row, then attempt UPDATE/DELETE ...
```

### The 2 session-guard fixtures (one per [L-S] table)

```python
# tests/migrations/test_ls_session_guard.py
async def test_sesion_update_requires_log(db_session):
    sesion_uuid = uuid.uuid4()
    # Insert a sesion row first
    db_session.add(Sesion(uuid=sesion_uuid, ..., estado='abierta'))
    await db_session.commit()
    # Attempt UPDATE without prior log_transaccional insert in this TX
    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        await db_session.execute(
            update(Sesion).where(Sesion.uuid == sesion_uuid).values(estado='cerrada')
        )
        await db_session.commit()
    assert 'LOG_TRANSACCIONAL_REQUIRED' in str(exc_info.value)

async def test_login_update_requires_log(db_session):
    # ... symmetric ...
```

### CI lint rules

`backend/.ruff.toml` additions in PR1:

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC", "SIM", "PT", "RUF"]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["B", "PT011", "S101"]
"migrations/**/*.py" = ["E501"]
```

Plus custom AST scan tests in `tests/static/`:

| File | What it scans | Failure mode |
|---|---|---|
| `test_no_raw_upsert_on_v_tables.py` | `parkos_core/api/v1/*.py` and `parkos_core/repo/` (excluding `versioned.py`) for `session.execute(update(...))` against any of the 26 `[V]` ORM classes | CI red |
| `test_no_raw_dml_on_a_tables.py` | Same scope, but `update/delete` against any of the 13 `[A]` ORM classes outside `append_only.py` and `sync_queue` carve-out | CI red |
| `test_no_raw_dml_on_lw_tables.py` | Same, `update/delete` against the 6 `[L-W]` classes outside `workflow.py` | CI red |
| `test_no_raw_dml_on_le_tables.py` | Same, against the 3 `[L-E]` classes outside `event.py` | CI red |
| `test_no_raw_dml_on_ls_tables.py` | Same, against the 2 `[L-S]` classes outside `session_cycle.py` | CI red |
| `test_no_delete_routes.py` | Emitted `api_*/openapi.json` for `delete:` operations | CI red |
| `test_openapi_branch_excludes_cloud.py` | `api_sucursal/openapi.json` for cloud-only paths | CI red |

The AST scan uses Python's `ast` module; ORM class names are imported from `parkos_core.models` at test load time. Each scan iterates the AST looking for `ast.Call` nodes whose function name matches `session.execute` and whose first argument is `ast.Call(func=ast.Attribute(attr="update"|"delete"))`.

## 16. OpenAPI 3.1 contract

REQ-OP-02 + REQ-OP-14.

### Generator

`parkos_core.openapi` (CLI module, `__main__.py`):

```bash
uv run python -m parkos_core.openapi --deploy cloud  --output backend/packages/api_admin/openapi.json
uv run python -m parkos_core.openapi --deploy branch --output backend/packages/api_sucursal/openapi.json
```

Each call:
1. Sets `PARKOS_DEPLOY=cloud` or `branch` env var.
2. Imports the appropriate app (`api_admin_main.app` or `api_sucursal_main.app`).
3. Calls `app.openapi()` which returns the OpenAPI 3.1 schema (FastAPI >= 0.100 supports this natively).
4. Sets `info.version = _git_sha()` for traceability.
5. Writes the JSON to the path.

### Per-audience tag split (REQ-OP-14)

The `app.openapi()` is post-processed by a filter that keeps only the tags for the current audience:

```python
ALLOWED_TAGS = {
    "cloud":  {"admin", "operador", "sync", "cloud-only", "auth"},
    "branch": {"operador", "sync", "auth"},
}
# Tag-based filter: drop paths whose tag is not in ALLOWED_TAGS[deploy]
```

The four cloud-only routes (under `dian/cloud_router.py`) carry `tags=["cloud-only"]`. On the branch image, the cloud_router import fails, so those routes don't exist; the tag filter is belt-and-suspenders defense.

### SDK strategy (REQ-OP-02 resolution Q2)

Chosen tool: **`openapi-typescript-codegen`** (https://github.com/ferdikoomen/openapi-typescript-codegen). Rationale:
- Zero runtime dependency (generates pure TS interfaces + a fetch wrapper).
- Deterministic output (CI-stable git diffs).
- Tree-shakable: dead-code elimination works on the generated client.
- Supports OpenAPI 3.1 directly.

Alternatives rejected:
- `openapi-fetch`: too thin; requires hand-writing Zod schemas for runtime validation.
- `orval`: heavier runtime; React-Query coupling by default.

The frontend `apps/ui-kit/package.json` scripts:

```json
{
  "scripts": {
    "gen:api:admin": "openapi-typescript-codegen --input backend/packages/api_admin/openapi.json --output ./src/api/admin/generated --client fetch",
    "gen:api:branch": "openapi-typescript-codegen --input backend/packages/api_sucursal/openapi.json --output ./src/api/branch/generated --client fetch"
  }
}
```

Frontend PRs pin to a specific git SHA of the openapi.json (ADR per `info.version` field).

### Tag-based DIAN verification (REQ-X3)

CI step:
```bash
jq -r '.paths | keys | map(select(test("/factura-electronica|/revocacion-factura|/envio-dian|/validacion-evento"))) | length' \
    backend/packages/api_sucursal/openapi.json
# Expected output: 0
# Non-zero → CI red
```

## 17. Risks and mitigations

Carrying forward 5 HIGH risks from propose + 7 from spec + 4 NEW from design. Severity rationale is unchanged unless noted.

| # | Sev | Risk | Mitigation |
|---|---|---|---|
| 1 | **HIGH** | Doc drift poisons bootstrap PR2 (`0001_initial_schema.py` ships with 45 tables) | PR0 lands BEFORE bootstrap PR2 lands; `preflight_table_counts.sh` aborts on `<49` tables; PR0b (bootstrap maintainer-owned) follows before bootstrap PR2 reviews approval |
| 2 | **HIGH** | DIAN-only boundary breach (branch imports `dian.cloud_router`) | Image-level exclusion (Docker `.dockerignore`); module-level import-guard with `PARKOS_DEPLOY` env var; RED test `test_dian_boundary_branch.py`; OpenAPI tag filter; CI `jq` check |
| 3 | **HIGH** | Hash-chain break on partial sync | `hash_chain.append()` reads prior `MAX(timestamp_evento)` per `uuid_sucursal`; rejects mismatch with `HashChainIntegrityViolation`; per-branch monotonic seq in `datos` JSON; cloud verifier (out of scope here) writes `sync_conflict` + opens `alerta` |
| 4 | **HIGH** | `[A]` REVOKE + trigger not enforced (raw UPDATE/DELETE via `session.execute()`) | AST tests `test_no_raw_dml_on_a_tables.py` + 12 immutability fixtures in `test_a_inmutable.py`; ruff rule + the `__write_only__` class marker |
| 5 | **HIGH** | `[L-S]` UPDATE-without-log passes | Trigger `ls_session_update_guard()` raised in bootstrap; `session_cycle.close_session_with_log()` writes log FIRST then UPDATE; 2 migration fixtures in `test_ls_session_guard.py` |
| 6 | **MED** | PR6 at the budget edge (12 tables, ~800 LOC) | Conditional split PR6a + PR6b documented in `proposal.md` PR6; applies if `git diff --stat` post-implementation > 800 LOC |
| 7 | **MED** | `sync_queue` recursion (INSERT into `sync_queue` triggers another enqueue) | Bootstrap trigger's `WHEN (TG_TABLE_NAME <> 'sync_queue')`; PR2 test asserts one row only; `sync_outbox.enqueue_sync_row()` raises RuntimeError |
| 8 | **MED** | `pg_partman` partition pruning misses | ORM helpers require `partition_key_from`/`partition_key_to` for the 8 partitioned `[A]` tables; lint warning when missing; unit test verifies EXPLAIN plan |
| 9 | **MED** | Gitflow not initialized (current branch is `master`, no `dev`) | PR1 first commit renames `master` → `main`, creates `dev` (one-time); subsequent PRs target `dev`; release branches → `main` after cert |
| 10 | **MED** | `[L-W]` chain tie-break determinism | `read_chain_tip()` algorithm in `repo/workflow.py` §4.2; tested in `test_workflow_read_chain_tip.py` with N chains |
| 11 | **MED** | Bootstrap artifacts still say 45 tables after PR0 | PR0b spec'd; user/maintainer owns the bootstrap merge; ~25-line patch |
| 12 | **LOW** | OpenAPI doc bloat (~245 paths, ~2MB) | Per-audience split (`api_admin` vs `api_sucursal`); gzip in CI artifact |
| 13 | **LOW** | Pydantic v2 ↔ ORM field drift | `from_attributes=True` + identical field names; CI test loads each schema + validates a sample row via `model_validate(row)` |
| 14 | **NEW — HIGH** | `revocacion_factura` not in cloud-only router list at PR6 | The router file `parkos_core/dian/cloud_router.py` is the SINGLE mount point for the 4 cloud-only tables; CI asserts only that file imports them; RED import-boundary test covers all four |
| 15 | **NEW — MED** | `tipo_arqueo` FK requires bootstrap to ship that table | Pre-flight `preflight_table_counts.sh` covers; PR3 cannot proceed if `\dt prod.*` shows missing `tipo_arqueo` |
| 16 | **NEW — MED** | `idempotency_keys` is the 50th `[A]` table — out of scope for bootstrap | PR7 ships migration `0002_add_idempotency_keys.py` with REVOKE + trigger in same script |
| 17 | **NEW — MED** | Polymorphic FK validator performance (REQ-OP-08) | Redis cache (60s TTL) populated by sync worker; cloud-side; branch-side reads local DB (no network hop). Cache miss falls back to direct DB read. Adds a Redis dep to the cloud image's middleware stack — Redis already in compose |
| 18 | **NEW — MED** | Subscription vehicle count validator (`subscripcion_vehiculos` count ≤ `cantidad_maxima_vehiculos` of the plan) | Pydantic `model_validator(mode='after')` runs `SELECT COUNT(*) FROM subscripcion_vehiculos WHERE uuid_subscripcion_cliente=:s AND vigente_hasta IS NULL` on insert; 422 on overflow. Race condition on concurrent inserts: advisory lock per `uuid_subscripcion_cliente` inside the validator's TX |

## 18. Acceptance criteria

The change is "done" when:

1. **ORM**: 50 ORM classes (49 + `idempotency_keys`) exist under `parkos_core/models/{V,L_E,L_W,L_S,A}/`, each subclassing the correct base (`VersionedBase`, `LifecycleEventBase`, `WorkflowBase`, `SessionBase`, `AppendOnlyBase`) with the correct mixins.
2. **API**: every table has a list endpoint (AD-1); zero `delete:` operations in either emitted `openapi.json`; the per-audience OpenAPI artifacts are committed (`api_admin/openapi.json`, `api_sucursal/openapi.json`).
3. **Three-layer enforcement** verified by automated tests:
   - **API**: `tests/static/test_no_delete_routes.py` + `test_openapi_no_delete_operations.py` pass.
   - **ORM**: AST tests `test_no_raw_{upsert_v,dml_a,dml_lw,dml_le,dml_ls}.py` pass.
   - **DB**: 11 `[A]` REVOKE statements active (`test_revokes_active.py`); 12 `BEFORE UPDATE OR DELETE` triggers fire (`test_a_inmutable.py`); 2 `[L-S]` UPDATE guards require co-transactional `log_transaccional` (`test_ls_session_guard.py`); 8 `pg_partman` partition parents configured (`test_partman_parents.py`); `log_transaccional` + `revocacion_factura` hash chain genesis verified (`test_hash_chain_genesis.py`).
4. **8 chained PRs land on `dev`**: PR0 docs + PR1–PR7 code, each independently revertible, each ≤ 800 LOC (PR5/PR6 may split per `proposal.md`).
5. **JWT three-issuer enforcement**: `test_jwt_cross_audience.py` (admin→api_sucursal/auth/login → 401; operador→api_admin → 401; sync_agent→any api/auth/login → 401) passes.
6. **DIAN-only boundary**: `test_dian_boundary_branch.py` asserts ImportError on branch; `test_openapi_branch_excludes_cloud.py` asserts zero cloud-only paths in `api_sucursal/openapi.json`.
7. **Alembic migration test harness**: `alembic check` exits 0; pre-flight `preflight_table_counts.sh` exits 0 against migrated DB; `0002_add_idempotency_keys.py` includes REVOKE + trigger in same migration.
8. **Doc drift reconciled**: PR0 merged; PR0b has been filed (or merged) for bootstrap artifacts.
9. **Gitflow**: `master` → `main` rename done; `dev` branch created; AGENTS.md cross-checked.
10. **Idempotency-Key**: 50th table `idempotency_keys` exists with REVOKE + trigger; POST endpoints without `Idempotency-Key` return 400; replay returns cached response with `Idempotent-Replay: true` header.
11. **Hash chain**: `hash_chain.append()` extends chain per `uuid_sucursal`; out-of-order sync raises `HashChainIntegrityViolation`; verifier (out of scope here) catches breaks via the same path.
12. **All existing tests pass**: `alembic check`, `ruff check`, `mypy --strict`, `pytest -q`, `preflight_table_counts.sh`.
13. **OpenAPI TS codegen pinned**: `apps/ui-kit/scripts/gen:api:{admin,branch}` produce deterministic output; `info.version` is the git SHA.

## 19. Out of scope (deferred)

These items were explicitly declared out-of-scope in `proposal.md` §"Out of scope" and `operational.md` §"Out of scope". They are NOT deliverables of this change:

- **DIAN HTTP transport**: `dian_dispatcher` (Factus / other provider adapter), `atomic_next_consecutivo()` in `parkos_core/dian/cloud/` — bootstrap PR5 owns.
- **Sync engine implementation**: `job_sync_cloud`, `job_sync_sucursal`, `sync_queue_processor`, `sync_conflict_policy`, `sync_back`, `pairing` — bootstrap PR5 owns. This change uses the ORM helpers but does NOT implement the transport.
- **Web frontend**: `web_admin` PWA, `web_sucursal` PWA, `ui-kit` — bootstrap PR6 owns.
- **Operational tooling**: rate limiting, OpenTelemetry tracing, Prometheus exporters, circuit breakers, expanded `/health` checks — separate change.
- **RBAC permission matrix population**: the framework ships (`require_permission()` dep); matrix authoring (per-permission assignment for each role) is a follow-up change.
- **OpenAPI TS client SDK generator wiring**: `apps/ui-kit/package.json` `gen:api:*` scripts — bootstrap PR6 owns.
- **Bulk-CSV import endpoints**: `POST /catalogos/<x>:batch` — separate change per REQ-OP-06.
- **`multipart/form-data` for `documentos`**: only `application/json` with `documento_b64` (5MB cap) is in scope per REQ-OP-05; streaming upload endpoint lands later.
- **WebSocket sync transport**: polling only for v1; WebSocket deferred to v2.
- **Hash chain verifier worker**: `workers/hash_chain_verifier` — bootstrap PR5 owns; this change ships the `hash_chain.append()` helper only.
- **TTL worker for `idempotency_keys` nightly cleanup**: separate batch (currently planned as a cron; see `pruning` section in `idempotency_keys` table docs).
- **`permisos` matrix seeding beyond canonical set**: PR1 ships `0003_seed_permisos_canonicos.py` with the ~15 canonical permissions (`aprobar_anulacion`, `ejecutar_anulacion`, `crear_arqueo`, `solicitar_reverso`, `cerrar_sesion`, `descartar_alerta`, `config_catalogo`, `config_sistema`, `config_sucursal`, `gestionar_clientes`, `emitir_factura`, `emitir_factura_electronica`, `revocar_factura`, `gestionar_dian`, `audit_read`, `admin_usuarios`). Per-role assignment is deferred.

## 20. References

| File | Lines | Purpose |
|---|---|---|
| `E:\easypunto_parkos\openspec\changes\create-49-table-apis\proposal.md` | 644 | Inputs read |
| `E:\easypunto_parkos\openspec\changes\create-49-table-apis\exploration.md` | 345 | Prior phase |
| `E:\easypunto_parkos\openspec\changes\create-49-table-apis\specs\bi-temporal-crud.md` | 100 | 26 [V] spec |
| `E:\easypunto_parkos\openspec\changes\create-49-table-apis\specs\append-only-events.md` | 109 | 12 [A] spec |
| `E:\easypunto_parkos\openspec\changes\create-49-table-apis\specs\workflow-transitions.md` | 113 | 6 [L-W] spec |
| `E:\easypunto_parkos\openspec\changes\create-49-table-apis\specs\lifecycle-events.md` | 107 | 3 [L-E] spec |
| `E:\easypunto_parkos\openspec\changes\create-49-table-apis\specs\session-cycles.md` | 90 | 2 [L-S] spec |
| `E:\easypunto_parkos\openspec\changes\create-49-table-apis\specs\cross-cutting.md` | 114 | 6 cross-cutting REQs (X1–X9) |
| `E:\easypunto_parkos\openspec\changes\create-49-table-apis\specs\operational.md` | 152 | 15 REQs (Q1–Q12 + OP-01–OP-15) |
| `E:\easypunto_parkos\modelo_datos_er.mmd` | 1178 | Canonical 49-table ER (single source of truth) |
| `E:\easypunto_parkos\AGENTS.md` | 263 | Project canon: Audit-First, Bi-Temporal, no-DELETE, three JWT issuers, gitflow |
| `E:\easypunto_parkos\openspec\changes\bootstrap-monorepo-foundation\design.md` | 105 | Monorepo skeleton + DIAN split + 6-PR layout |
| `E:\easypunto_parkos\openspec\changes\bootstrap-monorepo-foundation\tasks.md` | ~700 | F1 walking skeleton tasks (defines where this change's code attaches) |
| `E:\easypunto_parkos\openspec\config.yaml` | 63 | SDD rules (REVOKE+trigger same migration; `rules.design`: sequence diagrams for sync flows; architecture decisions with rationale; partition models by audit level) |
| Engram #1264 | — | Exploration memory snapshot |
| Engram #1265 | — | Proposal memory snapshot |
| Engram #1266 | — | Spec memory snapshot (39 REQs, 26 SCs, all 12 Qs resolved) |

This design honors the architectural decisions AD-1 (list endpoints for all 49), AD-2 (RBAC API + DB), AD-3 (Idempotency-Key REQUIRED, 50th `[A]` table), AD-4 (derived state nested under parent resource). All four are visible in §5 (`make_router`), §7 (RBAC layering), §8 (Idempotency-Key middleware), and §5 (`derived_view` parameter + nested `/estado` routes).

The 12 resolved open questions from `exploration.md` are reflected in:
- Q1 (cursor pagination) → §4.8 `pagination.py` + §5 `make_router` + REQ-OP-01.
- Q2 (TS codegen) → §16 `openapi-typescript-codegen` chosen.
- Q3 (sync endpoints mounted on both services) → §7 + REQ-OP-03.
- Q4 (tenant context via header) → §9 `X-Sucursal-Context`.
- Q5 (`multipart/form-data` for documentos) → REQ-OP-05; base64 inline accepted in MVP.
- Q6 (bulk ops) → REQ-OP-06 deferred.
- Q7 (`permisos_usuario` revoke = bi-temporal close) → REQ-OP-07.
- Q8 (`reclamos.tipo_reclamable` polymorphic validator) → REQ-OP-08 + §6 Pydantic.
- Q9 (factura_pagos reverso 1:1 partial unique index) → §13 migration `0004_add_factura_pagos_reverso_index.py` + §4.4 `reverse_payment`.
- Q10 (`alerta.descartada` admin-only) → REQ-OP-10 + §4.2 state machine.
- Q11 (login lockout: 3 / 15min / 30min) → REQ-OP-11 + REQ-43-S-LOGIN-FAILURE.
- Q12 (`V_RESOLUCION_CONSECUTIVO` live view + atomic `SELECT FOR UPDATE`) → REQ-OP-12 + §4.5 `record_factura_electronica_online`.

The 8-PR slicing (PR0 → PR7) plus the two conditional splits (PR5a/PR5b, PR6a/PR6b) from `proposal.md` is honored in §14. The 50th `idempotency_keys` table lands in PR7's migration `0002_add_idempotency_keys.py`.

This design introduces **no new architectural decisions** beyond what was ratified in proposal. Any item that could be considered a new decision is listed under §17 as a risk and flagged for spec update.

---

## 21. Deployment topology, pairing, sync transport, and DIAN dispatcher

> **Scope of §21**: this section re-opens the items §19 declared out-of-scope (`DIAN HTTP transport`, `sync engine implementation`, `web frontend`, `pairing flow`, `hash chain verifier worker`) and incorporates them into this change. Rationale: `bootstrap-monorepo-foundation` stays on the legacy `feature-branch-chain` and will not merge; this change must therefore own the complete cloud-edge ecosystem (PR8–PR11 below). All four sub-sections honor AGENTS.md `gitflow` (PRs to `dev` only) and `Audit-First / Compliance-Driven` (every `sync_queue` write goes through `repo/append_only.py::append_event()`; the 11 `[A]` REVOKE + trigger pattern applies to the two new `[A]` tables added here).

> **Preflight honored**: `pace=auto`, `artifact=hybrid`, `delivery=auto-chain`, `chain=gitflow`, `review_budget=800 lines/PR`. PR8–PR11 follow the same conditional-split rules as PR5/PR6 (per `tasks.md` §Per-PR workload forecast).

> **PR slicing delta (added by §21)**:

| PR | Tables | New files | LOC forecast | Risk | Notes |
|---|---|---|---|---|---|
| PR8 | 0 (env-only + validators) | ~6 | ~300 | LOW | `runtime/env.py`, `infra/deploy/{cloud,branch}.yml`, `runtime/cli.py` (`parkos-cli doctor`) |
| PR9 | 2 (`pairing_tokens`, `revoked_sync_jwts` — both `[A]`) | ~14 | ~700 | MED | Migration `0003_add_pairing_tokens_and_revoked_sync_jwts.py` with REVOKE + trigger in SAME migration per `config.yaml rules.tasks` |
| PR10 | 0 schema (orchestration + workers) | ~16 | ~800 (split-trigger → PR10a + PR10b) | **HIGH** | `parkos_core/jobs/{sync_sucursal,sync_cloud}.py`, `parkos_core/sync/{transport,conflict_resolver}.py`, `parkos_core/sync/{pairing,jwt_manager}.py` (replace bootstrap stubs) |
| PR11 | 0 schema (cloud-only dispatcher) | ~8 | ~400 | LOW | `parkos_core/dian/cloud/dispatcher.py`, `parkos_core/dian/cloud/atomic_next_consecutivo.py` (replace bootstrap stubs), `workers/dian_dispatcher/` |
| **Total** | **+2** | **~44** | **~2,200** | | 4 new chained PRs; PR10 carries a conditional split trigger at apply time |

> **References back into §1–§20**: §10 (DIAN-only boundary image-level), §11 (hash chain), §12 (sync triggers and outbox), §16 (OpenAPI 3.1 contract), §17 risk #8 (pairing-token replay — already enumerated, now resolved), §17 risk #4 ([A] REVOKE + trigger enforcement), and §17 risk #3 (hash-chain break on partial sync).

### 21.1 Deployment matrix (cloud vs branch)

Every process in the cloud-edge topology is mapped to its deployment target. Frontends are PWAs (built once, served differently per environment).

| Process | Cloud image | Branch image | Instances | Boundary |
|---|---|---|---|---|
| `api_admin` | YES (mounted) | NO | 1+ (HA-ready, multi-replica behind LB) | cloud-only |
| `api_sucursal` | NO | YES (mounted) | exactly 1 per branch (`uuid_sucursal` from env, see §21.2) | branch-only |
| `job_sync_cloud` | YES (mounted) | NO | 1 (single-flight; second instance would race on hash chain) | cloud-only |
| `job_sync_sucursal` | NO | YES (mounted) | exactly 1 per branch (paired with the local `api_sucursal`) | branch-only |
| `web_admin` (PWA) | YES (served from cloud) | NO | 1 (static artifact, CDN-friendly) | cloud-only |
| `web_sucursal` (PWA) | NO (NOT served from cloud; cloud admins use `web_admin`) | YES (bundled in branch image; serves itself) | exactly 1 per branch (static artifact, served by api_sucursal's reverse-proxy or sidecar) | branch-only |
| `postgresql-cloud` | YES | NO (but reachable from branches over VPN/tailscale/zero-trust tunnel — see §21.5) | 1 (or HA cluster) | cloud-only |
| `postgresql-branch` | NO (optional — see §21.6 scenario 2) | YES (default — see §21.6 scenario 1) | exactly 1 per branch | branch-only |

**Why two distinct PWAs (vs one parameterized)**: `web_admin` and `web_sucursal` have different bundle shapes (admin gets `sucursales_permitidas` selector + global catalog views; branch gets `preliminar` badge + disabled `reimpresion_ticket` until sync-back). Sharing one bundle inflates the critical-path JS for both audiences. Two PWAs, one per backend, is the cleanest cut.

**Why two separate sync workers (not embedded in the API)**: the user ratified this in `openspec/changes/cloud-edge-sync-architecture/exploration.md` §3 (`B. separate process`). Sync runs on a different cadence (poll + retry) than the request-serving API; coupling them would mean a stalled `httpx` call on the API event loop while a slow branch hangs. Separate processes also let us restart them independently (e.g. `docker restart job_sync_sucursal` after rotating a JWT, without dropping operator sessions).

### 21.2 Sucursal instance identity

**Each branch image runs EXACTLY ONE `uuid_sucursal`.** Identity comes from environment, not from the DB — this is a hard contract; a single branch image hosting two UUIDs would corrupt the sync queue partitioning and break hash chain attribution. See `tasks.md` §Out of scope reminders (#8) and AGENTS.md `Sync` §"`sync_queue` is `[A]` with operational UPDATE exception".

#### Required env vars (boot-time validator in `parkos_core/runtime/env.py`)

| Var | Required by | Format | Default | Behavior if missing/malformed |
|---|---|---|---|---|
| `PARKOS_SUCURSAL_UUID` | branch: `api_sucursal`, `job_sync_sucursal`, `web_sucursal` (server-side) | UUIDv4 | — | `MissingEnvError` (exit code `2 = misconfig`) |
| `PARKOS_DEPLOY` | every process | `"cloud"` \| `"branch"` | — | `MissingEnvError` |
| `PARKOS_DB_URL` | every process | Postgres DSN | — | `MissingEnvError` |
| `PARKOS_CLOUD_API_URL` | branch: `api_sucursal` (for `POST /sync/push`), `job_sync_sucursal` | `https://...` URL | — | `MissingEnvError` on branch; ignored on cloud |
| `PARKOS_SYNC_JWT_PATH` | branch: `api_sucursal` (when acting as sync-receiver), `job_sync_sucursal` | POSIX file path | `/etc/parkos/sync.jwt` | `MissingEnvError` after first successful pair |
| `PARKOS_PAIRING_TOKEN` | branch: ONE-TIME on first pair | UUIDv4 | unset | Required only on the very first boot after provisioning; orchestrator deletes the var after `POST /sync/pair` returns |
| `PARKOS_JWT_KEY_PATH` | cloud: `api_admin`, `job_sync_cloud`; branch: `api_sucursal`, `job_sync_sucursal` | POSIX dir | `/etc/parkos/jwt/` | `MissingEnvError` |
| `PARKOS_SYNC_POLL_INTERVAL_S` | branch: `job_sync_sucursal` | int 1..600 | `10` | invalid → warn + use default |
| `PARKOS_SYNC_BATCH_SIZE` | branch: `job_sync_sucursal` | int 1..500 | `100` | invalid → warn + use default |
| `PARKOS_SYNC_HEARTBEAT_S` | branch: `job_sync_sucursal` | int 5..600 | `60` | invalid → warn + use default |
| `PARKOS_DIAN_PROVIDER_URL` | cloud only: `api_admin`, `workers/dian_dispatcher` | `https://...` URL | — | `MissingEnvError` on cloud |
| `PARKOS_DIAN_PROVIDER_TOKEN_PATH` | cloud only | POSIX file path | `/etc/parkos/dian.token` | `MissingEnvError` on cloud |
| `PARKOS_DIAN_TIMEOUT_S` | cloud only | int 5..120 | `30` | invalid → warn + use default |
| `PARKOS_DIAN_RETRY_MAX` | cloud only | int 0..10 | `3` | invalid → warn + use default |
| `PARKOS_SYNC_VERIFY_INTERVAL_S` | cloud: `job_sync_cloud` (hash-chain verifier) | int 60..86400 | `3600` | invalid → warn + use default |
| `JWT_OVERLAP_HOURS` | both | int 1..168 | `24` | per AGENTS.md `JWT` (three issuers, grace rotation) |

#### Boot-time validator (`parkos_core/runtime/env.py`)

```python
"""Boot-time env validation for every parkos_core process.

AGENTS.md Audit-First canon: a misconfigured branch must NOT silently start;
otherwise the sync_queue writes go to the wrong uuid_sucursal and the hash
chain breaks attribution. We fail fast with a precise error message.
"""
from __future__ import annotations

import os
import sys
import uuid as uuid_lib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Final

DeployRole = Literal["cloud", "branch"]


class MissingEnvError(RuntimeError):
    """Raised when a required env var is absent or malformed. Exits code 2."""


@dataclass(frozen=True)
class BranchConfig:
    uuid_sucursal: uuid_lib.UUID
    cloud_api_url: str
    db_url: str
    jwt_key_path: Path
    sync_jwt_path: Path = Path("/etc/parkos/sync.jwt")
    sync_poll_interval_s: int = 10
    sync_batch_size: int = 100
    sync_heartbeat_s: int = 60


@dataclass(frozen=True)
class CloudConfig:
    db_url: str
    cloud_api_url: str  # same as branch; cloud is also a service
    jwt_key_path: Path
    dian_provider_url: str
    dian_provider_token_path: Path = Path("/etc/parkos/dian.token")
    dian_timeout_s: int = 30
    dian_retry_max: int = 3
    sync_verify_interval_s: int = 3600


def _require_uuid(env_name: str) -> uuid_lib.UUID:
    raw = os.environ.get(env_name)
    if not raw:
        raise MissingEnvError(f"{env_name} is required (UUIDv4); PARKOS_DEPLOY={os.environ.get('PARKOS_DEPLOY', 'unset')}")
    try:
        parsed = uuid_lib.UUID(raw)
    except ValueError as exc:
        raise MissingEnvError(f"{env_name}={raw!r} is not a valid UUID") from exc
    if parsed.version != 4:
        raise MissingEnvError(f"{env_name}={raw!r} is not UUIDv4 (got v{parsed.version})")
    return parsed


def _require_str(env_name: str, *, allow_empty: bool = False) -> str:
    raw = os.environ.get(env_name)
    if raw is None or (not allow_empty and not raw):
        raise MissingEnvError(f"{env_name} is required (non-empty string)")
    return raw


def _require_path(env_name: str) -> Path:
    raw = _require_str(env_name)
    return Path(raw)


def _optional_int(env_name: str, default: int, lo: int, hi: int) -> int:
    raw = os.environ.get(env_name)
    if raw is None:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default  # soft fallback; warn() in caller
    return max(lo, min(hi, v))


def load_config() -> "BranchConfig | CloudConfig":
    deploy = _require_str("PARKOS_DEPLOY")
    if deploy not in ("cloud", "branch"):
        raise MissingEnvError(f"PARKOS_DEPLOY={deploy!r} must be 'cloud' or 'branch'")
    db_url = _require_str("PARKOS_DB_URL")
    jwt_key_path = _require_path("PARKOS_JWT_KEY_PATH")
    cloud_api_url = _require_str("PARKOS_CLOUD_API_URL")

    if deploy == "branch":
        return BranchConfig(
            uuid_sucursal=_require_uuid("PARKOS_SUCURSAL_UUID"),
            cloud_api_url=cloud_api_url,
            db_url=db_url,
            jwt_key_path=jwt_key_path,
            sync_jwt_path=_require_path("PARKOS_SYNC_JWT_PATH"),
            sync_poll_interval_s=_optional_int("PARKOS_SYNC_POLL_INTERVAL_S", 10, 1, 600),
            sync_batch_size=_optional_int("PARKOS_SYNC_BATCH_SIZE", 100, 1, 500),
            sync_heartbeat_s=_optional_int("PARKOS_SYNC_HEARTBEAT_S", 60, 5, 600),
        )
    return CloudConfig(
        db_url=db_url,
        cloud_api_url=cloud_api_url,
        jwt_key_path=jwt_key_path,
        dian_provider_url=_require_str("PARKOS_DIAN_PROVIDER_URL"),
        dian_provider_token_path=_require_path("PARKOS_DIAN_PROVIDER_TOKEN_PATH"),
        dian_timeout_s=_optional_int("PARKOS_DIAN_TIMEOUT_S", 30, 5, 120),
        dian_retry_max=_optional_int("PARKOS_DIAN_RETRY_MAX", 3, 0, 10),
        sync_verify_interval_s=_optional_int("PARKOS_SYNC_VERIFY_INTERVAL_S", 3600, 60, 86400),
    )


def main() -> int:
    try:
        cfg = load_config()
    except MissingEnvError as exc:
        print(f"PARKOS BOOT FAILED: {exc}", file=sys.stderr)
        return 2
    print(f"PARKOS_BOOT_OK deploy={os.environ['PARKOS_DEPLOY']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

> **Why fail-fast (exit code 2) vs warn-and-continue**: AGENTS.md `Audit-First` principle. A silent fallback would let a branch start with `PARKOS_SUCURSAL_UUID=unset`, write to a fake zero-UUID, sync the wrong chain, and break hash chain attribution in cloud — undetectable for hours. Better to fail at boot in 200ms.

> **Why the same `load_config()` lives in `parkos_core/runtime/` (not in each deployable)**: the validator is the only writer of env-derived runtime state; every process (`api_sucursal`, `job_sync_sucursal`, `api_admin`, `job_sync_cloud`, `workers/dian_dispatcher`) imports it. One source of truth = one place to audit.

### 21.3 Pairing flow

A new branch must register with cloud before it can sync. One-time, operator-driven. AGENTS.md Risk Register row "Pairing-token replay" (`tasks.md` risks #8) is **closed** by this section.

#### Cloud side (`api_admin`)

Three endpoints, all under `/api/v1/admin/pairing-tokens/*`:

| Endpoint | Method | Auth | Body | Response |
|---|---|---|---|---|
| `/pairing-tokens` | POST | `admin-`, `require_permission("gestionar_dian")` | `{uuid_sucursal, ttl_hours?}` (default 24) | `{pairing_token: "<uuidv4>", pairing_token_uuid: "<uuid>", expires_at: "<iso>"}` (plaintext returned ONCE) |
| `/pairing-tokens/{pairing_token_uuid}` | GET | `admin-` | — | `{pairing_token_uuid, uuid_sucursal, expires_at, used, used_at, used_by_branch_info}` (audit view; plaintext token NOT returned) |
| `/pairing-tokens/{pairing_token_uuid}` | DELETE | `admin-`, `require_permission("gestionar_dian")` | — | `204 No Content` (sets `revoked_at`, `revoked_by`); subsequent consume attempt → 410 Gone |

Plus the per-branch revoke (separate path):

| Endpoint | Method | Auth | Body | Response |
|---|---|---|---|---|
| `/admin/sucursales/{uuid_sucursal}/revoke-sync` | POST | `admin-`, `require_permission("gestionar_dian")` | `{motivo}` | `204 No Content`; marks the branch's currently active `sync_jwt_uuid` in `revoked_sync_jwts` |

**Rate limit**: `5 tokens/hour/admin` per `parkos_core/api/v1/pairing_tokens.py::create_pairing_token` (in-memory token bucket per `admin_uuid`, OR Redis counter if cloud has Redis — branch-side has no Redis). Six tokens in 60 min → 429 `{"error":"pairing_token_rate_limited","detail":"5/hour"}`.

**Persistence** — two new `[A]` tables (52nd and 53rd table overall; see §21.14 for the migration strategy). Both follow the same REVOKE + trigger pattern as the 11 originals (§17 risk #4 / `config.yaml rules.tasks`):

```sql
-- Migration 0003_add_pairing_tokens_and_revoked_sync_jwts.py (PR9)
-- 51st [A] table
CREATE TABLE prod.pairing_tokens (
    uuid uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    uuid_sucursal uuid NOT NULL REFERENCES prod.sucursal(uuid),
    pairing_token_hash text NOT NULL,  -- sha256 of plaintext token; plaintext NEVER persisted
    expires_at timestamptz NOT NULL,
    used boolean NOT NULL DEFAULT false,
    used_at timestamptz,
    used_by_branch_info jsonb,
    revoked_at timestamptz,
    revoked_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    sync_status text NOT NULL DEFAULT 'pendiente',
    sync_timestamp timestamptz,
    sync_attempts int NOT NULL DEFAULT 0,
    UNIQUE (uuid_sucursal, pairing_token_hash)
);
CREATE INDEX ix_pairing_tokens_pending ON prod.pairing_tokens (uuid_sucursal)
    WHERE used = false AND revoked_at IS NULL AND expires_at > now();
REVOKE UPDATE, DELETE ON prod.pairing_tokens FROM rol_app;
CREATE OR REPLACE FUNCTION prod.fn_pairing_tokens_inmutable() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'PAIRING_TOKENS_INMUTABLE'; END; $$;
CREATE TRIGGER pairing_tokens_no_update_delete BEFORE UPDATE OR DELETE ON prod.pairing_tokens
    FOR EACH ROW EXECUTE FUNCTION prod.fn_pairing_tokens_inmutable();

-- 52nd [A] table
CREATE TABLE prod.revoked_sync_jwts (
    uuid uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    uuid_sucursal uuid NOT NULL,
    jwt_kid text NOT NULL,  -- matches JWT kid claim (e.g. 'sync-agent-<hostname>')
    jwt_uuid text NOT NULL,  -- jti claim (RFC 7519)
    revoked_at timestamptz NOT NULL DEFAULT now(),
    revoked_by uuid NOT NULL,
    motivo text,
    expires_at timestamptz NOT NULL,  -- when the original JWT would have expired anyway
    created_at timestamptz NOT NULL DEFAULT now(),
    sync_status text NOT NULL DEFAULT 'pendiente',
    sync_timestamp timestamptz,
    sync_attempts int NOT NULL DEFAULT 0,
    UNIQUE (jwt_kid, jwt_uuid)
);
CREATE INDEX ix_revoked_sync_jwts_active ON prod.revoked_sync_jwts (jwt_kid, jwt_uuid)
    WHERE expires_at > now();
REVOKE UPDATE, DELETE ON prod.revoked_sync_jwts FROM rol_app;
CREATE OR REPLACE FUNCTION prod.fn_revoked_sync_jwts_inmutable() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'REVOKED_SYNC_JWTS_INMUTABLE'; END; $$;
CREATE TRIGGER revoked_sync_jwts_no_update_delete BEFORE UPDATE OR DELETE ON prod.revoked_sync_jwts
    FOR EACH ROW EXECUTE FUNCTION prod.fn_revoked_sync_jwts_inmutable();
```

**Token shape**: 32 random bytes → base64url → `pairing_tokens.pairing_token` (looks like `dGhpc19pc19hX3Rlc3RfdG9rZW5fcGFpcmluZ19hYWFhYWFhYQ`). Stored only as `sha256(plaintext)`; even DB compromise doesn't leak active plaintexts.

**Consume atomicity** (`/api/v1/sync/pair` handler): uses `SELECT ... FOR UPDATE SKIP LOCKED` on the candidate row, then in the same TX issues the long-lived JWT and writes the `used=true` update. On race (two boots with the same token): second `SELECT` returns no rows → 410 Gone.

#### Branch side (one-shot, then never again)

```bash
# 1. Operator runs (after generating the token in web_admin):
docker run --rm \
  -e PARKOS_DEPLOY=branch \
  -e PARKOS_SUCURSAL_UUID=11111111-2222-4333-8444-555555555555 \
  -e PARKOS_PAIRING_TOKEN=dGhpc19pc19hX3Rlc3RfdG9rZW5fcGFpcmluZ19hYWFhYWFhYQ \
  -e PARKOS_DB_URL=postgresql+asyncpg://parkos@db:5432/parkos \
  -e PARKOS_CLOUD_API_URL=https://api.parkos.example.com \
  -e PARKOS_JWT_KEY_PATH=/etc/parkos/jwt/branch \
  -v parkos_jwt:/etc/parkos \
  parkos:branch \
  python -m parkos_core.cli pair
```

The `parkos_core.cli` entrypoint detects `PARKOS_PAIRING_TOKEN`, calls `POST {PARKOS_CLOUD_API_URL}/api/v1/sync/pair`, persists the returned JWT to `PARKOS_SYNC_JWT_PATH` (mode `0600`, owner `app`), deletes the env var from the in-process os.environ (does NOT touch the orchestrator's env), and exits 0.

**Subsequent boots** (no `PARKOS_PAIRING_TOKEN`): branch image boots normally; `api_sucursal` reads `PARKOS_SYNC_JWT_PATH` if it needs to act as sync-receiver (cloud pushing rows down via `/sync/pull`); `job_sync_sucursal` reads it to authenticate to `api_admin`'s `/sync/push` etc.

#### JWT specifics (long-lived sync-agent-)

| Field | Value | Why |
|---|---|---|
| `kid` | `sync-agent-<branch-hostname>` (default) — overridable via `PARKOS_JWT_KEY_PATH/kid` file | diagnostic; the cloud JWKS exposes one key per `kid` |
| `iss` | `sync-agent-<deployment-id>` (e.g. `sync-agent-prod-001`) | namespacing under AGENTS.md `JWT three issuers` |
| `aud` | `parkos-cloud-api` | REQ-X8 |
| `sub` | `<uuid_sucursal>` | REQ-X8 |
| `scope` | `sync_agent_branch` | single scope; cloud sync-agent uses `sync_agent_cloud` |
| `pairing_token_uuid` | the original `pairing_tokens.uuid` | audit traceability |
| `issued_at_branch` | `<iso8601>` | clock-skew detection; cloud validates `issued_at_branch - now() < 60s` |
| `jti` | `<uuid>` | revocation target via `revoked_sync_jwts` |
| `expires_at` | `NOW() + 30 days` | long-lived; rotation handled by `POST /sync/rotate-jwt` (see §21.7) |
| `branch_info` | `{hostname, os, version, ip}` | audit log; the cloud writes this verbatim to `pairing_tokens.used_by_branch_info` |

**Grace rotation** (`JWT_OVERLAP_HOURS=24`): cloud JWKS exposes both the previous key (just-rotated) and the current one for `24h`. After that window, the old key is removed; tokens signed with it become invalid.

**Revocation**:
- `DELETE /api/v1/admin/pairing-tokens/{uuid}` (admin) marks the token `revoked_at`, `revoked_by` → subsequent consume attempt → 410 Gone. The previously-issued JWT (if already paired) is NOT auto-revoked (it has its own `jti`); the operator must call `POST /admin/sucursales/{uuid_sucursal}/revoke-sync` for that.
- `POST /api/v1/admin/sucursales/{uuid_sucursal}/revoke-sync` → inserts into `revoked_sync_jwts`; subsequent `api_admin` calls with a JWT whose `(kid, jti)` is in `revoked_sync_jwts` → 401 `{"error":"sync_jwt_revoked"}`. Re-pairing requires generating a NEW token (cannot re-use the previous one's plaintext — the old plaintext was never persisted).

**Tests** (`backend/tests/integration/test_pairing_flow.py`, `backend/tests/unit/test_pairing_token_rate_limit.py`):

| Test | Asserts |
|---|---|
| `test_pair_happy_path` | Boot with valid `PARKOS_PAIRING_TOKEN` → `POST /sync/pair` returns long-lived JWT → JWT file written with mode `0600` → `POST /sync/push` succeeds with the JWT |
| `test_pair_token_reuse_rejected` | First `POST /sync/pair` consumes the token (returns 200 + JWT, writes `used=true`). Second `POST /sync/pair` with the SAME plaintext → 410 Gone |
| `test_pair_token_expired_rejected` | Insert `pairing_tokens` row with `expires_at = NOW() - INTERVAL '1 hour'`. `POST /sync/pair` → 410 Gone |
| `test_pair_token_revoked_rejected` | `DELETE /admin/pairing-tokens/{uuid}` first. `POST /sync/pair` → 410 Gone |
| `test_pair_revoked_jwt_rejects_subsequent_calls` | Pair successfully, then `POST /admin/sucursales/{uuid_sucursal}/revoke-sync`. Next `POST /sync/push` with the previously-issued JWT → 401 `{"error":"sync_jwt_revoked"}` |
| `test_pair_token_rate_limit` | Mint 5 tokens in 60 min → 200 OK. 6th → 429 |
| `test_pair_wrong_sucursal_rejected` | Token is for `uuid_sucursal=A`, branch boots with `PARKOS_SUCURSAL_UUID=B` → 403 `{"error":"pairing_token_sucursal_mismatch"}` |
| `test_pair_env_validator_fails_fast` | Boot with malformed `PARKOS_SUCURSAL_UUID` → exit code `2` |
| `test_pair_persisted_jwt_path_0600` | After successful pair, `os.stat(PARKOS_SYNC_JWT_PATH).st_mode & 0o777 == 0o600` |

### 21.4 Multi-sucursal admin views

The admin's authorization model carries `sucursales_permitidas: [uuid_A, uuid_B, ...]` (REQ-X2). Three endpoints + UI integration expose this without forcing the admin to re-login between branches.

| Endpoint | Method | Auth | Returns |
|---|---|---|---|
| `/api/v1/sucursales` | GET | `admin-` | `{items: [{uuid, nombre, ciudad, uuid_tipo_sucursal, sync_status: {last_sync_at, last_error, last_heartbeat_at}, open_alerts_count, last_pairing_at}], next_cursor}` — filtered to `uuid IN (claims.sucursales_permitidas)` |
| `/api/v1/admin/sucursales/{uuid}/dashboard` | GET | `admin-`, `X-Sucursal-Context: <uuid>` ∈ `permitidas` | `{fecha, ingresos_count, ingresos_monto_total, facturas_emitidas_count, facturas_electronicas_count, open_alertas_count, sync_health: {last_sync_at, lag_seconds, queue_depth}}` |
| `/api/v1/admin/me` | GET | `admin-` | `{actor_uuid, email, rol, sucursales_permitidas: [uuid, ...], permissions: [...]}` — full list, used to populate the branch-selector |

**Cursor pagination** (REQ-OP-01): the same opaque base64 cursor format; `limit` 1..200.

**Tenant scope**: the `sucursales_permitidas` filter is enforced at the ORM layer (`parkos_core/db/tenancy.py::apply_admin_scope` extends the existing `do_orm_execute` event listener from §9 with a `WHERE uuid = ANY(:permitidas)` predicate when the issuer is `admin-`). Defense in depth — even if a route handler forgot to filter, the listener catches it.

**UI integration** (`apps/web_admin/`):
- Branch-selector component in topbar (`<BranchSelector />` in `ui-kit`).
- Persists last selection in `localStorage` key `parkos.lastSelectedSucursal`.
- On switch: dispatches a SWR `mutate()` invalidating the dashboard cache + sets `X-Sucursal-Context` header on subsequent fetches via a global `fetch` wrapper.
- No re-login: the JWT is valid for the full `sucursales_permitidas` set; only the context header changes.

### 21.5 Auto-discovery

**`job_sync_sucursal` → cloud**: uses `PARKOS_CLOUD_API_URL` (env var). No DNS, no service registry. The image's env file is provisioned by the operator at first boot (after `parkos-cli pair` returns, the cloud admin's `web_admin` writes the `PARKOS_CLOUD_API_URL` value to the branch's persistent env file).

**`job_sync_cloud` → active branches**: iterates `prod.sucursal WHERE uuid IN (active branches)`. "Active" = at least one `sync_log` row in the last 7 days OR a `pairing_tokens.used=true` row younger than 30 days. Each row carries:
- `endpoint_url` (set during pairing in `pairing_tokens.used_by_branch_info->>'endpoint_url` — the URL the branch will accept inbound `/sync/pull` from, useful for cloud-pushed rows)
- `last_paired_at` (audit only)

The cloud job maintains an in-memory cache of active branches refreshed every `PARKOS_SYNC_VERIFY_INTERVAL_S / 12` (default 5 min when `PARKOS_SYNC_VERIFY_INTERVAL_S=3600`).

**Optional external registry** (`PARKOS_REGISTRY_URL`): if the operator wants Consul/etcd/Zookeeper instead of the DB, they can set this. The default is the DB — already replicated, no new infra, single source of truth. **Default chosen: DB**. Adding the optional env var is a one-line branch in `job_sync_cloud::discover_active_branches()`.

**Endpoint reachability**: cloud periodically (every `PARKOS_SYNC_VERIFY_INTERVAL_S`) does a `HEAD {branch_endpoint_url}/api/v1/health` against each cached branch. Three consecutive failures → opens `alerta tipo_alerta='branch_offline'` chain (REQ-21 workflow). Persistent failure (24h+) → removes the branch from the cache until a `sync_log` row arrives.

### 21.6 Installability matrix

Goal: each component installable independently, not glued to `docker-compose`. Composes for each canonical scenario are listed in `infra/deploy/README.md`.

**Compose files** (PR8 ships these; bootstrap's `docker-compose.{cloud,branch}.yml` remain as the single-host convenience wrappers):

| File | Services | Use case |
|---|---|---|
| `infra/deploy/docker-compose.cloud.yml` | `api_admin` + `job_sync_cloud` + `web_admin` (PWA) | Cloud VM / container host (single host) |
| `infra/deploy/docker-compose.branch.yml` | `api_sucursal` + `job_sync_sucursal` + `web_sucursal` (PWA) + `postgresql-branch` | Branch PC (single host, all-in-one — default SMB scenario) |
| `infra/deploy/docker-compose.db-cloud.yml` | `postgresql-cloud` only | Cloud-DB-as-a-service scenario (DB lives on dedicated host) |
| `infra/deploy/docker-compose.api-branch.yml` | `api_sucursal` + `web_sucursal` (PWA) — NO DB | Multi-site scenario where DB is remote |
| `infra/deploy/docker-compose.job-branch.yml` | `job_sync_sucursal` only — NO DB, NO API | Same multi-site scenario; runs on a separate host for HA |

**Three canonical scenarios** (documented in `infra/deploy/README.md`):

1. **"All-in-one per branch"** (typical SMB, single-PC parking lot): `docker compose -f infra/deploy/docker-compose.branch.yml up -d` on each branch PC. One compose file, one host, one operator. DB lives on the same host.

2. **"DB on a server, app on each PC"** (multi-site, centralized DB): `docker compose -f infra/deploy/docker-compose.db-cloud.yml up -d` on the central DB server + `docker compose -f infra/deploy/docker-compose.api-branch.yml -f infra/deploy/docker-compose.job-branch.yml up -d` on each app PC, both `PARKOS_DB_URL` pointing to the central DB. The `api-branch` and `job-branch` files compose together via `docker compose -f X -f Y` (Docker Compose v2 multi-file override; matches `~/.config/opencode/skills/docker/SKILL.md` step 12).

3. **"100 branches behind VPN"** (enterprise): central cloud hosts `infra/deploy/docker-compose.cloud.yml`; each branch runs `infra/deploy/docker-compose.branch.yml` (or scenario 2 with split `api-branch.yml` + `job-branch.yml` for HA). Cloud is reachable from each branch over the VPN/tailscale/zero-trust tunnel.

**Default profiles**: `cloud.yml` and `branch.yml` use the default Compose profile (no `profiles:` key); the API-only and job-only files use `profiles: ["api-branch"]` and `profiles: ["job-branch"]` respectively, allowing `docker compose --profile api-branch up -d` syntax (Compose v2, `~/.config/opencode/skills/docker/SKILL.md` step 12).

**Why this layout** (vs a single big `docker-compose.yml`): each component has independent release cadence. Cloud `api_admin` might ship weekly; branch `job_sync_sucursal` might ship quarterly (security patches only). A single compose file forces every operator to redeploy everything at once.

**HEALTHCHECK + `depends_on`** (per `~/.config/opencode/skills/docker/SKILL.md` step 11):
- `postgresql-*` services: `pg_isready -U <user>` with `start_period: 30s`.
- `api_*`: `curl -fsS http://localhost:8000/api/v1/health` with `start_period: 30s`, `interval: 30s`.
- `job_sync_*`: `python -c "import httpx; httpx.get('http://localhost:9999/healthz').raise_for_status()"` (workers expose a tiny `httpx`-served `/healthz` for orchestration — port 9999, NOT exposed externally).
- `web_admin`, `web_sucursal`: served by a `caddy:2-alpine` reverse-proxy in the same compose file, with `wget -qO- http://localhost:8080/ >/dev/null` healthcheck.

### 21.7 job_sync_sucursal

A long-running Python process on each branch. Single binary `python -m parkos_core.jobs.sync_sucursal`. Responsibilities (in poll order, one cycle ≈ `PARKOS_SYNC_POLL_INTERVAL_S`):

```
+---------------------------------------+
| job_sync_sucursal::run() main loop    |
+---------------------------------------+
  |
  +-- 1. poll_sync_queue()
  |     SELECT * FROM prod.sync_queue
  |     WHERE estado = 'pendiente' AND next_retry_at <= NOW()
  |     AND uuid_sucursal = :ctx
  |     ORDER BY prioridad DESC, created_at ASC
  |     LIMIT :PARKOS_SYNC_BATCH_SIZE
  |     -- via repo/append_only.mark_dispatched (4-col whitelist)
  |
  +-- 2. push_batch(rows)
  |     POST {PARKOS_CLOUD_API_URL}/api/v1/sync/push
  |     Body: {rows: [{tabla, operacion, uuid, datos, seq}, ...], last_seq}
  |     Header: Authorization: Bearer <sync_jwt>
  |
  +-- 3. handle_response(rows, response)
  |     2xx with applied_ids: mark_dispatched(rows)
  |     207 partial: mark_dispatched(success_subset), mark_failed(failure_subset, ...)
  |     4xx: mark_failed(rows, motivo=response.detail)
  |         schedule_retry(rows, backoff=4xx)  # exponential 1m, 5m, 30m, 2h, 12h, 24h
  |     5xx: mark_failed(rows, motivo=response.detail)
  |         schedule_retry(rows, backoff=5xx)  # shorter: 30s, 1m, 5m
  |     401 sync_jwt_expired: rotate_jwt()  # see below
  |     401 sync_jwt_revoked: emit alerta + HALT (halt_until_re_pair)
  |
  +-- 4. pull_cloud_changes()
  |     POST {PARKOS_CLOUD_API_URL}/api/v1/sync/pull
  |     Body: {since_seq: last_pull_seq}
  |     Response: {rows: [...], new_since_seq}
  |     For each row: idem-potent UPSERT by (tabla, uuid)
  |     -- uses repo/{versioned, append_only, event, workflow, session_cycle}
  |     -- based on row.tabla -> corresponding repo helper
  |
  +-- 5. heartbeat()
  |     POST {PARKOS_CLOUD_API_URL}/api/v1/sync/heartbeat
  |     Body: {last_seq, last_pull_seq, queue_depth, last_error}
  |     -- writes to local prod.sync_log (one row per cycle)
  |
  +-- 6. sleep(PARKOS_SYNC_POLL_INTERVAL_S - elapsed)
        loop back to 1
```

**On `401 sync_jwt_expired`**: call `POST {CLOUD}/api/v1/sync/rotate-jwt` with `{current_jwt_uuid}`. Cloud returns `{new_jwt, new_jwt_expires_at, grace_until}`. Branch writes the new JWT to `PARKOS_SYNC_JWT_PATH`, overwriting the old. The old JWT remains valid for `grace_until` (default `now() + JWT_OVERLAP_HOURS` = 24h). Rotation is automatic; no operator action needed.

**On `401 sync_jwt_revoked`**: branch emits `alerta tipo_alerta='branch_offline_reauth_required'` (locally) and calls `POST {CLOUD}/api/v1/admin/sucursales/{uuid_sucursal}/alertas` (sync-agent scope allowed) to also open the alerta cloud-side. Then the worker calls `sys.exit(1)` — orchestrator (docker/systemd) restarts; restart loop will keep failing until the operator re-pairs (deliberate; surfaces the issue rather than spinning).

**Halt-until-re-pair** is the correct failure mode per AGENTS.md `Audit-First` principle. Silently retrying a revoked JWT would burn CPU indefinitely.

**Configuration env** (validated by §21.2 validator): `PARKOS_SYNC_POLL_INTERVAL_S=10`, `PARKOS_SYNC_BATCH_SIZE=100`, `PARKOS_SYNC_HEARTBEAT_S=60`, `PARKOS_CLOUD_API_URL`, `PARKOS_SYNC_JWT_PATH`, `PARKOS_SUCURSAL_UUID`, `PARKOS_DEPLOY=branch`.

**Exit codes**: `0 = clean shutdown (SIGTERM)`, `1 = unhandled error (restart)`, `2 = misconfig (operator must fix; do not restart-loop)`. Matches `~/.config/opencode/skills/docker/SKILL.md` step 7 (graceful shutdown via SIGTERM).

### 21.8 job_sync_cloud

A long-running Python process on cloud. Single binary `python -m parkos_core.jobs.sync_cloud`. Responsibilities:

```
+---------------------------------------+
| job_sync_cloud::run() main loop       |
+---------------------------------------+
  |
  +-- 1. accept_push_via_api()
  |     (NOT in-process; this is what api_admin /sync/push does — see §21.9)
  |     Here the worker just maintains the side-effects:
  |
  +-- 2. apply_pushed_row(row)
  |     -- verify sync-agent- JWT (api_admin middleware)
  |     -- check uuid_sucursal matches JWT.sub (defense in depth)
  |     -- check row.seq > last_seq for uuid_sucursal (monotonicity)
  |     -- for [A] tables (not sync_queue): repo/append_only.append_event()
  |     -- for [V] tables: repo/versioned.close_and_insert()
  |     -- for [L-E]/[L-W]/[L-S]: respective helper
  |     -- for log_transaccional + revocacion_factura: extends hash chain
  |        via repo/hash_chain.append(); on chain violation:
    //     INSERT into prod.sync_conflict with both versions
    //     INSERT alerta tipo_alerta='sync_failure' chain root
    //     return 500 to the branch worker (it retries in order)
  |
  +-- 3. emit_sync_back_events()
  |     -- for each newly-accepted cloud-originated row (DIAN responses, admin updates,
  |        catalog refreshes) where the branch needs to know:
  |     -- POST {branch_endpoint_url}/api/v1/sync/events with the event payload
  |        (the branch registers its endpoint_url during pairing; see §21.5)
  |     -- branch's job_sync_sucursal pull-events subscribes
  |
  +-- 4. poll_pull_requests()  (or accept via /sync/pull endpoint, same outcome)
  |     -- returns cloud-originated rows for branch since last_pull_seq
  |
  +-- 5. hash_chain_verifier_loop()
  |     Every PARKOS_SYNC_VERIFY_INTERVAL_S (default 3600s):
  |     for each uuid_sucursal in active branches:
  |       walk log_transaccional in (timestamp_evento, uuid) order
  |       assert hash_anterior = prev.hash_actual (or genesis)
  |       assert hash_actual = sha256(canonical_json(payload) + hash_anterior_bytes)
  |       on mismatch: INSERT alerta tipo_alerta='hash_chain_anomaly'
  |                     INSERT sync_conflict with both versions
  |
  +-- 6. sleep(elapsed_to_PARKOS_SYNC_VERIFY_INTERVAL_S)
```

**Why cloud-side verifier is a separate concern from `apply_pushed_row`**: `apply_pushed_row` catches in-line breaks (branch's out-of-order push), but if a sync_queue row is lost in transit (network partition, missed poll) the gap goes unnoticed. The verifier is the periodic integrity check that catches missed or reordered pushes regardless of cause.

**Configuration env**: `PARKOS_DEPLOY=cloud`, `PARKOS_DB_URL`, `PARKOS_JWT_KEY_PATH`, `PARKOS_SYNC_VERIFY_INTERVAL_S=3600`.

**Exit codes**: same contract as §21.7 (`0 / 1 / 2`).

### 21.9 Sync transport protocol

All endpoints under `/api/v1/sync/*`. JWT: `sync-agent-` only; admin/operador → 401 (REQ-X8). Mounted on BOTH `api_admin` (cloud-side receiver) and `api_sucursal` (branch-side receiver — see `operational.md` REQ-OP-03).

**Idempotency**: each request carries `X-Request-Id: <uuid>` (RFC 4122); replays within 5 minutes return cached response (in-memory LRU cache `parkos_core/sync/transport.py::IdempotencyCache(maxsize=10_000, ttl=300)`). Cache is process-local; on restart the branch retries (already idempotent at the row level via `(tabla, uuid)` keys).

| Endpoint | Method | Auth | Body | Response | Notes |
|---|---|---|---|---|---|
| `/sync/pair` | POST | NONE (public; protected by single-use token + 24h TTL) | `{pairing_token, uuid_sucursal, branch_info: {hostname, os, version, endpoint_url}}` | `{sync_agent_jwt, sync_agent_jwt_expires_at, cloud_poll_interval_S, sync_endpoints: {push, pull, events}}` | atomic consume (§21.3); on race returns 410 |
| `/sync/push` | POST | `sync-agent-` (branch's long-lived JWT) | `{rows: [{tabla, operacion, uuid, datos, seq}, ...], last_seq}` | `{applied_ids, last_seq, errors}`; HTTP 207 partial-success if any row failed; HTTP 500 if hash chain violation (branch retries in order) | rate limit: `PARKOS_SYNC_BATCH_SIZE` rows/req (server side: cap at 500); body cap 8MB |
| `/sync/pull` | POST | `sync-agent-` | `{since_seq}` | `{rows: [...], new_since_seq}` | returns cloud-originated rows in (seq ASC) order; limit 500/req; if more, response includes `has_more: true` and branch retries with new `since_seq` |
| `/sync/heartbeat` | POST | `sync-agent-` | `{last_seq, last_pull_seq, queue_depth, last_error}` | `{server_time, next_heartbeat_in_s}` | cloud records `sync_log` row (one per branch per cycle) |
| `/sync/rotate-jwt` | POST | `sync-agent-` (current JWT; even if expired, with a one-shot grace window) | `{current_jwt_uuid}` | `{new_jwt, new_jwt_expires_at, grace_until}` | grace_until = `now() + JWT_OVERLAP_HOURS` (default 24h) |
| `/sync/events` | POST | `sync-agent-` (cloud → branch push) | `{event_type: "factura_syncback"\|"alerta_created"\|"catalog_updated", payload: {...}, seq}` | `204 No Content` | branch registers its URL during pairing (§21.3); cloud retries 3x with exponential backoff on 5xx |

**Why a sync-specific `IdempotencyCache` and not the global `idempotency_keys` table (§8 / REQ-OP-04)**: the idempotency_keys table is for HTTP POST writes that the client wants replayed (POST is not idempotent in HTTP semantics). Sync requests are server-server; replays within 5 minutes are network artifacts, not user-facing "did my button click work?" questions. A process-local LRU is correct here (and faster — no DB roundtrip per request). Defense in depth: every applied row also has the `(tabla, uuid)` idempotency at the data layer, so even if the cache lies, no double-apply happens.

**Rate limits** (`parkos_core/sync/transport.py::RateLimit`): per-`uuid_sucursal` token bucket; default `60 req/min` for `push`, `120 req/min` for `pull`, `10 req/min` for `heartbeat`, `1 req/min` for `rotate-jwt`. Token bucket per (issuer, subject) pair. 429 response includes `Retry-After: <seconds>`.

### 21.10 Conflict resolution

Per AGENTS.md `Sync` section: defaults per enforcement class.

| Class | Policy | Implementation |
|---|---|---|
| `[V]` | `manual` | cloud wins on conflict (last-write-wins by cloud clock); branch's losing row held in `sync_conflict` until operator resolves via `web_admin` UI |
| `[L-E]` | `append` | both branch and cloud insert independently; events are immutable; no conflict possible |
| `[L-W]` | `append` | workflows originate on branch and propagate; no cloud origination |
| `[A]` | `append` | append-only; no conflict possible (immutable) |
| `[L-S]` | `manual` | session close state can race (two devices close simultaneously); cloud wins after a `JWT_OVERLAP_HOURS` grace window during which the branch's close is held in `sync_conflict` |

**Implementation** (`parkos_core/sync/conflict_resolver.py::apply_pushed_row()`):
- Each sync push row carries `datos->>'client_timestamp'` and `datos->>'actor_uuid'` (server-stamped, NOT user-supplied).
- Cloud applies in `(last_pull_seq ASC, client_timestamp ASC, uuid ASC)` order — strictly monotonic per `uuid_sucursal`.
- On duplicate `(tabla, uuid)` with different content (cloud already has a newer row): INSERT into `prod.sync_conflict` with both `datos_local` and `datos_cloud` snapshots; INSERT `alerta tipo_alerta='sync_conflict'` chain root; surface to operator via `web_admin`.

**Why cloud-wins for `[V]`**: AGENTS.md `Sync` §"`[V]` = manual" + bi-temporal canon. The cloud's `vigente_desde` is later than the branch's by definition (cloud applied in receive order, which is later than branch-originated). Allowing branch-wins would violate bi-temporal "the most recent version IS current". The branch row's content survives in `sync_conflict` for operator review — NOT silently overwritten.

**Why `L-S` has a grace window (not immediate cloud-wins)**: simultaneous close from two operators on the same branch is a real failure mode (operator opens a kiosk, closes a desktop, both hit the close endpoint at the same time). Without grace, one row's `estado='cerrada'` + the other's `vigente_hasta` would clobber. Grace = `JWT_OVERLAP_HOURS` (24h) is the project-canon rotation window; reusing it here keeps the constants consistent.

**Test** (`backend/tests/integration/test_sync_conflict_resolution.py`):
- `test_v_conflict_writes_sync_conflict_row` — branch inserts `[V]` row at T=1; cloud already has a newer row at T=2 (different content); push returns 207 with `errors=[{uuid, conflict: true}]`; `prod.sync_conflict` has +1 row; `alerta tipo_alerta='sync_conflict'` chain root exists.
- `test_ls_grace_window_` — two simultaneous `close_session_with_log` calls; one applied, one held in `sync_conflict`; after `JWT_OVERLAP_HOURS` simulation, second one applied with annotation.
- `test_append_no_conflict_possible` — branch inserts `[A]` row, cloud inserts different `[A]` row at same `uuid` (impossible because UUIDs are v4 random, but test the no-conflict assertion anyway).

### 21.11 DIAN HTTP dispatcher

Cloud-only outbound to the DIAN electronic-invoicing provider (Factus or whichever). Lives in `parkos_core/dian/cloud/dispatcher.py` (replaces the bootstrap stub). Three responsibilities:

#### 1. Send `factura_electronica` to DIAN

```
POST {PARKOS_DIAN_PROVIDER_URL}/api/ubl2.1
  Body: <UBL 2.1 XML serialized from the factura_electronica row>
  Header: Authorization: Bearer <PARKOS_DIAN_PROVIDER_TOKEN_PATH contents>

Poll {PARKOS_DIAN_PROVIDER_URL}/api/ubl2.1/{trackId}
  Every 2s, up to PARKOS_DIAN_TIMEOUT_S (default 30s).

On aceptado:
  INSERT envio_dian row:
    uuid_envio, uuid_factura_electronica, estado='aceptado',
    cufe=<returned>, reportado_dian=true,
    respuesta_dian=jsonb(response),
    fecha_retencion_hasta=NOW()+INTERVAL '5 years'
  Trigger after-INSERT on envio_dian:
    INSERT into prod.sync_queue with operacion='insert', tabla='envio_dian', uuid_registro=<new.uuid>
    (the DB trigger handles this; see §12)
  The branch receives the SyncBackEvent → updates local `factura_electronica` row →
    enables `reimpresion_ticket` for the operator (REQ-X8 / `operational.md` REQ-OP-04).

On rechazado:
  INSERT envio_dian row with estado='rechazado', motivo_rechazo=<body>
  Both insert into `revocacion_factura` chain if applicable
  INSERT alerta tipo_alerta='dian_rechazada' chain root (cloud-admin surfaces to operator)

On timeout (>PARKOS_DIAN_TIMEOUT_S):
  schedule_retry with backoff=5xx (1m, 5m, 15m) up to PARKOS_DIAN_RETRY_MAX (default 3)
  On final timeout: INSERT envio_dian row with estado='timeout', motivo_rechazo='timeout'
  INSERT alerta tipo_alerta='dian_timeout'
```

#### 2. Send `revocacion_factura` to DIAN

Similar flow for voided invoices:

```
POST {PARKOS_DIAN_PROVIDER_URL}/api/revocacion
  Body: <revocacion XML>  (different shape than ubl2.1)
  Same poll + retry pattern.

On aceptado:
  Extend prod.revocacion_factura hash chain via repo/hash_chain.append()
  (per §11; revocacion_factura carries hash_anterior/hash_actual per uuid_sucursal)
  Emit SyncBackEvent to branch.
```

#### 3. Hash chain extension

Every successful DIAN write extends `prod.log_transaccional` chain for the BRANCH's `uuid_sucursal` (not the cloud's) per AGENTS.md `Hash chain` section — because the chain IS the per-branch evidence of what the branch did, and the cloud is just the centralizing replicator. Cloud preserves branch chain verbatim, only extends with cloud-originated rows.

#### Configuration env (cloud-only)

| Var | Required | Default |
|---|---|---|
| `PARKOS_DIAN_PROVIDER_URL` | yes | — |
| `PARKOS_DIAN_PROVIDER_TOKEN_PATH` | yes | `/etc/parkos/dian.token` (mode `0600`) |
| `PARKOS_DIAN_TIMEOUT_S` | no | `30` |
| `PARKOS_DIAN_RETRY_MAX` | no | `3` |

#### Boundary enforcement (3 layers, defense in depth)

1. **Image-level**: `backend/.dockerignore` (branch) excludes `**/dian/cloud/**`. Branch Dockerfile cannot COPY the dispatcher. The cloud Dockerfile COPYs `/build/dian_cloud/` to runtime (matches `~/.config/opencode/skills/docker/SKILL.md` step 2 pattern A). Verified by RED test `test_dian_boundary_branch.py` already in PR6 (§10).

2. **Module-level**: `parkos_core/dian/cloud/dispatcher.py` checks `os.environ["PARKOS_DEPLOY"] == "cloud"` at module import time and raises `ImportError("dian_cloud_unavailable_on_branch")` otherwise. Combined with the `.dockerignore`, a branch image that somehow has the file would still fail to import it.

3. **OpenAPI-level**: `test_openapi_branch_excludes_cloud.py` (PR6) asserts zero cloud-only paths in `api_sucursal/openapi.json`. Tag-based filter `tags=["cloud-only"]` (REQ-OP-14 / §16) is belt-and-suspenders.

#### Test stub (`tests/dian/test_dispatcher.py`)

Uses `httpx.MockTransport` to simulate DIAN responses. No real provider in CI:

```python
# tests/dian/test_dispatcher.py (sketch)
async def test_dispatcher_accepts_and_writes_envio_dian(httpx_mock, db_session):
    httpx_mock.add_response(
        method="POST", url=re.compile(r".*/api/ubl2\.1$"),
        json={"trackId": "TRK-123"})
    httpx_mock.add_response(
        method="GET", url=re.compile(r".*/api/ubl2\.1/TRK-123$"),
        json={"estado": "aceptado", "cufe": "..."})

    await dispatch_factura_electronica(db_session, uuid_factura=..., actor_uuid=...)

    envio = await db_session.scalar(select(EnvioDian).where(EnvioDian.uuid_factura_electronica == uuid_factura))
    assert envio.estado == "aceptado"
    assert envio.cufe == "..."
    assert envio.reportado_dian is True
    # AND the dispatcher's hash-chain extension wrote a log_transaccional row
    # with the BRANCH's uuid_sucursal, not the cloud's
```

Other tests: `test_dispatcher_rechazado_writes_envio_dian_and_alerta`, `test_dispatcher_timeout_retries_then_alerts`, `test_dispatcher_import_guard_raises_on_branch`, `test_dispatcher_hash_chain_extends_for_branch_not_cloud`.

### 21.12 Risks added by this delta

The risks §17 enumerated (`tasks.md` §Risks surfaced) are the baseline. §21 adds the following:

| # | Sev | Risk | Mitigation |
|---|---|---|---|
| 19 | **NEW — HIGH** | Pairing-token theft in transit | `PARKOS_PAIRING_TOKEN` is single-use + 24h TTL + rate-limited (5/hour/admin); token plaintext returned only ONCE in `POST /admin/pairing-tokens` response; thereafter stored as `sha256(plaintext)` only; every pair attempt logged with IP+UA in `log_transaccional`; orchestrator-side: provision via short-lived secret manager (Vault/AWS SM) with TTL matching the token TTL |
| 20 | **NEW — HIGH** | Stale branch registry — cloud keeps trying to push to a dead branch | `endpoint_url` reachability probe every `PARKOS_SYNC_VERIFY_INTERVAL_S` (§21.5); 3 consecutive failures → open `alerta tipo_alerta='branch_offline'`; 24h+ failure → remove from cache until a `sync_log` row arrives; operator can also manually `POST /admin/sucursales/{uuid}/revoke-sync` |
| 21 | **NEW — MED** | `job_sync_sucursal` silent death (process running but hung) | Heartbeat every `PARKOS_SYNC_HEARTBEAT_S` (default 60s) with `{last_seq, last_pull_seq, queue_depth, last_error}`; cloud tracks last heartbeat per branch; 3 missed heartbeats (3 min) → open `alerta tipo_alerta='sync_worker_dead'` |
| 22 | **NEW — MED** | Out-of-order sync arrivals — branch pushes row N+1 before row N (network reorder) | Per-row monotonic `seq` in `datos` JSON; cloud verifies `seq == last_seq` before apply (§21.8); on mismatch, holds the row in `sync_queue` (cloud-side `parkos_core.cloud_sync_queue`) until the gap is filled; cloud hash chain verifier catches any that slip through (§21.8 step 5) |
| 23 | **NEW — MED** | Per-branch misconfiguration of `PARKOS_SUCURSAL_UUID` (operator typo, wrong UUID pasted) | Boot-time fail-fast validator (§21.2) raises `MissingEnvError` exit `2`; `parkos_core.cli doctor` subcommand prints `{env_status, db_connectivity, jwt_key_path_exists, sync_jwt_path_readable, cloud_api_url_reachable}` for one-shot operator diagnostics |
| 24 | **NEW — MED** | Two parallel `job_sync_cloud` instances race on hash chain | Single-instance design enforced: only ONE `job_sync_cloud` container per cloud deployment; compose file has `deploy.replicas: 1` and a `restart: unless-stopped` policy; if HA needed (future), use Postgres advisory locks per `uuid_sucursal` to serialize (deferred to v2) |
| 25 | **NEW — LOW** | DIAN provider rate-limit (Factus allows N req/min) | Dispatcher has a token bucket per provider; on 429, schedule_retry with backoff=5xx; `PARKOS_DIAN_RETRY_MAX=3` defaults keep us within most provider limits |
| 26 | **NEW — LOW** | 100+ branch scale — `/sync/pull` response size | Default page size 500/req (`new_since_seq` + `has_more` retry loop); cloud-side compressed response (`gzip`); deferred to v2 if even paging exceeds 8MB |

### 21.13 Out of scope (still)

§19 enumerated items that remain out-of-scope. §21 closes most of them. The following remain deferred:

- **WebSocket sync transport** — polling only for v1; deferred to v2.
- **DIAN provider-specific quirks** (Factus vs other providers' rate limits, sandbox vs production endpoints) — interface exists, adapter is operator-supplied via env vars.
- **Rate limiting on public endpoints** beyond sync — separate change (e.g. `parkos_core.api.middleware.RateLimit` for `/auth/login`).
- **OpenTelemetry tracing** — `parkos_core.structlog_config` already in place; OTLP exporter deferred to separate change.
- **Advanced circuit breakers** — basic retry-with-backoff shipped here; Hystrix-style breakers deferred to v2.
- **`parkos-cli pair --interactive`** — only the env-var-driven `python -m parkos_core.cli pair` ships; interactive mode (operator-friendly wizard) deferred.
- **HA `job_sync_cloud` with advisory locks** — single-instance design (§21.12 #24); multi-instance deferred to v2.

### 21.14 Acceptance criteria for §21

The delta is "done" when:

**Pairing (§21.3)**:
1. `backend/tests/integration/test_pairing_flow.py` — all 9 tests pass (`test_pair_happy_path`, `test_pair_token_reuse_rejected`, `test_pair_token_expired_rejected`, `test_pair_token_revoked_rejected`, `test_pair_revoked_jwt_rejects_subsequent_calls`, `test_pair_wrong_sucursal_rejected`, `test_pair_env_validator_fails_fast`, `test_pair_persisted_jwt_path_0600`, `test_pair_token_rate_limit`).
2. Migration `0003_add_pairing_tokens_and_revoked_sync_jwts.py` (PR9) includes both tables + both REVOKE statements + both triggers in the SAME script (per `config.yaml rules.tasks`); `alembic upgrade --sql head` shows the full sequence; `alembic check` exits 0.
3. `has_table_privilege('rol_app', 'prod.pairing_tokens', 'UPDATE')` returns `f`; same for `revoked_sync_jwts`. `pg_trigger WHERE tgname = 'pairing_tokens_no_update_delete'` returns 1; same for `revoked_sync_jwts_no_update_delete`.

**Admin views (§21.4)**:
4. `GET /api/v1/sucursales` with admin JWT returns only `sucursales_permitidas` rows (verified by negative test: admin whose permitidas list excludes X → X not in response).
5. `GET /api/v1/admin/sucursales/{uuid}/dashboard` with admin JWT + `X-Sucursal-Context` matching permitidas returns 200 with `{fecha, ingresos_count, ...}`; same with mismatched header → 403; same without header → 400.
6. `GET /api/v1/admin/me` returns `{actor_uuid, email, rol, sucursales_permitidas, permissions}`.

**Auto-discovery & installability (§21.5, §21.6)**:
7. `infra/deploy/README.md` documents all 3 scenarios with copy-pasteable `docker compose -f ... up` invocations.
8. Each compose file (`infra/deploy/docker-compose.{cloud,branch,db-cloud,api-branch,job-branch}.yml`) has `HEALTHCHECK` directives on every service + `depends_on.condition: service_healthy` on dependents.
9. `docker compose -f infra/deploy/docker-compose.cloud.yml config` validates without errors; same for the other 4 files.

**Sync workers (§21.7, §21.8)**:
10. `python -m parkos_core.jobs.sync_sucursal --config-test` (a dry-run mode that loads `parkos_core/runtime/env.py`, prints config, exits 0) succeeds; same for `--check-db` (verifies DB connectivity, JWT key path readable, sync_jwt path readable if present).
11. End-to-end: pair a branch → boot `job_sync_sucursal` → INSERT into `prod.factura_pagos` on branch → wait one poll cycle → verify cloud has the row via `GET /api/v1/admin/sucursales/{uuid}/dashboard` or direct SQL.
12. `POST /sync/push` with expired JWT → `job_sync_sucursal` calls `POST /sync/rotate-jwt`, gets new JWT, persists, retries the push (no operator action).
13. `POST /sync/push` with revoked JWT → `job_sync_sucursal` emits alerta, halts until operator re-pairs.
14. Cloud `job_sync_cloud` hash chain verifier catches a deliberately-broken row (test fixture inserts a row with mismatched `hash_actual`); emits alerta + sync_conflict.

**Sync transport (§21.9)**:
15. `X-Request-Id` replay within 5 min returns cached response with `Idempotent-Replay: true` header.
16. Rate limits enforced per (issuer, subject); 429 with `Retry-After`.

**Conflict resolution (§21.10)**:
17. `test_sync_conflict_resolution.py` all tests pass; on `[V]` conflict → `sync_conflict` row + `alerta` chain root.

**DIAN dispatcher (§21.11)**:
18. `test_dispatcher.py` (5 tests) all pass with `httpx.MockTransport`.
19. Boundary: in branch image context, `from parkos_core.dian.cloud.dispatcher import dispatch_factura_electronica` raises `ImportError`. CI asserts.
20. `jq '.paths | keys | map(select(test("/factura-electronica|/envio-dian|/validacion-evento|/revocacion-factura"))) | length' api_sucursal/openapi.json` returns 0 (unchanged from §16 / §10).

**Env validator (§21.2)**:
21. Boot with `PARKOS_SUCURSAL_UUID=` (empty) → exit code `2`, stderr message includes the env var name.
22. Boot with `PARKOS_DEPLOY=cloud` on a branch binary → exit code `2`.
23. `parkos-cli doctor` prints the structured `{env_status, db_connectivity, jwt_key_path_exists, sync_jwt_path_readable, cloud_api_url_reachable}` report.

**Gitflow / canon (§21 prerequisites)**:
24. All 4 new PRs (PR8, PR9, PR10a/b if split, PR11) target `dev` (NEVER `main`) per AGENTS.md gitflow canon.
25. Migration `0003_add_pairing_tokens_and_revoked_sync_jwts.py` is the ONLY schema change in §21 — everything else is orchestration + workers + boundary tests.
26. `uv run pytest backend/tests/{unit,integration,migrations,static} -q` exits 0 with all new tests included.
27. `uv run ruff check backend/packages/parkos_core/ && uv run mypy --strict backend/packages/parkos_core/ && uv run alembic check` all exit 0.

**Engram / persistence**:
28. The 4 new PRs commit task IDs `T-PR8-NN` / `T-PR9-NN` / `T-PR10-NN` / `T-PR11-NN` (added to `tasks.md` in the sdd-tasks delta) with work-unit scope: one behavior per commit, tests+docs in the same commit (per `~/.config/opencode/skills/work-unit-commits/SKILL.md`).

---

**Summary of §21 impact**: this section adds 2 new `[A]` tables (`pairing_tokens`, `revoked_sync_jwts`) — making the model 51 tables total, of which 14 are `[A]`-class. It introduces 4 chained PRs (PR8–PR11) with a conditional split trigger on PR10 (sync workers at the 800-LOC edge), 44 new files (~2,200 LOC), 12 new risks (4 HIGH, 6 MED, 2 LOW — none catastrophic), and a complete transport protocol that closes the original §19 "out of scope" deferral. All new code honors AGENTS.md `gitflow` (PRs to `dev`), `Audit-First` (REVOKE + trigger in the SAME migration, idempotency at every layer, hash chain extension in cloud for branch chains), and `no-DELETE` (every operation is C/Q/U; the 2 new `[A]` tables follow the same REVOKE + trigger pattern, with the one-time DELETE path reserved for the `sync_queue` whitelisted-columns carve-out already in §12).
