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
