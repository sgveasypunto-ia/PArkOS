# Meta-PRD: 45 SQLAlchemy models (PRD-01)

> **NOT a table PRD.** Guides the creation of all 45 SQLAlchemy model classes
> in `parkos_core.models.{V,L_E,L_W,L_S,A}.<table>`. Each per-table PRD (T01..T45)
> defines WHAT the model must contain; this PRD defines HOW (conventions,
> base class, naming, type mappings, index patterns).

## Required References

### Canonical files outside this folder

- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd) — source of truth for columns + FKs
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md) — backend Python conventions
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration-plan.md`](../iteration-plan.md)
- **Bootstrap Tasks**: [`openspec/changes/bootstrap-monorepo-foundation/tasks.md`](../../changes/bootstrap-monorepo-foundation/tasks.md)
- **PRD-00 Scaffold**: [`_meta/00_scaffold.md`](00_scaffold.md)

### Shared PRD references (this folder)

- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md) — `uuid` (PK) vs `uuid_*` (FK); cardinality
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — `uuid_padre` self-references
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata

- **Type**: Meta-PRD (covers 45 table models)
- **Phase**: Phase 0 (Foundation Walking Skeleton) — F2/F3
- **Scope**: 45 SQLAlchemy 2.0 model classes + audit columns + sync columns + FK relations
- **Stack**: Python 3.13 + SQLAlchemy 2.0 async + Pydantic v2 + Alembic
- **Origin**: After PRD-00 scaffold
- **PRD status**: Draft
- **PRD version**: 2.0
- **Last updated**: 2026-08-31

## 2. Why this PRD is needed

Each per-table PRD (T01..T45) defines WHAT columns a table has and WHAT FKs it participates in. But there are conventions that apply uniformly:

- All models share the same `Base` (declarative).
- All models have the same audit columns (`created_at`, `created_by`).
- `[V]` models have `vigente_desde` + `vigente_hasta`.
- All models have sync columns (`sync_status`, `sync_timestamp`, `sync_attempts`).
- All FKs are typed `UUID` (matching `gen_random_uuid()` from `pgcrypto`).

This PRD defines the conventions once. Per-table PRDs only override when their table has unique columns (e.g., `log_transaccional.hash_anterior/hash_actual`, `facturas.numero_temporal`, etc.).

## 3. Deliverables

### 3.1 Base class (`backend/packages/parkos_core/src/parkos_core/db/base.py`)

```python
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, String, Integer, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class AuditMixin:
    """Common audit columns present in EVERY table."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )

class VersioningMixin:
    """For [V] projection tables."""
    vigente_desde: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    vigente_hasta: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

class SyncMixin:
    """Sync columns present in EVERY table (per model)."""
    sync_status: Mapped[str] = mapped_column(
        String(20), server_default="pending", nullable=False
    )
    sync_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sync_attempts: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )

class UUIDMixin:
    """Primary key — always uuid (server-generated)."""
    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
```

### 3.2 Table-by-table model classes

Each model lives at `backend/packages/parkos_core/src/parkos_core/models/<LEVEL>/<table>.py` where `<LEVEL>` is one of `V`, `L_E`, `L_W`, `L_S`, `A`. Each `__init__.py` in those subpackages re-exports the models.

#### Pattern (per-table example, all 45 follow this shape):

```python
# models/V/usuarios.py
from uuid import UUID
from datetime import datetime
from sqlalchemy import String, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from parkos_core.db.base import Base, AuditMixin, VersioningMixin, SyncMixin, UUIDMixin

class Usuarios(UUIDMixin, AuditMixin, VersioningMixin, SyncMixin, Base):
    __tablename__ = "usuarios"
    __table_args__ = ({"schema": "prod"},)

    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    apellido: Mapped[str] = mapped_column(String(100), nullable=False)
    cedula: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_cambio_password: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rol: Mapped[str] = mapped_column(String(20), nullable=False)

    # Outgoing relationships: NONE (usuarios is a FK source for many)
    # Incoming relationships (per _shared/fk-naming-convention.md):
    permisos_usuario_list: Mapped[list["PermisosUsuario"]] = relationship(
        back_populates="usuario", cascade="save-update"
    )
```

### 3.3 Per-table model index conventions

- Indexes for FK columns (so JOINs are fast): `Index(f"ix_<table>_<col>", uuid_<col>)`.
- Composite indexes for common query patterns:
  - `usuarios`: `Index("ix_usuarios_vigente", vigente_desde, vigente_hasta)` for "current user" lookups.
  - `sync_queue`: `Index("ix_sync_queue_estado", estado, next_retry_at)` for worker polling.
  - `log_transaccional`: `Index("ix_log_transaccional_sucursal_time", uuid_sucursal, created_at)` for chain verification queries.
- Unique indexes for natural keys (e.g., `usuarios.cedula`, `usuarios.email`).

### 3.4 Per-enforcement-level patterns

| Level | Mixins | REVOKE | Triggers |
|---|---|---|---|
| `[V]` projection | UUIDMixin + AuditMixin + VersioningMixin + SyncMixin | NO (DB allows UPDATE) | NO |
| `[L-E]` event | UUIDMixin + AuditMixin + SyncMixin | NO (state derived) | NO |
| `[L-W]` workflow | UUIDMixin + AuditMixin + SyncMixin (+ `uuid_padre: Mapped[UUID \| None]` self-ref) | NO | NO |
| `[L-S]` session | UUIDMixin + AuditMixin + SyncMixin | NO (only `estado` + `timestamp_cierre` allowed via trigger) | YES (`ls_session_update_guard`) |
| `[A]` source-of-truth | UUIDMixin + AuditMixin + SyncMixin | YES (UPDATE/DELETE revoked on `rol_app`) | YES (`reject_mutation`) |

### 3.5 Tables with special columns (per per-table PRDs)

Each per-table PRD's `## Metadata` lists table-specific columns that override the mixin defaults.

## 4. Use Cases enabled by these models

### 4.1 Use Case: `uc.model.first-boot-migration`

The 45 models drive Alembic's autogenerate. F1 task `F1.7` writes `0001_initial_schema.py` to create all 45 tables + REVOKE + triggers + partitions + hash-chain genesis.

**Steps**:
1. `uv run --package parkos_core alembic upgrade head` against fresh `postgres:16`.
2. `\dt prod.*` returns 45 tables.
3. Entrypoint verifier confirms REVOKE + triggers present.

**Models involved**: ALL 45.
**Integrations**: enables every iteration (IT-1..IT-12).

### 4.2 Use Case: `uc.model.sync-queue-enqueue`

Every state-mutating use case (login, ingreso, factura, etc.) calls `queue_processor.enqueue_<table>(...)` which serializes the row to JSONB and INSERTs into `sync_queue`. This use case depends on the 45 models having a stable serialization (Pydantic v2 `model_validate` round-trip).

**Steps**:
1. `api_sucursal/routers/ingresos.py::POST /ingresos` calls `IngresoWriter.write(session, datos)`.
2. Writer inserts `Ingreso` row, then calls `queue_processor.enqueue('ingres','', uuid, datos)`.
3. `job_sync_sucursal/drain_outbox` reads `sync_queue` rows, serializes via Pydantic, POSTs to cloud.

**Models involved**: `[A]` sync_queue + the model being enqueued (e.g., ingreso).

### 4.3 Use Case: `uc.model.cloud-receive-and-hash-chain`

Cloud receives a sync push and inserts the row. For `[A|L-S]` tables, the cloud handler MUST also INSERT into `log_transaccional` with hash chain verification.

**Steps**:
1. `api_admin/routers/sync.py::POST /sync/push` receives JSON payload.
2. Handler Pydantic-validates payload against model schema.
3. Handler INSERTs row.
4. For `[A|L-S]` tables, handler calls `log_transaccional_writer.write_event(...)` in same TX with hash chain verification.
5. Handler INSERTs into `sync_log`.

**Models involved**: target table + `log_transaccional` + `sync_log`.

## 5. Use Cases for the audit-first enforcement pattern

The 45 models are not just shape definitions — they participate in the **AUDIT-FIRST enforcement pattern**. When SQLAlchemy maps a model that inherits the `AuditMixin` + `VersioningMixin` + `SyncMixin`, the application layer is **automatically aware** of the enforcement level (because the model lives in a specific subpackage: `models/V/`, `models/L_E/`, `models/L_W/`, `models/L_S/`, `models/A/`). Writers check the level at runtime and apply the right write pattern.

### 5.1 Use Case: `uc.model.audit-first-enforcement-by-level`

Every business writer (`ingreso_writer`, `factura_writer`, etc.) inspects the model class's module path to determine its enforcement level. For `[A]` models, the writer delegates to `parkos_core/audit/source_of_truth_writer.py` which automatically: (a) opens a TX, (b) calls `log_writer.write_log()` to extend the hash chain, (c) checks the `BEFORE UPDATE OR DELETE` trigger exists on the table, (d) returns the inserted row. The same pattern applies for `[L-W]` workflow writers (insert-only, no hash chain unless explicitly required), `[L-S]` session writers (UPDATE exception with log_transaccional mandate), and `[V]` projection writers (versioning via archive old + INSERT new).

**Steps**:
1. Application code calls `ingreso_writer.write(session, datos)` (T04 use case 7.1).
2. `ingreso_writer` inspects `Ingreso.__module__` → resolves to `parkos_core.models.L_E.ingreso` → enforcement level `[L-E]`.
3. Writer opens TX; SELECT chain anchor from `log_transaccional`.
4. INSERT `ingreso` row (state derived from other events — NOT set explicitly).
5. Call `log_writer.write_log(accion='ingreso_creado', tabla='ingreso', uuid_registro=$uuid, ...)` — this is the same `log_writer` used by all 45 tables.
6. `log_writer` INSERTs `log_transaccional` with hash chain verification.
7. Writer enqueues to `sync_queue` via `queue_processor.enqueue('ingreso', $uuid, $snapshot)`.
8. Return the row.

**Models involved**: any of the 45 models. The pattern is uniform across levels; only the writer behavior differs.

**Integrations**: enables T01 (`log_transaccional`), T06 (`sync_queue`), and every per-table writer.

### 5.2 Use Case: `uc.model.polymorphic-fk-with-discriminator`

Tables with polymorphic FKs (`reclamos`, `alerta`, `log_transaccional.uuid_registro_afectado`, `documentos` sprint 5) represent a FK target that depends on a discriminator column. SQLAlchemy models use the `Mapped[UUID]` + a string discriminator column (e.g., `tipo_reclamable`). The application layer enforces the FK semantics via `polymorphic_fk_resolver.py::resolve_target(tipo_discriminator, uuid_referenciado)` which validates the UUID exists in the corresponding table. NO database-level FK constraint (the constraint is per-row, based on the discriminator value).

**Steps**:
1. Application calls `reclamo_writer.write_reclamo(tipo_reclamable='factura', uuid_reclamable=$factura_uuid, motivo=...)` (T40 use case 7.1).
2. Writer inspects `Reclamos.tipo_reclamable` — must be in the ENUM (`ingreso` | `salida` | `factura` | `subscripcion`).
3. Writer calls `polymorphic_fk_resolver.resolve_target(tipo_reclamable='factura', uuid_reclamable=$uuid)`:
   - SELECT `uuid FROM facturas WHERE uuid=$uuid` → returns row.
   - If NOT found → reject with `POLYMORPHIC_FK_INVALID`.
4. Writer INSERTs `reclamos` row.
5. Application code JOINs `reclamos` with the target table based on `tipo_reclamable`: `SELECT r.*, COALESCE(i.placa, f.numero_oficial, s.placa, sc.uuid_cliente) AS target_label FROM reclamos r LEFT JOIN ingreso i ON r.tipo_reclamable='ingreso' AND r.uuid_reclamable=i.uuid LEFT JOIN facturas f ON r.tipo_reclamable='factura' AND r.uuid_reclamable=f.uuid ...`.

**Models involved**: `reclamos`, `alerta` (manual type), `log_transaccional.uuid_registro_afectado`, `documentos` (sprint 5).

**Integrations**: enables T40, T41, T01 (audit log), and sprint 5 documentos.

### 5.3 Use Case: `uc.model.versioning-mixin-vigente-desde-hasta`

For `[V]` projection tables (`usuarios`, `permisos`, `clientes`, `sucursal`, `tarifas_sucursal`, `tipo_subscripciones`, `impuestos`, `otros_cobros`, `costos_servicios`, `configuracion_tolerancias`, `configuracion_seguridad`, `empresa`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos`, etc.), the `VersioningMixin` provides `vigente_desde` (mandatory) + `vigente_hasta` (nullable). Writers implement the standard versioning flow: SELECT current vigente row `FOR UPDATE` → UPDATE `vigente_hasta=NOW()` on the old row → INSERT new row with new UUID + `vigente_desde=NOW()`. This pattern is enforced uniformly across all 24 `[V]` tables.

**Steps**:
1. Admin calls `usuarios_writer.update(session, uuid_usuario=$X, nombre=$new_nombre, vigente_desde=NOW())` (T07).
2. Writer SELECTs current vigente: `SELECT * FROM usuarios WHERE uuid=$X AND vigente_hasta IS NULL FOR UPDATE`.
3. UPDATE `usuarios SET vigente_hasta=NOW() WHERE uuid=$X`.
4. INSERT new `usuarios` row (`uuid=server-generated`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `nombre=$new_nombre`).
5. INSERT `log_transaccional` (`accion='usuario_actualizado'`, `datos_anteriores={nombre:$old}`, `datos_nuevos={nombre:$new}`).
6. New version is now vigente. Old version is preserved for audit (point-in-time queries can reconstruct the historical state).
7. `queue_processor.enqueue('usuarios', $new_uuid, $snapshot)` for parametrization push.

**Models involved**: any `[V]` table (24 models).

**Integrations**: enables T07 (`usuarios`), T14 (`tarifas_sucursal`), T21 (`empresa`), T27 (`otros_cobros`), and the audit-first contract for catalog/projection data.

## 6. Atomic DB Operations

## 6. FK Map (incoming + outgoing)

Each per-table PRD will document the FKs. This meta-PRD only requires:

- All FK columns are typed `Mapped[UUID]` (mapped to `PGUUID(as_uuid=True)`).
- All FK columns use `ForeignKey("prod.<target>.uuid", ondelete="RESTRICT", onupdate="CASCADE")` per `_shared/fk-naming-convention.md`.
- Each FK has a corresponding `relationship()` on both sides (back_populates).
- Composite FKs not used (single UUID is sufficient).

## 7. CodeGraph Dependencies

After models land, `codegraph init` indexes the entire `parkos_core.models/` package. Then each per-table PRD's `## CodeGraph Dependencies` is auto-populated by querying:

```bash
codequery query --name <TableName> --direction both
```

## 8. Layer-by-Layer Impact

| Layer | Impact | Path |
|---|---|---|
| 1. DB schema | YES (45 model classes drive Alembic `0001_initial_schema.py`) | `parkos_core/models/...` |
| 8. Pydantic schemas | YES (`parkos_core/schemas/<table>.py` derives from each model) | `parkos_core/schemas/...` |
| 12. Sync queue/conflict | YES (models drive serialization in `sync_queue.datos`) | `parkos_core/sync/...` |
| 24. CI/test | YES (pytest imports models for integration tests) | `tests/integration/test_<table>.py` |
| 26. CI/typecheck | YES (mypy strict on models) | `pyproject.toml` `[tool.mypy]` |

## 9. Cross-cutting Use Case Integration Matrix

| Downstream Use Case | Touches these models (in order of write) |
|---|---|
| `uc.login.operator` | `usuarios`, `usuarios_sucursal`, `permisos_usuario`, `login`, `log_transaccional`, `sync_log` |
| `uc.login.admin` | same as operator + `sucursal` (admin may switch branches) |
| `uc.pairing.branch-first-boot` | `sucursal`, `login`, `log_transaccional`, `sync_log` |
| `uc.param.push.cloud-to-branch` | `sucursal`, `tipo_sucursal`, `documentos`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos`, `em`,`, `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `impuestos`, `otros_cobros`, `costos_servicios`, `configuracion_tolerancias`, `configuracion_seguridad`, `usuarios`, `permisos`, `permisos_usuario`, `usuarios_sucursal` |
| `uc.event.ingreso` | `ingreso`, `sync_queue`, `log_transaccional`, `sync_log` |
| `uc.event.salida` | `salidas`, `ingreso`, `sync_queue`, `log_transaccional` |
| `uc.factura.online` | `facturas`, `factura_detalle`, `factura_pagos`, `factura_impuestos`, `factura_otros_cobros`, `em`,`, `factura_electronica`, `revocacion_factura` (cloud-only), `sync_queue`, `log_transaccional`, `sync_log` |
| `uc.factura.offline` | same as online, but `numero_temporal` placeholder + `SyncBackEvent` later |
| `uc.workflow.anulacion` | `anulaciones` (chain), `ingreso`, `log_transaccional`, `sync_queue` |
| `uc.workflow.reclamo` | `reclamos` (chain), `ingreso` or `salidas` or `facturas` or `subscripciones_cliente` (polymorphic), `log_transaccional`, `sync_queue` |
| `uc.workflow.alerta` | `alerta` (chain), `arqueo` (if diferencia_arqueo), `log_transaccional`, `sync_queue` |
| `uc.workflow.reimpresion` | `reimpresion_ticket` (chain), `facturas`, `factura_electronica`, `costos_servicios`, `usuarios`, `ingreso`, `log_transaccional`, `sync_queue` |
| `uc.subscripcion.admin` | `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos`, `tipo_subscripciones`, `tipo_persona`, `tipos_vehiculo`, `sync_queue`, `log_transaccional` |
| `uc.cash.apertura` | `sesion`, `caja`, `usuarios`, `sucursal`, `log_transaccional`, `sync_queue` |
| `uc.cash.cierre` | `sesion`, `arqueo`, `caja`, `configuracion_tolerancias`, `alerta` (if diferencia), `log_transaccional`, `sync_queue` |
| `uc.dian.process-online` | `facturas` (received), `factura_electronica`, `em` (atomic consecutivo), `revocacion_factura` (on DIAN error) |
| `uc.dian.process-offline` | `SyncBackEvent`, `factura_electronica` (after cloud receive), `numero_oficial` field on `facturas` |
| `uc.reportes.admin` | `facturas`, `factura_pagos`, `arqueo`, `alerta`, `log_transaccional` (read-only aggregates) |
| `uc.audit.hash-chain-verifier` | `log_transaccional`, `revocacion_factura`, `alerta` (creates alert on break) |

## 10. RED Tests

- (RED) `parkos_core.models.<table>.Model` for all 45 tables importable; Alembic sees `target_metadata`.
- (RED) FK relationships resolve both ways (e.g., `usuarios.permisos_usuario_list` and `permisos_usuario.usuario`).
- (RED) Mixin columns present on every model (`uuid`, `created_at`, `created_by`, sync columns).
- (RED) `[A]` models have `__table_args__` declaring schema = "prod".
- (RED) Hash-chain models (`log_transaccional`, `revocacion_factura`) have `hash_anterior`, `hash_actual` columns typed `String(64)`.
- (RED) Workflow models have `uuid_padre` self-reference.

## 11. Implementation Tasks

Per-table sub-PRD. Each per-table PRD's `## Implementation Tasks` lists the model creation task as the first item (after F1 schema).

## 12. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| 45 model files is a lot to maintain | Med | Use mixins to reduce boilerplate; per-table PRDs define only table-specific columns |
| Circular import between related models | Med | Use `TYPE_CHECKING` for forward references in relationships |
| Alembic autogenerate creates migrations not matching `.mmd` | Med | `0001_initial_schema.py` is hand-written (per bootstrap tasks F1); models drive FUTURE migrations only |
| Mapped[] vs mapped_column() typing | Low | Use the new SQLAlchemy 2.0 `Mapped[T]` declarative style throughout |

## 13. Open Questions

- (a) Should `created_by` FK to `usuarios.uuid` be enforced at the DB level or only at the application level? Currently application-level (no DB FK) to avoid bootstrap circular dependency. May add later.
- (b) Should models include `__repr__` for debugging? Yes, by default.
- (c) `sync_status` enum values — string column with values "pending" | "synced" | "skipped". Use Python `enum.Enum` and SQLAlchemy `Enum` type, or string with `CheckConstraint`? Default: string + `CheckConstraint` for simplicity.

## 14. Hand-off

After this PRD lands, **PRD-02 (jobs queries)** can specify exactly which tables each sync worker reads and writes. Then **PRD-03 (APIs queries)** can specify the CRUD surface.