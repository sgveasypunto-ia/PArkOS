"""0091_mv_ocupacion_salida_anulada -- la ocupacion cuenta la placa con salida anulada.

Revision ID: 0091_mv_ocupacion_salida_anulada
Revises: 0090_cotizar_ignora_salida_anulada
Create Date: 2026-10-07

PROBLEMA
--------
``prod.mv_ocupacion_diaria`` (0024/0034) excluia un ingreso si existia CUALQUIER
fila en ``prod.salidas`` y tambien si existia una anulacion ejecutada de tipo
``salida`` con ese ``uuid_ingreso`` (``repo/salida.py::anular_salida_no_pagada``
la guarda con ``uuid_ingreso``). Tras compensar una salida no pagada la placa
vuelve a estar dentro (``V_INGRESO_ESTADO``, ``repo/ingreso_activo.py::
salida_vigente_exists_sql``), pero el cupo seguia mostrando la plaza libre.

FIX
---
Se recrea la vista con la misma definicion de "salida vigente" del resto del
sistema: una salida solo descuenta si NO existe una anulacion ``ejecutada`` de
esa salida (``a.uuid_salida = s.uuid``). Solo la anulacion de INGRESO excluye el
ingreso. Mismo contrato de columnas, mismo UNIQUE INDEX (requerido por
REFRESH CONCURRENTLY) y mismo GRANT; el helper SECURITY DEFINER
``prod.refresh_mv_ocupacion_diaria()`` (0045) resuelve la vista por nombre, no
necesita cambios. PG no soporta ``CREATE OR REPLACE MATERIALIZED VIEW``: se hace
DROP + CREATE (la vista se repuebla en el CREATE). Sin tablas ``[A]`` ni datos
tocados.

DOWNGRADE: restaura la definicion exacta de 0034.
"""
from __future__ import annotations

from alembic import op

revision = "0091_mv_ocupacion_salida_anulada"
down_revision = "0090_cotizar_ignora_salida_anulada"
branch_labels = None
depends_on = None

_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_ocupacion_diaria_sucursal_tipo "
    "ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo)"
)
_GRANT = "GRANT SELECT ON prod.mv_ocupacion_diaria TO parkos_app"


def upgrade() -> None:
    """Recrea la MV contando salidas vigentes (sin anuladas)."""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria")
    op.execute(
        """
        CREATE MATERIALIZED VIEW prod.mv_ocupacion_diaria AS
        SELECT
            i.uuid_sucursal,
            i.uuid_tipo_vehiculo,
            count(*) AS activos
        FROM prod.ingreso i
        WHERE
            i.uuid_tipo_vehiculo IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM prod.salidas s
                WHERE s.uuid_ingreso = i.uuid
                  AND s.uuid_sucursal = i.uuid_sucursal
                  AND NOT EXISTS (
                      SELECT 1 FROM prod.anulaciones a
                      WHERE a.uuid_salida = s.uuid
                        AND a.tipo_anulable = 'salida'
                        AND a.estado = 'ejecutada'
                  )
            )
            AND NOT EXISTS (
                SELECT 1 FROM prod.anulaciones a
                WHERE a.uuid_ingreso = i.uuid
                  AND a.estado = 'ejecutada'
                  AND a.tipo_anulable = 'ingreso'
            )
        GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo
        """
    )
    op.execute(_INDEX)
    op.execute(_GRANT)


def downgrade() -> None:
    """Restaura la definicion de 0034."""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria")
    op.execute(
        """
        CREATE MATERIALIZED VIEW prod.mv_ocupacion_diaria AS
        SELECT
            i.uuid_sucursal,
            i.uuid_tipo_vehiculo,
            count(*) AS activos
        FROM prod.ingreso i
        WHERE
            i.uuid_tipo_vehiculo IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM prod.salidas s
                WHERE s.uuid_ingreso = i.uuid
                  AND s.uuid_sucursal = i.uuid_sucursal
            )
            AND NOT EXISTS (
                SELECT 1 FROM prod.anulaciones a
                WHERE a.uuid_ingreso = i.uuid
                  AND a.estado = 'ejecutada'
                  AND a.tipo_anulable IN ('ingreso', 'salida')
            )
        GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo
        """
    )
    op.execute(_INDEX)
    op.execute(_GRANT)
