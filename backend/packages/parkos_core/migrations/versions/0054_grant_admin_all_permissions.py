"""MIGRATION 0054 -- grant every live permission code to the active admin.

BUG REAL
--------
``admin@parkos.local`` could log in successfully and then received HTTP
403 on every ``permission_required``-gated route. The cause is not a
missing grant on the row that login resolves -- it is that the row login
resolves never received one.

``auth.py`` resolves the actor with::

    select(Usuarios).where(
        Usuarios.email == payload.email,
        Usuarios.vigente_hasta.is_(None),
    ).scalar_one_or_none()

and ``require_permission`` authorizes with::

    PermisosUsuario.vigente_hasta.is_(None) AND Permisos.permiso == codigo

Both filter on the OPEN version. The live cloud DB holds SEVEN rows for
``admin@parkos.local``, all sharing ``cedula = '1234567890'``, created
between 19:23:13 and 20:09:13 on 2026-09-23 -- roughly 46 minutes, i.e.
seven runs of ``infra/scripts/bootstrap_pairing.py``. Six are closed
(``estado='inactivo'``) and each carries 7 grants; the seventh is open and
carries ZERO.

The grants went to the wrong row because two defects compounded:

1. ``ensure_admin_user`` inserts with ``ON CONFLICT (cedula, vigente_desde)
   DO NOTHING``. ``usuarios_uk01`` is ``(cedula, vigente_desde)`` and
   ``vigente_desde = NOW()`` is re-evaluated per INSERT, so the conflict
   target never matches and every run appends another version.
2. The grant loop then resolves the target with
   ``SELECT uuid FROM prod.usuarios WHERE email = %s LIMIT 1`` -- no
   ``ORDER BY``, so the row returned is whichever one the planner likes,
   not the open one.

Result: the bootstrap script grants 7 permissions and the admin can use
none of them. This migration does NOT repeat that mistake.

WHY ``rol = 'admin'`` AND NOT A HARDCODED EMAIL
-----------------------------------------------
``bootstrap_pairing.py`` is a dev script, but a migration ships to every
environment. Targeting ``rol = 'admin'`` expresses the actual policy --
"an admin holds every permission the catalogue defines" -- and stays
correct in prod, staging and CI alike. Hardcoding ``admin@parkos.local``
would silently no-op in any environment where the admin has a different
address, reintroducing the same invisible-failure class.

SECURITY POSTURE (read this before widening it)
------------------------------------------------
This is deliberately NOT least-privilege. The data model has no
``superadmin`` concept and ``rol`` carries no CHECK constraint, so
"admin gets everything" is the only coherent reading available today.
It is the correct call for dev and staging, where seeding every code
keeps the RBAC surface exercisable.

It is NOT what you want in production. Before this reaches prod, either
narrow the predicate to an explicit code list, or add the
``superadmin`` role to the model and grant that instead. The predicate is
deliberately isolated at the bottom of this file so that narrowing it is
a one-place change.

Additive by construction: this migration INSERTs ``permisos_usuario``
rows and never touches an existing one. ``operador@parkos.local`` keeps
all 47 of its grants, closed and open, untouched.
"""
from __future__ import annotations

from alembic import op


revision = "0054_grant_admin_all_permissions"
down_revision = "0053_seed_resolver_reclamo_permiso"
branch_labels = None
depends_on = None


# The role whose open rows receive every live permission code. Narrow this
# to an explicit `p.permiso IN (...)` list for a least-privilege deployment.
ADMIN_ROLE_PREDICATE = "u.rol = 'admin'"


def upgrade() -> None:
    """Grant every live permission to every open admin.

    Idempotent: the ``NOT EXISTS`` predicate tests for an already-open
    grant on the same ``(uuid_usuario, uuid_permiso)`` pair. Running this
    N times converges on exactly one open grant per (admin, code) pair,
    which is what ``require_permission`` needs.

    A no-op on databases with no open admin -- so this is safe to apply to
    a branch node that has never been bootstrapped.

    Grants resolve through ``DISTINCT ON (permiso)`` rather than a plain
    ``CROSS JOIN prod.permisos``. A cross join emits one grant per
    physical CATALOG ROW, and the live cloud DB carries 47 rows for 32
    distinct codes -- the duplicate-version damage left by
    ``0002_seed_permisos_canonicos.py``'s broken ``ON CONFLICT``. Joining
    on distinct codes keeps this migration correct regardless of catalog
    hygiene, and the ``ORDER BY permiso, vigente_desde DESC`` picks the
    LATEST version of each code, which is the correct bi-temporal answer
    to "what is this permission right now".
    """
    op.execute(
        f"""
        INSERT INTO prod.permisos_usuario (
            uuid, created_at, created_by,
            vigente_desde, vigente_hasta, estado,
            sync_status, sync_attempts,
            uuid_usuario, uuid_permiso
        )
        SELECT gen_random_uuid(), NOW(), NULL,
               NOW(), NULL, 'activo',
               'sincronizado', 0,
               u.uuid, p.uuid
        FROM prod.usuarios u
        CROSS JOIN (
            SELECT DISTINCT ON (permiso) uuid, permiso
            FROM prod.permisos
            WHERE vigente_hasta IS NULL
              AND permiso IS NOT NULL
            ORDER BY permiso, vigente_desde DESC
        ) p
        WHERE {ADMIN_ROLE_PREDICATE}
          AND u.vigente_hasta IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM prod.permisos_usuario pu
              WHERE pu.uuid_usuario = u.uuid
                AND pu.uuid_permiso = p.uuid
                AND pu.vigente_hasta IS NULL
          );
        """
    )
    _close_grants_on_closed_principals()


def _close_grants_on_closed_principals() -> None:
    """Close grants whose principal version is closed (step 2 of 2).

    The bootstrap bug left 28 dangling grants: four CLOSED ``admin``
    versions, each carrying 7 grants that were never closed with their
    principal. They are inert for authorization -- ``auth.py`` resolves
    the actor with ``vigente_hasta IS NULL``, so a closed version can
    never become ``actor_uuid``, and ``require_permission`` matches on
    that uuid.

    They are still a live hazard. Any query that joins ``permisos_usuario``
    to ``usuarios`` without also filtering ``usuarios.vigente_hasta IS
    NULL`` returns a count inflated by them. That is not hypothetical:
    while writing the verification for this migration, a
    ``count(*) ... WHERE u.email = 'admin@parkos.local'`` reported 60
    grants for an admin who holds 32, because it spanned all seven user
    versions. A mis-scoped admin screen or audit query is exactly where
    that number would surface and be believed.

    Closing them makes "open grant" mean "grant belonging to a live
    principal", which is the invariant the rest of the system assumes.

    Scoped to closed principals of ANY role, which is the correct general
    rule. It cannot strip authority from a live principal by definition,
    and ``operador@parkos.local`` has a single open version with no
    closed versions, so its grants are untouched.
    """
    op.execute(
        """
        UPDATE prod.permisos_usuario
        SET vigente_hasta = NOW(),
            estado = 'inactivo'
        WHERE vigente_hasta IS NULL
          AND uuid_usuario IN (
              SELECT uuid FROM prod.usuarios
              WHERE vigente_hasta IS NOT NULL
          );
        """
    )


def downgrade() -> None:
    """Close every open admin grant (no physical DELETE).

    This is the semantic inverse of ``upgrade``: "an admin holds all
    permission codes" becomes "an admin holds none". It is deliberately
    NOT scoped to the rows this migration opened.

    Why not scoped: a narrower predicate would have to identify rows by
    their creation marker, and there isn't a usable one --
    ``created_by`` is NULL for every seed-inserted grant (this
    migration and ``bootstrap_pairing.py`` alike), and
    ``sync_status``/``sync_attempts`` are shared with runtime updates.
    Rather than invent a marker column for a single rollback path, the
    downgrade states the honest inverse.

    This is safe in practice: a pre-migration admin held either 0 grants
    (the bootstrap bug this migration fixes) or 7 (whatever
    ``REQUIRED_PERMISSIONS`` last managed to attach), and neither is a
    state worth preserving through a rollback.

    Per the no-physical-DELETE canon, retraction CLOSES the version.
    A later re-run of ``upgrade`` inserts fresh versions whose
    ``vigente_desde`` opens after this ``vigente_hasta``, so the
    retraction stays auditable and the admin can be re-granted without
    a destructive operation.
    """
    op.execute(
        """
        UPDATE prod.permisos_usuario
        SET vigente_hasta = NOW(),
            estado = 'inactivo'
        WHERE vigente_hasta IS NULL
          AND uuid_usuario IN (
              SELECT uuid FROM prod.usuarios
              WHERE rol = 'admin' AND vigente_hasta IS NULL
          );
        """
    )


__all__ = ["upgrade", "downgrade"]
