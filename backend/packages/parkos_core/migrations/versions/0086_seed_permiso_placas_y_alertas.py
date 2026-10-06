"""0086_seed_permiso_placas_y_alertas -- PT-2 foundations: permission + alert types.

Revision ID: 0086_seed_permiso_placas_y_alertas
Revises: 0085_pull_rls
Create Date: 2026-10-06 00:00:00.000000

SCOPE
-----
Data-only migration (no DDL). Prepares the ground for PT-2 (managing the
plates attached to a subscription) so a later wave can ship endpoints and UI
without touching the catalogue again.

1. **Permission ``gestionar_placas_suscripcion``.** Seeded in
   ``prod.permisos`` with the SAME continuous ``uuid5`` namespace
   ``0019``/``0056``/``0059``/``0066`` established
   (``a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60``), so cloud and every branch
   converge on the identical catalogue row. Deterministic value computed
   OFFLINE and hardcoded (recompute to verify, never generate at runtime --
   see ``0059``)::

       uuid.uuid5(UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60"),
                  "gestionar_placas_suscripcion")
       => 3cfef8c2-7f34-5eed-b7a0-4ca169343d5d

   Same idempotent 3-step shape as ``0059``/``0066`` (``NOT EXISTS`` guards,
   never ``ON CONFLICT``: the UK is ``(permiso, vigente_desde)`` and
   ``vigente_desde = clock_timestamp()`` never repeats). Granted to every open
   user whose ``rol`` is ``Supervisor`` or ``Administrador`` (business-role
   labels, see ``api/v1/auth.py::ROLES_OPERADOR``) and, following ``0054``,
   to the legacy ``admin`` role that holds every code. ``operador`` / ``Usuario``
   deliberately receive nothing.

2. **Alert types ``suscripcion_placa_agregada`` / ``suscripcion_placa_quitada``**
   (severity ``info``) in ``prod.alert_types``. The registry is
   immutable by trigger for UPDATE/DELETE, but plain INSERT is allowed
   (``0013``/``0025``/``0032`` precedent: ``INSERT ... ON CONFLICT
   (tipo_alerta) DO NOTHING``).

VERIFIED (not assumed)
----------------------
* ``prod.alerta.tipo_alerta`` is a free ``VARCHAR`` (``0001_initial_schema``):
  no CHECK, no FK to ``alert_types``. The registry is a deploy-seeded
  documentation/validation list consulted by Python (``alert_emitter``), so
  the ``alerta`` partitions accept the new codes with no further DDL.
* ``alert_types`` is OUT_OF_CATALOG (never replicated; see ``0013``): both
  databases get the rows from THIS migration, exactly like every earlier
  alert seed. There is nothing for the sync to carry. ``alerta`` rows
  themselves travel through the normal ``alerta`` catalog entry, whose
  ``tipo_alerta`` column is free text.

DOWNGRADE
---------
Documented no-op (see ``downgrade``): closing the deterministic permission row
would make a re-upgrade unable to restore it, and ``alert_types`` is immutable
by trigger. Nothing is physically deleted.
"""
from __future__ import annotations

from alembic import op

revision = "0086_seed_permiso_placas_y_alertas"
down_revision = "0085_pull_rls"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# Same continuous namespace as 0019 / 0056 / 0059 / 0066.
_PERMISSION_NAMESPACE = "a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60"
_PERMISSION_CODE = "gestionar_placas_suscripcion"
# uuid5(UUID(_PERMISSION_NAMESPACE), _PERMISSION_CODE), computed offline.
_PERMISSION_UUID = "3cfef8c2-7f34-5eed-b7a0-4ca169343d5d"

# Roles that receive the grant. 'admin' follows 0054 (admin holds every code);
# 'Administrador' / 'Supervisor' are the business-role labels (HU-F13.2).
_GRANTED_ROLES = ("admin", "Administrador", "Supervisor")

_ROLES_SQL = ", ".join(f"'{r}'" for r in _GRANTED_ROLES)

# (tipo_alerta, descripcion, severity)
_ALERT_TYPES: tuple[tuple[str, str, str], ...] = (
    (
        "suscripcion_placa_agregada",
        "Se agrego una placa a una suscripcion vigente",
        "info",
    ),
    (
        "suscripcion_placa_quitada",
        "Se quito una placa de una suscripcion vigente",
        "info",
    ),
)


def upgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)

    # Step 1 -- catalogue row (skip if an open row for the code exists, or the
    # deterministic uuid is already taken by a closed version: PK is (uuid)).
    op.execute(
        f"""
            INSERT INTO prod.permisos
                (uuid, permiso, vigente_desde, vigente_hasta, estado,
                 created_at, created_by, sync_status, sync_attempts)
            SELECT CAST('{_PERMISSION_UUID}' AS uuid), '{_PERMISSION_CODE}', clock_timestamp(), NULL, 'activo',
                   clock_timestamp(), NULL, 'sincronizado', 0
            WHERE NOT EXISTS (
                      SELECT 1 FROM prod.permisos p
                      WHERE p.permiso = '{_PERMISSION_CODE}'
                        AND p.vigente_hasta IS NULL
                  )
              AND NOT EXISTS (
                      SELECT 1 FROM prod.permisos p
                      WHERE p.uuid = CAST('{_PERMISSION_UUID}' AS uuid)
                  )
            """
    )

    # Step 2 -- grant to every open user holding one of the granted roles.
    op.execute(
        f"""
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
                  AND permiso = '{_PERMISSION_CODE}'
                ORDER BY permiso, vigente_desde DESC
            ) p
            WHERE u.rol = ANY (ARRAY[{_ROLES_SQL}]::text[])
              AND u.vigente_hasta IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM prod.permisos_usuario pu
                  WHERE pu.uuid_usuario = u.uuid
                    AND pu.uuid_permiso = p.uuid
                    AND pu.vigente_hasta IS NULL
              )
            """
    )

    # Step 3 -- retire grants left dangling on a closed catalogue version.
    op.execute(
        f"""
            UPDATE prod.permisos_usuario pu
            SET vigente_hasta = clock_timestamp(),
                estado = 'inactivo'
            WHERE pu.vigente_hasta IS NULL
              AND pu.uuid_permiso IN (
                  SELECT p.uuid
                  FROM prod.permisos p
                  WHERE p.vigente_hasta IS NOT NULL
                    AND p.permiso = '{_PERMISSION_CODE}'
              )
            """
    )

    # Alert types -- idempotent INSERT, allowed by alert_types_inmutable.
    for tipo, descripcion, severity in _ALERT_TYPES:
        op.execute(
            f"""
                INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)
                VALUES ('{tipo}', '{descripcion}', '{severity}')
                ON CONFLICT (tipo_alerta) DO NOTHING
                """
        )


def downgrade() -> None:
    """Intentional no-op: the seeds are additive and harmless.

    Closing the catalogue row here would make a later re-upgrade impossible to
    restore (the deterministic uuid stays taken by the CLOSED version and the
    NOT EXISTS guard in step 1 skips it), and reopening it would rewrite valid
    time. Leaving the permission, its grants and the info-level alert types in
    place keeps downgrade -> upgrade lossless; no physical DELETE is used.
    """


__all__ = ["downgrade", "upgrade"]
