"""add identity natural-key lookup indexes (D17, T-PR5-007)

Revision ID: 0008_add_identity_nk_indexes
Revises: 0007_add_v_resolucion_consecutivo_view
Create Date: 2026-09-08 00:00:00.000000

design.md §2 Issue #10 / §4: non-unique functional partial indexes on the
NORMALIZED natural key of the three ``bidirectional`` identity masters —
``clientes``, ``clientes_b2b``, ``vehiculos`` — restricted to the currently
-open version (``WHERE vigente_hasta IS NULL``). These back
``IdentityReconciler``'s (``hooks/impls/identity_reconciler.py``, T-PR5-005)
lookup of "the currently-open version for this normalized natural key".

**Non-unique, by design** (design.md's Issue #10 decision table): a
``UNIQUE`` functional partial index would enforce the invariant in the DB,
but a constraint violation raises on the applying transaction and would
block an invoice at the counter — exactly what D17 case 4 (divergent data)
forbids. The invariant is instead proven in CI
(``tests/integration/test_identity_invariant.py``, T-PR5-009): a violation
fails that test, not a live sale.

Both functional expressions mirror ``catalog/normalizers.py`` EXACTLY
(``tests/unit/test_natural_key_normalizer_parity.py`` asserts Python and
SQL agree over a shared fixture set):

  - ``clientes`` / ``clientes_b2b``-equivalent shape:
    ``regexp_replace(numero_identificacion, '[^0-9A-Za-z]', '', 'g')``
  - ``vehiculos``: ``upper(regexp_replace(placa, '[^0-9A-Za-z]', '', 'g'))``

Both expressions are built ONLY from ``regexp_replace`` / ``upper`` over a
plain column — both are ``IMMUTABLE`` (deterministic, no catalog/locale
lookups), which is required for a value to be indexable at all.

``clientes_b2b``'s natural key is ``(uuid_cliente,)`` — a plain UUID column
needs no regexp normalization, so its index is a plain (non-functional)
partial index; it is still declared here (same migration, same D17 concern)
for lookup-symmetry with the other two identity masters.

Renumbering note (session decision, confirmed against
``ls migrations/versions/`` — the highest existing revision at the start
of this PR was ``0007_add_v_resolucion_consecutivo_view``; ``0008``/``0009``
are the next real sequential numbers): tasks.md originally named this file
``0014_add_identity_nk_indexes.py``. That number is a draft-era artifact
from an earlier tasks.md revision and does not reflect the actual applied
migration order — see ``tasks.md``'s PR5 section header for the full
rationale and the note to PR7/PR8/PR10 about continuing from ``0010``.

Every migration in this project is expected to set ``lock_timeout`` on its
first statement (design.md §4); none of 0001-0007 do this yet (a
pre-existing gap, out of this migration's scope to retrofit) — this
migration and 0009 start doing it going forward.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0008_add_identity_nk_indexes"
down_revision = "0007_add_v_resolucion_consecutivo_view"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"


def upgrade() -> None:
    """Create the 3 identity-master natural-key lookup indexes (T-PR5-007)."""
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_clientes_nk_open
        ON prod.clientes (
            tipo_identificador,
            regexp_replace(numero_identificacion, '[^0-9A-Za-z]', '', 'g')
        )
        WHERE vigente_hasta IS NULL
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_clientes_b2b_nk_open
        ON prod.clientes_b2b (uuid_cliente)
        WHERE vigente_hasta IS NULL
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_vehiculos_nk_open
        ON prod.vehiculos (
            upper(regexp_replace(placa, '[^0-9A-Za-z]', '', 'g'))
        )
        WHERE vigente_hasta IS NULL
        """
    )


def downgrade() -> None:
    """Drop the 3 identity-master lookup indexes.

    Lossy only in the sense that ``IdentityReconciler``'s natural-key lookup
    reverts to an unindexed scan (D17 reconciliation still works — this
    index only speeds up the lookup, it is never the source of the
    invariant, which is a CI-proven property, not a DB constraint). No
    persisted data is affected.
    """
    op.execute("DROP INDEX IF EXISTS prod.ix_vehiculos_nk_open")
    op.execute("DROP INDEX IF EXISTS prod.ix_clientes_b2b_nk_open")
    op.execute("DROP INDEX IF EXISTS prod.ix_clientes_nk_open")
