"""0089_seed_alert_types_fe_emision -- alert types for FE emission failures.

Revision ID: 0089_seed_alert_types_fe_emision
Revises: 0088_seed_cliente_estandar
Create Date: 2026-10-06 01:10:00.000000

SCOPE
-----
Data-only. Electronic invoicing is always emitted after a payment; if the
emission fails the payment stays, the invoice is left pending and the branch
worker retries automatically (``repo/fe_emision.py``). Two alert types:

* ``fe_emision_pendiente`` (info): informational marker written when an
  emission fails; it carries the data a retry needs (invoice, customer).
  Written already ``resuelta`` so it does not clutter the admin's open queue.
* ``fe_emision_fallida`` (warning): raised ONCE per invoice when the bounded
  retries are exhausted. This is the alert the administrator acts on.

No existing type fits (``fe_numbering_exhausted`` only covers one cause and
is fired by the manual endpoint). ``alert_types`` is out-of-catalog and
immutable for UPDATE/DELETE by trigger; INSERT ... ON CONFLICT DO NOTHING is
the 0013/0086 pattern.

DOWNGRADE: no-op (registry is immutable by trigger; nothing is deleted).
"""
from __future__ import annotations

from alembic import op

revision = "0089_seed_alert_types_fe_emision"
down_revision = "0088_seed_cliente_estandar"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

_ALERT_TYPES: tuple[tuple[str, str, str], ...] = (
    (
        "fe_emision_pendiente",
        "Fallo la emision de la factura electronica; queda pendiente de reintento",
        "info",
    ),
    (
        "fe_emision_fallida",
        "La factura electronica no pudo emitirse tras los reintentos automaticos",
        "warning",
    ),
)


def upgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)
    for tipo, descripcion, severity in _ALERT_TYPES:
        op.execute(
            f"""
            INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)
            VALUES ('{tipo}', '{descripcion}', '{severity}')
            ON CONFLICT (tipo_alerta) DO NOTHING
            """
        )


def downgrade() -> None:
    """Intentional no-op: the registry is immutable by trigger."""


__all__ = ["downgrade", "upgrade"]
