"""0062_canonical_tipos_vehiculo -- canonical 5 tipos (carro, moto, bicicleta, patineta, otro).

THE PROBLEM THIS PINS
---------------------
The ``tipos_vehiculo`` catalog accumulates test garbage over the lifetime
of a dev DB: anyone with ``config_catalogo`` can POST arbitrary strings
to ``/api/v1/catalogos/tipos-vehiculo`` (e.g. ``"barco"``, ``"camion"``,
``"motoo"``). The factory's ``TiposVehiculoCreate`` schema is just
``Annotated[str, StringConstraints(min_length=1, max_length=64)]`` —
no allow-list, no length cap on the catalog itself.

Operational fallout:

* The branch-and-cloud sync replicates every catalog row (catalog level 0
  in sync_entries_v.py:118), so typos propagate to every branch.
* The placa detector (electron-sucursal/src/lib/validation/placa.ts:67)
  hardcodes ``["carro", "moto", "bicicleta", "patineta"]`` — a typo
  (``"motoo"``) silently bypasses it.
* Cupos pointing to garbage tipos render "Desconocido" in the admin
  (apps/web_admin/src/features/cupos/pages/Cupos.tsx:124) because the
  ``tiposVehiculo.find(...)`` lookup misses.

The product canonical set is exactly 5:
``carro``, ``moto``, ``bicicleta``, ``patineta``, ``otro``.

This migration:

1. **Closes** the three known garbage rows (``barco``, ``camion``,
   ``motoo``) via bi-temporal close — ``vigente_hasta = NOW(),
   estado = 'inactivo'``. NO physical DELETE: 5 tables FK-reference
   ``prod.tipos_vehiculo.uuid`` (tarifas_sucursal,
   cantidad_vehiculos_sucursal, vehiculos, ingreso,
   ingreso_consecutivo_contador). Physical DELETE would cascade to
   those and violate the no-DELETE canon. Bi-temporal close keeps the
   row, lets historical references resolve (the cupos pointing to
   ``barco``/``camion``/``motoo`` stay in the FK chain), and excludes
   them from the GET-list filter (``vigente_hasta IS NULL``).

2. **Seeds** ``otro`` as the 5th canonical tipo. Idempotent:
   ``INSERT ... WHERE NOT EXISTS`` so re-running on a DB that already
   has ``otro`` is a no-op. Compatible with a branch that already
   created ``otro`` out-of-band (sync replication + this migration
   converge to the same state).

3. **Doc-only**: updates ``infra/scripts/seed_catalogs.py`` docstring
   to list the 5 canonical tipos (handled in the same PR, not in the
   migration — doc scripts are not migration-managed).

POST-MIGRATION STATE
--------------------
``SELECT tipo, vigente_hasta IS NULL AS activo FROM prod.tipos_vehiculo
 ORDER BY tipo;`` returns the 5 active canonical tipos plus any
historical closed versions (e.g. the closed ``moto`` from a prior
PUT-edit, garbage rows from this migration).

The 5-type cap on creation (409 ``tipos_vehiculo_max_reached``) is
enforced by the dedicated POST handler in
``backend/packages/parkos_core/src/parkos_core/api/v1/catalogos.py``
shipped in the same PR — this migration only cleans existing state.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0062_canonical_tipos_vehiculo"
down_revision = "0061_repair_sucursal_fk_chain"
branch_labels = None
depends_on = None


# Known garbage rows accumulated by dev testing. Identified manually
# from a live cloud-db query on 2026-09-29:
#
#   SELECT tipo, estado, vigente_hasta FROM prod.tipos_vehiculo
#   WHERE tipo NOT IN ('carro','moto','bicicleta','patineta','otro');
#
# The migration is idempotent: if any of these are already closed (the
# post-state from a prior run), the UPDATE matches 0 rows.
_GARBAGE_TIPOS = ("barco", "camion", "motoo")
# The canonical ``moto`` row was closed by a prior PUT-edit (visible as
# ``vigente_hasta IS NOT NULL`` on 2026-09-29 01:38:26). The user's spec
# requires all 5 canonical tipos (carro, moto, bicicleta, patineta, otro)
# to be active simultaneously, so the migration REOPENS ``moto`` by
# closing the stale closed version (a fresh open row already exists from
# the close+insert Carril B — the original edit was a "rename to motoo"
# typo that left moto without an active successor). The reopen is
# idempotent: if moto is already active (post-state from a prior run),
# the INSERT matches 0 rows.
_CANONICAL_REOPEN = ("moto",)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Bi-temporal close on garbage rows. The WHERE clause is defensive:
    # only touches rows that are still ACTIVE (vigente_hasta IS NULL), so
    # a re-run is a no-op. ``estado='inactivo'`` aligns with the close+insert
    # Carril B convention (see backend/.../repo/versioned.py:169-173).
    placeholders = ", ".join(f":t{i}" for i in range(len(_GARBAGE_TIPOS)))
    params = {f"t{i}": v for i, v in enumerate(_GARBAGE_TIPOS)}
    bind.execute(
        text(
            f"""
            UPDATE prod.tipos_vehiculo
               SET vigente_hasta = NOW(),
                   estado        = 'inactivo'
             WHERE tipo IN ({placeholders})
               AND vigente_hasta IS NULL
            """
        ),
        params,
    )

    # 2. Reopen canonical ``moto`` if it ended up closed (Carril B +
    # leave-behind from a prior typo edit). Idempotent: skips when an
    # active moto row already exists. New row inherits server defaults
    # (uuid=gen_random_uuid(), created_at=NOW(), sync_status=pendiente).
    reopen_params = {f"r{i}": v for i, v in enumerate(_CANONICAL_REOPEN)}
    bind.execute(
        text(
            f"""
            INSERT INTO prod.tipos_vehiculo (
                uuid, tipo, vigente_desde, vigente_hasta, estado,
                created_at, created_by, sync_status, sync_attempts
            )
            SELECT
                gen_random_uuid(),
                r.tipo,
                NOW(),
                NULL,
                'activo',
                NOW(),
                NULL,
                'pendiente',
                0
              FROM (VALUES ({", ".join(f"(:r{i})" for i in range(len(_CANONICAL_REOPEN)))}))
                AS r(tipo)
             WHERE NOT EXISTS (
                SELECT 1
                  FROM prod.tipos_vehiculo t2
                 WHERE t2.tipo = r.tipo
                   AND t2.vigente_hasta IS NULL
             )
            """
        ),
        reopen_params,
    )

    # 3. Seed ``otro`` (the 5th canonical tipo). Idempotent: only inserts
    # if no active row for tipo='otro' already exists. The bi-temporal
    # close+insert helper isn't used here because:
    # - the catalog has no overlap / business guards
    # - the row is initial seed, not a "change to an existing tipo"
    # - this migration runs at the SQL level, not the ORM (no session)
    # The resulting row inherits server defaults: uuid=gen_random_uuid(),
    # created_at=NOW(), created_by=NULL, sync_status=pendiente.
    bind.execute(
        text(
            """
            INSERT INTO prod.tipos_vehiculo (
                uuid, tipo, vigente_desde, vigente_hasta, estado,
                created_at, created_by, sync_status, sync_attempts
            )
            SELECT
                gen_random_uuid(),
                'otro',
                NOW(),
                NULL,
                'activo',
                NOW(),
                NULL,
                'pendiente',
                0
             WHERE NOT EXISTS (
                SELECT 1
                  FROM prod.tipos_vehiculo
                 WHERE tipo = 'otro'
                   AND vigente_hasta IS NULL
             )
            """
        )
    )


def downgrade() -> None:
    # Intentionally a no-op: this migration is a data cleanup + seed, both
    # semantically safe to keep after downgrade. Restoring garbage rows
    # would re-introduce the drift the migration was designed to eliminate.
    # Rolling forward is the supported path.
    pass