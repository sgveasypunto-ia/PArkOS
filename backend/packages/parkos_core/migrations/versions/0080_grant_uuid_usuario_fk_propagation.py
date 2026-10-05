"""0080_grant_uuid_usuario_fk_propagation -- narrow UPDATE(uuid_usuario) for FK repoint.

Revision ID: 0080_grant_uuid_usuario_fk_propagation
Revises: 0079_fix_empresa_demo_seed_nit_dv
Create Date: 2026-10-05 00:00:00.000000

THE PROBLEM THIS PINS
----------------------
``repo.versioned.close_and_insert`` calls ``repo.admin_usuarios.
propagate_usuario_uuid_to_fks`` after every ``usuarios`` bi-temporal
close+insert -- fired for BOTH a local admin edit (Datos tab save,
password reset) AND a ``cloud_to_branch`` sync apply that ``identity_
reconciler`` reconciles onto an already-open local row via the
``cedula`` natural key (``sync/catalog/entries/sync_entries_v.py::
_USUARIOS``). That helper runs a raw ``UPDATE prod.<table> SET
uuid_usuario = :new WHERE uuid_usuario = :old`` against the 2
user-facing FK tables (``usuarios_sucursal``, ``permisos_usuario`` --
same list as ``repo/admin_usuarios.py::_USUARIO_FK_TABLES``). It runs on
the live ``rol_app``/``parkos_app`` connection, not a migration-time
superuser session -- the exact same class of gap
``0069_grant_uuid_sucursal_fk_propagation.py`` closed for ``Sucursal``'s
own ``propagate_uuid_to_fks``.

``0021_least_privilege_and_immutability_contract.py`` put both tables in
``_NARROW_UPDATE_V_TABLES`` and granted ``UPDATE (vigente_hasta,
estado)`` only. ``uuid_usuario`` was never added to that grant, so EVERY
close+insert of a ``usuarios`` row that already has an open
``usuarios_sucursal`` or ``permisos_usuario`` assignment raises
``asyncpg.exceptions.InsufficientPrivilegeError: permission denied for
table usuarios_sucursal``.

Live defect confirmed in qa/integracion-admin-sucursal (2026-10-05): a
branch operator user was created and assigned to a sucursal in one admin
wizard action, cloud-side. The operator's ``cedula`` happened to collide
with the admin seed user's own ``cedula`` (a QA seed-data artifact,
flagged separately -- see the incident report; NOT fixed by this
migration). When the pair replicated to the branch, ``identity_
reconciler`` matched the arriving ``usuarios`` row onto the admin's
already-open local row via that shared ``cedula`` -- correctly, per its
own natural-key contract -- and attempted the FK repoint, which this
missing grant turned into a permanent, every-cycle
``ProgrammingError:42501`` failure instead of a clean propagation. The
failed ``usuarios`` apply then rolled back inside its own SAVEPOINT,
which is also why the declared-dependent ``usuarios_sucursal`` row
raised its own, separate ``fk_violation`` every cycle (see
``sync/motor/sync_motor.py::SyncMotor.apply_batch`` -- fixed separately
in this same incident to buffer a dependent once its declared parent
fails in the same batch, not just when the parent is itself buffered).

THE FIX
-------
Column-scoped ``GRANT UPDATE (uuid_usuario)`` on both tables, additive to
the existing ``(vigente_hasta, estado)`` grant from 0021 (Postgres
column-level GRANTs accumulate; this does not touch that earlier grant).
``DELETE`` stays revoked -- unaffected by this migration. Deliberately
NOT a widening of the generic sync-motor FK-remap heuristic
(``sync_motor.py::_remap_foreign_keys``/``_remappable_uuid_columns``) --
that mechanism never fired in this incident (its ``aliases`` map is only
populated after a row APPLIES successfully, and the ``usuarios`` row
here never did); this grant unblocks the purpose-built, already-scoped
``propagate_usuario_uuid_to_fks`` hook instead, which is what actually
needs it, on BOTH cloud and branch (either side may run
``close_and_insert`` for a ``usuarios`` row: a branch via sync apply, or
cloud via the admin API's own direct write).
"""
from __future__ import annotations

from alembic import op

revision = "0080_grant_uuid_usuario_fk_propagation"
down_revision = "0079_fix_empresa_demo_seed_nit_dv"
branch_labels = None
depends_on = None

# Keep in sync with ``repo.admin_usuarios._USUARIO_FK_TABLES``.
_FK_TABLES: tuple[str, ...] = (
    "usuarios_sucursal",
    "permisos_usuario",
)


def upgrade() -> None:
    for table in _FK_TABLES:
        op.execute(f"GRANT UPDATE (uuid_usuario) ON prod.{table} TO rol_app;")


def downgrade() -> None:
    for table in _FK_TABLES:
        op.execute(f"REVOKE UPDATE (uuid_usuario) ON prod.{table} FROM rol_app;")
