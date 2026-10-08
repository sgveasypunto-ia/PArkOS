"""0097_seed_alert_type_dian_reintento -- request type for the manual DIAN retry.

Revision ID: 0097_seed_alert_type_dian_reintento
Revises: 0096_pull_rls_envio_dian

SCOPE
-----
Data-only. ``envio_dian`` is cloud-authored (``cloud_to_branch``): the branch
cannot push a retry row. A manual retry is therefore filed as a request in an
existing ``branch_to_cloud`` workflow entity, ``alerta``, with
``tipo_alerta='dian_reintento_solicitado'`` and ``uuid_arqueo`` pointing at the
``factura_electronica`` (the same historical reference column the dispatcher's
own alertas use). On arrival the cloud creates the retry attempt.

``alert_types`` is out-of-catalog and immutable for UPDATE/DELETE by trigger;
INSERT ... ON CONFLICT DO NOTHING is the 0013/0086/0089 pattern. No ``[A]``
table is created or altered, so there is no REVOKE / trigger to add.

DOWNGRADE: no-op (registry is immutable by trigger; nothing is deleted).
"""
from __future__ import annotations

from alembic import op

revision = "0097_seed_alert_type_dian_reintento"
down_revision = "0096_pull_rls_envio_dian"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

_TIPO = "dian_reintento_solicitado"
_DESCRIPCION = "La sucursal solicito reintentar el envio de una factura electronica a la DIAN"
_SEVERITY = "info"


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
