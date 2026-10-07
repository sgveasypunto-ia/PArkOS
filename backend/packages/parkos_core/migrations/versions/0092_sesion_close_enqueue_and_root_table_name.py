"""propagate the closing of a ``sesion`` and stamp the PARENT table name in
``sync_queue.tabla`` (SS1)

Revision ID: 0092_sesion_close_enqueue_and_root_table_name
Revises: 0091_mv_ocupacion_salida_anulada
Create Date: 2026-10-07 18:00:00.000000

Two independent defects of the branch -> cloud outbox, one migration because
both are fixed by the same pair of trigger functions.

**1. Closing a sesion never reached the cloud.** ``sesion_enqueue_sync`` is
``AFTER INSERT`` only (``0001``), but closing a cash session is an UPDATE of an
``[L-S]`` lifecycle row (``close_session_with_log``). Nothing was enqueued, so
the cloud kept the sesion ACTIVE forever; the same operator's next sesion then
violated ``uq_prod_sesion_one_active_per_user`` on the cloud and every child row
(arqueo, factura_pagos, facturas, factura_electronica, envio_dian, ...) failed
its FK until ``fallido``.

Design: the branch is the source of truth for its own sesions, so the closing
is shipped as one more outbox event, produced by the SAME function as the INSERT
(``prod.fn_enqueue_sync()``): ``AFTER UPDATE ... WHEN (the lifecycle columns
changed)``. The payload is the full ``to_jsonb(NEW)`` snapshot with
``timestamp_cierre`` set, which the cloud apply path already routes to
``close_session_with_log`` (``motor/apply_row.py``). Rows applied FROM sync never
loop back: the apply path sets ``parkos.sync_apply_in_progress`` (0016) and the
function returns before touching ``sync_queue``. The cloud applies the event as
an UPDATE of the same uuid (never a second insert), so the unique-active index
is never at risk. No physical DELETE anywhere; the ``[L-S]`` guard
(``sesion_ls_session_guard``) is untouched.

The ``WHEN`` clause keeps the trigger silent for UPDATEs that do not change the
lifecycle (``observaciones`` edits, ``sync_status`` bookkeeping): only
``timestamp_cierre``, ``uuid_usuario_cierre`` and ``estado`` matter.

**2. ``sync_queue.tabla`` carried the physical partition name.** On a
partitioned table (10 of them, pg_partman) the cloned row trigger fires with
``TG_TABLE_NAME`` = the CHILD (``log_transaccional_p_2026_10``,
``factura_pagos_p_2026_10``, ``*_default``). ``SYNC_CATALOG_BY_NAME`` is keyed by
the parent, so the cloud's own drain loop settled every such row
``unknown_table`` and it sat ``pendiente`` forever. Both enqueue functions now
resolve the partition root (``pg_partition_root(TG_RELID)``, falling back to
``TG_TABLE_NAME`` for an ordinary table) and use it for ``tabla`` and for the
priority ``CASE`` (children used to get priority 1 instead of the intended
5/10). Existing bad rows are NOT rewritten or deleted: the worker now
normalizes the name and settles self-origin rows (see ``jobs/sync_cloud.py``);
the operational reset (``estado/intentos/next_retry_at/ultimo_error`` only) is
documented in ``docs/03-desarrollo/setup.md``.

Pre-flight: ``uv run alembic upgrade --sql 0091_mv_ocupacion_salida_anulada:0092_sesion_close_enqueue_and_root_table_name``
(2 ``CREATE OR REPLACE FUNCTION`` + 1 ``CREATE TRIGGER``; nothing destructive).
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0092_sesion_close_enqueue_and_root_table_name"
down_revision = "0091_mv_ocupacion_salida_anulada"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

_GUC_NAME = "parkos.sync_apply_in_progress"

# PL/pgSQL fragment shared by both functions. ``pg_partition_root`` returns NULL
# for a relation that is not part of a partition tree, hence the COALESCE.
_ROOT_TABLE_SQL = """
            root_table := COALESCE(
                (SELECT c.relname FROM pg_class c
                  WHERE c.oid = pg_partition_root(TG_RELID)),
                TG_TABLE_NAME);"""


def upgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute(f"""
        CREATE OR REPLACE FUNCTION prod.fn_enqueue_sync()
        RETURNS trigger AS $$
        DECLARE
            next_seq bigint;
            payload jsonb;
            root_table text;
        BEGIN
            IF current_setting('{_GUC_NAME}', true) = 'true' THEN
                RETURN NEW;
            END IF;
            IF TG_TABLE_NAME = 'sync_queue' THEN
                RETURN NEW;
            END IF;{_ROOT_TABLE_SQL}
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
                root_table,
                NEW.uuid,
                payload,
                CASE root_table
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
            root_table text;
        BEGIN
            IF current_setting('{_GUC_NAME}', true) = 'true' THEN
                RETURN NEW;
            END IF;{_ROOT_TABLE_SQL}
            payload := to_jsonb(NEW);
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
                root_table,
                NEW.uuid,
                payload,
                1,
                'pendiente', 0,
                NOW(), NEW.created_by, 'pendiente', 0);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("DROP TRIGGER IF EXISTS sesion_enqueue_sync_close ON prod.sesion;")
    op.execute("""
        CREATE TRIGGER sesion_enqueue_sync_close
            AFTER UPDATE ON prod.sesion
            FOR EACH ROW
            WHEN (
                OLD.timestamp_cierre IS DISTINCT FROM NEW.timestamp_cierre
                OR OLD.uuid_usuario_cierre IS DISTINCT FROM NEW.uuid_usuario_cierre
                OR OLD.estado IS DISTINCT FROM NEW.estado
            )
            EXECUTE FUNCTION prod.fn_enqueue_sync();
    """)


def downgrade() -> None:
    """Drop the close trigger and restore both functions to their 0016 bodies."""
    op.execute(_LOCK_TIMEOUT_SQL)
    op.execute("DROP TRIGGER IF EXISTS sesion_enqueue_sync_close ON prod.sesion;")

    op.execute(f"""
        CREATE OR REPLACE FUNCTION prod.fn_enqueue_sync()
        RETURNS trigger AS $$
        DECLARE
            next_seq bigint;
            payload jsonb;
        BEGIN
            IF current_setting('{_GUC_NAME}', true) = 'true' THEN
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
                RETURN NEW;
            END IF;
            payload := to_jsonb(NEW);
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
                1,
                'pendiente', 0,
                NOW(), NEW.created_by, 'pendiente', 0);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
