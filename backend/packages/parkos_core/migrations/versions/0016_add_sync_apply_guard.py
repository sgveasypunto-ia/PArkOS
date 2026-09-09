"""add ``parkos.sync_apply_in_progress`` session GUC check to
``fn_enqueue_sync()`` / ``fn_enqueue_sync_catalog()`` — echo-amplification
fix (post-sync-overhaul Docker E2E hardening, real defect #3)

Revision ID: 0016_add_sync_apply_guard
Revises: 0015_drop_infra_triggers
Create Date: 2026-09-09 07:30:00.000000

**The bug (confirmed against the real Docker deployment, not testcontainers).**
``openspec/changes/sync-overhaul/tasks.md``'s post-PR14 real-Docker closing
exercise disclosed — and deliberately left unfixed at the time — that every
``AFTER INSERT ... fn_enqueue_sync()``/``fn_enqueue_sync_catalog()`` trigger
(``0001_initial_schema.py``, ``0014_add_catalog_triggers.py``) fires
UNCONDITIONALLY on every INSERT, including the ones the sync motor itself
performs while APPLYING an event that already arrived via sync
(``motor/apply_row.py::apply_row``, dispatched from
``jobs/sync_cloud.py::_apply_pending_batch_once``,
``jobs/sync_sucursal.py::_pull_and_apply``/``_pull_and_apply_catalog``, and
``api/v1/sync_router.py::sync_events`` — the last one mounted on BOTH
processes, so both the cloud-side and branch-side receivers are affected).
That confirmed as real once a genuine long-running worker exercised it end
to end: ``motor.verify_chain`` found dozens of real ``ChainAnomaly`` breaks
on both ``log_transaccional`` and ``revocacion_factura`` — an "echo" row
re-enqueued by the motor's own write got picked back up by
``job-sync-cloud``'s apply loop and RE-APPLIED, extending the SHA-256 hash
chain a SECOND time for the same logical event (``repo.hash_chain.append``
has no way to know the row it is chaining is a duplicate of one already
chained). The data itself always lands correctly (every row is present,
confirmed by uuid) — only the chain-integrity invariant (`hash_anterior`
must equal the prior row's `hash_actual`, exactly one extension per logical
event) breaks, which is the single most important DIAN-compliance defense
this schema has.

**The fix (standard Postgres "don't re-trigger on your own re-apply"
pattern).** A session-local GUC (``SET LOCAL parkos.sync_apply_in_progress
= 'true'``, transactional — resets itself automatically at the end of the
current transaction/savepoint, NEVER a column or a table) that the sync
motor sets immediately before writing a row it received via sync
(``sync.motor.apply_guard.enable_echo_suppression``, wired into the 4 call
sites named above — see that module's own docstring). Both trigger
functions now check ``current_setting('parkos.sync_apply_in_progress',
true)`` (the ``true`` second argument means "return NULL instead of raising
when unset" — a plain, locally-originated INSERT from application code,
e.g. an admin creating a row from the UI, never sets this GUC and therefore
enqueues exactly as before) as the VERY FIRST statement in each function
body, before any enqueue logic runs. When the GUC reads ``'true'`` the
function returns ``NEW`` immediately, WITHOUT touching ``prod.sync_queue`` —
the row itself is still inserted into its real table normally; only the
echo enqueue is skipped.

**Why ``CREATE OR REPLACE FUNCTION``, not a new function.** Both trigger
functions already exist (``fn_enqueue_sync()`` since ``0001``,
``fn_enqueue_sync_catalog()`` since ``0014``) and every trigger already
wired to them (30 + 18 = 48 ``AFTER INSERT`` triggers across the two) keeps
working unchanged — a trigger is bound to a function by name/OID, and
``CREATE OR REPLACE FUNCTION`` swaps the body in place without touching any
``CREATE TRIGGER`` statement, matching the exact precedent
``0010``/``0014``/``0015`` already established for fixing a real trigger
defect discovered after the fact (this migration's own note mirrors
``0015``'s "an oversight... this migration removes exactly..." framing).
No table is recreated, no trigger is dropped/recreated, no data is touched.

**Why the GUC and not (a) a payload flag, (b) a dedicated bypass role, or
(c) a post-apply self-settle step (the 3 alternatives ``tasks.md`` itself
listed as "neither attempted" when this was first disclosed).** (a) would
require every one of the 48 trigger-attached tables' INSERT statements
across every ``repo/*`` helper to carry an extra sentinel column/value that
means nothing to the schema itself — a leaky, per-write parameter for what
is fundamentally a per-CONNECTION/transaction concern. (b) (a second DB
role the motor's connection assumes while applying) would need its own
migration-driven ``GRANT``/``REVOKE`` surface AND a second connection pool
just for that role — solving a trigger-recursion problem with a
credentials/authorization mechanism. (c) (let the echo enqueue happen, then
have the motor delete/settle it after the fact) still lets
``job-sync-cloud``'s independent, concurrently-running apply loop win the
race and re-apply the echo before the "self-settle" step runs — it does not
actually close the race, only narrows it. The session GUC is the standard,
narrowly-scoped Postgres idiom for exactly this "don't re-fire my own
trigger" problem, transactional by construction (auto-resets, cannot leak
across connections/requests), and requires no schema/authorization surface
at all.

Pre-flight: ``uv run alembic upgrade --sql 0016_add_sync_apply_guard``
reviewed before apply (2 ``CREATE OR REPLACE FUNCTION`` statements only —
no ``CREATE``/``DROP TRIGGER``, no data-destructive statements).
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0016_add_sync_apply_guard"
down_revision = "0015_drop_infra_triggers"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

#: The session GUC name both trigger functions check (sync.motor.apply_guard
#: mirrors this exact literal on the Python side — see that module).
_GUC_NAME = "parkos.sync_apply_in_progress"


def upgrade() -> None:
    """``CREATE OR REPLACE`` both enqueue-trigger functions with the new
    echo-suppression GUC check as their first statement."""
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute(f"""
        CREATE OR REPLACE FUNCTION prod.fn_enqueue_sync()
        RETURNS trigger AS $$
        DECLARE
            next_seq bigint;
            payload jsonb;
        BEGIN
            IF current_setting('{_GUC_NAME}', true) = 'true' THEN
                -- The sync motor itself is writing this row while applying
                -- an event that already arrived via sync (T-PR11-001+'s
                -- confirmed echo-amplification gap) — the row still gets
                -- inserted into its real table normally; only the
                -- re-enqueue is skipped. See this migration's own docstring.
                RETURN NEW;
            END IF;
            IF TG_TABLE_NAME = 'sync_queue' THEN
                RETURN NEW;
            END IF;
            SELECT COALESCE(MAX((datos->>'seq')::bigint), 0) + 1 INTO next_seq
              FROM prod.sync_queue
             WHERE uuid_sucursal IS NOT DISTINCT FROM NEW.uuid_sucursal;
            payload := to_jsonb(NEW);
            payload := jsonb_set(payload, '{{seq}}', to_jsonb(next_seq));
            INSERT INTO prod.sync_queue (
                uuid, uuid_sucursal, operacion, tabla, uuid_registro,
                datos, prioridad, estado, intentos,
                created_at, created_by, sync_status, sync_attempts)
            VALUES (
                gen_random_uuid(),
                NEW.uuid_sucursal,
                TG_OP,
                TG_TABLE_NAME,
                NEW.uuid,
                payload,
                CASE TG_TABLE_NAME
                    WHEN 'factura_electronica' THEN 10
                    WHEN 'revocacion_factura'  THEN 10
                    WHEN 'ingreso'             THEN 5
                    WHEN 'salidas'             THEN 5
                    WHEN 'factura_pagos'       THEN 5
                    ELSE 1
                END,
                'pendiente', 0,
                NOW(), NEW.created_by, 'pendiente', 0);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute(f"""
        CREATE OR REPLACE FUNCTION prod.fn_enqueue_sync_catalog()
        RETURNS trigger AS $$
        DECLARE
            next_seq bigint;
            payload jsonb;
            row_uuid_sucursal uuid;
        BEGIN
            IF current_setting('{_GUC_NAME}', true) = 'true' THEN
                -- Same echo-suppression guard as fn_enqueue_sync() above —
                -- see this migration's own docstring.
                RETURN NEW;
            END IF;
            payload := to_jsonb(NEW);
            -- Extract uuid_sucursal from the JSONB payload rather than
            -- referencing NEW.uuid_sucursal directly: none of the 18
            -- tables this function is attached to has a physical
            -- uuid_sucursal column (has_uuid_sucursal=False for all of
            -- them), and PL/pgSQL only validates NEW.<col> field access
            -- at trigger-fire time, not at CREATE FUNCTION time. NULL
            -- here correctly means "global, all_branches scope".
            row_uuid_sucursal := NULLIF(payload->>'uuid_sucursal', '')::uuid;
            SELECT COALESCE(MAX((datos->>'seq')::bigint), 0) + 1 INTO next_seq
              FROM prod.sync_queue
             WHERE uuid_sucursal IS NOT DISTINCT FROM row_uuid_sucursal;
            payload := jsonb_set(payload, '{{seq}}', to_jsonb(next_seq));
            INSERT INTO prod.sync_queue (
                uuid, uuid_sucursal, operacion, tabla, uuid_registro,
                datos, prioridad, estado, intentos,
                created_at, created_by, sync_status, sync_attempts)
            VALUES (
                gen_random_uuid(),
                row_uuid_sucursal,
                TG_OP,
                TG_TABLE_NAME,
                NEW.uuid,
                payload,
                -- SyncCatalogEntry.priority defaults to 1 for every [V]
                -- entry this trigger covers (REQ-CAT-012, D18) — an
                -- intra-level FIFO tie-break only, never a cross-table
                -- ordering criterion.
                1,
                'pendiente', 0,
                NOW(), NEW.created_by, 'pendiente', 0);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Restore both functions to their pre-0016 bodies (no GUC check) —
    verbatim from ``0001_initial_schema.py`` / ``0014_add_catalog_triggers.py``."""
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_enqueue_sync()
        RETURNS trigger AS $$
        DECLARE
            next_seq bigint;
            payload jsonb;
        BEGIN
            IF TG_TABLE_NAME = 'sync_queue' THEN
                RETURN NEW;
            END IF;
            SELECT COALESCE(MAX((datos->>'seq')::bigint), 0) + 1 INTO next_seq
              FROM prod.sync_queue
             WHERE uuid_sucursal IS NOT DISTINCT FROM NEW.uuid_sucursal;
            payload := to_jsonb(NEW);
            payload := jsonb_set(payload, '{seq}', to_jsonb(next_seq));
            INSERT INTO prod.sync_queue (
                uuid, uuid_sucursal, operacion, tabla, uuid_registro,
                datos, prioridad, estado, intentos,
                created_at, created_by, sync_status, sync_attempts)
            VALUES (
                gen_random_uuid(),
                NEW.uuid_sucursal,
                TG_OP,
                TG_TABLE_NAME,
                NEW.uuid,
                payload,
                CASE TG_TABLE_NAME
                    WHEN 'factura_electronica' THEN 10
                    WHEN 'revocacion_factura'  THEN 10
                    WHEN 'ingreso'             THEN 5
                    WHEN 'salidas'             THEN 5
                    WHEN 'factura_pagos'       THEN 5
                    ELSE 1
                END,
                'pendiente', 0,
                NOW(), NEW.created_by, 'pendiente', 0);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prod.fn_enqueue_sync_catalog()
        RETURNS trigger AS $$
        DECLARE
            next_seq bigint;
            payload jsonb;
            row_uuid_sucursal uuid;
        BEGIN
            payload := to_jsonb(NEW);
            row_uuid_sucursal := NULLIF(payload->>'uuid_sucursal', '')::uuid;
            SELECT COALESCE(MAX((datos->>'seq')::bigint), 0) + 1 INTO next_seq
              FROM prod.sync_queue
             WHERE uuid_sucursal IS NOT DISTINCT FROM row_uuid_sucursal;
            payload := jsonb_set(payload, '{seq}', to_jsonb(next_seq));
            INSERT INTO prod.sync_queue (
                uuid, uuid_sucursal, operacion, tabla, uuid_registro,
                datos, prioridad, estado, intentos,
                created_at, created_by, sync_status, sync_attempts)
            VALUES (
                gen_random_uuid(),
                row_uuid_sucursal,
                TG_OP,
                TG_TABLE_NAME,
                NEW.uuid,
                payload,
                1,
                'pendiente', 0,
                NOW(), NEW.created_by, 'pendiente', 0);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
