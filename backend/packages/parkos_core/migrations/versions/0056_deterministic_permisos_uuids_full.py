"""MIGRATION 0056 -- extend deterministic permission uuids to every code.

WHY THIS MIGRATION EXISTS
-------------------------
``0019_deterministic_permisos_uuids`` fixed cross-node identity for SIXTEEN
canonical codes by reconciling each one to a fixed ``uuid5`` value. Its own
docstring already named this exact failure mode::

    cloud and a branch each mint their OWN random uuid for e.g.
    "gestionar_clientes" ... any ``permisos_usuario`` grant created on one
    node referencing ITS OWN local uuid can never push to the other
    (guaranteed ForeignKeyViolationError on uuid_permiso -- also confirmed
    live).

The diagnosis was right; the COVERAGE was not. ``0019`` enumerated 16 codes
(``config_catalogo``, ``gestionar_clientes``, ``emitir_factura``, ...). Every
other code the seed creates was still minted with ``gen_random_uuid()``, once
per node, by ``0002_seed_permisos_canonicos`` running INDEPENDENTLY on cloud
and on each branch. Sixteen of the codes converged. The rest never could.

MEASURED, not predicted
-----------------------
Before this migration, comparing the OPEN catalogue row of every code on the
live cloud DB against the live branch DB:

    32 codes on both sides, 0 missing on either side, 15 DIVERGENT

Every one of the 15 followed the same shape -- cloud held the ``19:11:32``
batch, the branch held the ``19:16:38`` batch, and the two batches were
minted with different random uuids. The 16 codes inside ``0019``'s map
already agreed across both nodes, which is the control that confirms the
divergence is exactly "not in the map" and not something else.

CONSEQUENCE OBSERVED LIVE
-------------------------
``job_sync_sucursal`` logged 522 consecutive
``ForeignKeyViolationError`` on ``fk_permisos_usuario_uuid_permiso`` and
retried the same batch forever: cloud grants referenced a ``uuid_permiso``
the branch had never seen. The branch therefore stopped consuming
cloud-to-branch changes entirely.

WHY DETERMINISTIC VALUES INSTEAD OF "CONVERGE ON THE BRANCH'S UUID"
-------------------------------------------------------------------
Re-pointing the cloud's grants at whatever uuid the branch happens to hold
would clear today's foreign keys and leave the defect intact: the value
would still be a random uuid that only one node knows, so the next node
built from scratch diverges again and the bug returns. A ``uuid5`` derived
from a fixed namespace converges EVERY node -- present and future -- on the
identical value for a given code, which is the property the sync actually
needs. This migration therefore extends ``0019``'s existing namespace rather
than inventing a second scheme.

The values below are computed OFFLINE from that same namespace and hardcoded,
never recomputed at migration runtime (mirroring ``0019``; a runtime
``uuid_generate_v5`` would need a ``pgcrypto`` dependency the project does not
carry).

GRANTS ARE RE-POINTED BI-TEMPORALLY, NOT MUTATED IN PLACE
---------------------------------------------------------
``0019`` re-pointed grants with ``UPDATE prod.permisos_usuario SET
uuid_permiso = ...``, rewriting history on a ``[V]`` row. This project
forbids that shape: a ``[V]`` row is never mutated, it is closed and
superseded. ``0055`` already established the correct vocabulary for exactly
this operation, and this migration reuses it -- the old grant version is
closed (``vigente_hasta``, ``estado='inactivo'``) and an equivalent open
version is inserted against the deterministic row. Every grant's valid-time
history survives; nothing is overwritten.

No physical DELETE is performed anywhere. Closed rows remain in the table
forever.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0056_deterministic_permisos_uuids_full"
down_revision = "0055_dedupe_permisos_catalogo"
branch_labels = None
depends_on = None


_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# code -> uuid5(namespace=UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60"), code)
#
# Same namespace as 0019, so the sixteen codes already covered there and the
# sixteen added here form one continuous, consistent scheme. A code already
# present in 0019's map is deliberately NOT repeated here: 0019 owns it, and
# restating a uuid in two migrations invites the two maps to drift apart.
#
# The first fifteen are the codes measured as divergent between the live
# cloud and branch DBs. ``resolver_reclamo`` is included so that a code added
# by a later seed converges on first use instead of minting another random
# uuid on every node that runs it.
_DETERMINISTIC_UUIDS: dict[str, str] = {
    "abrir_cerrar_caja": "7f6eb995-a09a-5c61-aa82-4de7cc874929",
    "administrar_clientes": "21a33fd9-8f87-5545-872a-16c47d6cc0d8",
    "administrar_subscripciones": "92a1590a-53b8-5300-be86-9bfeba825b42",
    "administrar_tarifas": "b1c3a10b-ed98-56b7-880c-56d7ea1a253b",
    "administrar_vehiculos": "a980f8a1-d341-5755-821c-74e97f50fb07",
    "anular_ingreso": "0af47445-b482-592c-bb94-a0762c2f323d",
    "anular_reimpresion": "cf1ced97-d342-5f98-92eb-cf2715f11adb",
    "anular_salida": "77119cd9-8bb6-50dd-ad5b-20c1377b45dc",
    "configurar_sucursal": "01df8441-2fc8-582e-8804-10f27f0df04b",
    "login": "66dcda01-1a55-57ff-a66b-a5ce0799ee14",
    "realizar_arqueo": "b4a461e7-13c9-5a87-9b8f-cfd98c2c4a4f",
    "realizar_ingreso": "bcdc4ef3-631f-504e-aeed-b8e167568d77",
    "realizar_salida": "a56f88b9-9845-574d-98b7-e1c7210a39d4",
    "reimprimir_ticket": "3d538889-1ef1-5867-8aaa-005045c8fc33",
    "ver_reportes": "c0420f4f-921c-5956-a3fa-7be8ddfadbd1",
    "resolver_reclamo": "c363bd61-2634-523d-9ad2-0a1c6696c99c",
}


def upgrade() -> None:
    """Converge every code in the map onto its deterministic uuid.

    Per code, in three ordered steps:

    1. INSERT the deterministic ``permisos`` row if that uuid is not present.
       A plain INSERT of a brand new primary key, so no FK can conflict.
    2. Re-point grants: for every OPEN grant naming a non-deterministic uuid
       of this code, open an equivalent grant on the deterministic row and
       close the superseded version. Both halves happen inside this
       transaction, so the intermediate state (an actor holding two open
       grants for one code) is never externally visible.
    3. Close every non-deterministic open ``permisos`` row for the code.

    A code whose only open row already carries the deterministic uuid is
    skipped entirely, which makes the migration idempotent and makes a
    re-run on an already-converged node a genuine no-op.
    """
    op.execute(_LOCK_TIMEOUT_SQL)
    bind = op.get_bind()

    for codigo, det_uuid in _DETERMINISTIC_UUIDS.items():
        open_uuids = [
            str(u)
            for u in bind.execute(
                text(
                    "SELECT uuid FROM prod.permisos "
                    "WHERE permiso = :codigo AND vigente_hasta IS NULL "
                    "ORDER BY created_at"
                ),
                {"codigo": codigo},
            ).scalars().all()
        ]
        # Nothing to converge: the open row already IS the deterministic one.
        if not open_uuids or open_uuids == [det_uuid]:
            continue
        stale_uuids = [u for u in open_uuids if u != det_uuid]

        # Step 1 -- the deterministic row. A code that has never been seen on
        # this node has no row to copy attributes from, so the description and
        # category fall back to NULL, matching what 0019's copy-from-old-row
        # INSERT would leave for a missing row.
        exists = bind.execute(
            text("SELECT 1 FROM prod.permisos WHERE uuid = :det_uuid"),
            {"det_uuid": det_uuid},
        ).scalar_one_or_none()
        if exists is None:
            bind.execute(
                text(
                    """
                    INSERT INTO prod.permisos
                        (uuid, permiso, vigente_desde, vigente_hasta, estado,
                         created_at, created_by, sync_status, sync_attempts)
                    SELECT :det_uuid, :codigo, clock_timestamp(), NULL, 'activo',
                           clock_timestamp(), NULL, 'sincronizado', 0
                    """
                ),
                {"det_uuid": det_uuid, "codigo": codigo},
            )

        # Step 2 -- re-point grants bi-temporally. Insert first, then close:
        # closing first would drop the access this migration exists to
        # preserve, and the NOT EXISTS guard keeps an actor from ending up
        # with two open grants for the same code.
        bind.execute(
            text(
                """
                INSERT INTO prod.permisos_usuario
                    (uuid, created_at, created_by,
                     vigente_desde, vigente_hasta, estado,
                     sync_status, sync_attempts,
                     uuid_usuario, uuid_permiso)
                SELECT gen_random_uuid(), clock_timestamp(), created_by,
                       clock_timestamp(), NULL, 'activo',
                       'sincronizado', 0,
                       pu.uuid_usuario, :det_uuid
                FROM prod.permisos_usuario pu
                WHERE pu.uuid_permiso = ANY(CAST(:stale AS uuid[]))
                  AND pu.vigente_hasta IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM prod.permisos_usuario ya
                      WHERE ya.uuid_usuario = pu.uuid_usuario
                        AND ya.uuid_permiso = :det_uuid
                        AND ya.vigente_hasta IS NULL
                  )
                """
            ),
            {"det_uuid": det_uuid, "stale": stale_uuids},
        )
        bind.execute(
            text(
                """
                UPDATE prod.permisos_usuario
                SET vigente_hasta = clock_timestamp(), estado = 'inactivo'
                WHERE uuid_permiso = ANY(CAST(:stale AS uuid[]))
                  AND vigente_hasta IS NULL
                """
            ),
            {"stale": stale_uuids},
        )

        # Step 3 -- close the superseded catalogue versions.
        bind.execute(
            text(
                """
                UPDATE prod.permisos
                SET vigente_hasta = clock_timestamp(), estado = 'inactivo'
                WHERE uuid = ANY(CAST(:stale AS uuid[]))
                  AND vigente_hasta IS NULL
                """
            ),
            {"stale": stale_uuids},
        )


def downgrade() -> None:
    """No-op by design.

    The original random uuids were never recorded anywhere, so a reversal
    could not restore them even in principle. Re-deriving some OTHER uuid
    would leave the node diverged from every other node, which is the
    defect. Both the deterministic row and every closed predecessor remain
    in the table with their full valid-time range, so the pre-migration
    state is reconstructable by deliberate query.

    Re-running ``upgrade`` after a future re-divergence repairs the
    catalogue again.
    """
    return


__all__ = ["downgrade", "upgrade"]
