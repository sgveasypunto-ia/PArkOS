"""0098_seed_alert_type_fe_consecutivo_duplicado -- duplicate (resolucion, consecutivo).

Revision ID: 0098_seed_alert_type_fe_consecutivo_duplicado
Revises: 0097_seed_alert_type_dian_reintento

SCOPE
-----
Data-only. When a pushed ``factura_electronica`` collides with another
document on ``(uuid_resolucion_facturacion, consecutivo)`` (UK
``factura_electronica_uk01``) the push is reported as a ``conflict`` and this
alert is raised once per document, so the row no longer retries forever and
a person decides the compensatory path. Neither document is modified: both
are immutable ([A] / DIAN).

``alert_types`` is out-of-catalog and immutable for UPDATE/DELETE by trigger;
INSERT ... ON CONFLICT DO NOTHING is the 0013/0086/0089/0097 pattern.

DOWNGRADE: no-op (registry is immutable by trigger; nothing is deleted).
"""
from __future__ import annotations

from alembic import op

revision = "0098_seed_alert_type_fe_consecutivo_duplicado"
down_revision = "0097_seed_alert_type_dian_reintento"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

_TIPO = "fe_consecutivo_duplicado"
_DESCRIPCION = "Dos facturas electronicas comparten resolucion y consecutivo; requiere decision contable"
_SEVERITY = "critical"


def upgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)
    op.execute(
        f"""
        INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)
        VALUES ('{_TIPO}', '{_DESCRIPCION}', '{_SEVERITY}')
        ON CONFLICT (tipo_alerta) DO NOTHING
        """
    )


def downgrade() -> None:
    """Intentional no-op: the registry is immutable by trigger."""


__all__ = ["downgrade", "upgrade"]
