"""0065_add_usuarios_must_change -- must-change flag on password reset.

THE PROBLEM THIS PINS
---------------------
HU-F16's reset-password endpoint (``POST /admin/usuarios/{uuid}/reset-password``)
writes a 12-char temporary bcrypt hash to ``prod.usuarios.password_hash``
and tells the caller, in the response message, that the operator
"must change it on next login". The system did not enforce that
promise. The login handler compared the bcrypt, issued a normal
``TokenPair``, and never looked at whether the password was
temporary -- the operator could use the temporary password forever
until the next reset.

This migration adds the column the handler needs to make the
enforcement honest. Existing open rows receive ``false`` (the
default); only the close+insert path in ``reset_admin_password``
writes ``true``, and only ``POST /auth/cambiar-password`` clears it
back to ``false``.

WHY A COLUMN AND NOT A DERIVED CHECK
------------------------------------
The information is reachable from ``log_transaccional.accion='reset_password'``
plus ``usuarios.fecha_cambio_password``. We chose not to do that
because:

1. The derived check is invisible to the schema. CI tooling
   (``openspec/scripts/check_schema_match.py``) cannot assert the
   invariant because the data is in two unrelated tables.
2. The derived check assumes ``log_transaccional`` is never purged.
3. The login handler would need an extra round trip per login.

WHY ``NOT NULL DEFAULT false`` AND NOT A NULLABLE COLUMN
--------------------------------------------------------
A nullable flag with a sentinel meaning "unknown / not set" invites
every future caller to handle the unknown. There is no unknown.
Every existing row has a definitive answer: the password was not
issued by an admin reset, so it is not temporary. ``DEFAULT false``
writes that answer automatically. New rows via ``close_and_insert``
carry ``False`` from the inherited column unless the close+insert
explicitly writes ``True``.

WHY NO REVOKE / TRIGGER / RLS CARVE-OUT
--------------------------------------
``prod.usuarios`` is ``[V]`` (Versioned -- bi-temporal close+insert).
The audit-first contract only applies REVOKE / DELETE constraints
and ``_inmutable`` triggers on ``[A]`` (Append-only / source-of-truth)
tables. ``[V]`` rows are routinely updated via close+insert. The
new ``debe_cambiar_password`` column lives under that same protection;
no additional constraint is required.
"""
from alembic import op
from sqlalchemy import text

revision = "0065_add_usuarios_must_change"
down_revision = "0064_ensure_forward_partitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            "ALTER TABLE prod.usuarios "
            "ADD COLUMN IF NOT EXISTS debe_cambiar_password boolean "
            "NOT NULL DEFAULT false"
        )
    )


def downgrade() -> None:
    """Drop the column.

    Reversibility caveat: closing+inserted rows with
    ``debe_cambiar_password=true`` lose that signal on down-migration.
    This migration SHOULD NOT be downgraded in production where
    operators may still hold temporary passwords that should be
    flagged.
    """
    bind = op.get_bind()
    bind.execute(
        text(
            "ALTER TABLE prod.usuarios "
            "DROP COLUMN IF EXISTS debe_cambiar_password"
        )
    )