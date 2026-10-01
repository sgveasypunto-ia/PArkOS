"""MIGRATION 0061 -- repair Sucursal FK chain after bi-temporal edits.

THE DEFECT THIS PINS
--------------------
``backend/packages/parkos_core/src/parkos_core/repo/versioned.py::close_and_insert``
**regenerates a new UUID per version** when performing bi-temporal close+insert.
The PK of ``prod.sucursal`` is single-column ``uuid`` (not composite
``(uuid, vigente_desde)``), so the new row's server-default
``gen_random_uuid()`` produces a UUID different from the closed row's.

Every FK pointing to ``prod.sucursal`` carries the OLD UUID. After an edit,
the OLD row carries ``vigente_hasta IS NOT NULL``; the new active row carries
a NEW UUID that NO FK in the system points to. The consequences:

* ``admin_views.list_sucursales`` filters ``if row.uuid not in permitidas:
  continue`` -- the admin's JWT ``sucursales_permitidas`` was issued with the
  OLD UUID; the new UUID is invisible to the picker. **User-reported 2026-09-28**:
  editing E2E-NORTE twice made it disappear from the branch picker.
* 48 FK references to ``prod.sucursal`` (operational: ``ingreso``, ``salidas``,
  ``factura_*``, ``arqueo``, ``caja``, ``sync_*``, ``usuarios_sucursal``,
  ``tarifas_sucursal``, ``cantidad_vehiculos_sucursal``, ``subscripciones_cliente``,
  ``configuracion_*``, ``resolucion_facturacion``, ``pairing_tokens``, etc.)
  carry stale UUIDs. Queries JOINing ``prod.sucursal s ON s.uuid = i.uuid_sucursal
  WHERE s.vigente_hasta IS NULL`` silently miss data after every edit.

WHY NOW (2026-09-28) AND NOT EARLIER
------------------------------------
The smoke + QA seeds create Sucursal rows but almost never PUT-edit them.
The 2026-09-28 admin edit of E2E-NORTE was the first local admin PUT
on Sucursal in this DB, exposing the pre-existing architectural gap.

WHY NOT FIX THE ROOT CAUSE IN THIS MIGRATION
-------------------------------------------
The root-cause fix is to make the PK bi-temporal
(``(uuid, vigente_desde)`` instead of ``uuid`` alone), which would require
changing 48 FK constraints, every ``vigente_hasta IS NULL`` filter, every
JOIN, every test that asserts ``new_row.uuid != old_row.uuid``. Estimated
500-1000 LOC across multiple PRs. **Out of scope** for the immediate
operational unblock. The architectural fix lives in follow-up work.

WHAT THIS MIGRATION DOES (AND DOES NOT)
----------------------------------------
**Does:** one-shot data fix that walks the Sucursal version chain
(closed version -> successor -> ... -> open version) and repoints every
FK row in 7 tables where the FK column carries a now-stale closed
Sucursal UUID. The 7 tables chosen are the ones where the admin
explicitly interacts with FK data via the UI:

* ``prod.usuarios_sucursal`` -- drives ``sucursales_permitidas`` claim.
* ``prod.tarifas_sucursal`` -- admin CRUD via the Tarifas page.
* ``prod.cantidad_vehiculos_sucursal`` -- admin CRUD via the Cupos page.
* ``prod.configuracion_tolerancias`` -- admin CRUD.
* ``prod.configuracion_seguridad`` -- admin CRUD.
* ``prod.resolucion_facturacion`` -- admin CRUD.
* ``prod.subscripciones_cliente`` -- drives the suscripcion flow.

NOTE: ``pairing_tokens`` is deliberately EXCLUDED. It is an ``[A]``
(append-only) table with ``REVOKE UPDATE`` + the
``fn_pairing_tokens_inmutable()`` trigger -- AGENTS.md §1 audit-first
canon forbids corrections via UPDATE on ``[A]`` tables. Pairing
tokens reference the Sucursal UUID at issuance time; an admin that
issued a token, then later edited the branch, leaves the token
pointing at the closed UUID. That's accepted: a branch operator who
pairs with a stale token sees a clean validation error (the
POST /sync/pair flow re-validates the FK at consume time and rejects
with 404 -- the closed Sucursal row still exists, but admin_views
filters it out of ``sucursales_permitidas``). Forcing a token
repoint would require compensating rows, not UPDATE.

**Does NOT:** the 40+ operational tables (``ingreso``, ``salidas``,
``facturas``, ``arqueo``, ``caja``, ``sync_*``, ``login``, ``sesion``,
etc.) keep their OLD Sucursal UUID -- the OLD row in ``prod.sucursal``
still EXISTS (just closed), so the FK is still satisfied; queries
filtering ``s.vigente_hasta IS NULL`` on those JOINs need a separate fix
to look up the current version by ``(uuid_tipo_sucursal, vigente_hasta IS
NULL)`` or similar. That's the operational-data side of the same gap
and lives in follow-up work.

The recursive CTE walks: starting from each row in the chosen tables,
find the successor (closed-version `vigente_hasta` matches
next-version `vigente_desde`), repeat until reaching a row with
``vigente_hasta IS NULL``. UPDATE the FK column to the final successor.

IDEMPOTENCY
-----------
The CTE selects only FK rows whose current FK UUID points to a Sucursal
row with ``vigente_hasta IS NOT NULL`` (i.e., a closed version). Once
the migration runs, every FK points to an open Sucursal row, so a re-run
UPDATEs 0 rows.

DOWNGRADE
---------
A downgrade would need to snapshot the pre-migration FK state. Not
worth the disk + complexity for a one-shot data fix -- the FK rewrites
are semantically correct (they restore the invariant "every FK points
to the current version of the referenced [V] row"), so a rollback to
the broken state would itself be a regression. The DOWNGRADE is a no-op
that documents this.

AFTER THIS MIGRATION
--------------------
* Run ``alembic upgrade head`` on cloud-db.
* Force-relogin every active admin/operator session -- their JWT carries
  the OLD ``sucursales_permitidas`` claim (signed payload, can't be
  patched server-side without a revocation). New login rebuilds the
  claim from the now-correct DB state.
* Prevention: ``backend/.../repo/versioned.py::close_and_insert`` has a
  post-flush call into ``repo.sucursal.propagate_uuid_to_fks`` that
  handles the same FK repoint on every future Sucursal edit. Without it,
  the next admin PUT re-introduces the gap.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0061_repair_sucursal_fk_chain"
down_revision = "0059_seed_router_permission_codes"
branch_labels = None
depends_on = None


# The 7 FK tables that the admin explicitly interacts with and that drive
# the symptoms (picker invisible, edit page 404, etc.). The other 40+
# FKs stay pinned to their original (closed) Sucursal UUID because the
# row still exists in prod.sucursal; the JOIN-vs-vigente_hasta mismatch
# is a separate, larger fix.
#
# NOTE: ``pairing_tokens`` is deliberately EXCLUDED. It is an ``[A]``
# (append-only) table with ``REVOKE UPDATE`` + the
# ``fn_pairing_tokens_inmutable()`` trigger -- AGENTS.md §1 audit-first
# canon forbids corrections via UPDATE on ``[A]`` tables. Pairing
# tokens reference the Sucursal UUID at issuance time; an admin that
# issued a token, then later edited the branch, leaves the token
# pointing at the closed UUID. That's accepted: a branch operator who
# pairs with a stale token sees a clean validation error (the
# POST /sync/pair flow re-validates the FK at consume time and rejects
# with 404 -- the closed Sucursal row still exists, but admin_views
# filters it out of ``sucursales_permitidas``). Forcing a token
# repoint would require compensating rows, not UPDATE.
_FK_TABLES: tuple[tuple[str, str], ...] = (
    ("prod", "usuarios_sucursal"),
    ("prod", "tarifas_sucursal"),
    ("prod", "cantidad_vehiculos_sucursal"),
    ("prod", "configuracion_tolerancias"),
    ("prod", "configuracion_seguridad"),
    ("prod", "resolucion_facturacion"),
    ("prod", "subscripciones_cliente"),
)


def _walk_chain_sql(table_qualifier: str) -> str:
    """Recursive CTE: for each FK row, walk the Sucursal version chain
    forward to the currently-open version.

    Inputs: ``table_qualifier`` like ``prod.usuarios_sucursal``.
    Output: result rows ``(uuid_fk, current_sucursal_uuid)`` ready to be
    JOINed against the FK table's ``uuid`` PK to UPDATE its
    ``uuid_sucursal`` column. Idempotent: when the FK already points to
    the open version, ``chain`` walks one step and returns the same UUID.
    """
    return f"""
    WITH RECURSIVE chain AS (
      SELECT
        us.uuid_sucursal       AS root_uuid,
        us.uuid_sucursal       AS current_uuid,
        s.vigente_hasta
      FROM {table_qualifier} us
      JOIN prod.sucursal s
        ON s.uuid = us.uuid_sucursal
      UNION ALL
      SELECT
        c.root_uuid,
        next_s.uuid            AS current_uuid,
        next_s.vigente_hasta
      FROM chain c
      JOIN prod.sucursal next_s
        ON next_s.vigente_desde = c.vigente_hasta
      WHERE c.vigente_hasta IS NOT NULL
    )
    SELECT
      c.root_uuid                                          AS stale_uuid,
      (SELECT current_uuid FROM chain
        WHERE root_uuid = c.root_uuid
        ORDER BY vigente_hasta NULLS FIRST LIMIT 1)        AS fresh_uuid
    FROM (SELECT DISTINCT root_uuid FROM chain) c
    WHERE c.root_uuid <> (
      SELECT current_uuid FROM chain
      WHERE root_uuid = c.root_uuid
      ORDER BY vigente_hasta NULLS FIRST LIMIT 1
    )
    """


def upgrade() -> None:
    for schema, table in _FK_TABLES:
        qualified = f"{schema}.{table}"
        # The CTE selects (stale_uuid, fresh_uuid) pairs. UPDATE rewrites
        # uuid_sucursal in place. The 7 tables all use the same FK column
        # name (``uuid_sucursal``) by FK-convention -- see 0001_initial_schema.
        sql = f"""
        WITH stale AS ({_walk_chain_sql(qualified)})
        UPDATE {qualified} AS t
           SET uuid_sucursal = s.fresh_uuid
          FROM stale s
         WHERE t.uuid_sucursal = s.stale_uuid;
        """
        op.execute(sql)


def downgrade() -> None:
    # Intentionally a no-op: the data fix is semantically correct
    # (restoring the invariant "every FK points to the current version"),
    # and rolling back would re-introduce the bug. See the migration
    # docstring for the rationale.
    pass
