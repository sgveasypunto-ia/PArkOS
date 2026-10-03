"""0072_grant_v_factura_electronica_acuse_select -- rol_app SELECT on the FE ack view.

Revision ID: 0072_grant_v_factura_electronica_acuse_select
Revises: 0071_seed_tipo_tarifa_modalidades
Create Date: 2026-10-02 00:00:00.000000

THE PROBLEM THIS PINS
----------------------
``0009_add_derived_read_views.py`` created ``prod.v_clientes_actual``,
``prod.v_vehiculos_actual`` and ``prod.v_factura_electronica_acuse``, and
its docstring claims "views are not subject to the [A]-table REVOKE
discipline ... PostgreSQL views inherit permissions from the underlying
relations" -- true for the VIEW OWNER's access to the base tables, false
for any OTHER role's access to the view itself. A non-owner role still
needs its own ``GRANT SELECT`` on the view object, exactly like any other
relation. ``0001_initial_schema.py``'s one-time ``GRANT SELECT, INSERT,
UPDATE, DELETE ON ALL TABLES IN SCHEMA prod TO rol_app`` is a snapshot --
this project has no ``ALTER DEFAULT PRIVILEGES``, so it never applied to
these views (created later, by migration 0009).

Net effect: the real ``rol_app``/``parkos_app`` connection the admin API
runs under has had ZERO privilege on ``prod.v_factura_electronica_acuse``
since it was created -- every call to
``GET /api/v1/admin/reporteria/fe`` 500s with ``asyncpg.exceptions.
InsufficientPrivilegeError: permission denied for view
v_factura_electronica_acuse``. Live defect found QA-testing Reportería
financiera's "FE" tab (2026-10-02) -- same root-cause shape as
``0070_grant_configuracion_caja_privileges.py`` (a table missing its
post-0001 grant), just on a view instead of a table.

Scope: only ``v_factura_electronica_acuse`` -- the one this QA batch's
live endpoint actually hits through the ``rol_app``-constrained
connection. ``v_clientes_actual``/``v_vehiculos_actual`` share the same
gap but have no live reproduction in this batch (identity-reconciler sync
jobs appear to query them under a different, unconstrained role) and are
out of scope here.

THE FIX
-------
``GRANT SELECT`` to ``rol_app`` (the group role from ``0021``'s
least-privilege model, not the ``parkos_app`` login role directly --
``parkos_app`` already inherits ``rol_app`` via ``GRANT rol_app TO
parkos_app;``). Read-only view: no INSERT/UPDATE/DELETE is meaningful.
"""
from __future__ import annotations

from alembic import op

revision = "0072_grant_v_factura_electronica_acuse_select"
down_revision = "0071_seed_tipo_tarifa_modalidades"
branch_labels = None
depends_on = None

_VIEW = "v_factura_electronica_acuse"


def upgrade() -> None:
    op.execute(f"GRANT SELECT ON prod.{_VIEW} TO rol_app;")


def downgrade() -> None:
    op.execute(f"REVOKE SELECT ON prod.{_VIEW} FROM rol_app;")
