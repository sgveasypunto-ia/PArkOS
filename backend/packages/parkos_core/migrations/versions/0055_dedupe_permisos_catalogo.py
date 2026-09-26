"""MIGRATION 0055 -- collapse duplicate OPEN rows in the permission catalogue.

THE BUG
-------
``0002_seed_permisos_canonicos.py`` seeded the canonical codes with::

    INSERT INTO prod.permisos (...)
    VALUES (..., NOW(), NULL, ...)                 -- vigente_desde = NOW()
    ON CONFLICT (permiso, vigente_desde) DO NOTHING

``permisos_uk01`` is ``(permiso, vigente_desde)``. ``vigente_desde`` was
``NOW()``, re-evaluated per INSERT, so the conflict target could never
match a pre-existing row. Every re-run appended a fresh OPEN version of
all 16 codes. The migration's own docstring claimed this made re-runs a
no-op; it did not.

Measured on the live cloud DB before this migration: 47 OPEN rows for 32
distinct codes. 15 codes carried two OPEN rows each, the earlier batch
stamped ``2026-09-23 19:11:32`` and the later ``19:16:38`` -- two
executions roughly five minutes apart.

The duplicate rows are not cosmetic. They reached the authorization path:
``require_permission`` joined ``permisos_usuario -> permisos`` on
``permiso = codigo`` and called ``scalar_one_or_none()``, so an actor
holding a grant on either copy got ``MultipleResultsFound`` and an
unhandled HTTP 500 on 16 codes. That crash is fixed at the query level in
``auth/permissions.py``; this migration removes the corruption that fed it.

WHY THIS IS NOT A PHYSICAL DELETE
---------------------------------
The no-physical-DELETE canon applies. Duplicates are collapsed by CLOSING
the losing version (``vigente_hasta = NOW()``, ``estado = 'inactivo'``),
which is the project's own close-and-insert vocabulary. Both rows remain
in the table forever and the history is reconstructable.

GRANTS ARE RE-POINTED, NOT DROPPED
----------------------------------
A grant names a specific ``uuid_permiso``. Closing a duplicate row without
migrating the grants that referenced it would silently revoke access, so
before closing the losers this migration re-points every OPEN grant onto
the surviving row: the old grant version is closed and a new one is
inserted, bi-temporally. The actor's effective permission set is therefore
unchanged.

SURVIVOR RULE: OLDEST OPEN ROW WINS
-----------------------------------
Deliberately NOT "the row that happens to carry a grant". That rule reads
intuitively but is UNSTABLE: re-pointing grants changes which rows carry
grants, so a survivor set recomputed mid-migration could shift under the
statements that are using it. ``(vigente_desde ASC, uuid ASC)`` is a pure
function of rows that are not being modified, so all three statements
agree on the same survivor set no matter what order they run in. Grant
re-pointing makes the choice itself irrelevant to the final access set.

Idempotent: after a successful run no code has two OPEN rows, so the
loser set is empty and all three statements no-op. Safe on a branch node
whose catalogue was never duplicated. Verified on the live cloud DB
(15 codes repaired) and the branch DB (0 codes affected, no-op).
"""
from __future__ import annotations

from alembic import op


revision = "0055_dedupe_permisos_catalogo"
down_revision = "0054_grant_admin_all_permissions"
branch_labels = None
depends_on = None


# Shared prologue. Picks one survivor per code -- the OLDEST open row --
# and exposes the rest as the losers to close. Deliberately free of any
# dependency on prod.permisos_usuario so the result cannot shift between
# the three statements below.
_CTE = """
WITH abiertos AS (
    SELECT uuid, permiso, vigente_desde
    FROM prod.permisos
    WHERE vigente_hasta IS NULL
),
ranked AS (
    SELECT uuid,
           permiso,
           row_number() OVER (
               PARTITION BY permiso
               ORDER BY vigente_desde ASC, uuid ASC
           ) AS rn
    FROM abiertos
),
ganador AS (
    SELECT DISTINCT ON (permiso) permiso, uuid AS sobreviviente
    FROM ranked
    ORDER BY permiso, rn
),
perdedores AS (
    SELECT r.uuid, r.permiso
    FROM ranked r
    JOIN ganador g ON g.permiso = r.permiso
    WHERE r.rn > 1
)
"""


def upgrade() -> None:
    """Re-point grants onto the survivor, then close the losing versions.

    Order matters and is the reverse of the obvious reading: the new grant
    is inserted BEFORE the old one is closed, because the re-point reads
    the still-open grants on the losing rows. Within the migration
    transaction the intermediate state (an actor holding two open grants
    for the same code) is never externally visible.
    """
    # Step 1 -- re-point. For every open grant sitting on a losing row,
    # open an equivalent grant on the survivor. The NOT EXISTS guard is
    # mandatory: permisos_usuario_uk01 is
    # (uuid_usuario, uuid_permiso, vigente_desde), and vigente_desde is
    # NOW(), so an ON CONFLICT on that target is inert and would append
    # yet another duplicate. The guard also correctly skips the insert
    # when the actor already holds an open grant on the survivor.
    op.execute(
        f"""
        {_CTE}
        INSERT INTO prod.permisos_usuario (
            uuid, created_at, created_by,
            vigente_desde, vigente_hasta, estado,
            sync_status, sync_attempts,
            uuid_usuario, uuid_permiso
        )
        SELECT gen_random_uuid(), NOW(), NULL,
               NOW(), NULL, 'activo',
               'sincronizado', 0,
               pu.uuid_usuario, g.sobreviviente
        FROM prod.permisos_usuario pu
        JOIN perdedores pe ON pe.uuid = pu.uuid_permiso
        JOIN ganador g ON g.permiso = pe.permiso
        WHERE pu.vigente_hasta IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM prod.permisos_usuario ya
              WHERE ya.uuid_usuario = pu.uuid_usuario
                AND ya.uuid_permiso = g.sobreviviente
                AND ya.vigente_hasta IS NULL
          );
        """
    )

    # Step 2 -- close the superseded grant versions.
    op.execute(
        f"""
        {_CTE}
        UPDATE prod.permisos_usuario pu
        SET vigente_hasta = NOW(),
            estado = 'inactivo'
        FROM perdedores pe
        WHERE pu.uuid_permiso = pe.uuid
          AND pu.vigente_hasta IS NULL;
        """
    )

    # Step 3 -- close the losing catalogue versions. The losing row is
    # version history, not the current state of the code.
    op.execute(
        f"""
        {_CTE}
        UPDATE prod.permisos p
        SET vigente_hasta = NOW(),
            estado = 'inactivo'
        FROM perdedores pe
        WHERE p.uuid = pe.uuid
          AND p.vigente_hasta IS NULL;
        """
    )


def downgrade() -> None:
    """Intentionally a no-op -- the inverse is the bug.

    The semantic inverse of "collapse duplicate open versions" is "re-open
    every losing version", which recreates exactly the state that made
    ``require_permission`` raise HTTP 500. There is no marker column that
    identifies which rows this migration closed (``created_by`` is NULL
    for every seed-inserted row, and ``sync_status`` / ``sync_attempts``
    are shared with runtime updates), so a scoped reversal is not
    expressible without inventing schema for a single rollback path.

    Both rows of every collapsed pair remain in the table with their full
    valid-time range, so the pre-migration state is fully reconstructable
    by a deliberate query -- it is simply not the state this table should
    be rolled back to. Re-running ``upgrade`` after any future
    re-duplication repairs the catalogue again.
    """
    return None


__all__ = ["upgrade", "downgrade"]
