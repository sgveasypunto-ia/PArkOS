"""0066_add_configuracion_caja -- HU-F13.3 cash-box config (base, redondeo, denominaciones).

Revision ID: 0066_add_configuracion_caja
Revises: 0065_add_usuarios_must_change
Create Date: 2026-10-01 00:00:00.000000

THE PROBLEM THIS PINS
---------------------
CU-13 asks for a per-branch admin screen covering "base inicial, umbral de
alerta y redondeo" for the cash drawer. The canonical ER has no table for
this (DEC-ADM-12) -- ``configuracion_tolerancias`` already owns the
descuadre threshold (``tolerancia_efectivo`` / ``tolerancia_datafono``, BR2
below) and the real opening balance of a shift lives in
``sesion.valor_inicial_efectivo`` / ``valor_inicial_datafono`` (BR1 below).
What is genuinely missing is a place to configure the SUGGESTED opening
base, the rounding rule, and the allowed cash-denomination set -- so this
migration adds exactly that, as an explicit ER exception with the same
bi-temporal override shape as its two siblings
(``configuracion_tolerancias`` / ``configuracion_seguridad``, both in
``0001_initial_schema.py``).

BUSINESS RULES CARRIED BY THIS SHAPE (plan.md HU-F13.3)
--------------------------------------------------------
- BR1. ``base_inicial_sugerida`` is a reference value the sucursal UI
  pre-fills when opening an arqueo; it NEVER overwrites
  ``sesion.valor_inicial_efectivo`` / ``valor_inicial_datafono`` (untouched
  by this migration). The arqueo itself always uses the base configured at
  the START of the arqueo, not the start of the shift.
- BR2. The "umbral de alerta por descuadre" is NOT modeled here --
  ``configuracion_tolerancias.tolerancia_efectivo`` /
  ``tolerancia_datafono`` already own it (untouched by this migration; no
  duplicate columns).
- BR3. ``redondeo`` is a string enum (``ninguno`` | ``100`` | ``500`` |
  ``1000``), validated at the Pydantic edge (schemas/configuracion.py),
  NOT as a DB CHECK constraint -- consistent with how the sibling tables
  leave enum-shaped columns (``estado``, ``sync_status``) unconstrained at
  the DB layer and validate at the API edge instead.
  ``denominaciones_permitidas`` is a JSON array of integers (e.g.
  ``[1000, 2000, 5000, 10000, 20000, 50000]``), UI-validated, not
  DB-constrained.
- BR4. Changing the base mid-shift is allowed; this is the standard
  bi-temporal close+insert pattern already used by every other ``[V]``
  table -- nothing is overwritten, the open version is closed
  (``vigente_hasta``) and a new one is inserted.

SHAPE: EXACT MIRROR OF ``configuracion_tolerancias`` / ``configuracion_seguridad``
-----------------------------------------------------------------------------------
Same global-default-vs-per-branch-override pattern (``uuid_sucursal IS
NULL`` == global default, per REQ-OP-12 + SC-OP-06): same audit / versioning
/ sync columns, same ``UniqueConstraint(uuid_sucursal, vigente_desde)``, same
FK to ``prod.sucursal``, and the same three BEFORE/AFTER INSERT triggers
wired to the shared trigger functions ``0001_initial_schema.py`` already
created (``prod.fn_audit_columns()``, ``prod.fn_set_vigente_inicial()``,
``prod.fn_enqueue_sync()``) -- those functions dispatch on
``TG_TABLE_NAME`` / ``NEW.uuid_sucursal`` generically, so a table created in
a LATER migration only needs to attach triggers to them, never redefine
them (confirmed against ``0006_add_pairing_tokens_and_normalized_revoked_sync_jwts.py``,
which does the same for its own, differently-shaped, append-only tables).

PERMISSION SEED: ``config_caja`` (F13.1 debt, closed here)
-----------------------------------------------------------
F13.1 named the ``config_caja`` permission code for this very screen but
the catalogue never carried it (the same class of defect ``0059`` fixed
for ten other router-only codes). Seeded here with the SAME continuous
``uuid5`` namespace ``0019``/``0056``/``0059`` established
(``a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60``) so every node -- cloud and every
branch -- converges on the identical catalogue row instead of minting one
independently per node. Deterministic value, computed OFFLINE and
hardcoded below (recompute to verify, never regenerate at runtime --
``0059``'s docstring explains why: a runtime ``uuid_generate_v5`` would
need ``pgcrypto``, a dependency this project does not carry):

    uuid.uuid5(uuid.UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60"), "config_caja")
    => c016e2e7-a3b1-57b0-a9b3-3ae797edb04d

Same idempotent 3-step shape as ``0059``: (1) INSERT the catalogue row if no
open one exists for the code, (2) GRANT it to every open ``rol='admin'``
usuario missing the grant, (3) retire any grant left dangling on a closed
version of the code. ``NOT EXISTS`` guards, not ``ON CONFLICT`` -- the UK is
``(permiso, vigente_desde)`` and ``vigente_desde = clock_timestamp()`` never
repeats, so a conflict target naming that UK would never fire (the exact
defect ``0059`` already documents for ``0002``'s seed).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

revision = "0066_add_configuracion_caja"
down_revision = "0065_add_usuarios_must_change"
branch_labels = None
depends_on = None

PG_UUID = postgresql.UUID(as_uuid=True)

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# Same continuous namespace as 0019 / 0056 / 0059 -- see module docstring.
_PERMISSION_NAMESPACE = "a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60"
_PERMISSION_CODE = "config_caja"
# uuid5(UUID(_PERMISSION_NAMESPACE), _PERMISSION_CODE), computed offline.
_PERMISSION_UUID = "c016e2e7-a3b1-57b0-a9b3-3ae797edb04d"


# --- local helpers (redefined per-migration per this repo's convention --
# see 0006_add_pairing_tokens_and_normalized_revoked_sync_jwts.py; these are
# NOT imported from a shared module). ---


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "uuid",
        PG_UUID,
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
        nullable=False,
    )


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("NOW()"),
    )


def _created_by() -> sa.Column:
    return sa.Column("created_by", PG_UUID, nullable=True)


def _audit_columns() -> list[sa.Column]:
    return [_created_at(), _created_by()]


def _versioning_columns() -> list[sa.Column]:
    return [
        sa.Column("vigente_desde", sa.DateTime(timezone=False), nullable=True),
        sa.Column("vigente_hasta", sa.DateTime(timezone=False), nullable=True),
        sa.Column("estado", sa.String(length=16), nullable=True),
    ]


def _sync_columns() -> list[sa.Column]:
    return [
        sa.Column("sync_status", sa.String(length=16), nullable=True),
        sa.Column("sync_timestamp", sa.DateTime(timezone=False), nullable=True),
        sa.Column("sync_attempts", sa.Integer(), nullable=True),
    ]


def upgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)

    # --- configuracion_caja (V) ---
    op.create_table(
        "configuracion_caja",
        _uuid_pk(),
        sa.Column("uuid_sucursal", PG_UUID, nullable=True),
        sa.Column("base_inicial_sugerida", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("redondeo", sa.String(length=16), nullable=True),
        sa.Column("denominaciones_permitidas", JSONB(), nullable=True),
        *_audit_columns(),
        *_versioning_columns(),
        *_sync_columns(),
        sa.UniqueConstraint("uuid_sucursal", "vigente_desde", name="configuracion_caja_uk01"),
        schema="prod",
    )

    op.create_foreign_key(
        "fk_configuracion_caja_uuid_sucursal",
        "configuracion_caja",
        "sucursal",
        ["uuid_sucursal"],
        ["uuid"],
        source_schema="prod",
        referent_schema="prod",
    )

    # Reuse the shared trigger functions 0001_initial_schema.py already
    # created -- they dispatch generically (TG_TABLE_NAME / NEW.uuid /
    # NEW.uuid_sucursal), so a table created in a later migration only
    # attaches triggers, it never redefines the functions.
    op.execute(
        """
        CREATE TRIGGER configuracion_caja_audit_columns
            BEFORE INSERT ON prod.configuracion_caja
            FOR EACH ROW EXECUTE FUNCTION prod.fn_audit_columns();
        """
    )
    op.execute(
        """
        CREATE TRIGGER configuracion_caja_set_vigente_inicial
            BEFORE INSERT ON prod.configuracion_caja
            FOR EACH ROW EXECUTE FUNCTION prod.fn_set_vigente_inicial();
        """
    )
    op.execute(
        """
        CREATE TRIGGER configuracion_caja_enqueue_sync
            AFTER INSERT ON prod.configuracion_caja
            FOR EACH ROW EXECUTE FUNCTION prod.fn_enqueue_sync();
        """
    )

    # --- Idempotent seed: config_caja permission code (closes F13.1 debt,
    # same shape as 0059). ---
    bind = op.get_bind()
    params = {"uuid": _PERMISSION_UUID, "codigo": _PERMISSION_CODE}

    # Step 1 -- the catalogue row, guarded the same two ways as 0059:
    # skip if an open row for the code already exists, and skip if the
    # deterministic uuid is already taken by a CLOSED version of it
    # (permisos_pkey is PRIMARY KEY (uuid), so a re-insert would be a PK
    # violation, not a UK violation).
    bind.execute(
        text(
            """
            INSERT INTO prod.permisos
                (uuid, permiso, vigente_desde, vigente_hasta, estado,
                 created_at, created_by, sync_status, sync_attempts)
            SELECT CAST(:uuid AS uuid), :codigo, clock_timestamp(), NULL, 'activo',
                   clock_timestamp(), NULL, 'sincronizado', 0
            WHERE NOT EXISTS (
                      SELECT 1 FROM prod.permisos p
                      WHERE p.permiso = :codigo
                        AND p.vigente_hasta IS NULL
                  )
              AND NOT EXISTS (
                      SELECT 1 FROM prod.permisos p
                      WHERE p.uuid = CAST(:uuid AS uuid)
                  )
            """
        ),
        params,
    )

    # Step 2 -- grant to every open admin missing the grant.
    bind.execute(
        text(
            """
            INSERT INTO prod.permisos_usuario
                (uuid, created_at, created_by,
                 vigente_desde, vigente_hasta, estado,
                 sync_status, sync_attempts,
                 uuid_usuario, uuid_permiso)
            SELECT gen_random_uuid(), clock_timestamp(), NULL,
                   clock_timestamp(), NULL, 'activo',
                   'sincronizado', 0,
                   u.uuid, p.uuid
            FROM prod.usuarios u
            CROSS JOIN (
                SELECT DISTINCT ON (permiso) uuid, permiso
                FROM prod.permisos
                WHERE vigente_hasta IS NULL
                  AND permiso = :codigo
                ORDER BY permiso, vigente_desde DESC
            ) p
            WHERE u.rol = 'admin'
              AND u.vigente_hasta IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM prod.permisos_usuario pu
                  WHERE pu.uuid_usuario = u.uuid
                    AND pu.uuid_permiso = p.uuid
                    AND pu.vigente_hasta IS NULL
              )
            """
        ),
        params,
    )

    # Step 3 -- retire grants left dangling on a closed catalogue version.
    bind.execute(
        text(
            """
            UPDATE prod.permisos_usuario pu
            SET vigente_hasta = clock_timestamp(),
                estado = 'inactivo'
            WHERE pu.vigente_hasta IS NULL
              AND pu.uuid_permiso IN (
                  SELECT p.uuid
                  FROM prod.permisos p
                  WHERE p.vigente_hasta IS NOT NULL
                    AND p.permiso = :codigo
              )
            """
        ),
        params,
    )


def downgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)
    bind = op.get_bind()
    params = {"codigo": _PERMISSION_CODE}

    # Permission seed -- reverse order: grants first, catalogue second
    # (same rationale as 0059: closing the catalogue row alone already
    # deactivates it for require_permission, but leaves a dangling open
    # grant pointing at a closed permission).
    bind.execute(
        text(
            """
            UPDATE prod.permisos_usuario pu
            SET vigente_hasta = clock_timestamp(),
                estado = 'inactivo'
            WHERE pu.vigente_hasta IS NULL
              AND pu.uuid_permiso IN (
                  SELECT p.uuid
                  FROM prod.permisos p
                  WHERE p.permiso = :codigo
              )
            """
        ),
        params,
    )
    bind.execute(
        text(
            """
            UPDATE prod.permisos
            SET vigente_hasta = clock_timestamp(),
                estado = 'inactivo'
            WHERE vigente_hasta IS NULL
              AND permiso = :codigo
            """
        ),
        params,
    )

    # Triggers + FK + table, in reverse creation order.
    op.execute(
        "DROP TRIGGER IF EXISTS configuracion_caja_enqueue_sync ON prod.configuracion_caja;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS configuracion_caja_set_vigente_inicial ON prod.configuracion_caja;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS configuracion_caja_audit_columns ON prod.configuracion_caja;"
    )
    op.drop_constraint(
        "fk_configuracion_caja_uuid_sucursal",
        "configuracion_caja",
        schema="prod",
        type_="foreignkey",
    )
    op.drop_table("configuracion_caja", schema="prod")


__all__ = ["downgrade", "upgrade"]
