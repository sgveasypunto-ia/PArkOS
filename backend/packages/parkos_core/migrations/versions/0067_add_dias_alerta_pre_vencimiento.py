"""0067_add_dias_alerta_pre_vencimiento -- per-subscripcion vencimiento alert window.

Revision ID: 0067_add_dias_alerta_pre_vencimiento
Revises: 0066_add_configuracion_caja
Create Date: 2026-10-02 00:00:00.000000

THE PROBLEM THIS PINS
---------------------
HU-F20.2 / CU-06 BR4 requires ``dias_alerta_pre_vencimiento`` **per
subscripcion** (editable, default 7). The canonical ER
(``.mmd`` lines 496-516) has no such column on
``prod.subscripciones_cliente`` -- only ``uuid_cliente``,
``uuid_sucursal``, ``uuid_tipo_subscripcion``, ``fecha_inicio_cobertura``,
``fecha_vencimiento`` are modeled as business columns. This migration adds
the column as an explicit, declared ER extension -- same criterion as
``0065_add_usuarios_must_change`` (``debe_cambiar_password`` on
``prod.usuarios``) and ``0066_add_configuracion_caja``.

WHY NULLABLE + DEFAULT 7 AND NOT NOT NULL
------------------------------------------
Unlike ``0065`` (``NOT NULL DEFAULT false``), the task brief for this
column is explicit: nullable, ``DEFAULT 7``. ``prod.subscripciones_cliente``
is a ``[V]`` bi-temporal table (``close_and_insert``) -- a ``NULL`` here
simply means "use the plan-wide default of 7 days" at the API/UI edge
(``schemas/clientes.py``'s Pydantic ``Field(ge=1, le=90)`` never emits
``NULL`` for a NEW row created through the API, since the API defaults to
7 itself when absent -- see that schema's own docstring). Existing rows
backfill to 7 via the column ``DEFAULT`` clause (instant metadata-only
change in Postgres 11+, no table rewrite -- same ``ADD COLUMN`` shape as
``0065``, just nullable instead of ``NOT NULL``).

WHY A COLUMN AND NOT A ``tipo_sucursal.caracteristicas`` DEFAULT
------------------------------------------------------------------
BR1 (plan.md HU-F20.2): globalizing this value at the branch-characteristics
level would force every subscripcion at that branch to share one alert
window, directly violating CU-06 BR4's "editable per subscripcion"
requirement. The column lives on ``subscripciones_cliente`` itself.
"""
from alembic import op
from sqlalchemy import text

revision = "0067_add_dias_alerta_pre_vencimiento"
down_revision = "0066_add_configuracion_caja"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            "ALTER TABLE prod.subscripciones_cliente "
            "ADD COLUMN IF NOT EXISTS dias_alerta_pre_vencimiento integer "
            "DEFAULT 7"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            "ALTER TABLE prod.subscripciones_cliente "
            "DROP COLUMN IF EXISTS dias_alerta_pre_vencimiento"
        )
    )
