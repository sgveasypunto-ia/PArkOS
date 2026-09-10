"""make ``tipo_persona`` and ``empresa`` uuids deterministic (uuid5) — the
same real cross-node identity defect migration 0019 fixed for ``permisos``,
confirmed live for these two tables while running the full test suite
against a freshly-rebuilt cloud+branch Docker stack (2026-09-10).

Revision ID: 0020_deterministic_tipo_persona_empresa_uuids
Revises: 0019_deterministic_permisos_uuids
Create Date: 2026-09-10 04:50:00.000000

**The bug.** ``0001_initial_schema.py`` seeds both ``tipo_persona``
(``natural``/``juridica``) and the single ``empresa`` row independently on
EVERY node via ``gen_random_uuid()`` — exactly the pattern 0019's docstring
already documents for ``permisos``. Both tables are real ``SYNC_CATALOG``
entries (``clientes.uuid_tipo_persona``, ``sucursal.uuid_empresa`` are real
FK-enforced columns), so backfilling/pulling a ``clientes`` or ``sucursal``
row from one node to another carries the ORIGIN's random ``uuid_tipo_
persona``/``uuid_empresa`` value — which the destination's OWN
independently-seeded ``tipo_persona``/``empresa`` rows never have,
guaranteed ``ForeignKeyViolationError`` (confirmed live: 3 different real
integration tests hit exactly this — ``test_e2e_full_catalog_sync``,
``test_offline_numbering_reconciliation_on_reconnect``,
``test_snapshot_columns_immutable_on_catalog_mutation`` — the moment they
backfilled ``clientes`` or ``sucursal`` across two independently-migrated
databases).

**The fix.** Identical mechanics to 0019, generalized to two tables with
different natural keys (``tipo_persona.tipo``; ``empresa.nit``): reconcile
every currently-open row (matched by its natural key) to a fixed ``uuid5``
computed once, offline, from the SAME private namespace UUID 0019 uses —
so a node that has already run 0019 and a node running this for the first
time still converge on the identical uuid per code. Never rewrites a
referenced PRIMARY KEY in place (confirmed live in 0019: violates the FK
immediately) — insert the new deterministic row, redirect every dependent
FK reference (``clientes.uuid_tipo_persona``, ``sucursal.uuid_empresa``),
then close the old row(s).

Idempotent: re-running against a node already on the deterministic uuid is
a no-op, same as 0019.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "0020_deterministic_tipo_persona_empresa_uuids"
down_revision = "0019_deterministic_permisos_uuids"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# code -> uuid5(namespace=UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60"), code)
# — the SAME namespace 0019 uses — computed once, offline, never at
# migration runtime.
_TIPO_PERSONA_DETERMINISTIC_UUIDS: dict[str, str] = {
    "natural": "9ff893fd-e771-5b6a-8b18-6648e47c69d9",
    "juridica": "b6e77ae6-744e-5c72-8653-75e898decd3e",
}

# keyed by `nit` (empresa's actual natural key, per empresa_uk01) rather
# than a synthetic "singleton" marker — the seeded demo row's nit is the
# one stable value every node's copy of this migration shares.
_EMPRESA_DETERMINISTIC_UUIDS: dict[str, str] = {
    "900000000-0": "11de9b03-8be3-5688-93e1-d283b6557f70",
}


def _reconcile_table(
    bind,
    *,
    table: str,
    key_column: str,
    deterministic_uuids: dict[str, str],
    dependent_fk_columns: tuple[tuple[str, str], ...],
) -> None:
    """Shared reconciliation shape (0019's ``upgrade`` body, generalized).

    ``dependent_fk_columns`` is a tuple of ``(dependent_table, fk_column)``
    pairs to redirect before closing the old row(s) — mirrors 0019's own
    single-table ``permisos_usuario`` redirect, just for however many
    dependents a given table actually has.
    """
    for key_value, new_uuid in deterministic_uuids.items():
        old_rows = (
            bind.execute(
                text(
                    f"SELECT uuid FROM prod.{table} "
                    f"WHERE {key_column} = :key_value AND vigente_hasta IS NULL "
                    "ORDER BY created_at"
                ),
                {"key_value": key_value},
            )
            .scalars()
            .all()
        )
        old_uuids = [str(u) for u in old_rows if str(u) != new_uuid]
        if not old_uuids:
            continue

        already_exists = bind.execute(
            text(f"SELECT 1 FROM prod.{table} WHERE uuid = :new_uuid"),
            {"new_uuid": new_uuid},
        ).scalar_one_or_none()
        if already_exists is None:
            bind.execute(
                text(
                    f"""
                    INSERT INTO prod.{table}
                        (uuid, {key_column}, vigente_desde, vigente_hasta, estado,
                         created_at, created_by, sync_status, sync_attempts)
                    SELECT :new_uuid, {key_column}, clock_timestamp(), NULL, 'activo',
                           clock_timestamp(), created_by, sync_status, sync_attempts
                    FROM prod.{table} WHERE uuid = :old_uuid
                    """
                ),
                {"new_uuid": new_uuid, "old_uuid": old_uuids[0]},
            )

        for old_uuid in old_uuids:
            for dependent_table, fk_column in dependent_fk_columns:
                bind.execute(
                    text(
                        f"UPDATE prod.{dependent_table} SET {fk_column} = :new_uuid "
                        f"WHERE {fk_column} = :old_uuid"
                    ),
                    {"new_uuid": new_uuid, "old_uuid": old_uuid},
                )
            bind.execute(
                text(
                    f"UPDATE prod.{table} SET vigente_hasta = clock_timestamp(), estado = 'inactivo' "
                    "WHERE uuid = :old_uuid"
                ),
                {"old_uuid": old_uuid},
            )


def upgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)
    bind = op.get_bind()

    _reconcile_table(
        bind,
        table="tipo_persona",
        key_column="tipo",
        deterministic_uuids=_TIPO_PERSONA_DETERMINISTIC_UUIDS,
        dependent_fk_columns=(("clientes", "uuid_tipo_persona"),),
    )
    _reconcile_table(
        bind,
        table="empresa",
        key_column="nit",
        deterministic_uuids=_EMPRESA_DETERMINISTIC_UUIDS,
        dependent_fk_columns=(("sucursal", "uuid_empresa"),),
    )


def downgrade() -> None:
    """No-op by design — same reasoning as 0019's downgrade."""
