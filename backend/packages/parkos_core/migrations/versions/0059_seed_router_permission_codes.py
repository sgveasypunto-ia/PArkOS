"""MIGRATION 0059 -- seed the permission codes the routers require but the
catalogue never defined.

THE DEFECT THIS PINS
--------------------
``backend/packages/parkos_core/src/parkos_core/api/v1/empresa.py`` builds
every empresa router through ``make_router(..., permisos=...)``, and
``require_permission`` authorizes with::

    PermisosUsuario.vigente_hasta.is_(None) AND Permisos.permiso == codigo

Ten of the codes named in those ``_ROUTER_CONFIG`` maps have NEVER existed in
``prod.permisos``. Measured live on the cloud DB::

    32 distinct codes in the catalogue, 0 of the 10 required ones present

The failure is silent at boot and total at runtime. Nothing warns that a
route is unreachable; the route simply answers ``403 Forbidden`` for every
caller, including a fully-granted admin, forever. Measured on the live
cloud: ``POST``/``PUT`` on both ``/api/v1/empresa/tarifas-sucursal`` and
``/api/v1/empresa/cantidad-vehiculos-sucursal`` returned 403 for all three
live users. ``GET`` on the same paths succeeded, which is what made this
look like a frontend gap rather than a catalogue gap: the read path does not
pass through the gate, so the only visible symptom is that nothing can ever
be WRITTEN.

That is the shape of a dead feature. The endpoints are implemented, the
schemas are implemented, the ORM is implemented, the UI to drive them does
not exist -- and the reason nobody noticed is that the 403 is
indistinguishable from "the frontend was never built".

WHY TEN AND NOT TWO
-------------------
Only ``config_tarifas`` and ``config_cupos`` block the work in flight. The
other eight are the same defect in the same file and would each resurface
as an equally unexplained 403 the first time someone builds the screen for
it. Fixing the whole set is one migration and one test; fixing two would
guarantee the same conversation again in six months.

Deliberately NOT done: renaming the routes to the pre-existing canonical
codes (``administrar_tarifas``, ``registrar_reclamos``, ...). The canonical
catalogue and the router config are two independent lists that drifted; the
drift is real, but renaming a public route to suit a permission string is
the wrong direction of travel. The router map is the consumer; the
catalogue is the thing that was incomplete. So the catalogue grows.

IDENTITY: WHY uuid5 AND NOT gen_random_uuid()
--------------------------------------------
``0002_seed_permisos_canonicos.py`` mints with ``gen_random_uuid()`` and
runs INDEPENDENTLY on the cloud and on every branch, so a random uuid
diverges per node forever. ``0019`` and then ``0056`` established the fix
for the codes that existed: a ``uuid5`` from a fixed namespace, so every
node -- present and future -- converges on the identical value.

The property is not cosmetic. ``0019``'s own docstring records the cost of
getting it wrong: cloud grants referenced a ``uuid_permiso`` the branch had
never seen, ``job_sync_sucursal`` rejected 522 consecutive pull batches
with ``ForeignKeyViolationError`` on
``fk_permisos_usuario_uuid_permiso``, and the branch stopped consuming
cloud-to-branch changes for 11 hours behind a container reporting
``healthy``. These ten codes will be INSERTed on both the cloud and each
branch by this very migration, so they are the most exposed rows in the
catalogue. Random uuids here would reproduce that failure from scratch.

The values below are ``uuid5(NAMESPACE, <code>)`` with the SAME namespace
``0019`` and ``0056`` use, computed OFFLINE and hardcoded -- never at
migration runtime, because a runtime ``uuid_generate_v5`` would require a
``pgcrypto`` dependency this project does not carry. One continuous
namespace across three migrations: 0019's sixteen codes, 0056's sixteen,
and these ten.

PROPAGATION IS AUTOMATIC, AND THAT IS WHY THE NAMESPACE MATTERS TWICE
--------------------------------------------------------------------
``permisos_enqueue_sync_catalog`` is an ``AFTER INSERT ... FOR EACH ROW``
trigger on ``prod.permisos`` calling ``prod.fn_enqueue_sync_catalog()``, so
every row inserted here is enqueued for the branches with no extra work.
``permisos_usuario`` carries the same trigger, so the grants enqueue too.

That also means the INSERT runs on the branch side of the sync as well as
the cloud. A random uuid would be minted twice -- once per node -- and the
``NOT EXISTS`` guard below would be satisfied independently on each, leaving
two open catalogue rows for one code and the drift intact. The deterministic
uuid makes the second node's INSERT a no-op instead.

IDEMPOTENCE: WHY NOT ``ON CONFLICT DO NOTHING``
----------------------------------------------
``permisos_uk01`` is ``UNIQUE (permiso, vigente_desde)`` and
``vigente_desde = clock_timestamp()`` is re-evaluated per INSERT, so a
conflict target naming that UK never matches and every run appends another
open version. ``0002``'s seed and ``bootstrap_pairing.py::ensure_admin_user``
both carry that exact defect; ``0054``'s docstring names it as the cause of
seven admin versions inside 46 minutes. The guards below test explicit
``NOT EXISTS`` predicates instead, which is what actually makes a re-run a
genuine no-op.

No physical DELETE is performed anywhere. Retraction CLOSES the version
(``vigente_hasta`` + ``estado='inactivo'``) and the row stays forever.
"""

from __future__ import annotations

import json

from alembic import op
from sqlalchemy import text

revision = "0059_seed_router_permission_codes"
down_revision = "0058_hash_chain_causal_seq"
branch_labels = None
depends_on = None


_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# Same namespace as 0019 and 0056 -- one continuous scheme across all three
# migrations, so a code owned by one and not another can never diverge.
_NAMESPACE = "a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60"

# code -> uuid5(UUID(_NAMESPACE), code), computed offline and hardcoded.
#
# Recompute to verify (never to generate at runtime):
#   uuid.uuid5(uuid.UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60"), code)
#
# A typo in any character yields a still-valid uuid: it inserts cleanly, the
# grants resolve, the FK is satisfied LOCALLY, and nothing fails until the
# other node computes or carries a different value -- which is the exact
# failure this whole scheme exists to prevent, and the reason the test for
# this migration recomputes every value instead of trusting the literals.
_ROUTER_PERMISSION_UUIDS: dict[str, str] = {
    "admin_documentos": "f22565c3-6b4f-5423-9ce0-cd0b986f5efd",
    "admin_resolucion_facturacion": "c21d4cfb-dafa-52e1-be03-833da08cd04a",
    "anular_ingreso_salida": "4113a009-2ae2-5538-8059-2a1e2eb8dc84",
    "config_cupos": "2f251133-895b-56d3-8899-1120d8a147e1",
    "config_empresa": "bb9ed47f-b758-552d-89b7-54ac33293b66",
    "config_seguridad": "cd800cb2-3fcf-5a02-be3b-261bd900b4ac",
    "config_tarifas": "ab5c57bf-2bbe-5b51-8ad1-31cf3b7a5fee",
    "config_tolerancias": "66ecaafd-5963-5678-92c8-5d8c94a60bfb",
    "registrar_alerta": "5bbbe7cb-3fce-5a58-812a-1d7740e82800",
    "registrar_reclamo": "fa2bdaf4-b7e3-557b-84d0-2af9212a970a",
}

# The codes whose grants are the reason the INSERT above exists. Kept as an
# explicit set so the grant step cannot accidentally widen to "every code in
# the catalogue" -- that broader policy belongs to 0054 and is not restated
# here, because silently re-granting unrelated codes would make this
# migration's blast radius unreadable.
_NEW_CODES = sorted(_ROUTER_PERMISSION_UUIDS)


def _codes_json() -> str:
    """The map as a JSON array of ``{"uuid":..., "codigo":...}`` objects."""
    return json.dumps(
        [
            {"uuid": det_uuid, "codigo": codigo}
            for codigo, det_uuid in sorted(_ROUTER_PERMISSION_UUIDS.items())
        ]
    )


def upgrade() -> None:
    """Make the ten codes exist, then make the admin hold them.

    Three ordered steps, all in one transaction:

    1. INSERT the catalogue row for each code that has no open one.
    2. Grant each code to every open admin, skipping (user, code) pairs that
       already hold an open grant.
    3. Close any open grant pointing at a CLOSED version of one of these
       codes, restoring the invariant "an open grant names an open
       permission".

    Step 2 after step 1 is load-bearing: grants are FK-constrained to
    ``permisos``, so granting before the row exists is impossible and
    granting after a failed insert leaves the catalogue half-fixed.

    Step 3 is the cleanup ``0054`` established for the same class of damage.
    A grant whose permission row is closed cannot authorize anything --
    ``require_permission`` filters ``Permisos.vigente_hasta.is_(None)`` -- but
    it is still a live hazard: any query that joins ``permisos_usuario``
    without also filtering the permission's own open version reports a count
    inflated by it. ``0054``'s docstring records exactly that miscount (60
    grants reported for an admin holding 32) and calls a mis-scoped admin
    screen "precisely where that number would surface and be believed".

    Idempotent. N runs converge on exactly one open catalogue row and one
    open grant per (admin, code) pair, which is what ``require_permission``
    needs. A no-op on a node with no open admin, so it is safe to apply to a
    branch that has never been bootstrapped.
    """
    op.execute(_LOCK_TIMEOUT_SQL)
    bind = op.get_bind()
    params = {"codes": _codes_json(), "code_list": _NEW_CODES}

    # Step 1 -- the catalogue rows.
    #
    # Two independent guards, because there are two distinct ways a row can
    # already exist and only one of them is a duplicate:
    #   * the code already has an OPEN row (possibly a different uuid) --
    #     another node or an earlier run got here first;
    #   * the deterministic uuid is already taken by a CLOSED version of the
    #     same code -- `permisos_pkey` is `PRIMARY KEY (uuid)`, so a
    #     re-insert would be a PK violation, not a UK violation.
    bind.execute(
        text(
            """
            WITH nuevos AS (
                SELECT
                    (r->>'uuid')::uuid   AS uuid,
                    (r->>'codigo')::text AS codigo
                FROM jsonb_array_elements(CAST(:codes AS jsonb)) AS r
            )
            INSERT INTO prod.permisos
                (uuid, permiso, vigente_desde, vigente_hasta, estado,
                 created_at, created_by, sync_status, sync_attempts)
            SELECT uuid, codigo, clock_timestamp(), NULL, 'activo',
                   clock_timestamp(), NULL, 'sincronizado', 0
            FROM nuevos
            WHERE NOT EXISTS (
                      SELECT 1 FROM prod.permisos p
                      WHERE p.permiso = nuevos.codigo
                        AND p.vigente_hasta IS NULL
                  )
              AND NOT EXISTS (
                      SELECT 1 FROM prod.permisos p
                      WHERE p.uuid = nuevos.uuid
                  )
            """
        ),
        params,
    )

    # Step 2 -- grant to admins.
    #
    # `rol = 'admin'`, not a hardcoded address: a migration ships to every
    # environment, and "an admin holds every permission the catalogue
    # defines" stays correct where the admin's address does not.
    #
    # `DISTINCT ON (permiso)` with `ORDER BY permiso, vigente_desde DESC`
    # rather than a plain CROSS JOIN: a cross join emits one grant per
    # physical CATALOG ROW, and the live cloud DB carries more rows than
    # distinct codes (duplicate-version damage from 0002's broken
    # ON CONFLICT). Joining on the latest open version of each code is the
    # correct bi-temporal answer to "what is this permission right now",
    # and it keeps this correct regardless of catalogue hygiene.
    bind.execute(
        text(
            """
            INSERT INTO prod.permisos_usuario
                (uuid, created_at, created_by,
                 vigente_desde, vigente_hasta, estado,
                 sync_status, sync_attempts,
                 uuid_usuario, uuid_permiso)
            SELECT gen_random_uuid(), clock_timestamp(), NULL,
                   clock_timestamp(), NULL, 'activo',
                   'sincronizado', 0,
                   u.uuid, p.uuid
            FROM prod.usuarios u
            CROSS JOIN (
                SELECT DISTINCT ON (permiso) uuid, permiso
                FROM prod.permisos
                WHERE vigente_hasta IS NULL
                  AND permiso = ANY(CAST(:code_list AS text[]))
                ORDER BY permiso, vigente_desde DESC
            ) p
            WHERE u.rol = 'admin'
              AND u.vigente_hasta IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM prod.permisos_usuario pu
                  WHERE pu.uuid_usuario = u.uuid
                    AND pu.uuid_permiso = p.uuid
                    AND pu.vigente_hasta IS NULL
              )
            """
        ),
        params,
    )

    # Step 3 -- retire grants left dangling on a closed catalogue version.
    bind.execute(
        text(
            """
            UPDATE prod.permisos_usuario pu
            SET vigente_hasta = clock_timestamp(),
                estado = 'inactivo'
            WHERE pu.vigente_hasta IS NULL
              AND pu.uuid_permiso IN (
                  SELECT p.uuid
                  FROM prod.permisos p
                  WHERE p.vigente_hasta IS NOT NULL
                    AND p.permiso = ANY(CAST(:code_list AS text[]))
              )
            """
        ),
        params,
    )


def downgrade() -> None:
    """Close the ten codes' grants, then the ten codes themselves.

    Grants first, catalogue second: closing only the catalogue row already
    deactivates the permission (``require_permission`` filters
    ``Permisos.vigente_hasta.is_(None)``), but it would leave open grants
    naming a closed permission -- the dangling state step 3 of ``upgrade``
    exists to eliminate, and re-introducing it on the way out would make the
    rollback leave the same hazard it was written to clean up.

    Not scoped to the rows this migration opened. ``created_by`` is NULL for
    every seed-inserted row, ``sync_status`` and ``sync_attempts`` are shared
    with runtime updates, and ``vigente_desde`` is not recorded anywhere --
    so there is no usable marker to narrow on, and inventing a column to
    carry a single rollback path is not worth it. The predicate "one of these
    ten codes" is the honest inverse: before 0059 the codes did not exist,
    so closing them is the correct pre-migration state.

    No physical DELETE. A later re-run of ``upgrade`` inserts fresh versions
    whose ``vigente_desde`` opens after this ``vigente_hasta``, so a
    retracted code is auditable and re-grantable without a destructive
    operation.
    """
    op.execute(_LOCK_TIMEOUT_SQL)
    bind = op.get_bind()
    params = {"code_list": _NEW_CODES}

    bind.execute(
        text(
            """
            UPDATE prod.permisos_usuario pu
            SET vigente_hasta = clock_timestamp(),
                estado = 'inactivo'
            WHERE pu.vigente_hasta IS NULL
              AND pu.uuid_permiso IN (
                  SELECT p.uuid
                  FROM prod.permisos p
                  WHERE p.permiso = ANY(CAST(:code_list AS text[]))
              )
            """
        ),
        params,
    )

    bind.execute(
        text(
            """
            UPDATE prod.permisos
            SET vigente_hasta = clock_timestamp(),
                estado = 'inactivo'
            WHERE vigente_hasta IS NULL
              AND permiso = ANY(CAST(:code_list AS text[]))
            """
        ),
        params,
    )


__all__ = ["downgrade", "upgrade"]
