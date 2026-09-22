# Design — `ingreso-multi-tipo-consecutivo`

> **Change**: `ingreso-multi-tipo-consecutivo` · **Folder**: `openspec/changes/ingreso-multi-tipo-consecutivo/`
> **Phase**: design (sdd-design) · **Status**: ready-for-sdd-tasks
> **Date**: 2026-09-22 · **Author**: Parkos Dev <dev@parkos.local>
> **Inputs**: `openspec/changes/ingreso-multi-tipo-consecutivo/{spec.md,proposal.md,exploration.md}` (this change)
> **Base spec**: `openspec/specs/operations/spec.md` (canonical, REQ-OPS-001..190; delta is REQ-OPS-191..198 + REQ-OPS-040 modified)
> **Base architecture**: `AGENTS.md` §Architectural Principles (audit-first, bi-temporal, C/Q/U-no-D, multi-tenant, hash chain)
> **Pattern sources**: `assign_consecutivo` precedent (`backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py:47-183`); `idempotency_keys` precedent (`models/A/idempotency_keys.py`, 50th table `[A]`); `0037_add_uuid_subscripcion_cliente_to_facturas.py` precedent (nullable ADD COLUMN + idempotent FK)

---

## 1. Technical Approach

Open the `POST /api/v1/operacion/ingresos` endpoint to vehicles without placa (`bicicleta`, `patineta`) by stamping a per-`(uuid_sucursal, uuid_tipo_vehiculo)` monotonic `consecutivo` in the format `<TIPO>-NNNNNN-<uuid8>` (e.g. `BICI-000001-3f8a1b2c`) and persisting it as a new nullable column on `prod.ingreso` (REQ-OPS-192). The consecutivo is assigned by an app-side helper `assign_ingreso_consecutivo` (REQ-OPS-191) that mirrors the proven `assign_consecutivo` pattern (T-PR9-002) — `SELECT … FOR UPDATE` over a new `[A]` counter table `prod.ingreso_consecutivo_contador` (51st table, 49 + idempotency_keys + counter). Defense in depth: a partial unique index `WHERE consecutivo IS NOT NULL` rejects duplicate consecutivos at DB level if the helper ever races.

Two chained PRs land this: **PR-A** ships the backend foundation (migration + counter table + helper + handler + schemas + tests), **PR-B** ships the frontend wiring (discriminated-union Zod + `<IngresoSinPlacaPanel>` + `<TipoIngresoToggle>` + `<TiqueteModal>` `consecutivo` prop + `<escposBuilder>` discriminated union + i18n + tests). Linear dependency: PR-A must land before PR-B because the response shape changes.

The existing 11-step V-chain (`api/v1/operacion.py::create_ingreso:145-316`) is extended at exactly three points: **Step 2** is loosened to accept `placa=None` when `uuid_tipo_vehiculo` is supplied (REQ-OPS-194), **Step 8** is skipped for `placa=None` (REQ-OPS-040 modified), **Step 8.5** (new) calls `assign_ingreso_consecutivo` for the no-placa path and pre-generates the `Ingreso.uuid` so the `<uuid8>` suffix is deterministic, **Step 9** carries `consecutivo` into `new_attrs` BEFORE `crear_ingreso_evento` (preserves the `[L-E]` insert-only AST lock — R4 mitigation), **Step 11** exposes `consecutivo` in the response. No UPDATE path exists; `tests/static/test_no_write_after_insert.py` is preserved.

Audit-first is preserved without any extra work: `record_event`'s canonical payload (`event.py:115-137`) reads every `new_attrs` key and writes them to `log_transaccional.datos_nuevos`, so the new column enters the hash chain for free. Multi-tenant is preserved by scoping the counter to `(uuid_sucursal, uuid_tipo_vehiculo)` and the partial UK likewise. Sync (eventual) is preserved because `record_event` flows the new column with the row, and the cloud preserves branch-assigned values verbatim per `cloud-edge-sync-architecture` §4 + DEC-SUC-28.

---

## 2. Architecture Overview

```
                       ┌────────────────────────────────────────────────────┐
                       │  apps/electron-sucursal (renderer)                  │
                       │                                                    │
   operator clicks      │  <Principal.tsx> / <IngresoPanel.tsx>               │
   "Sin placa"   ───►   │     └─► <TipoIngresoToggle>                         │
                       │           ├─► <PlacaInput>      (variant: con-placa)│
                       │           └─► <IngresoSinPlacaPanel>                │
                       │                 ├─► useTiposVehiculoSinPlaca()      │
                       │                 ├─► <TipoSelect> (shadcn)           │
                       │                 └─► postIngreso({ placa_presente:   │
                       │                       false, uuid_tipo_vehiculo })  │
                       └─────────────────────────┬──────────────────────────┘
                                                 │ HTTPS (parkosFetch)
                                                 ▼
                       ┌────────────────────────────────────────────────────┐
                       │  api_sucursal (FastAPI, F1.6 handler)               │
                       │                                                    │
                       │  create_ingreso() 11-step chain:                    │
                       │   1 KD-3 → 2 V5 (loosen for placa=None) ─►          │
                       │   3 V4 → 4 KD-FORZADO-01 → 5 V1+V2 → 6 V3 → 7 V6   │
                       │   8 V8  [SKIP if placa is None] ─►                  │
                       │   8.5 [NEW] assign_ingreso_consecutivo()  ─►        │
                       │   9   INSERT prod.ingreso (record_event, [L-E]) ─►  │
                       │   10  V9 derivation  ─► 11 response w/ consecutivo   │
                       └─────────────────────────┬──────────────────────────┘
                                                 │
                                                 ▼
                       ┌────────────────────────────────────────────────────┐
                       │  repo/ingreso_consecutivo.py (NEW, ~150 LOC)        │
                       │                                                    │
                       │  assign_ingreso_consecutivo(                        │
                       │      session,                                      │
                       │      uuid_sucursal, uuid_tipo_vehiculo,             │
                       │      source_event_uuid                             │
                       │  ) -> str                                         │
                       │                                                    │
                       │   1. SELECT counter by (sucursal, tipo)             │
                       │      WHERE vigente_hasta IS NULL                    │
                       │   2. If absent  → INSERT counter row 1              │
                       │   3. If present → SELECT FOR UPDATE →               │
                       │                   UPDATE counter (n+1)             │
                       │                   RETURN formato                   │
                       │   4. format = "<TIPO>-{n:06d}-{source[:8]}"        │
                       └─────────────────────────┬──────────────────────────┘
                                                 │
                                                 ▼
                       ┌────────────────────────────────────────────────────┐
                       │  Postgres 16 (branch + cloud)                       │
                       │                                                    │
                       │  prod.ingreso                          [L-E]        │
                       │    uuid_sucursal, placa NULL,                        │
                       │    uuid_tipo_vehiculo,                               │
                       │    consecutivo VARCHAR(20) NULL        ← NEW        │
                       │    UNIQUE PARTIAL INDEX (sucursal, tipo, consec)     │
                       │                                                    │
                       │  prod.ingreso_consecutivo_contador   [A]  51st tbl   │
                       │    uuid_sucursal, uuid_tipo_vehiculo,               │
                       │    ultimo_consecutivo INT, last_event_uuid          │
                       │    UK (sucursal, tipo, vigente_desde)               │
                       │    REVOKE UPDATE/DELETE FROM rol_app   (R6)         │
                       │    TRIGGER fn_revoke_modify (carve-out cols only)   │
                       │    fecha_retencion_hasta (DIAN 5y)                  │
                       └────────────────────────────────────────────────────┘
```

**Wire-shape impact (additive)**:
- `POST /operacion/ingresos` accepts a discriminated-union payload keyed on `placa_presente: boolean` (REQ-OPS-194).
- `IngresoRead` and `IngresoReadForzado` add `consecutivo: str | None = None` (REQ-OPS-197).
- `SalidaReadForzado` does NOT need `consecutivo`; the salida handler reads via JOIN (`ingreso.consecutivo`) and the operator-side re-uses `uuid_ingreso` to identify the vehicle.

**Ticket rendering**:
- `<escposBuilder>::buildEntradaBuffer` discriminates on `payload.variant` (`'con-placa' | 'con-consecutivo'`):
  - `con-placa` → `Placa: <placa>` line (12th conceptual field).
  - `con-consecutivo` → `Identificación: <consecutivo>` line (REQ-OPS-197, operator-facing label per DEC-SUC-26).
- `<TiqueteModal>` renders the same line via the new `consecutivo?: string | null` prop.

---

## 3. Data Model Changes

### 3.1 New `[A]` table `prod.ingreso_consecutivo_contador` (51st table)

#### Schema (migration `0042_add_ingreso_consecutivo.py`)

```sql
CREATE TABLE prod.ingreso_consecutivo_contador (
    -- IdMixin
    uuid                     UUID        NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    -- AuditMixin
    created_at               TIMESTAMP   NOT NULL DEFAULT NOW(),
    created_by               UUID,
    -- SyncMixin
    sync_status              VARCHAR(16)          DEFAULT 'pendiente',
    sync_timestamp           TIMESTAMP,
    sync_attempts            INTEGER              DEFAULT 0,
    -- VersionedMixin (bi-temporal; counter has close+insert semantics)
    vigente_desde            TIMESTAMP            DEFAULT NOW(),
    vigente_hasta            TIMESTAMP,
    estado                   VARCHAR(16) NOT NULL DEFAULT 'activo',
    -- RetentionMixin (DIAN 5y retention per AGENTS.md §1; conservative
    -- default even though this is operational — see DEC-INCOME-01)
    fecha_retencion_hasta    DATE,
    -- Business columns
    uuid_sucursal            UUID        NOT NULL REFERENCES prod.sucursal(uuid),
    uuid_tipo_vehiculo       UUID        NOT NULL REFERENCES prod.tipos_vehiculo(uuid),
    ultimo_consecutivo       INTEGER     NOT NULL DEFAULT 0
        CHECK (ultimo_consecutivo >= 0 AND ultimo_consecutivo < 1000000),
    last_event_uuid          UUID,                       -- idempotency anchor (mirror of assign_consecutivo)
    -- UK: bi-temporal — version is part of identity
    UNIQUE (uuid_sucursal, uuid_tipo_vehiculo, vigente_desde)
);
```

#### REVOKE + `BEFORE UPDATE OR DELETE` trigger (same pattern as `models/A/idempotency_keys.py:9-12`)

```sql
REVOKE UPDATE, DELETE ON prod.ingreso_consecutivo_contador FROM rol_app;

CREATE OR REPLACE FUNCTION prod.fn_revoke_modify_ingreso_consecutivo() RETURNS TRIGGER AS $$
DECLARE
    is_carveout BOOLEAN := false;
BEGIN
    -- Operational UPDATE carve-out (REQ-OPS-193 / R6 / DIAN assign_consecutivo precedent):
    -- only the columns needed to advance the counter may be UPDATEd by rol_app.
    IF TG_OP = 'UPDATE' THEN
        IF (
            OLD.uuid_sucursal      IS NOT DISTINCT FROM NEW.uuid_sucursal
            AND OLD.uuid_tipo_vehiculo IS NOT DISTINCT FROM NEW.uuid_tipo_vehiculo
            AND OLD.created_at      IS NOT DISTINCT FROM NEW.created_at
            AND OLD.created_by      IS NOT DISTINCT FROM NEW.created_by
            AND OLD.vigente_desde   IS NOT DISTINCT FROM NEW.vigente_desde
            AND OLD.vigente_hasta   IS NOT DISTINCT FROM NEW.vigente_hasta
            AND OLD.estado          IS NOT DISTINCT FROM NEW.estado
            AND OLD.uuid            IS NOT DISTINCT FROM NEW.uuid
            AND OLD.fecha_retencion_hasta IS NOT DISTINCT FROM NEW.fecha_retencion_hasta
        ) THEN
            is_carveout := true;
        END IF;
        IF NOT is_carveout THEN
            RAISE EXCEPTION 'ingreso_consecutivo_contador_immutable: only (ultimo_consecutivo, last_event_uuid, sync_status, sync_timestamp, sync_attempts) may be UPDATEd';
        END IF;
    ELSE
        RAISE EXCEPTION 'ingreso_consecutivo_contador_immutable: DELETE is forbidden (REVOKE + TRIGGER)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ingreso_consecutivo_contador_inmutable
BEFORE UPDATE OR DELETE ON prod.ingreso_consecutivo_contador
FOR EACH ROW EXECUTE FUNCTION prod.fn_revoke_modify_ingreso_consecutivo();
```

#### Sync-trigger exclusion (R9 mitigation — prevent recursion)

The 18 `[V]` tables' `fn_enqueue_sync_catalog` triggers fire on any INSERT/UPDATE/DELETE. The counter is **local-only** (no `branch_to_cloud` propagation — it's a per-branch operational counter). Add to the trigger function in `fn_enqueue_sync_catalog`:

```sql
IF TG_TABLE_NAME = 'ingreso_consecutivo_contador' THEN
    RETURN NULL;  -- skip sync enqueue
END IF;
```

(Per AGENTS.md precedent for `sync_queue` exclusion: counter table never propagates.)

#### Operational notes

- **Not partitioned**: counters never grow beyond O(branches × tipos) ≈ 100s of rows. `pg_partman` would add overhead for no gain.
- **`[A]` audit class** (canonical): REVOKE + trigger + retention column, all in the SAME migration per `config.yaml rules.tasks`.
- **Bi-temporal UK**: `(uuid_sucursal, uuid_tipo_vehiculo, vigente_desde)`. Closing + re-inserting is the only valid mutation; an operational UPDATE is allowed only on carve-out columns by the trigger function.

### 3.2 New column `prod.ingreso.consecutivo`

```sql
ALTER TABLE prod.ingreso ADD COLUMN consecutivo VARCHAR(20) NULL;
-- PG11+ metadata-only; nullable for backward compat.

CREATE UNIQUE INDEX uq_ingreso_consecutivo_partial
    ON prod.ingreso (uuid_sucursal, uuid_tipo_vehiculo, consecutivo)
    WHERE consecutivo IS NOT NULL;  -- defense in depth (R1, R5)
```

**Backward compat**: existing carro/moto rows (50k+ in production, ~hundreds in dev) keep `consecutivo = NULL`. The partial UK only applies to NOT NULL values; legacy rows are unaffected. Frontend `PostIngresoResponseSchema` declares `consecutivo: z.string().nullable()` so legacy rows return `null` without breaking (REQ-OPS-192 scenario 1).

### 3.3 ORM updates

#### `backend/packages/parkos_core/src/parkos_core/models/L_E/ingreso.py` (modify)

```python
class Ingreso(LifecycleEventBase):
    __tablename__ = "ingreso"
    # ... existing 6 columns ...
    consecutivo: Mapped[str | None] = mapped_column(String(20), nullable=True)  # NEW (REQ-OPS-192)
```

#### `backend/packages/parkos_core/src/parkos_core/models/A/ingreso_consecutivo_contador.py` (NEW)

```python
"""[A] Per-(sucursal, tipo) monotonic counter for ingresos sin placa (REQ-OPS-193).

51st table in the model; out of bootstrap-monorepo-foundation scope.
REVOKE UPDATE/DELETE on rol_app + BEFORE UPDATE OR DELETE trigger carve-out for
(ultimo_consecutivo, last_event_uuid) ONLY (per DIAN assign_consecutivo precedent).
"""
from __future__ import annotations
import uuid as uuid_lib
from sqlalchemy import Integer, String, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from ..base import AppendOnlyBase  # IdMixin + AuditMixin + SyncMixin + RetentionMixin + __write_only__


class IngresoConsecutivoContador(AppendOnlyBase):
    """[A] Per-(uuid_sucursal, uuid_tipo_vehiculo) ingreso.consecutivo counter."""

    __tablename__ = "ingreso_consecutivo_contador"

    uuid_sucursal: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False,
    )
    uuid_tipo_vehiculo: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False,
    )
    ultimo_consecutivo: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    last_event_uuid: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True,
    )

    __table_args__ = (
        # Bi-temporal UK mirrors [V] convention
        Index("uq_ingreso_consecutivo_contador_ns",
              "uuid_sucursal", "uuid_tipo_vehiculo", "vigente_desde",
              unique=True),
        CheckConstraint(
            "ultimo_consecutivo >= 0 AND ultimo_consecutivo < 1000000",
            name="ck_ingreso_consecutivo_contador_range",
        ),
        {"schema": "prod", "extend_existing": True},
    )


__all__ = ["IngresoConsecutivoContador"]
```

---

## 4. Backend Service — `assign_ingreso_consecutivo`

**Location**: `backend/packages/parkos_core/src/parkos_core/repo/ingreso_consecutivo.py` (NEW, ~150 LOC)

Mirrors `assign_consecutivo` (`repo/resolucion_facturacion.py:47-183`) verbatim where possible — same idempotency-then-lock-then-UPDATE pattern.

### 4.1 Signature

```python
async def assign_ingreso_consecutivo(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    source_event_uuid: uuid_lib.UUID,
) -> str:
    """Return the next consecutivo in format `<TIPO>-NNNNNN-<uuid8>`.

    Idempotent per source_event_uuid (REQ-OPS-191). No side effect outside
    the caller's transaction. Caller commits together with the Ingreso INSERT.
    """
```

### 4.2 Algorithm

```python
async def assign_ingreso_consecutivo(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    source_event_uuid: uuid_lib.UUID,
) -> str:
    """Idempotent per-source-event; SELECT FOR UPDATE on counter row."""
    # 0. Resolve TIPO uppercase from catalog (mirror of assign_consecutivo's
    #    resolution_uuid lookup). One round-trip; cached per-call.
    tipo_row = (
        await session.execute(
            select(TiposVehiculo.tipo).where(
                TiposVehiculo.uuid == uuid_tipo_vehiculo,
                TiposVehiculo.vigente_hasta.is_(None),
                TiposVehiculo.estado == "activo",
            )
        )
    ).first()
    if tipo_row is None:
        raise ValueError(
            f"uuid_tipo_vehiculo={uuid_tipo_vehiculo} not vigente in prod.tipos_vehiculo"
        )
    tipo_upper = tipo_row.tipo.upper()  # 'BICI' | 'PATIN'

    # 1. IDEMPOTENCY CHECK (mirror assign_consecutivo step 1):
    #    if a counter row already has last_event_uuid == source_event_uuid,
    #    reuse its ultimo_consecutivo — never recompute, never increment twice.
    existing = (
        await session.execute(
            select(IngresoConsecutivoContador).where(
                IngresoConsecutivoContador.uuid_sucursal == uuid_sucursal,
                IngresoConsecutivoContador.uuid_tipo_vehiculo == uuid_tipo_vehiculo,
                IngresoConsecutivoContador.last_event_uuid == source_event_uuid,
                IngresoConsecutivoContador.vigente_hasta.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _format_consecutivo(tipo_upper, existing.ultimo_consecutivo, source_event_uuid)

    # 2. SELECT FOR UPDATE on the vigente counter row (mirror step 2).
    #    Serializes concurrent POSTs on the same (sucursal, tipo).
    counter = (
        await session.execute(
            select(IngresoConsecutivoContador).where(
                IngresoConsecutivoContador.uuid_sucursal == uuid_sucursal,
                IngresoConsecutivoContador.uuid_tipo_vehiculo == uuid_tipo_vehiculo,
                IngresoConsecutivoContador.vigente_hasta.is_(None),
            ).with_for_update()
        )
    ).scalar_one_or_none()

    if counter is None:
        # 3a. FIRST INGRESO for this (sucursal, tipo) — INSERT counter row 1.
        new_counter = IngresoConsecutivoContador(
            uuid_sucursal=uuid_sucursal,
            uuid_tipo_vehiculo=uuid_tipo_vehiculo,
            ultimo_consecutivo=1,
            last_event_uuid=source_event_uuid,
            vigente_desde=datetime.now(UTC).replace(tzinfo=None),
            fecha_retencion_hasta=date.today() + relativedelta(years=5),  # DIAN retention
        )
        session.add(new_counter)
        await session.flush()  # materialise before format
        return _format_consecutivo(tipo_upper, 1, source_event_uuid)

    # 3b. SUBSEQUENT INGRESO — UPDATE counter (carve-out allows this).
    counter.ultimo_consecutivo = counter.ultimo_consecutivo + 1
    counter.last_event_uuid = source_event_uuid
    return _format_consecutivo(tipo_upper, counter.ultimo_consecutivo, source_event_uuid)


def _format_consecutivo(tipo_upper: str, n: int, source_uuid: uuid_lib.UUID) -> str:
    """<TIPO>-{n:06d}-{source.hex[:8]} — REQ-OPS-191 format."""
    return f"{tipo_upper}-{n:06d}-{source_uuid.hex[:8]}"
```

### 4.3 Idempotency contract

The function reads FIRST to detect retries keyed on `source_event_uuid` (mirroring `assign_consecutivo:97-108`). The caller pre-generates `source_event_uuid = new_uuid` in the handler so the `<uuid8>` suffix in the formatted string is deterministic across retries — same uuid → same suffix → same byte-identical string.

### 4.4 Locking

- `SELECT … FOR UPDATE` on the vigente counter row. Postgres serialises concurrent acquisition; the next concurrent transaction waits for the holder's commit/rollback. No deadlock risk because we acquire ONE lock per call and the helper commits alongside the Ingreso INSERT.
- Defense in depth: the partial UK on `prod.ingreso.consecutivo` rejects duplicate numbers at DB level if the helper ever races (e.g. two kiosko POSTs that both minted `BICI-000001-...` due to a fork).

### 4.5 Counter overflow

`ultimo_consecutivo` is bounded at 999999 by `CHECK (ultimo_consecutivo < 1000000)`. Realistic single-branch scale never approaches this, but if a counter hits 999999:
- The next `assign_ingreso_consecutivo` raises an exception that maps to `alerta tipo_alerta='consecutivo_ingreso_exhausted'` (operational alert; needs a manual reset flow, deferred per Q1).
- For PR-A, raise `ConsecutivoExhaustedError` from the helper and the handler maps to 503. Follow-up PR documents the alert + manual reset.

---

## 5. Handler Changes — `create_ingreso`

**File**: `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py`

The 11-step chain (lines 145-316) is modified at three steps + one new step. **No** step is removed; the order is locked by `tests/static/test_kd_forzado_in_handler.py`.

### 5.1 Step 2 REVISED — accept `placa=None` (REQ-OPS-194)

```python
# Step 2 REVISED:
# REQ-OPS-194: when placa is None, uuid_tipo_vehiculo MUST be supplied
# client-side (no-placa discriminator). V5 regex derivation is skipped.
uuid_tipo_vehiculo = payload.uuid_tipo_vehiculo
if uuid_tipo_vehiculo is None:
    if payload.placa is None:
        # Operator clicked "Sin placa" but didn't pick a tipo (UI bug).
        raise HTTPException(
            status_code=422,
            detail={"error": "tipo_vehiculo_requerido_sin_placa"},
            headers=no_store,
        )
    uuid_tipo_vehiculo = await detectar_tipo_vehiculo(session, payload.placa)
    if uuid_tipo_vehiculo is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "placa_formato_invalido",
                "formatos_aceptados": ["ABC123", "ABC12D"],
            },
            headers=no_store,
        )
```

### 5.2 Step 8 REVISED — skip V8 for `placa is None` (REQ-OPS-040 modified)

```python
# Step 8 REVISED:
# REQ-OPS-040 modified — skip existe_ingreso_activo when placa is None.
# For no-placa ingresos, duplicate detection is delegated to the
# partial UK on prod.ingreso.consecutivo (REQ-OPS-192, defense in depth).
if payload.placa is not None:
    uuid_activo = await existe_ingreso_activo(
        session, uuid_sucursal=target, placa=payload.placa
    )
    if uuid_activo is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "ingreso_activo_existente",
                "uuid_ingreso_existente": str(uuid_activo),
            },
            headers=no_store,
        )
```

### 5.3 NEW Step 8.5 — assign `consecutivo` (REQ-OPS-191)

```python
# NEW Step 8.5 (REQ-OPS-191):
# Pre-generate the Ingreso.uuid so the <uuid8> suffix is deterministic
# across retries (assign_consecutivo's idempotency anchor).
consecutivo: str | None = None
new_uuid: uuid_lib.UUID | None = None
if payload.placa is None:
    new_uuid = uuid_lib.uuid4()
    consecutivo = await assign_ingreso_consecutivo(
        session,
        uuid_sucursal=target,
        uuid_tipo_vehiculo=uuid_tipo_vehiculo,
        source_event_uuid=new_uuid,
    )
```

### 5.4 Step 9 REVISED — add `consecutivo` to `new_attrs`

```python
# Step 9 REVISED:
new_attrs = payload.model_dump(exclude_none=True, exclude={"forzado"})
new_attrs["uuid_tipo_vehiculo"] = uuid_tipo_vehiculo
new_attrs["uuid_sucursal"] = target
if consecutivo is not None and new_uuid is not None:
    new_attrs["consecutivo"] = consecutivo
    new_attrs["uuid"] = new_uuid  # pre-generated to match the <uuid8> suffix
new_row = await crear_ingreso_evento(
    session,
    actor_uuid=ctx.actor_uuid,
    new_attrs=new_attrs,
)
```

The `new_attrs["uuid"] = new_uuid` pre-assignment is supported by `record_event` (it respects caller-supplied PK when present in `new_attrs`); this guarantees the persisted row's UUID is the same one that was passed to `assign_ingreso_consecutivo` as `source_event_uuid`. **The `[L-E]` AST lock is preserved** — `consecutivo` is in `new_attrs` of an INSERT, not an UPDATE (`tests/static/test_no_write_after_insert.py`).

### 5.5 Step 11 REVISED — expose `consecutivo` in response

```python
# Step 11 REVISED:
apply_no_store_header(response)
await session.refresh(new_row)
base = IngresoRead.model_validate(new_row).model_dump()
return IngresoReadForzado(
    **base,
    tipo_entrada=tipo_entrada,
    forzado_en_creacion=bypass_reason is not None,
    motivo_forzado=motivo if bypass_reason else None,
    consecutivo=consecutivo,  # NEW (REQ-OPS-197)
)
```

### 5.6 Imports to add

```python
from ...repo.ingreso_consecutivo import assign_ingreso_consecutivo  # NEW
```

---

## 6. Pydantic Schema Changes

**File**: `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py`

### 6.1 `IngresoRead` — add `consecutivo`

```python
class IngresoRead(_Base):
    # ... existing 6 inherited + 6 business columns ...
    consecutivo: str | None = None  # NEW (REQ-OPS-197, REQ-OPS-192 nullable)
```

Pure additive — `extra='forbid'` (inherited from `_Base`) preserves wire compat for clients that don't read `consecutivo`; the field appears as `null` for legacy carro/moto rows.

### 6.2 `IngresoReadForzado` — add `consecutivo`

```python
class IngresoReadForzado(_Base):
    # ... existing 13 columns ...
    tipo_entrada: Literal["MENSUALIDAD", "ROTACION"]
    forzado_en_creacion: bool = False
    motivo_forzado: str | None = None
    consecutivo: str | None = None  # NEW (REQ-OPS-197)
```

### 6.3 `IngresoCreate` / `IngresoCreateForzado` — no wire-shape change required

Both already declare `placa: str | None = None` and `uuid_tipo_vehiculo: uuid_lib.UUID | None = None` (REQ-OPS-194). The discriminated union is implemented on the **frontend** (Zod) — the backend accepts any shape that the Pydantic schema parses (the legacy shape with `placa=string` + `uuid_tipo_vehiculo=string`, and the new shape with `placa=null` + `uuid_tipo_vehiculo=uuid` both pass).

`consecutivo` is server-generated; client MUST NOT send it. `IngresoCreate` / `IngresoCreateForzado` keep `extra='forbid'` so a client attempt to inject `consecutivo` is rejected with 422.

### 6.4 `SalidaReadForzado` — no change required

The salida handler reads the parent `Ingreso.consecutivo` via JOIN if needed (`ingreso.consecutivo`) but does NOT echo it in the salida response. The salida's identifying field is `uuid_ingreso` (the QR + the operator's reference); the tiquete de salida already carries `Placa:` (from the parent ingreso's `placa` column or, for no-placa, would carry `Identificación:` — but that's a forward F13.x UI follow-up, out of PR-A's scope).

---

## 7. Frontend Changes

### 7.1 Discriminated-union Zod schema (REQ-OPS-194)

**File**: `apps/electron-sucursal/src/features/operacion/lib/ingresoApi.ts` (MODIFY, ~30 LOC delta)

```typescript
// REQ-OPS-194: discriminated union on placa_presente.
// Discriminator is the BOOLEAN literal itself (Zod's `discriminatedUnion`
// accepts `z.literal(true)` / `z.literal(false)` discriminators).
const placaConPlacaSchema = z.object({
  placa_presente: z.literal(true),
  placa: z.string().regex(/^[A-Z]{3}[0-9]{3}$|^[A-Z]{3}[0-9]{2}[A-Z]$/),
  uuid_tipo_vehiculo: z.string().uuid().optional(),
  observaciones: z.string().max(500).optional(),
  forzado: z.boolean().optional(),
});

const placaSinPlacaSchema = z.object({
  placa_presente: z.literal(false),
  placa: z.null(),  // explicit (Zod forbids undefined in literals)
  uuid_tipo_vehiculo: z.string().uuid(),  // REQUIRED
  observaciones: z.string().max(500).optional(),
  forzado: z.boolean().optional(),
});

export const PostIngresoPayloadSchema = z.discriminatedUnion('placa_presente', [
  placaConPlacaSchema,
  placaSinPlacaSchema,
]);
export type PostIngresoPayload = z.infer<typeof PostIngresoPayloadSchema>;

export const PostIngresoResponseSchema = z.object({
  uuid_ingreso: z.string().uuid(),
  tipo_entrada: z.enum(['MENSUALIDAD', 'ROTACION']),
  uuid_subscripcion_cliente: z.string().uuid().nullable(),
  consecutivo: z.string().nullable(),  // NEW (REQ-OPS-197)
});
export type PostIngresoResponse = z.infer<typeof PostIngresoResponseSchema>;
```

The `consecutivo` field is server-generated and read back; `payload.consecutivo` on the request is NOT supported (legacy clients sending `consecutivo` in `placaConPlacaSchema` are rejected by `extra='forbid'` semantics inherited from the existing schema — verify on apply).

### 7.2 New hook `useTiposVehiculoSinPlaca`

**File**: `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculoSinPlaca.ts` (NEW, ~25 LOC)

```typescript
/** Filter useTiposVehiculo() to tipos that have NO placa regex (bici, patineta). */
export function useTiposVehiculoSinPlaca(): UseTiposVehiculoReturn {
  const full = useTiposVehiculo();
  // Filter on the F4.1 sentinel-aware fallback (HARDCODED_CATALOG only has
  // carro/moto — when the API is up, the catalog includes bici/patineta;
  // when down, no bici/patineta is shown, which is the documented
  // degraded UX per DEC-F4.1-05).
  return {
    ...full,
    tipos: full.tipos.filter((t) => t.tipo === 'bicicleta' || t.tipo === 'patineta'),
  };
}
```

The `isFromFallback` flag from `useTiposVehiculo()` is propagated as-is. When the catalog is degraded, the filter is empty, and `<IngresoSinPlacaPanel>` renders the disabled-state message (REQ-OPS-196 scenario 2).

### 7.3 New component `<IngresoSinPlacaPanel>`

**File**: `apps/electron-sucursal/src/features/operacion/components/IngresoSinPlacaPanel.tsx` (NEW, ~120 LOC)

**Props**:

```typescript
export interface IngresoSinPlacaPanelProps {
  onSuccess: (response: PostIngresoResponse) => void;
  disabled?: boolean;
}
```

**Internal structure**:
- `useTiposVehiculoSinPlaca()` for the available tipos list.
- Empty-state branch: `tipos.length === 0` → render `<EmptyState>` with message "Esta sucursal no admite ingresos sin placa" + a tooltip explaining the catalog is degraded. **No** "Generar ingreso" button rendered.
- Populated branch: `<Select>` (shadcn) bound to RHF + Zod (`placaSinPlacaSchema`); `<Button>` "Generar ingreso" submits `postIngreso({ placa_presente: false, placa: null, uuid_tipo_vehiculo: selectedUuid })`.
- `<FormMessage>` renders Zod errors inline (accessibility — `aria-describedby`).
- onSuccess → invoke the parent's `onSuccess(response)` which opens `<TiqueteModal>` with `consecutivo={response.consecutivo}`.

**Accessibility** (R5 mitigation, WCAG 2.1 AA): shadcn `<Select>` is keyboard-navigable out of the box; the submit button is `type="submit"` with explicit `aria-label`; the empty state uses `role="status"`.

### 7.4 New wrapper `<TipoIngresoToggle>` (optional but recommended — R8 mitigation)

**File**: `apps/electron-sucursal/src/features/operacion/components/TipoIngresoToggle.tsx` (NEW, ~80 LOC)

Encapsulates the two-buttons-side-by-side layout to DRY-up `Principal.tsx` and `IngresoPanel.tsx`:

```typescript
export interface TipoIngresoToggleProps {
  renderConPlaca: () => ReactNode;
  renderSinPlaca: () => ReactNode;
}

export function TipoIngresoToggle({ renderConPlaca, renderSinPlaca }: TipoIngresoToggleProps) {
  const [variant, setVariant] = useState<'con-placa' | 'sin-placa'>('con-placa');
  return (
    <div className="space-y-4">
      <div role="group" aria-label="Tipo de ingreso" className="flex gap-2">
        <Button
          type="button"
          variant={variant === 'con-placa' ? 'default' : 'outline'}
          aria-pressed={variant === 'con-placa'}
          onClick={() => setVariant('con-placa')}
        >
          Con placa
        </Button>
        <Button
          type="button"
          variant={variant === 'sin-placa' ? 'default' : 'outline'}
          aria-pressed={variant === 'sin-placa'}
          aria-describedby="sin-placa-tooltip"
          onClick={() => setVariant('sin-placa')}
        >
          Sin placa
        </Button>
      </div>
      {variant === 'con-placa' ? renderConPlaca() : renderSinPlaca()}
    </div>
  );
}
```

**R8 mitigation rationale**: both `Principal.tsx` and `IngresoPanel.tsx` render the same dual-flow; factoring this into one component keeps the diff small and the review boundary tight (PR-B total ~455 LOC budget).

### 7.5 `Principal.tsx` and `IngresoPanel.tsx` updates

Replace the direct `<PlacaInput>` with `<TipoIngresoToggle>`:

```tsx
<TipoIngresoToggle
  renderConPlaca={() => (
    <PlacaInput onValidSubmit={handlePlacaSubmit} disabled={submitting} />
  )}
  renderSinPlaca={() => (
    <IngresoSinPlacaPanel onSuccess={handleIngresoSinPlacaSuccess} disabled={submitting} />
  )}
/>
```

After each successful submit (con placa or sin placa), the parent resets the variant to `'con-placa'` (default) via a `key` prop or by lifting state up. **Simplest**: the toggle owns its own state; on each submit, the parent does NOT reset the toggle (the operator sees the same panel they just used). After they dismiss `<TiqueteModal>` (`onSiguiente`), the next mount re-initializes the toggle to default — handled by remounting via `key="fresh"` on `<TipoIngresoToggle>` after `handleSiguiente`.

### 7.6 `<TiqueteModal>` — `consecutivo` prop

**File**: `apps/electron-sucursal/src/features/operacion/components/TiqueteModal.tsx` (MODIFY, +15 LOC)

```typescript
export interface TiqueteModalProps {
  // ... existing ...
  consecutivo?: string | null;  // NEW (REQ-OPS-197)
}

// In the body:
{consecutivo ? (
  <p>
    <span className="font-medium">
      {t('tiquete_identificacion_label', { defaultValue: 'Identificación' })}:
    </span>{' '}
    <code className="rounded bg-muted px-1 py-0.5 text-xs">{consecutivo}</code>
  </p>
) : null}
{/* Folio always rendered for QR + audit trail */}
<p>
  <span className="font-medium">
    {t('tiquete_entrada_folio', { defaultValue: 'Folio' })}:
  </span>{' '}
  <code className="rounded bg-muted px-1 py-0.5 text-xs">{uuid_ingreso}</code>
</p>
```

The `Folio:` line is ALWAYS rendered (it carries `uuid_ingreso` for the QR payload per DEC-SUC-26 + the audit trail per AGENTS.md §1). The `Identificación:` line replaces the visible `Placa:` line for no-placa ingresos.

### 7.7 `useIngresoActivo` for the no-placa path

`useIngresoActivo(placa)` (`features/operacion/hooks/useIngresoActivo.ts`) takes `placa` and filters by it. For no-placa ingresos there is no placa to filter on; the hook is NOT called. The doble-ingreso check for no-placa is delegated to the backend's `asyncio.gather` race + partial UK (R1 mitigation) — no client-side path-1 filter needed.

### 7.8 i18n keys (REQ-OPS-194 / 195 / 196 / 197)

**File**: `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json`

```json
{
  "ingreso_sin_placa_cta": "Sin placa",
  "ingreso_sin_placa_selector_label": "Tipo de vehículo",
  "ingreso_sin_placa_tipo_bicicleta": "Bicicleta",
  "ingreso_sin_placa_tipo_patineta": "Patineta",
  "ingreso_sin_placa_generar_boton": "Generar ingreso",
  "ingreso_sin_placa_exito": "Ingreso registrado: {{consecutivo}}",
  "ingreso_sin_placa_empty_state": "Esta sucursal no admite ingresos sin placa",
  "tiquete_identificacion_label": "Identificación"
}
```

---

## 8. Ticket Rendering Changes (REQ-OPS-197)

### 8.1 `escposTemplates.ts` — discriminated-union `entradaPayloadSchema`

**File**: `apps/electron-sucursal/src/lib/print/escposTemplates.ts` (MODIFY, ~30 LOC delta)

```typescript
const entradaConPlacaSchema = z.object({
  variant: z.literal('con-placa'),
  placa: placaSchema,  // existing F6.2 strict
  fechaEntrada: z.string().datetime({ offset: true }),
  qrDataUrl: z.string(),
  logoDataUrl: z.string(),
  empresa: empresaSchema,
  operario: z.string().min(1),
  tarifaAplicada: z.number().nonnegative(),
  horarioAtencion: z.string().min(1),
  polizaRC: z.string().optional(),
  folio: z.string().uuid(),
  observaciones: z.string().optional(),
  esMensualidad: z.boolean().optional(),
  sucursal: sucursalSchema,
});

const entradaConConsecutivoSchema = z.object({
  variant: z.literal('con-consecutivo'),
  placa: z.null(),  // explicit null (Zod literal semantics)
  consecutivo: z.string().regex(/^[A-Z]{3,12}-[0-9]{6}-[0-9a-f]{8}$/),
  fechaEntrada: z.string().datetime({ offset: true }),
  qrDataUrl: z.string(),
  logoDataUrl: z.string(),
  empresa: empresaSchema,
  operario: z.string().min(1),
  tarifaAplicada: z.number().nonnegative(),
  horarioAtencion: z.string().min(1),
  polizaRC: z.string().optional(),
  folio: z.string().uuid(),
  observaciones: z.string().optional(),
  esMensualidad: z.boolean().optional(),  // always false in practice (no subscripcion for bici)
  sucursal: sucursalSchema,
});

export const entradaPayloadSchema = z.discriminatedUnion('variant', [
  entradaConPlacaSchema,
  entradaConConsecutivoSchema,
]);
export type EntradaPayload = z.infer<typeof entradaPayloadSchema>;
```

The `consecutivo` regex is the canonical format enforcer — backend emits, frontend validates. Other tiquete schemas (`salida`, `salida-mensualidad`, `recibo_pago`, `arqueo`) are unchanged: salida / salida-mensualidad / recibo_pago all read from a parent ingreso that has a `placa` (or will read `consecutivo` via JOIN in a forward F13.x — not in PR-B's scope).

### 8.2 `escposBuilder.ts` — conditional `Placa:` vs `Identificación:` (REQ-OPS-197)

**File**: `apps/electron-sucursal/src/lib/print/escposBuilder.ts` (MODIFY, +10 LOC)

```typescript
function buildEntradaBody(payload: EntradaPayload): Buffer {
  // ... existing 17-field layout up to the 12th conceptual field ...
  if (payload.variant === 'con-placa') {
    lines.push(utf8(`Placa: ${payload.placa}\n`));        // doceavo (legacy)
  } else {
    // payload.variant === 'con-consecutivo'
    lines.push(utf8(`Identificación: ${payload.consecutivo}\n`));  // doceavo (REQ-OPS-197)
  }
  lines.push(utf8(`Horario: ${payload.horarioAtencion}\n`));
  // ... rest unchanged ...
}
```

The byte sequence at the 12th conceptual field changes per variant:
- `con-placa`: `Placa: ABC123\n` (existing regression).
- `con-consecutivo`: `Identificación: BICI-000001-3f8a1b2c\n` (REQ-OPS-197 scenario 2).

### 8.3 `fallbackBrowser.ts` — mirror change (REQ-OPS-197)

**File**: `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` (MODIFY, +5 LOC)

```typescript
if (payload.variant === 'con-placa') {
  html.push(`<p>Placa: ${escapeHtml(payload.placa)}</p>`);
} else {
  html.push(`<p>Identificación: ${escapeHtml(payload.consecutivo)}</p>`);
}
```

---

## 9. File Changes Summary

| File | Action | LOC | Notes |
|---|---|---:|---|
| `backend/packages/parkos_core/migrations/versions/0042_add_ingreso_consecutivo.py` | NEW | ~80 | ADD COLUMN + partial UK + counter table + REVOKE + trigger + sync exclusion |
| `backend/packages/parkos_core/src/parkos_core/models/L_E/ingreso.py` | MODIFY | +5 | `consecutivo: Mapped[str \| None]` column |
| `backend/packages/parkos_core/src/parkos_core/models/A/ingreso_consecutivo_contador.py` | NEW | ~50 | ORM for 51st table |
| `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` | MODIFY | +6 | `consecutivo: str \| None = None` on `IngresoRead` and `IngresoReadForzado` |
| `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` | MODIFY | +50 | Steps 2/8/9/11 revised, new Step 8.5, `assign_ingreso_consecutivo` import |
| `backend/packages/parkos_core/src/parkos_core/repo/ingreso_consecutivo.py` | NEW | ~150 | Helper + `ConsecutivoExhaustedError` |
| `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py` | MODIFY | +3 | Re-export `assign_ingreso_consecutivo` (R-A5 precedent) |
| `apps/electron-sucursal/src/features/operacion/lib/ingresoApi.ts` | MODIFY | ~30 delta | Discriminated union Zod + `consecutivo` on response |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculoSinPlaca.ts` | NEW | ~25 | Filter hook |
| `apps/electron-sucursal/src/features/operacion/components/IngresoSinPlacaPanel.tsx` | NEW | ~120 | RHF + Zod + Select + Button |
| `apps/electron-sucursal/src/features/operacion/components/TipoIngresoToggle.tsx` | NEW | ~80 | Two-button wrapper |
| `apps/electron-sucursal/src/features/operacion/pages/Principal.tsx` | MODIFY | +20 | Replace `<PlacaInput>` with `<TipoIngresoToggle>` |
| `apps/electron-sucursal/src/features/operacion/components/IngresoPanel.tsx` | MODIFY | +20 | Same as Principal |
| `apps/electron-sucursal/src/features/operacion/components/TiqueteModal.tsx` | MODIFY | +15 | `consecutivo` prop + `Identificación:` line |
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | MODIFY | ~30 delta | Discriminated union `entradaPayloadSchema` |
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | MODIFY | +10 | Conditional `Placa:` / `Identificación:` line |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` | MODIFY | +5 | Mirror change in HTML render |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | MODIFY | +10 | 8 new keys |
| `backend/tests/unit/test_operacion_ingresos_validaciones.py` | MODIFY | +60 | 4 new scenarios (T1..T4: no-placa accept/reject + V8 skip + 23505) |
| `backend/tests/unit/test_repo_ingreso_consecutivo.py` | NEW | ~150 | 8 unit scenarios (T7..T14) |
| `backend/tests/integration/test_consecutivo_concurrent_posts.py` | NEW | ~80 | `asyncio.gather` race-condition lock |
| `backend/tests/integration/test_ocupacion_view.py` | MODIFY | +30 | MV regression (no-placa INSERT counted) |
| `apps/electron-sucursal/src/features/operacion/lib/__tests__/ingresoApi.test.ts` | NEW | ~50 | 4 discriminated-union scenarios |
| `apps/electron-sucursal/src/features/catalogos/hooks/__tests__/useTiposVehiculoSinPlaca.test.tsx` | NEW | ~30 | Filter logic |
| `apps/electron-sucursal/src/features/operacion/components/__tests__/IngresoSinPlacaPanel.test.tsx` | NEW | ~50 | 3 scenarios (render / submit / empty state) |
| `apps/electron-sucursal/src/features/operacion/components/__tests__/TipoIngresoToggle.test.tsx` | NEW | ~30 | 2 scenarios (default / switch) |
| `apps/electron-sucursal/src/features/operacion/components/__tests__/TiqueteModal.test.tsx` | NEW | ~50 | 2 scenarios (con-placa / sin-placa rendering) |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts` | MODIFY | +30 | byte-fixture for `con-consecutivo` |
| `apps/electron-sucursal/src/lib/print/__tests__/fallbackBrowser.entrada.test.ts` | MODIFY | +20 | HTML render for `con-consecutivo` |
| `apps/electron-sucursal/src/features/operacion/components/__tests__/Principal.test.tsx` | NEW (gap G12) | ~40 | Mount with toggle, click sin-placa, submit |

---

## 10. PR Split — Chained (gitflow to `dev`)

### 10.1 PR-A — Backend (~600 LOC)

**Branch**: `feature/hu-ingreso-sin-placa-backend`

**Merge target**: `origin/dev` (gitflow strict per AGENTS.md §12).

**Strategy**: single PR; pre-flight `alembic upgrade --sql` + REVOKE/trigger verifier from `infra/docker/entrypoint.sh::pg_trigger_check` at boot.

**Commits** (work-unit-commits — `work-unit-commits` skill):

1. `feat(backend): add ingreso.consecutivo column + counter table + REVOKE/trigger (HU-F4.1-NN)`
   - Migration `0042_add_ingreso_consecutivo.py`
   - ORM `models/L_E/ingreso.py` + `models/A/ingreso_consecutivo_contador.py`
   - Pre-flight `alembic upgrade --sql 0042_add_ingreso_consecutivo`
2. `feat(backend): assign_ingreso_consecutivo helper + Step 8.5 integration`
   - `repo/ingreso_consecutivo.py` (NEW)
   - `api/v1/operacion.py` Steps 2/8/8.5/9/11 modified
   - `schemas/operacion.py` `consecutivo` on Read + ReadForzado
3. `test(backend): 8 unit scenarios + concurrent integration for assign_ingreso_consecutivo`
   - `tests/unit/test_repo_ingreso_consecutivo.py` (NEW)
   - `tests/integration/test_consecutivo_concurrent_posts.py` (NEW)
   - `tests/unit/test_operacion_ingresos_validaciones.py` (4 new scenarios)
   - `tests/integration/test_ocupacion_view.py` (MV regression)

### 10.2 PR-B — Frontend (~455 LOC)

**Branch**: `feature/hu-ingreso-sin-placa-frontend`

**Merge target**: `origin/dev` (after PR-A merged).

**Dependency**: PR-B uses the response shape `consecutivo` added by PR-A. PR-B may begin development in parallel with PR-A's review, but MUST NOT merge before PR-A merges to `dev`.

**If PR-B exceeds 400 LOC during implementation**: split into **PR-B1** (Zod + Panel + Hook) and **PR-B2** (Print layer + TiqueteModal + tests). Total still ~455 LOC.

**Commits**:

1. `feat(frontend): discriminated-union IngresoPayload (con-placa | con-consecutivo)`
   - `lib/ingresoApi.ts` Zod discriminated union
   - `__tests__/ingresoApi.test.ts` (NEW)
2. `feat(frontend): useTiposVehiculoSinPlaca hook + IngresoSinPlacaPanel + TipoIngresoToggle`
   - `hooks/useTiposVehiculoSinPlaca.ts` (NEW) + tests
   - `components/IngresoSinPlacaPanel.tsx` (NEW) + tests
   - `components/TipoIngresoToggle.tsx` (NEW) + tests
   - `pages/Principal.tsx` + `components/IngresoPanel.tsx` (toggle mount)
3. `feat(frontend): render Identificación in tiquete for consecutivo variant`
   - `lib/print/escposTemplates.ts` discriminated union
   - `lib/print/escposBuilder.ts` + `fallbackBrowser.ts` conditional line
   - `components/TiqueteModal.tsx` `consecutivo` prop
   - `renderer/i18n/locales/operacion.json` +8 keys
   - byte-fixture tests (`escposBuilder.entrada.test.ts`, `fallbackBrowser.entrada.test.ts`)
   - `__tests__/TiqueteModal.test.tsx` (NEW)
   - `__tests__/Principal.test.tsx` (NEW — closes gap G12)

---

## 11. Migration / Rollout

### 11.1 Pre-flight (mandatory per `config.yaml rules.tasks`)

```bash
cd backend/packages/parkos_core
uv run alembic upgrade --sql 0042_add_ingreso_consecutivo > /tmp/0042.sql
# Visual review of the SQL — confirm ADD COLUMN is metadata-only,
# CREATE TABLE has REVOKE + trigger in same script, partial UK is
# correct, sync-trigger exclusion is present.
```

### 11.2 Apply to dev

```bash
uv run alembic upgrade head
# Boot api_sucursal — entrypoint runs pg_trigger_check on REVOKE/trigger.
```

### 11.3 Deploy

The migration is included in `ghcr.io/easypunto/parkos:vX.Y.Z`; `infra/docker/entrypoint.sh` orchestrates: `wait-postgres → rol_app precheck → alembic upgrade head → REVOKE/trigger verifier → exec CMD`.

### 11.4 Rollback

**PR-A rollback** (full):
```bash
uv run alembic downgrade 0041_seed_configuracion_tolerancias
# Drops: prod.ingreso.consecutivo column + partial UK
# Drops: prod.ingreso_consecutivo_contador table + REVOKE + trigger
```

**PR-B rollback**: `git revert <merge-commit>` of PR-B (independent of PR-A).

**Atomic rollback**: each PR is independently revertible. Reverting PR-B with PR-A still merged leaves the backend accepting `consecutivo` responses that the frontend cannot display — acceptable degraded state until PR-B lands.

### 11.5 No data backfill required

Existing carro/moto rows have `consecutivo = NULL` post-migration. The partial UK only applies to NOT NULL — no row rewrite. The frontend `PostIngresoResponseSchema.consecutivo: z.string().nullable()` handles legacy rows gracefully.

---

## 12. Testing Strategy

### 12.1 Backend unit tests

| File | Scenarios | What they verify |
|---|---|---|
| `tests/unit/test_repo_ingreso_consecutivo.py` (NEW) | T1..T8 | (T1) first ingreso for `(X, bicicleta)` → `ultimo_consecutivo=1`, formatted `BICI-000001-<uuid8>`. (T2) monotonic increment. (T3) cross-tipo isolation (`PATIN-...` not affected by `BICI-...` counter). (T4) cross-sucursal isolation. (T5) idempotency: same `source_event_uuid` returns same value across 5 retries. (T6) format `<TIPO>-NNNNNN-<uuid8>` for n=1..999. (T7) REVOKE: `UPDATE prod.ingreso_consecutivo_contador SET uuid_sucursal=...` from `rol_app` raises `insufficient_privilege`. (T8) trigger carve-out: `UPDATE prod.ingreso_consecutivo_contador SET ultimo_consecutivo=ultimo_consecutivo+1, last_event_uuid=...` from `rol_app` SUCCEEDS (only carve-out columns change). |
| `tests/unit/test_operacion_ingresos_validaciones.py` (modify) | T1..T4 | (T1) POST `placa=null + uuid_tipo_vehiculo=bici` → 201 with `consecutivo`. (T2) POST `placa=null + uuid_tipo_vehiculo=unknown_uuid` → 422 `tipo_vehiculo_invalido`. (T3) POST `placa='ABC123' + uuid_tipo_vehiculo=null` → 201 (legacy path). (T4) V8 skip: POST `placa=null + uuid_tipo_vehiculo=bici` does NOT call `existe_ingreso_activo` (mock assertion). |
| `tests/unit/test_operacion_ingresos_kd_forzado.py` (modify) | T5 | bici + `cupo_agotado=True` + `forzado=true` + motivo ≥10 chars → 201 + `alerta tipo_alerta='cupo_agotado_forzado'` + `consecutivo` persisted. |
| `tests/static/test_no_write_after_insert.py` (no change) | — | AST lock: confirms `consecutivo` is INSERT-only, never UPDATEd. |

### 12.2 Backend integration tests

| File | Scenarios | What they verify |
|---|---|---|
| `tests/integration/test_consecutivo_concurrent_posts.py` (NEW) | T1 | `asyncio.gather` of 10 concurrent POSTs for the same `(X, bicicleta)` → 10 distinct consecutivos (`BICI-000001-...` through `BICI-000010-...`). |
| `tests/integration/test_consecutivo_unique_uk.py` (NEW) | T2 | Concurrent attempts to INSERT two `prod.ingreso` rows with the same `(sucursal, tipo, consecutivo)` → second INSERT raises `23505 unique_violation` (partial UK defense in depth). |
| `tests/integration/test_ocupacion_view.py` (modify) | T3..T4 | (T3) no-placa INSERT increments `mv_ocupacion_diaria.activos` for `(sucursal, 'bicicleta')`. (T4) regression: carro/moto MV count unchanged. |
| `tests/integration/test_hash_chain_no_placa.py` (NEW) | T5 | After a no-placa INSERT, `log_transaccional.datos_nuevos` carries `consecutivo` (audit-first invariant preserved). |

### 12.3 Frontend unit tests

| File | Scenarios | What they verify |
|---|---|---|
| `apps/electron-sucursal/src/features/operacion/lib/__tests__/ingresoApi.test.ts` (NEW) | T1..T4 | (T1) con-placa payload parses. (T2) sin-placa payload parses. (T3) mixed payload rejected with ZodError on discriminator. (T4) response parses `consecutivo: "BICI-000001-3f8a1b2c"`. |
| `apps/electron-sucursal/src/features/catalogos/hooks/__tests__/useTiposVehiculoSinPlaca.test.tsx` (NEW) | T1..T3 | (T1) returns only bici/patineta. (T2) empty state when fallback active (HARDCODED_CATALOG has no bici/patineta). (T3) `isFromFallback` propagated. |
| `apps/electron-sucursal/src/features/operacion/components/__tests__/IngresoSinPlacaPanel.test.tsx` (NEW) | T1..T3 | (T1) renders with tipos. (T2) submits via `postIngreso` with `placa_presente: false`. (T3) empty state: no submit button. |
| `apps/electron-sucursal/src/features/operacion/components/__tests__/TipoIngresoToggle.test.tsx` (NEW) | T1..T2 | (T1) default `con-placa` rendered. (T2) click swaps variant. |
| `apps/electron-sucursal/src/features/operacion/components/__tests__/TiqueteModal.test.tsx` (NEW) | T1..T2 | (T1) `consecutivo` prop renders `Identificación:` line. (T2) `consecutivo=null` hides `Identificación:` line but keeps `Folio:`. |
| `apps/electron-sucursal/src/features/operacion/pages/__tests__/Principal.test.tsx` (NEW — closes gap G12) | T1..T3 | (T1) mounts with toggle. (T2) click "Sin placa" → renders `<IngresoSinPlacaPanel>`. (T3) click "Con placa" → renders `<PlacaInput>`. |

### 12.4 Byte-fixture tests (REQ-OPS-197 verification)

| File | Scenarios | What they verify |
|---|---|---|
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts` (modify) | T1..T3 | (T1) `con-placa` payload → byte sequence contains `Placa: ABC123\n` at the 12th conceptual field. (T2) `con-consecutivo` payload → byte sequence contains `Identificación: BICI-000001-3f8a1b2c\n` at the same field. (T3) regression: existing `con-placa` fixture still passes byte-identical. |
| `apps/electron-sucursal/src/lib/print/__tests__/fallbackBrowser.entrada.test.ts` (modify) | T1..T2 | (T1) `con-consecutivo` payload → HTML contains `<p>Identificación: ...</p>`. (T2) regression: `con-placa` still passes. |

### 12.5 E2E (deferred per F.6 sandbox precedent)

Playwright spec `apps/electron-sucursal/e2e/ingreso-sin-placa.spec.ts` (deferred — no exercisable UI in sandbox F.6). Byte-fixture + component test coverage is the verification surface for PR-A/PR-B.

---

## 13. Threat Matrix (N/A — no new routing / shell / subprocess / VCS automation)

This change does NOT introduce new routing decisions, shell subprocesses, executable-file classification, or VCS/PR automation. The existing FastAPI routes (`POST /operacion/ingresos`), ORM write path (`record_event`), Alembic migration machinery, and React renderer patterns are reused as-is. Per the sdd-design skill §Step 2a, the threat matrix is **not applicable** — recorded here for the auditor's review.

The risks below (R1..R11) are application-domain risks (architectural, data-integrity, UX), not threat-matrix risks.

---

## 14. Risks and Mitigations

| ID | Severity | Risk | Mitigation |
|---|---|---|---|
| **R1** | HIGH | Race condition between 2+ concurrent POSTs for the same `(sucursal, tipo)` mint the same `consecutivo`. | (a) `assign_ingreso_consecutivo` uses `SELECT … FOR UPDATE` on the counter row (REQ-OPS-191). (b) Defense in depth: partial UK `WHERE consecutivo IS NOT NULL` on `prod.ingreso` rejects duplicate consecutivos at DB level (REQ-OPS-192). (c) Integration test T1 (`asyncio.gather` of 10 concurrent POSTs) verifies no collision. |
| **R2** | MED | Legacy carro/moto rows have `consecutivo = NULL` post-migration. | Column is nullable. UK is partial (`WHERE consecutivo IS NOT NULL`). Frontend `consecutivo: z.string().nullable()` reads `null` for legacy rows. (REQ-OPS-192 scenario 1.) |
| **R3** | LOW | DIAN `consecutivo` confusion (`prod.factura_electronica.consecutivo` vs `prod.ingreso.consecutivo`). | DEC-INCOME-01 (proposal §4) — explicit naming + table separation + format difference (`<TIPO>-NNNNNN-<uuid8>` vs DIAN range-gated integer). No code change needed; document in the spec. |
| **R4** | LOW | AST walk `test_no_write_after_insert.py` rejects UPDATE/DELETE on `[L-E]`. | `consecutivo` is INSERT-only; assigned in `new_attrs` BEFORE `crear_ingreso_evento` (Step 9). No UPDATE path. AC-11 verifies. |
| **R5** | MED | `<IngresoSinPlacaPanel>` UX divergence from `<PlacaInput>` confuses operators. | (a) "Con placa" visually dominant (default `<Button variant="default">` shadcn); "Sin placa" secondary (`variant="outline"`). (b) Tooltip on "Sin placa" via `aria-describedby`. (c) Onboarding runbook update (deferred to v2). |
| **R6** | MED | `ingreso_consecutivo_contador` is the 51st table — out of `bootstrap-monorepo-foundation` scope. | Precedent `idempotency_keys` (50th, mitigated by PR7). `[A]` with REVOKE + `BEFORE UPDATE OR DELETE` trigger (carve-out for `ultimo_consecutivo` + `last_event_uuid`) + `fecha_retencion_hasta` 5y DIAN retention in SAME migration per `config.yaml rules.tasks`. |
| **R7** | LOW | Counter exhaustion (`ultimo_consecutivo >= 1000000`). | `CHECK (ultimo_consecutivo < 1000000)` constraint. Helper raises `ConsecutivoExhaustedError` → handler maps to 503. Forward alert `tipo_alerta='consecutivo_ingreso_exhausted'` is operational follow-up (deferred). |
| **R8** | LOW | `Principal.tsx` and `IngresoPanel.tsx` are duplicate-shaped. | (a) Factor `<TipoIngresoToggle>` wrapper (REQ-OPS-195). (b) Both updated in PR-B same PR (~20 LOC each). |
| **R9** | LOW | `sync_queue` recursion if sync trigger misconfigured. | Migration includes `IF TG_TABLE_NAME = 'ingreso_consecutivo_contador' THEN RETURN NULL` in `fn_enqueue_sync_catalog` (AGENTS.md precedent for `sync_queue` exclusion). Counter never propagates `branch_to_cloud`. |
| **R10** | LOW | `mv_ocupacion_diaria` 10s polling latency (stale cupo momentarily). | Already-accepted per DEC-SUC-11; V2 `cupo_agotado` reads same MV, so race is symmetric. No new mitigation. |
| **R11** | LOW | Idempotency-Key migration: F6.1 payload (`placa='ABC123'`) hashes differently from F6.2 payload (`placa=null`). | Operator retry window ~5s acceptable; documented as known migration cost (proposal §6 Q7). No backward-compat shim — adds complexity for a 5-second window. |
| **R12** | LOW | `assign_ingreso_consecutivo` re-entrancy via nested transactions (e.g. handler calls another helper that triggers another `assign`). | Helper reads FIRST, locks SECOND — re-entry from same TX would deadlock on the row lock. The only call site is `create_ingreso` Step 8.5, which has no nested helper that re-enters. Documented in helper docstring. |
| **R13** | LOW | Migration `0042` runs against a branch DB that already has no `prod.idempotency_keys` (very early bootstrap) — REVOKE references unknown role. | REVOKE is `IF EXISTS`-safe in modern PG; if the role is missing, the statement is a no-op. Idempotent on replays. |

---

## 15. Open Questions (resolved in this design)

| ID | Question | Resolution | Reference |
|---|---|---|---|
| Q1 | Reset semantics for `consecutivo`? | **Monotonic forever** (no reset). | Proposal §6 Q1, Exploration §Open questions 1. |
| Q2 | Source of `<uuid8>` suffix? | `source_event_uuid.hex[:8]` where `source_event_uuid = Ingreso.uuid` (pre-generated). | Proposal §6 Q2. |
| Q3 | Tiquete label? | **`Identificación:`** (operator-facing per DEC-SUC-26; field name stays `consecutivo`). | Proposal §6 Q3, REQ-OPS-197. |
| Q4 | Frontend TipoSelect source? | **NEW hook `useTiposVehiculoSinPlaca()`** (single responsibility per F3.3 `useSesionActiva` precedent). | Proposal §6 Q4, REQ-OPS-196. |
| Q5 | Layout? | **Two `<Button>` side-by-side** (direct read of "two buttons separated"; tabs/cards rejected). | Proposal §6 Q5, REQ-OPS-195. |
| Q6 | `<IngresoSinPlacaPanel>` file location? | `components/IngresoSinPlacaPanel.tsx` (peer of `PlacaInput`). | Proposal §6 Q6. |
| Q7 | Idempotency-Key migration risk? | **Accept** (5s retry window). | Proposal §6 Q7, R11. |
| Q8 | UX: tipo before/after click? | **Click → modal-pattern panel** (simmetry with `<ForzarIngresoModal>`, `<TiqueteModal>`). | Proposal §6 Q8, REQ-OPS-196 (inline RHF panel inside `<TipoIngresoToggle>`). |
| Q9 | Cupo agotado UX? | **Reuse `<ForzarIngresoModal>`** (no new modal). | Proposal §6 Q9, REQ-OPS-198. |
| Q10 | Sync replication? | **Yes** — cloud preserves branch-assigned verbatim. `record_event` flows the column automatically. | Proposal §6 Q10, R-A5 in AGENTS.md. |
| Q11 | Salida flow for bici/patineta? | **Same salida handler** (already reads by `uuid_ingreso`, JOIN carries `consecutivo`). UX follow-up for operator-side identification at exit is F13.x (forward). | Proposal §6 Q11. |

---

## 16. Decisions Locked

| ID | Decision | Rationale |
|---|---|---|
| **DEC-INCOME-01** (proposal §4) | `prod.ingreso.consecutivo` is the parking-lot identifier for bici/patineta; it is NOT a DIAN invoice number. | Distinct tables, distinct UKs, distinct formats, distinct lifecycles. The prefijo `BICI-` / `PATIN-` makes the distinction operativa inequívoca. |
| **DEC-INCOME-02** (this design) | `assign_ingreso_consecutivo` is the canonical counter helper; mirrors `assign_consecutivo` (DIAN) verbatim where possible. | Reduces cognitive load; pattern is battle-tested for T-PR9-002 DIAN. |
| **DEC-INCOME-03** (this design) | The counter is local-only (no `branch_to_cloud` sync). | Per-branch operational state; cloud has no use for it. Excluded from `fn_enqueue_sync_catalog`. |
| **DEC-INCOME-04** (this design) | V8 `existe_ingreso_activo` is SKIPPED for `placa is None` (REQ-OPS-040 modified). | V8 was meaningful only for placa-driven duplicates; no-placa duplicates are caught by the partial UK on `prod.ingreso.consecutivo` (REQ-OPS-192). |
| **DEC-INCOME-05** (this design) | `<TipoIngresoToggle>` is the canonical wrapper for the dual-flow layout. | DRY between `Principal.tsx` and `IngresoPanel.tsx` (R8 mitigation). |

---

## 17. Out of Scope (deferred)

- **Reset of `consecutivo`** — monotonic forever per Q1.
- **UI admin for managing resolutions** — not DIAN, not applicable.
- **Changes in salida flow handler** — JOIN carries `consecutivo`; UX follow-up (operator types `consecutivo` instead of placa at exit) is F13.x.
- **Sync pipeline changes** — `record_event` flows the column automatically.
- **Hash chain changes** — automatic via `record_event`'s canonical payload.
- **Backend sync workers (`job_sync_*`)** — no changes.
- **BFF (deferred to v2)** — renderer talks to `api_sucursal` directly.
- **Selector manual de tipo en flujo con placa** — BR2 invariante preserved.
- **Multi-idioma para `operacion.json`** — solo es-CO in this PR; en-US/pt-BR follow-up.
- **Auto-cancel / auto-renew del counter** — operational follow-up.
- **`mv_ocupacion_diaria` changes** — already counts by `(sucursal, tipo)`; only regression test added.
- **Salida tiquete for bici/patineta** — JOIN reads `consecutivo`; UX update deferred to F13.x.

---

## 18. References

- **Inputs (this change)**:
  - `openspec/changes/ingreso-multi-tipo-consecutivo/specs/operations/spec.md` (311 lines, REQ-OPS-191..198 + REQ-OPS-040 modified)
  - `openspec/changes/ingreso-multi-tipo-consecutivo/proposal.md` (205 lines)
  - `openspec/changes/ingreso-multi-tipo-consecutivo/exploration.md` (278 lines, 12 gaps + 11 risks)
- **Canonical specs**:
  - `openspec/specs/operations/spec.md` (REQ-OPS-001..190, REQ-OPS-040 V8 baseline, REQ-OPS-134 explicit UUID short-circuit)
  - `openspec/specs/operacion.md` (HU-F1.6 / F1.5 / F1.8 chain canon)
- **Code precedents**:
  - `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::assign_consecutivo:47-183` (canonical `SELECT FOR UPDATE` pattern, T-PR9-002)
  - `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py::validar_cupo_disponible:138-214` (tipo-agnostic V1+V2)
  - `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py:57-127` (V8 `existe_ingreso_activo`, V4 `validar_tipo_vehiculo_vigente`)
  - `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py:174-194` (`crear_ingreso_evento` — `record_event` wrapper)
  - `backend/packages/parkos_core/src/parkos_core/models/L_E/ingreso.py` (`Ingreso` ORM)
  - `backend/packages/parkos_core/src/parkos_core/models/A/idempotency_keys.py` (50th table `[A]` precedent)
  - `backend/packages/parkos_core/src/parkos_core/models/base.py::AppendOnlyBase:177` (abstract base)
  - `backend/packages/parkos_core/migrations/versions/0037_add_uuid_subscripcion_cliente_to_facturas.py` (nullable ADD COLUMN + idempotent FK precedent)
  - `apps/electron-sucursal/src/features/operacion/lib/ingresoApi.ts` (Zod schema baseline)
  - `apps/electron-sucursal/src/features/operacion/components/PlacaInput.tsx` (RHF + Zod pattern)
  - `apps/electron-sucursal/src/features/operacion/components/TiqueteModal.tsx` (modal pattern)
  - `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (SWR + dedup precedent)
  - `apps/electron-sucursal/src/lib/print/escposBuilder.ts::buildEntradaBody:171-227` (17-field tiquete layout)
  - `apps/electron-sucursal/src/lib/print/escposTemplates.ts::entradaPayloadSchema:224` (Zod payload)
- **Conventions**:
  - `AGENTS.md` §Architectural Principles (audit-first, bi-temporal, C/Q/U-no-D, multi-tenant, hash chain)
  - `AGENTS.md` §Operational Timeouts (migration pre-flight + REVOKE/trigger in same script)
  - `openspec/config.yaml` `rules.tasks` (REVOKE + trigger in same migration for `[A]` tables; pre-flight `alembic upgrade --sql`)
  - `modelo_datos_er.mmd` lines 577-596 (canonical `[L-E] ingreso` shape, pre-change baseline)
- **Archived precedents**:
  - `openspec/changes/archive/2026-09-16-hu-f4-1-deteccion-tipo-vehiculo/` (detection + useTiposVehiculo)
  - `openspec/changes/archive/2026-09-17-fase-6-1-flujo-ingreso/` (Principal + PlacaInput + TiqueteModal baseline)
  - `openspec/changes/archive/2026-09-19-fase-7-3-tiquetes-salida/` (escposBuilder byte-fixture pattern)
- **DEC-INCOME-01 (proposal §4)** — explicit naming separation between `prod.ingreso.consecutivo` and `prod.factura_electronica.consecutivo`.

---

## Ready for next phase

**Status**: `ready-for-sdd-tasks`.

This design locks:
- 1 new table (`prod.ingreso_consecutivo_contador`, 51st) + 1 new column (`prod.ingreso.consecutivo`).
- 1 new helper (`assign_ingreso_consecutivo`, ~150 LOC).
- 1 new hook (`useTiposVehiculoSinPlaca`, ~25 LOC).
- 2 new components (`<IngresoSinPlacaPanel>` ~120 LOC, `<TipoIngresoToggle>` ~80 LOC).
- 4 modified backend files (model, schemas, handler, repo re-export).
- 7 modified frontend files (Zod, page, panel, modal, 3 print-layer files).
- 8 new i18n keys.
- 13 risks documented (R1..R13) — all mitigated.
- 11 open questions resolved (Q1..Q11 from proposal §6).
- 5 decisions locked (DEC-INCOME-01..05).
- 2 chained PRs (PR-A ~600 LOC, PR-B ~455 LOC), well within the 800-LOC review budget per `config.yaml rules.tasks`.

The next phase (`sdd-tasks`) breaks this design into reviewable work units along the commit-splitting already specified in §10.
