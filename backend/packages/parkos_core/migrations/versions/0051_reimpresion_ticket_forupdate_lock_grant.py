"""MIGRATION 0051 -- grant column-scoped UPDATE on prod.reimpresion_ticket
para permitir el lock ``SELECT ... FOR UPDATE`` de HU-F1.11.

BUG REAL (encontrado 2026-09-25 al validar HU-F8.3 con Chrome DevTools
contra el backend real por primera vez): ``POST /api/v1/workflows/
reimpresion-ticket`` respondia 500:

    asyncpg.exceptions.InsufficientPrivilegeError:
        permission denied for table reimpresion_ticket

``prod.reimpresion_ticket`` es ``[L-W]`` insert-only (append_transition
via close+insert semantico, jamas un UPDATE real de fila) y por eso
``rol_app`` solo tenia ``SELECT, INSERT`` (igual que ``alerta``,
``anulaciones``, ``reclamos``) -- correcto para el resto de esos
workflows. Pero ``repo/reimpresion_ticket.py::buscar_reimpresion_activa_
por_ingreso`` (DEC-TKT-02 / KD-TKT-02, guard de concurrencia V2 contra
doble cobro) usa ``.with_for_update()`` sobre el chain-tip -- es el
UNICO ``[L-W]`` del repo que lockea asi. PostgreSQL exige el privilegio
UPDATE sobre la tabla para ``SELECT ... FOR UPDATE``, sin importar que
columna toque el UPDATE (o que nunca se ejecute ninguno).

Mismo patron ya usado en la migracion 0043 (``ingreso_consecutivo_
contador``): GRANT UPDATE columna-scoped, nunca full-table, para
mantener la disciplina insert-only a nivel de permisos DB. Se eligen
las 3 columnas de ``SyncMixin`` (las unicas semanticamente candidatas a
un UPDATE in-place futuro, p. ej. si el worker de sync algun dia marca
``sync_status`` tras el push) -- ninguna columna de negocio
(``motivo``, ``uuid_ingreso``, ``costo_aplicado``, etc.) queda
UPDATEable por ``rol_app``.
"""
from __future__ import annotations

from alembic import op


revision = "0051_reimpresion_ticket_forupdate_lock_grant"
down_revision = "0050_cotizar_mensualidad_factura_descuento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Grant column-scoped UPDATE on prod.reimpresion_ticket to rol_app."""
    op.execute(
        "GRANT UPDATE (sync_status, sync_timestamp, sync_attempts) "
        "ON prod.reimpresion_ticket TO rol_app"
    )


def downgrade() -> None:
    """Revoke the column-scoped UPDATE grant added in 0051."""
    op.execute(
        "REVOKE UPDATE (sync_status, sync_timestamp, sync_attempts) "
        "ON prod.reimpresion_ticket FROM rol_app"
    )


__all__ = ["upgrade", "downgrade"]
