"""add derived current-identity + DIAN acknowledgement read views (D17, T-PR5-008)

Revision ID: 0009_add_derived_read_views
Revises: 0008_add_identity_nk_indexes
Create Date: 2026-09-08 00:05:00.000000

design.md §2 Issue #10 step 5 + ADR-001 §2 Issue #1's no-UPDATE consequence:
since ``IdentityReconciler`` (T-PR5-005) NEVER rewrites an existing FK
(``factura_electronica.uuid_cliente``, ``subscripcion_vehiculos.
uuid_vehiculo``, ... keep pointing at the version the emitting branch
actually saw — correct snapshot semantics), a reader that wants "the
CURRENT identity" for a natural key must resolve it AT READ TIME, not by
following a stored FK. These two views are that resolution:

  - ``prod.v_clientes_actual`` — one row per normalized ``(tipo_identificador,
    numero_identificacion)``, the OPEN version with the latest
    ``vigente_desde`` (tie-broken by ``uuid``) among open rows sharing a
    normalized key (a same-key double-open-version would only occur if the
    CI invariant, T-PR5-009, were ever violated — this view still resolves
    deterministically to one row rather than erroring).
  - ``prod.v_vehiculos_actual`` — the ``placa``-normalized analogue.
  - ``prod.v_factura_electronica_acuse`` — the DIAN acknowledgement view:
    one row per ``uuid_factura_electronica``, the most recent
    ``envio_dian`` row (``cufe``, ``estado``) by ``timestamp_evento``
    (tie-broken by ``uuid``). ``envio_dian`` is ``[L-W]`` (a self-chained
    workflow table, ``uuid_envio_padre``); this view uses a simpler
    "latest timestamp" tie-break than ``repo.workflow.read_chain_tip``'s
    full ``(max(timestamp_evento), max(chain_length), lex(uuid))`` — a
    documented simplification acceptable for a read-only acknowledgement
    projection (not a state-machine authority), not a general chain-tip
    resolver.

**Both functional expressions mirror ``catalog/normalizers.py`` /
migration ``0008``'s index expressions EXACTLY** — a divergence here would
mean the view and the index disagree about what "the same natural key"
means.

**Adds no table.** Views are not subject to the ``[A]``-table REVOKE /
inmutable-trigger discipline (same reasoning as migration ``0007``'s
``v_resolucion_consecutivo``: PostgreSQL views inherit permissions from the
underlying relations). ``check_table_counts.py``'s 51/54 physical-table
canon is unaffected — see this PR's ``tasks.md`` PR5 header for the
migration-renumbering note.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0009_add_derived_read_views"
down_revision = "0008_add_identity_nk_indexes"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"


def upgrade() -> None:
    """Create the 3 derived read views (T-PR5-008)."""
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute(
        """
        CREATE OR REPLACE VIEW prod.v_clientes_actual AS
        SELECT DISTINCT ON (
            c.tipo_identificador,
            regexp_replace(c.numero_identificacion, '[^0-9A-Za-z]', '', 'g')
        )
            c.*
        FROM prod.clientes c
        WHERE c.vigente_hasta IS NULL
        ORDER BY
            c.tipo_identificador,
            regexp_replace(c.numero_identificacion, '[^0-9A-Za-z]', '', 'g'),
            c.vigente_desde DESC,
            c.uuid DESC
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW prod.v_vehiculos_actual AS
        SELECT DISTINCT ON (
            upper(regexp_replace(v.placa, '[^0-9A-Za-z]', '', 'g'))
        )
            v.*
        FROM prod.vehiculos v
        WHERE v.vigente_hasta IS NULL
        ORDER BY
            upper(regexp_replace(v.placa, '[^0-9A-Za-z]', '', 'g')),
            v.vigente_desde DESC,
            v.uuid DESC
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW prod.v_factura_electronica_acuse AS
        SELECT DISTINCT ON (ed.uuid_factura_electronica)
            ed.uuid_factura_electronica,
            ed.cufe,
            ed.estado,
            ed.timestamp_evento
        FROM prod.envio_dian ed
        WHERE ed.uuid_factura_electronica IS NOT NULL
        ORDER BY
            ed.uuid_factura_electronica,
            ed.timestamp_evento DESC NULLS LAST,
            ed.uuid DESC
        """
    )


def downgrade() -> None:
    """Drop the 3 derived read views.

    Lossy only for readers of these views — no persisted data is affected
    (``clientes``, ``vehiculos``, ``envio_dian`` rows are untouched).
    """
    op.execute("DROP VIEW IF EXISTS prod.v_factura_electronica_acuse")
    op.execute("DROP VIEW IF EXISTS prod.v_vehiculos_actual")
    op.execute("DROP VIEW IF EXISTS prod.v_clientes_actual")
