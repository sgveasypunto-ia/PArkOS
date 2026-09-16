"""make the 16 canonical ``permisos`` uuids deterministic (uuid5) —
confirmed real duplicate-uuid defect once real cross-node pull started
working.

Revision ID: 0019_deterministic_permisos_uuids
Revises: 0018_add_default_partitions_pairing_revoked_jwts
Create Date: 2026-09-10 02:00:00.000000

**The bug (confirmed live, real HTTP push+pull against Docker
containers).** ``permisos`` is declared ``direction="cloud_to_branch"``,
``broadcast_policy="all_branches"`` in ``SYNC_CATALOG`` (per
``modelo_datos_er.mmd`` — REQ-CAT-004 — confirmed via
``tests/static/test_check_catalog_drift.py`` that this IS the intended,
documented direction, not a classification mistake). But
``0002_seed_permisos_canonicos.py`` seeds the SAME 16 canonical codes
independently on EVERY node via ``gen_random_uuid()`` — cloud and a branch
each mint their OWN random uuid for e.g. ``"gestionar_clientes"``. Once
``/sync/pull`` actually started delivering rows (this session's other real
fix), cloud's copy landed on the branch ALONGSIDE the branch's own
already-seeded row for the identical code — same permission, two
permanently-different uuids, and any ``permisos_usuario`` grant created on
one node referencing ITS OWN local uuid can never push to the other
(guaranteed ``ForeignKeyViolationError`` on ``uuid_permiso`` — also
confirmed live).

**The fix.** Reconcile every currently-open ``permisos`` row (matched by
``permiso`` code) to a FIXED ``uuid5`` value computed once, offline, from a
private namespace UUID + the code string (never computed at migration
runtime — no ``uuid-ossp``/pgcrypto ``uuid_generate_v5`` dependency, just a
literal per-code mapping) — so every node that ever runs this migration
converges on the IDENTICAL uuid per canonical code, past or future. Cloud's
subsequent pull of a branch's already-reconciled row (or vice versa) then
hits ``apply_guard.row_already_present`` (this session's other real fix)
and correctly no-ops instead of duplicating.

Never rewrites an existing row's ``uuid`` in place — changing a referenced
PRIMARY KEY while a FK still points at the old value violates the
constraint immediately (confirmed live, not theoretical). Instead: INSERT
a brand-new row carrying the deterministic uuid (a plain new row, no FK
conflict possible), redirect every existing ``permisos_usuario`` reference
to it, THEN close every old row for that code — the standard ``[V]``
close+insert shape, expressed in raw SQL since migrations don't import the
ORM/repo layer. Uses ``clock_timestamp()``, not ``NOW()``, for the new
row's ``vigente_desde``/``created_at`` — ``NOW()`` is frozen to
transaction-start (the whole ``alembic upgrade head`` chain runs in one
transaction), which would collide with migration 0002's own ``NOW()``-timed
seed row on the ``(permiso, vigente_desde)`` unique constraint.

Idempotent: re-running against a node already on the deterministic uuid is
a no-op (the ``WHERE uuid = :old_uuid`` matches nothing once ``uuid`` is
already ``:new_uuid``).
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "0019_deterministic_permisos_uuids"
down_revision = "0018_add_default_partitions_pairing_revoked_jwts"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# code -> uuid5(namespace=UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60"), code)
# computed once, offline — never recomputed at migration runtime.
_DETERMINISTIC_UUIDS: dict[str, str] = {
    "config_catalogo": "9cfbb830-d7f0-5582-8af9-923e61d3544d",
    "config_sistema": "8b58837a-e064-5d12-bea8-5d39d41851e3",
    "config_sucursal": "9dc67eab-a2e9-528c-bdc1-e6171a5f7d34",
    "gestionar_clientes": "545d8d8b-4ec7-52d4-a404-37a0c82ebd7a",
    "emitir_factura": "a63d7616-8f73-5fbe-9afd-60593eb05e06",
    "emitir_factura_electronica": "ab925ea7-08eb-52b0-816c-e3cf14951b54",
    "revocar_factura": "b63d9f05-b0e3-59d8-9d27-8dfc3754aedd",
    "gestionar_dian": "cf17d0ef-5297-5c2e-9d42-2a74b93a9de8",
    "audit_read": "ec60cf31-105b-5bdf-8231-af17f415ba2b",
    "admin_usuarios": "0db38ad8-2f78-5399-a8d4-40ff7d531609",
    "aprobar_anulacion": "ce3ec269-5445-55b7-a0de-5774bde109db",
    "ejecutar_anulacion": "a1d5640c-f13e-5bf3-99b9-1b4cb10c0324",
    "crear_arqueo": "5bb9819e-f356-57be-a069-884bb5365a8a",
    "solicitar_reverso": "6893c95e-f1ef-5549-9cd5-28035503cce4",
    "cerrar_sesion": "de8a20a3-a69a-5a1b-9af3-c96f21f59169",
    "descartar_alerta": "3d1cb0aa-8ee6-53f3-b734-c29a6d4d7c92",
}


def upgrade() -> None:
    """Never rewrites an existing row's ``uuid`` in place (changing a
    referenced PRIMARY KEY while a FK still points at the old value
    violates the constraint immediately — confirmed live, this is not
    theoretical). Instead: INSERT the new deterministic row (a plain new
    row, no FK conflict possible), redirect every existing
    ``permisos_usuario`` reference to it, THEN close every old row for
    this code — the standard ``[V]`` close+insert shape, just expressed in
    raw SQL since migrations don't import the ORM/repo layer.

    Handles more than one pre-existing open row per code (this session's
    own manual QA left some live environments with duplicate canonical
    permisos from before this fix existed) by redirecting/closing ALL of
    them, not just one.
    """
    op.execute(_LOCK_TIMEOUT_SQL)
    bind = op.get_bind()

    for codigo, new_uuid in _DETERMINISTIC_UUIDS.items():
        old_rows = (
            bind.execute(
                text(
                    "SELECT uuid FROM prod.permisos "
                    "WHERE permiso = :codigo AND vigente_hasta IS NULL "
                    "ORDER BY created_at"
                ),
                {"codigo": codigo},
            )
            .scalars()
            .all()
        )
        old_uuids = [str(u) for u in old_rows if str(u) != new_uuid]
        if not old_uuids:
            continue

        already_exists = bind.execute(
            text("SELECT 1 FROM prod.permisos WHERE uuid = :new_uuid"),
            {"new_uuid": new_uuid},
        ).scalar_one_or_none()
        if already_exists is None:
            bind.execute(
                text(
                    """
                    INSERT INTO prod.permisos
                        (uuid, permiso, vigente_desde, vigente_hasta, estado,
                         created_at, created_by, sync_status, sync_attempts)
                    SELECT :new_uuid, permiso, clock_timestamp(), NULL, 'activo',
                           clock_timestamp(), created_by, sync_status, sync_attempts
                    FROM prod.permisos WHERE uuid = :old_uuid
                    """
                ),
                {"new_uuid": new_uuid, "old_uuid": old_uuids[0]},
            )

        for old_uuid in old_uuids:
            bind.execute(
                text(
                    "UPDATE prod.permisos_usuario SET uuid_permiso = :new_uuid "
                    "WHERE uuid_permiso = :old_uuid"
                ),
                {"new_uuid": new_uuid, "old_uuid": old_uuid},
            )
            bind.execute(
                text(
                    "UPDATE prod.permisos SET vigente_hasta = clock_timestamp(), estado = 'inactivo' "
                    "WHERE uuid = :old_uuid"
                ),
                {"old_uuid": old_uuid},
            )


def downgrade() -> None:
    """No-op by design.

    Reverting to the ORIGINAL random uuids is neither recoverable (they
    were never recorded) nor desirable (it would just reintroduce the
    cross-node mismatch this migration fixes). A downgrade that ran this
    same mapping in reverse would still leave every node on the SAME
    (deterministic) uuid — indistinguishable from not downgrading at all.
    """
