"""0088_seed_cliente_estandar -- "cliente estandar" (consumidor final) for the FE.

Revision ID: 0088_seed_cliente_estandar
Revises: 0087_add_tipo_subscripciones_tipo_vehiculo
Create Date: 2026-10-06 01:00:00.000000

SCOPE
-----
Data-only migration (no DDL). Electronic invoicing is now ALWAYS emitted; when
the payer does not ask for the invoice in their own name the document goes to
a standard customer (DIAN generic consumer).

WHY A SEEDED ROW (and not a sync)
---------------------------------
``clientes`` uses the ``derived`` pull policy (``sync/motor/pull_scope.py``): a
customer only travels down to a branch when a subscription or invoice
references it. The standard customer must exist in EVERY node from the start,
so each node seeds it with the SAME deterministic identity:

* ``uuid``          = uuid5(``a3f1c9d4-...``, ``cliente_estandar_consumidor_final``)
                      = ``5e60b3e6-000a-5fdc-8dd7-d27a80c10e96`` (offline-computed)
* ``vigente_desde`` = constant ``2026-01-01 00:00:00`` (never ``now()``)
* ``uuid_tipo_persona`` = the deterministic ``natural`` uuid from ``0020``

so when the AFTER INSERT trigger queues the row and it reaches the other node
it is the same (uuid, natural key, vigente_desde): a no-op for
``identity_reconciler``.

[POR DEFINIR] with accounting / the provider (Factus): identification
``222222222222``, identifier type ``CC`` (the existing code for cedula de
ciudadania; the list is open), name ``Consumidor final``.

IDEMPOTENCY
-----------
``NOT EXISTS`` guards by open natural key AND by uuid (PK): re-running, or a
node where a row with that natural key already exists, inserts nothing. No
``ON CONFLICT`` (the UK includes ``vigente_desde``).

DOWNGRADE
---------
Documented no-op: no physical DELETE (AGENTS.md); invoices may already
reference the row.
"""
from __future__ import annotations

from alembic import op

revision = "0088_seed_cliente_estandar"
down_revision = "0087_add_tipo_subscripciones_tipo_vehiculo"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# Must match parkos_core.constants (kept literal: migrations never import app code).
_UUID = "5e60b3e6-000a-5fdc-8dd7-d27a80c10e96"
_TIPO_PERSONA_NATURAL = "9ff893fd-e771-5b6a-8b18-6648e47c69d9"
_TIPO_IDENTIFICADOR = "CC"
_NUMERO = "222222222222"
_NOMBRE = "Consumidor final"
_VIGENTE_DESDE = "2026-01-01 00:00:00"


def upgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)
    op.execute(
        f"""
        INSERT INTO prod.clientes
            (uuid, tipo_identificador, numero_identificacion, nombre,
             uuid_tipo_persona, created_at, created_by,
             vigente_desde, vigente_hasta, estado,
             sync_status, sync_attempts)
        SELECT CAST('{_UUID}' AS uuid), '{_TIPO_IDENTIFICADOR}', '{_NUMERO}', '{_NOMBRE}',
               CAST('{_TIPO_PERSONA_NATURAL}' AS uuid), clock_timestamp(), NULL,
               TIMESTAMP '{_VIGENTE_DESDE}', NULL, 'activo',
               'sincronizado', 0
        WHERE NOT EXISTS (
                  SELECT 1 FROM prod.clientes c
                  WHERE c.tipo_identificador = '{_TIPO_IDENTIFICADOR}'
                    AND c.numero_identificacion = '{_NUMERO}'
                    AND c.vigente_hasta IS NULL
              )
          AND NOT EXISTS (
                  SELECT 1 FROM prod.clientes c
                  WHERE c.uuid = CAST('{_UUID}' AS uuid)
              )
        """
    )


def downgrade() -> None:
    """Intentional no-op: no physical DELETE; invoices may reference the row."""


__all__ = ["downgrade", "upgrade"]
