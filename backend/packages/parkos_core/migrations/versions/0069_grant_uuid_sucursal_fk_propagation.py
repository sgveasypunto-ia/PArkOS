"""0069_grant_uuid_sucursal_fk_propagation -- narrow UPDATE(uuid_sucursal) for FK repoint.

Revision ID: 0069_grant_uuid_sucursal_fk_propagation
Revises: 0068_usuarios_email_activo_uk
Create Date: 2026-10-02 00:00:00.000000

THE PROBLEM THIS PINS
----------------------
``repo.versioned.close_and_insert`` calls ``repo.sucursal.propagate_uuid_to_fks``
after every Sucursal bi-temporal close+insert (PUT /api/v1/empresa/sucursal/{uuid}).
That helper runs a raw ``UPDATE prod.<table> SET uuid_sucursal = :new WHERE
uuid_sucursal = :old`` against the 7 admin-facing FK tables (same list as
``0061_repair_sucursal_fk_chain.py::_FK_TABLES``). It runs on the live
``rol_app``/``parkos_app`` connection, not a migration-time superuser session.

``0021_least_privilege_and_immutability_contract.py`` put all 7 of those
tables in ``_NARROW_UPDATE_V_TABLES`` and granted ``UPDATE (vigente_hasta,
estado)`` only. ``uuid_sucursal`` was never added to that grant, so the very
first edit of a Sucursal that already has a row in any of those 7 tables
(e.g. the auto-assigned ``usuarios_sucursal`` row every branch gets on
create, see ``assign_creator_to_new_sucursal``) raises
``asyncpg.exceptions.InsufficientPrivilegeError: permission denied for
table usuarios_sucursal`` and surfaces as a bare 500 on the PUT -- live
defect found QA-testing the Sucursal detail "General" tab update
(2026-10-02).

THE FIX
-------
Column-scoped ``GRANT UPDATE (uuid_sucursal)`` on the same 7 tables, additive
to the existing ``(vigente_hasta, estado)`` grant from 0021 (Postgres
column-level GRANTs accumulate; this does not touch that earlier grant).
``DELETE`` stays revoked -- unaffected by this migration.
"""
from __future__ import annotations

from alembic import op

revision = "0069_grant_uuid_sucursal_fk_propagation"
down_revision = "0068_usuarios_email_activo_uk"
branch_labels = None
depends_on = None

# Keep in sync with ``repo.sucursal._FK_TABLES`` /
# ``0061_repair_sucursal_fk_chain.py::_FK_TABLES``.
_FK_TABLES: tuple[str, ...] = (
    "usuarios_sucursal",
    "tarifas_sucursal",
    "cantidad_vehiculos_sucursal",
    "configuracion_tolerancias",
    "configuracion_seguridad",
    "resolucion_facturacion",
    "subscripciones_cliente",
)


def upgrade() -> None:
    for table in _FK_TABLES:
        op.execute(f"GRANT UPDATE (uuid_sucursal) ON prod.{table} TO rol_app;")


def downgrade() -> None:
    for table in _FK_TABLES:
        op.execute(f"REVOKE UPDATE (uuid_sucursal) ON prod.{table} FROM rol_app;")
