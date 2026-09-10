"""fix ``fn_extend_hash_chain()``'s "prior row" ordering — was
``timestamp_evento`` (business-supplied, can collide), now ``created_at``
(server-stamped append order) — confirmed live real-Docker chain fork.

Revision ID: 0017_fix_hash_chain_prior_row_ordering
Revises: 0016_add_sync_apply_guard
Create Date: 2026-09-09 23:10:00.000000

**The bug (confirmed against a real Docker deployment).** Both
``prod.fn_extend_hash_chain()`` (this trigger, BEFORE INSERT on
``log_transaccional`` only — ``revocacion_factura`` carries no DB trigger,
see ``repo/hash_chain.py::_ensure_genesis_row``'s own docstring) and its
Python-side mirror (``repo/hash_chain.py::_read_prior_hash``, fixed
separately in this same change) picked the chain's "prior" row via
``ORDER BY timestamp_evento DESC, uuid DESC``. ``timestamp_evento`` is a
business-supplied event time, not a physical append order — once 2+
EXISTING rows for the same ``uuid_sucursal`` share the identical value
(any burst of events landing in the same second is enough), the ``uuid``
tie-break picks whichever row happens to have the lexicographically
largest random UUID as "prior", which has no relationship to which row
was truly inserted last. Confirmed live: a real branch's
``log_transaccional`` chain forked in exactly this way — TWO rows both
computed the SAME earlier row as their ``hash_anterior`` (both inserts
independently "agreed" with this same trigger, since the trigger's own
query returned that same wrong-but-self-consistent answer at each
respective INSERT time) — and ``motor.verify_chain``'s walk later
surfaced it as a real ``hash_chain_break``.

**The fix.** Swap ``timestamp_evento`` for ``created_at`` — stamped once,
in Python, immediately before each row's own INSERT (``AuditMixin``,
mandatory on every table). Two rows landing in the very same wall-clock
second still get distinct microsecond-resolution ``created_at`` values in
the overwhelming common case, so the tie-break is no longer reachable in
practice, and both sides of the chain (this trigger's "find the prior"
and ``repo.hash_chain.append``'s own read) now sort by the exact same
column — they must, or every INSERT with 2+ existing rows for a tenant
fails outright with ``HASH_CHAIN_INTEGRITY_VIOLATION`` (Python computes
one "prior" candidate, the trigger independently computes a different
one, and the trigger rejects Python's ``hash_anterior`` as not matching
its own — confirmed by this change's own regression test before this
migration was added).

**Why ``CREATE OR REPLACE FUNCTION``, not a new function.** Same
established precedent as ``0010``/``0014``/``0015``/``0016`` — the
function already exists, the trigger is bound to it by name/OID, and
``CREATE OR REPLACE`` swaps the body without touching the ``CREATE
TRIGGER`` statement or any data.

**Data note.** This migration does NOT and cannot repair any row already
written under the old ordering — ``log_transaccional`` is ``[A]``
(append-only, no UPDATE/DELETE at the ``rol_app`` grant level, enforced
by ``fn_log_transaccional_inmutable()``). A chain that already forked
under the old code stays forked; the existing ``alerta`` +
``sync_conflict`` manual-resolution path (``jobs/sync_cloud.py::
_handle_chain_break``) is how that gets triaged. This migration only
stops NEW forks from happening going forward.

Pre-flight: ``uv run alembic upgrade --sql 0017_fix_hash_chain_prior_row_ordering``
reviewed before apply (1 ``CREATE OR REPLACE FUNCTION`` statement only —
no ``CREATE``/``DROP TRIGGER``, no data-destructive statements).
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0017_fix_hash_chain_prior_row_ordering"
down_revision = "0016_add_sync_apply_guard"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"


def upgrade() -> None:
    """``CREATE OR REPLACE`` ``fn_extend_hash_chain()`` with the
    ``created_at``-ordered "prior row" lookup."""
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_extend_hash_chain()
        RETURNS trigger AS $$
        DECLARE
            prev_hash text;
        BEGIN
            IF NEW.accion = 'inicialización'
               AND NEW.hash_anterior IS NOT NULL
               AND NEW.hash_anterior = NEW.hash_actual THEN
                RETURN NEW;
            END IF;
            SELECT hash_actual INTO prev_hash
              FROM prod.log_transaccional
             WHERE uuid_sucursal IS NOT DISTINCT FROM NEW.uuid_sucursal
               AND NOT (uuid = NEW.uuid)
             ORDER BY created_at DESC, uuid DESC
             LIMIT 1;
            IF prev_hash IS NULL THEN
                RAISE EXCEPTION 'HASH_CHAIN_INTEGRITY_VIOLATION: no genesis row for uuid_sucursal=%', NEW.uuid_sucursal;
            END IF;
            IF NEW.hash_anterior IS NULL THEN
                NEW.hash_anterior := prev_hash;
            ELSIF NEW.hash_anterior <> prev_hash THEN
                RAISE EXCEPTION 'HASH_CHAIN_INTEGRITY_VIOLATION: hash_anterior=% expected=%', NEW.hash_anterior, prev_hash;
            END IF;
            IF NEW.hash_actual IS NULL THEN
                NEW.hash_actual := encode(digest(coalesce(NEW.datos_nuevos::text, '') || '|' || coalesce(NEW.uuid_registro_afectado::text, '') || prev_hash, 'sha256'), 'hex');
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Restore the pre-0017 ``timestamp_evento``-ordered body verbatim
    from ``0001_initial_schema.py``."""
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_extend_hash_chain()
        RETURNS trigger AS $$
        DECLARE
            prev_hash text;
        BEGIN
            IF NEW.accion = 'inicialización'
               AND NEW.hash_anterior IS NOT NULL
               AND NEW.hash_anterior = NEW.hash_actual THEN
                RETURN NEW;
            END IF;
            SELECT hash_actual INTO prev_hash
              FROM prod.log_transaccional
             WHERE uuid_sucursal IS NOT DISTINCT FROM NEW.uuid_sucursal
               AND NOT (uuid = NEW.uuid)
             ORDER BY timestamp_evento DESC, uuid DESC
             LIMIT 1;
            IF prev_hash IS NULL THEN
                RAISE EXCEPTION 'HASH_CHAIN_INTEGRITY_VIOLATION: no genesis row for uuid_sucursal=%', NEW.uuid_sucursal;
            END IF;
            IF NEW.hash_anterior IS NULL THEN
                NEW.hash_anterior := prev_hash;
            ELSIF NEW.hash_anterior <> prev_hash THEN
                RAISE EXCEPTION 'HASH_CHAIN_INTEGRITY_VIOLATION: hash_anterior=% expected=%', NEW.hash_anterior, prev_hash;
            END IF;
            IF NEW.hash_actual IS NULL THEN
                NEW.hash_actual := encode(digest(coalesce(NEW.datos_nuevos::text, '') || '|' || coalesce(NEW.uuid_registro_afectado::text, '') || prev_hash, 'sha256'), 'hex');
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
