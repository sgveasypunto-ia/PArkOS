"""MIGRATION 0093 -- deterministic uuid for the seeded ``costos_servicios`` rows.

Revision ID: 0093_deterministic_costos_servicios_uuids
Revises: 0092_sesion_close_enqueue_and_root_table_name

WHY THIS MIGRATION EXISTS
-------------------------
``0029`` seeds ``prod.costos_servicios.concepto = 'reimpresion'`` with
``gen_random_uuid()`` and ``NOW()``, once per node, because every node runs
the migration chain on its own. Measured on the live stacks (2026-10-07)::

    cloud  : ad489879  reimpresion  open
    branch : c09e5d24  reimpresion  open   (ad489879 arrived by pull as a
                                            closed historical version)

``costos_servicios`` replicates cloud -> branch only, so ``c09e5d24`` never
reaches the cloud. Every ``reimpresion_ticket`` the branch creates names
``c09e5d24`` in ``uuid_costo_servicio`` and its push fails with an FK
violation on the cloud, retried forever. It is the same failure class that
``0019``/``0020``/``0056`` fixed for permissions, tipo_persona and empresa: a
seeded catalog row minted with a random uuid per node breaks the FKs of the
transactional rows that reference it.

DESIGN
------
Same scheme as ``0019``/``0056`` (same namespace, values computed OFFLINE and
hardcoded, never at runtime): ``uuid5(NAMESPACE, 'costos_servicios:<concepto>')``.
Every node, present and future, converges on one uuid per seeded concept.

Per concept, only when this node has no row with the deterministic uuid yet:

1. INSERT the deterministic row as the new open version, copying the business
   columns (``costo``, ``tipo_calculo``) of the open row it supersedes so a
   price an administrator already configured survives.
2. Close every other open version of the concept (``vigente_hasta``,
   ``estado='inactivo'``).

Rows already referencing the superseded uuid (``reimpresion_ticket``) are NOT
touched: closed versions stay in the table forever and still satisfy the FK
locally. Their push to the cloud is repaired by recording the
branch-uuid -> cloud-uuid alias on the cloud (``prod.sync_identity_alias``,
see ``docs/03-desarrollo/setup.md`` section 3.2).

No physical DELETE. Idempotent: a converged node is a no-op.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0093_deterministic_costos_servicios_uuids"
down_revision = "0092_sesion_close_enqueue_and_root_table_name"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# concepto -> uuid5(UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60"), "costos_servicios:<concepto>")
# (same namespace as 0019/0056). A concept seeded by a later migration must be
# added here (or minted deterministically in its own seed) to converge.
_DETERMINISTIC_UUIDS: dict[str, str] = {
    "reimpresion": "08e06c53-60cf-5392-8b96-51024d6d3c9e",
}


def converge_costos_servicios(bind) -> None:  # noqa: ANN001 - sync Connection
    """Converge every concept of ``_DETERMINISTIC_UUIDS`` (idempotent)."""
    for concepto, det_uuid in _DETERMINISTIC_UUIDS.items():
        open_rows = bind.execute(
            text(
                "SELECT uuid, costo, tipo_calculo FROM prod.costos_servicios "
                "WHERE concepto = :concepto AND vigente_hasta IS NULL "
                "ORDER BY created_at DESC"
            ),
            {"concepto": concepto},
        ).all()
        if not open_rows or [str(r.uuid) for r in open_rows] == [det_uuid]:
            continue
        exists = bind.execute(
            text("SELECT 1 FROM prod.costos_servicios WHERE uuid = :u"), {"u": det_uuid}
        ).scalar_one_or_none()
        if exists is not None:
            # The deterministic row is already part of this node's history (a
            # later version legitimately supersedes it): nothing to converge.
            continue
        stale = [str(r.uuid) for r in open_rows]
        newest = open_rows[0]
        bind.execute(
            text(
                """
                INSERT INTO prod.costos_servicios
                    (uuid, concepto, costo, tipo_calculo, vigente_desde, vigente_hasta,
                     estado, created_at, created_by, sync_status, sync_attempts)
                VALUES (:u, :concepto, :costo, :tipo, clock_timestamp(), NULL,
                        'activo', clock_timestamp(), NULL, 'sincronizado', 0)
                """
            ),
            {"u": det_uuid, "concepto": concepto, "costo": newest.costo, "tipo": newest.tipo_calculo},
        )
        bind.execute(
            text(
                "UPDATE prod.costos_servicios SET vigente_hasta = clock_timestamp(), "
                "estado = 'inactivo' WHERE uuid = ANY(CAST(:stale AS uuid[])) "
                "AND vigente_hasta IS NULL"
            ),
            {"stale": stale},
        )


def upgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)
    converge_costos_servicios(op.get_bind())


def downgrade() -> None:
    """No-op by design (the random uuids were never recorded; see 0056)."""
    return


__all__ = ["converge_costos_servicios", "downgrade", "upgrade"]
