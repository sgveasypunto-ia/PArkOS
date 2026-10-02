"""0070_grant_configuracion_caja_privileges -- rol_app privileges on configuracion_caja.

Revision ID: 0070_grant_configuracion_caja_privileges
Revises: 0069_grant_uuid_sucursal_fk_propagation
Create Date: 2026-10-02 00:00:00.000000

THE PROBLEM THIS PINS
----------------------
``0066_add_configuracion_caja.py`` created ``prod.configuracion_caja`` (a
``[V]`` bi-temporal table, same shape as ``configuracion_seguridad`` /
``configuracion_tolerancias``) but never granted ``rol_app`` any privilege
on it. ``0001_initial_schema.py``'s blanket ``GRANT SELECT, INSERT, UPDATE,
DELETE ON ALL TABLES IN SCHEMA prod TO rol_app`` is a snapshot taken at
THAT migration's run time -- it does not apply to tables created by later
migrations (there is no ``ALTER DEFAULT PRIVILEGES`` in this project), so
every table added after 0001 must (re-)grant privileges for ``rol_app``
itself. ``0021_least_privilege_and_immutability_contract.py`` did this for
every ``[V]``/``[L]`` table that existed by then (narrow ``UPDATE
(vigente_hasta, estado)``, ``DELETE`` revoked) -- ``configuracion_caja``
didn't exist yet, and ``0066`` never added the equivalent grant.

Net effect: the real ``rol_app``/``parkos_app`` connection the API runs
under has had ZERO privileges on ``prod.configuracion_caja`` since it was
created -- every ``GET``/``POST``/``PUT`` on
``/configuracion/configuracion-caja*`` (including the dedicated
``.../efectiva`` route) 500s with ``asyncpg.exceptions.
InsufficientPrivilegeError: permission denied for table
configuracion_caja``. Live defect found QA-testing the Sucursal detail
"Caja" tab's "Base y redondeo" section (2026-10-02) -- surfaced only after
fixing the UNRELATED route-registration-order bug on the same
``.../efectiva`` endpoint (see ``api/v1/configuracion.py``'s "ROUTE ORDER"
comment), which had been masking this one.

THE FIX
-------
Same narrow-privilege shape ``0021`` gives every other ``[V]`` config
table: ``SELECT``/``INSERT`` unrestricted, ``UPDATE`` scoped to
``(vigente_hasta, estado)`` (bi-temporal close+insert never updates any
other column), ``DELETE`` forbidden (``[V]`` rows are never physically
deleted — AGENTS.md §3).
"""
from __future__ import annotations

from alembic import op

revision = "0070_grant_configuracion_caja_privileges"
down_revision = "0069_grant_uuid_sucursal_fk_propagation"
branch_labels = None
depends_on = None

_TABLE = "configuracion_caja"
_NARROW_UPDATE_COLUMNS = ("vigente_hasta", "estado")


def upgrade() -> None:
    op.execute(f"GRANT SELECT, INSERT ON prod.{_TABLE} TO rol_app;")
    cols_sql = ", ".join(_NARROW_UPDATE_COLUMNS)
    op.execute(f"GRANT UPDATE ({cols_sql}) ON prod.{_TABLE} TO rol_app;")
    op.execute(f"REVOKE DELETE ON prod.{_TABLE} FROM rol_app;")


def downgrade() -> None:
    op.execute(f"REVOKE SELECT, INSERT, UPDATE ON prod.{_TABLE} FROM rol_app;")
