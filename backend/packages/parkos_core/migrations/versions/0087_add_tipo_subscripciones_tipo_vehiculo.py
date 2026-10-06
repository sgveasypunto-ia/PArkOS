"""0087_add_tipo_subscripciones_tipo_vehiculo -- vehicle type on subscription plans.

Revision ID: 0087_add_tipo_subscripciones_tipo_vehiculo
Revises: 0086_seed_permiso_placas_y_alertas
Create Date: 2026-10-06 00:10:00.000000

SCOPE
-----
Adds ``prod.tipo_subscripciones.uuid_tipo_vehiculo`` (nullable UUID, FK to
``prod.tipos_vehiculo(uuid)``) so a plan can declare which vehicle type it
covers. ``NULL`` means "any type" (e.g. ``MENSUAL_EMPRESA``). Until now that
relation lived only in the plan NAME suffix
(``repo/tipos_vehiculo_subscripcion.py``: ``*_AUTO`` -> carro,
``*_MOTO`` -> moto). This migration is the schema half only; sale/plate
validation is deliberately NOT changed here (a later unit consumes it).

BACKFILL AND THE BI-TEMPORAL MODEL
----------------------------------
The 0039 seed plans are backfilled in place:

    MENSUAL_MOTO                              -> tipo 'moto'
    MENSUAL_AUTO / BIMESTRAL_AUTO / TRIMESTRAL_AUTO -> tipo 'carro'
    MENSUAL_EMPRESA                           -> NULL (any type)

This UPDATE does not violate the bi-temporal rule ("close the version and
insert a new one"): that rule governs mutation of BUSINESS FACTS, where the
past value must stay reconstructable. Here the column did not exist before, so
there is no prior value to preserve and no business fact changes -- the plan
was always a car (or motorcycle) plan; the migration only materialises, as a
column, what the name suffix already encoded. This is schema evolution (the
same class as ``0083`` indexes or any ``ADD COLUMN ... DEFAULT``), not a
mutation of the plan's valid time. Consequently:

* ALL versions of the five plan names are filled (open and closed), so a
  subscription pointing at an older plan version resolves the same type.
* ``vigente_desde`` / ``vigente_hasta`` / ``estado`` are NOT touched, and the
  UPDATE only writes rows whose new column is still NULL (idempotent).
* No ``fn_enqueue_sync`` fires (it is AFTER INSERT only): the backfill is NOT
  replicated. It does not need to be -- every node (cloud and each branch)
  runs this same migration and resolves the type by NAME against ITS OWN
  ``tipos_vehiculo`` row (the uuid of 'carro'/'moto' can differ per node until
  the identity alias settles; see 0081). Plans the cloud versions AFTER this
  migration travel with the cloud's ``uuid_tipo_vehiculo``, which the sync
  motor remaps through ``sync_identity_alias`` (``identity_fk_map.py``).
* If a node has no open 'carro'/'moto' row, the plans stay NULL (= any type)
  instead of failing the migration.

No physical DELETE; ``tipo_subscripciones`` is a [V] table (no REVOKE or
inmutable trigger applies, those are for [A]).

DOWNGRADE
---------
Drops the FK and the column. The data lost is derivable again from the name
suffix, so nothing irrecoverable is discarded.
"""
from __future__ import annotations

from alembic import op

revision = "0087_add_tipo_subscripciones_tipo_vehiculo"
down_revision = "0086_seed_permiso_placas_y_alertas"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"
_FK_NAME = "fk_tipo_subscripciones_uuid_tipo_vehiculo"

# plan name -> canonical tipos_vehiculo.tipo (None = any type, stays NULL)
_BACKFILL: dict[str, str] = {
    "MENSUAL_MOTO": "moto",
    "MENSUAL_AUTO": "carro",
    "BIMESTRAL_AUTO": "carro",
    "TRIMESTRAL_AUTO": "carro",
}


def upgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute(
        """
        ALTER TABLE prod.tipo_subscripciones
            ADD COLUMN IF NOT EXISTS uuid_tipo_vehiculo UUID NULL;
        """
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = '{_FK_NAME}'
                  AND conrelid = 'prod.tipo_subscripciones'::regclass
            ) THEN
                ALTER TABLE prod.tipo_subscripciones
                    ADD CONSTRAINT {_FK_NAME}
                    FOREIGN KEY (uuid_tipo_vehiculo)
                    REFERENCES prod.tipos_vehiculo (uuid);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_tipo_subscripciones_uuid_tipo_vehiculo
            ON prod.tipo_subscripciones (uuid_tipo_vehiculo);
        """
    )

    # Backfill by NAME against this node's own open tipos_vehiculo row.
    # Literals come from the module constant above (no user input).
    for plan, vehiculo in _BACKFILL.items():
        op.execute(
            f"""
            UPDATE prod.tipo_subscripciones ts
               SET uuid_tipo_vehiculo = tv.uuid
              FROM (
                    SELECT uuid
                      FROM prod.tipos_vehiculo
                     WHERE tipo = '{vehiculo}'
                       AND vigente_hasta IS NULL
                     ORDER BY vigente_desde DESC
                     LIMIT 1
                   ) tv
             WHERE ts.tipo = '{plan}'
               AND ts.uuid_tipo_vehiculo IS NULL;
            """
        )


def downgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)
    op.execute("DROP INDEX IF EXISTS prod.ix_tipo_subscripciones_uuid_tipo_vehiculo;")
    op.execute(
        f"ALTER TABLE prod.tipo_subscripciones DROP CONSTRAINT IF EXISTS {_FK_NAME};"
    )
    op.execute(
        "ALTER TABLE prod.tipo_subscripciones DROP COLUMN IF EXISTS uuid_tipo_vehiculo;"
    )
