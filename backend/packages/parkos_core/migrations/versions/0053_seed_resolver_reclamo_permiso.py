"""MIGRATION 0053 -- seed the ``resolver_reclamo`` permission code.

WHY THIS MIGRATION EXISTS
-------------------------
HU-R04 ("Como administrador, quiero marcar un reclamo como ``en_revision``
y luego ``resuelto``/``rechazado``") is the only workflow in the admin
roadmap whose transition has NO permission code in the canonical
catalogue. The other five admin responsibilities already have one:

    HU-R02  users        -> admin_usuarios
    HU-R03  annulment    -> aprobar_anulacion + ejecutar_anulacion
    HU-R05  alert        -> descartar_alerta
    HU-R06  reports      -> ver_reportes
    HU-R07  hash audit   -> audit_read

``resolver_reclamo`` closes that gap. The code is seeded here so the
vocabulary is decided BEFORE the endpoint exists -- exactly the way the
other five were decided. The endpoint that actually gates on it is
HU-R04's own migration, a later PR.

WHY ``WHERE NOT EXISTS`` AND NOT ``ON CONFLICT``
------------------------------------------------
This is the second time this pattern has burned us, so the reasoning is
recorded here rather than left to the next reader.

``prod.permisos`` has UK ``permisos_uk01 (permiso, vigente_desde)``. The
``vigente_desde = NOW()`` is evaluated per-INSERT, so every run of
migration ``0002_seed_permisos_canonicos.py`` produced a DIFFERENT
``vigente_desde`` and its ``ON CONFLICT (permiso, vigente_desde) DO
NOTHING`` never fired. The docstring in ``0002`` asserts the opposite
("this conflict target is exact ... even though we always use the same
instant") and that assertion is simply wrong.

The live cloud DB carries the proof: 46 rows for 31 distinct codes, 15
of them duplicated.

So the rule for this project is: **an ``ON CONFLICT`` whose conflict
target includes ``vigente_desde`` does not do what it looks like it
does.** A bi-temporal UK is a logical-identity key, not a physical
uniqueness constraint, and it cannot be used as an idempotency guard
for a seed. Use an explicit ``WHERE NOT EXISTS`` on the open row
(``vigente_hasta IS NULL``) instead -- that expresses the real intent
("do not seed a code that is already live") and cannot be defeated by a
clock tick.

Idempotency contract: running this migration N times leaves exactly one
open ``resolver_reclamo`` row.

Reversibility: ``downgrade`` CLOSES the row (``vigente_hasta = NOW()``,
``estado = 'inactivo'``) rather than DELETEing it. ``permisos`` is a
``[V]`` table, and the project's no-physical-DELETE canon
(``AGENTS.md`` "API Operation Contract") expresses retraction as a
closed version plus a compensating row, never as a destructive DELETE.
Note that ``0002``'s own ``downgrade`` does issue a DELETE -- that is a
pre-existing canon violation, out of scope here.
"""
from __future__ import annotations

from alembic import op


revision = "0053_seed_resolver_reclamo_permiso"
down_revision = "0052_reimpresion_ticket_forupdate_lock_grant"
branch_labels = None
depends_on = None


# HU-R04: reclamo lifecycle ``nuevo -> en_revision -> resuelto|rechazado``.
NEW_PERMISOS: tuple[str, ...] = ("resolver_reclamo",)


def upgrade() -> None:
    """Seed one row per code, skipping any code that is already live.

    Idempotent by construction: the ``NOT EXISTS`` predicate is evaluated
    against the OPEN row (``vigente_hasta IS NULL``), so a re-run on a
    partially-seeded DB is a no-op for codes already present and still
    seeds the ones that are missing.
    """
    for code in NEW_PERMISOS:
        op.execute(
            f"""
            INSERT INTO prod.permisos (
                uuid, permiso, created_at, created_by,
                vigente_desde, vigente_hasta, estado,
                sync_status, sync_attempts
            )
            SELECT gen_random_uuid(), '{code}', NOW(), NULL,
                   NOW(), NULL, 'activo',
                   'sincronizado', 0
            WHERE NOT EXISTS (
                SELECT 1
                FROM prod.permisos
                WHERE permiso = '{code}'
                  AND vigente_hasta IS NULL
            );
            """
        )


def downgrade() -> None:
    """Retract the code by closing its open version (no physical DELETE).

    Closing rather than deleting keeps the bi-temporal history intact: a
    later re-seed inserts a NEW version whose ``vigente_desde`` opens
    after this ``vigente_hasta``, so the retraction is itself auditable.
    """
    codes_list = ", ".join(f"'{c}'" for c in NEW_PERMISOS)
    op.execute(
        f"""
        UPDATE prod.permisos
        SET vigente_hasta = NOW(),
            estado = 'inactivo'
        WHERE permiso IN ({codes_list})
          AND vigente_hasta IS NULL;
        """
    )


__all__ = ["upgrade", "downgrade"]
