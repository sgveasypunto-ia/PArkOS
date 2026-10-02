"""0068_usuarios_email_activo_uk -- partial UNIQUE index on email for active rows.

Revision ID: 0068_usuarios_email_activo_uk
Revises: 0067_add_dias_alerta_pre_vencimiento
Create Date: 2026-10-02 00:00:00.000000

THE PROBLEM THIS PINS
---------------------
``create_admin_usuario`` (repo/admin_usuarios.py) guards email uniqueness
with a SELECT-then-INSERT pre-check only, inside the application layer,
with NO backing constraint in the database (``prod.usuarios`` has no
unique index/constraint on ``email`` -- only ``usuarios_uk01`` on
``(cedula, vigente_desde)``, see ``0001_initial_schema.py``). Two
concurrent ``POST /admin/usuarios`` requests with the same ``email``
both read "no active row" before either commits, so both pass the
pre-check and the backend ends up with two ACTIVE ``prod.usuarios`` rows
sharing the same email -- the exact bug the ``EmailYaRegistradoError``
guard was written to prevent, reachable again via a plain race
condition. The same hole exists on ``update_admin_usuario``'s email-edit
path, which previously had NO guard at all.

THE FIX
-------
A partial ``UNIQUE INDEX`` on ``email`` scoped to active rows
(``vigente_hasta IS NULL``) -- same shape as
``0063_fix_tarifas_sucursal_uk01``. Two closed (historical) rows, or a
closed row and a fresh active one, may still share an email; only two
ACTIVE rows cannot. The repo layer's SELECT pre-check remains as the
fast-path UX guard (a clean 409 on the common case); this index is the
backstop the concurrent-request case needs -- the repo layer catches the
resulting ``IntegrityError`` (``asyncpg.exceptions.UniqueViolationError``)
and re-raises it as the same ``EmailYaRegistradoError`` the pre-check
raises, so the HTTP handler's 409 mapping covers both paths identically.

``email`` is nullable on ``prod.usuarios`` (an account may have no
email); PostgreSQL never considers two ``NULL`` values equal under a
UNIQUE index, so multiple active rows with ``email IS NULL`` are
unaffected -- consistent with the repo guard, which only runs its
pre-check ``if email is not None``.

CONCURRENT INDEX (Postgres)
----------------------------
Same caveat as ``0063``: a plain ``CREATE INDEX`` (no ``CONCURRENTLY``)
takes an ACCESS EXCLUSIVE lock on ``prod.usuarios`` during creation.
Acceptable for dev/QA (container restart); a production rollout would
want ``CONCURRENTLY`` run out-of-band of the regular migration sweep.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0068_usuarios_email_activo_uk"
down_revision = "0067_add_dias_alerta_pre_vencimiento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partial UNIQUE index: only ACTIVE rows (``vigente_hasta IS NULL``)
    # are checked for a duplicate ``email``. Closed (historical) rows are
    # excluded, so a user's past email doesn't block a future row from
    # reusing it once the old row is closed.
    op.create_index(
        "usuarios_email_uk01",
        "usuarios",
        ["email"],
        schema="prod",
        unique=True,
        postgresql_where=sa.text("vigente_hasta IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "usuarios_email_uk01",
        table_name="usuarios",
        schema="prod",
    )
