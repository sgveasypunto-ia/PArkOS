"""0075_fix_ensure_partitions_overlap_and_grants -- repair the two
non-blocking defects left by 0064 (missing grants + pairing_tokens UPDATE),
and upgrade ``prod.fn_ensure_partitions()`` to self-heal grants on every
call.

Revision ID: 0075_fix_ensure_partitions_overlap_and_grants
Revises: 0074_backfill_arqueo_uuid_sucursal
Create Date: 2026-10-02 00:00:00.000000

SPLIT WITH 0064 -- WHY PART OF THIS FIX IS HERE AND PART IS IN 0064
----------------------------------------------------------------------
Fase 0 QA bootstrap (2026-10-02) found THREE real defects in
``0064_ensure_forward_partitions.py``. Two of them (described below) are
data/privilege gaps that a SUCCESSFULLY-COMPLETED 0064 silently leaves
behind -- exactly the shape this repo's append-only convention already has
five precedents for (0043, 0052, 0057, 0069, 0070: each fixes a gap left by
an earlier, successfully-applied migration for environments that already
ran it). Those two live here, as a new migration, per that convention.

The THIRD defect -- a partition name/bound collision that makes
``fn_ensure_partitions()`` raise ``ERROR: partition ... would overlap
partition ...`` (SQLSTATE 42P17) on literally every fresh bootstrap -- does
NOT fit that convention: it crashes 0064 itself, so Alembic never advances
past it and a later migration (this one) could never be reached to fix it.
No environment has ever successfully completed that function body via a
clean ``alembic upgrade head`` (every existing environment, including this
project's own QA ``cloud-db``/``branch-db``, bootstrapped around it with a
manual, undocumented, data-level workaround). Since Alembic only executes
a revision once per environment, editing 0064's SQL body is inert for any
environment that already recorded it as applied -- it only changes
behavior for NEW environments that haven't run it yet. That fix was
therefore made IN PLACE in ``0064_ensure_forward_partitions.py`` (see that
file's module docstring, "IN-PLACE FIX" section, for the full account) --
it is the only way a fresh bootstrap can ever reach this migration at all.

This migration assumes 0064 already includes that overlap fix and focuses
on the two defects below, plus folding the grant-sync helper into
``fn_ensure_partitions()`` itself so every future call -- fresh bootstrap
or ops re-run -- keeps partition grants correct automatically.

TWO REAL DEFECTS FIXED HERE
-------------------------------
1. MISSING GRANTS on partitions ``fn_ensure_partitions()`` creates (and on
   every pre-existing partition, including the ``0001``-era ``_p_current``
   / ``_default`` ones). PostgreSQL does NOT check a partitioned table's
   privileges when a partition is referenced DIRECTLY by name -- only
   queries against the ROOT partitioned table are checked against the
   root's ACL. Confirmed empirically: ``\\dp prod.arqueo_p_current`` on a
   DB migrated straight through ``0074`` shows an EMPTY ACL, while
   ``prod.arqueo`` itself carries ``rol_app=ar`` + ``rol_admin_auditor=r``.
   Any code path that names a partition directly (ops runbooks, exports,
   the DIAN retention worker, ad hoc audit queries) gets
   ``InsufficientPrivilegeError`` even though the identical query against
   the parent works fine. There is no ``ALTER DEFAULT PRIVILEGES`` in this
   project (same root cause documented in 0070's docstring), so nothing
   ever re-grants for tables created outside a migration's own GRANT
   statements -- and partitions created by a PL/pgSQL function are exactly
   that case.

   FIX: new helper ``prod.fn_sync_partition_grants(p_parent text)`` reads
   every grantee + privilege ``rol_app``/``rol_admin_auditor``/etc. actually
   hold on the PARENT (via ``information_schema.role_table_grants`` for
   table-wide privileges and ``role_column_grants`` for column-scoped ones
   such as the narrow bi-temporal ``UPDATE (col1, col2)`` pattern used
   elsewhere in this chain), then replicates the exact same grants onto
   every current child partition of that parent. It is generic (no
   per-table hardcoded privilege list) and safe to re-run (GRANT is
   idempotent). ``fn_ensure_partitions()`` now calls it once per parent
   after processing that parent's windows, so every call -- fresh bootstrap
   or a later ops re-run -- also repairs any partition (old or new)
   missing grants.

2. ``pairing_tokens`` is missing ``UPDATE`` for ``rol_app``, which breaks
   ``POST /sync/pair``. ``0006_add_pairing_tokens_and_normalized_revoked_
   sync_jwts.py`` deliberately did ``REVOKE UPDATE, DELETE ON
   prod.pairing_tokens FROM rol_app`` + a ``BEFORE UPDATE OR DELETE``
   immutable trigger ([A] canon -- corrections are new rows, never
   in-place updates). But ``repo/pairing.py::consume_pairing_token`` locks
   the candidate row with ``SELECT ... FOR UPDATE SKIP LOCKED`` to make the
   consume atomic -- and PostgreSQL requires the ``UPDATE`` privilege on
   the table to execute ``FOR UPDATE`` AT ALL, regardless of which column
   an eventual UPDATE would touch, and regardless of whether any UPDATE
   statement ever actually runs (confirmed empirically in the sandbox: the
   SAME append-only shape reproduces ``permission denied`` on
   ``FOR UPDATE`` with UPDATE revoked, and succeeds once a column-scoped
   UPDATE grant is added -- while a REAL ``UPDATE`` statement still fails
   with the immutable trigger's exception, proving the trigger remains the
   actual enforcement layer). Exact same shape already fixed once in this
   chain for ``reimpresion_ticket`` (``0052_reimpresion_ticket_forupdate_
   lock_grant.py``).

   FIX: ``GRANT UPDATE (used_at) ON prod.pairing_tokens TO rol_app`` --
   column-scoped (never full-table) per the project's least-privilege
   pattern, satisfies PostgreSQL's ``FOR UPDATE`` ACL check, and the
   pre-existing immutable trigger still blocks any real UPDATE DML
   (including from ``rol_app``) exactly as before.

VERIFICATION
------------
All three defects reproduced AND the fixes verified against a disposable,
throwaway ``parkos-postgres:16-pgpartman`` container (NOT ``cloud-db``/
``branch-db``) migrated 0001->head on 2026-10-02: the pre-fix chain failed
at ``0064`` with the exact 42P17 overlap above; with this migration
applied, ``alembic upgrade head`` completes cleanly, every monthly/daily
partition (old and new) carries the same ACL as its parent, and a
synthetic ``SELECT ... FOR UPDATE SKIP LOCKED`` against ``pairing_tokens``
as ``rol_app`` succeeds post-grant (and a real ``UPDATE`` still raises
``PAIRING_TOKENS_INMUTABLE``).
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0075_fix_ensure_partitions_overlap_and_grants"
down_revision = "0074_backfill_arqueo_uuid_sucursal"
branch_labels = None
depends_on = None


SYNC_GRANTS_FN = """
CREATE OR REPLACE FUNCTION prod.fn_sync_partition_grants(p_parent text)
RETURNS void
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_child   text;
    v_grantee text;
    v_priv    text;
    v_cols    text;
BEGIN
    FOR v_child IN
        SELECT c.relname
        FROM pg_inherits i
        JOIN pg_class c ON c.oid = i.inhrelid
        JOIN pg_class p ON p.oid = i.inhparent
        JOIN pg_namespace n ON n.oid = p.relnamespace
        WHERE n.nspname = 'prod' AND p.relname = p_parent
    LOOP
        FOR v_grantee IN
            SELECT DISTINCT grantee
            FROM information_schema.role_table_grants
            WHERE table_schema = 'prod' AND table_name = p_parent
        LOOP
            -- Table-wide privileges the grantee holds on the parent.
            FOR v_priv IN
                SELECT privilege_type
                FROM information_schema.role_table_grants
                WHERE table_schema = 'prod' AND table_name = p_parent
                  AND grantee = v_grantee
            LOOP
                EXECUTE format('GRANT %s ON prod.%I TO %I', v_priv, v_child, v_grantee);
            END LOOP;

            -- Column-scoped UPDATE (only relevant when there is no
            -- table-wide UPDATE already granted above) -- mirrors the
            -- narrow bi-temporal UPDATE(col, col) pattern used elsewhere
            -- in this chain (0021, 0043, 0052, 0070).
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.role_table_grants
                WHERE table_schema = 'prod' AND table_name = p_parent
                  AND grantee = v_grantee AND privilege_type = 'UPDATE'
            ) THEN
                SELECT string_agg(DISTINCT column_name, ', ' ORDER BY column_name)
                INTO v_cols
                FROM information_schema.role_column_grants
                WHERE table_schema = 'prod' AND table_name = p_parent
                  AND grantee = v_grantee AND privilege_type = 'UPDATE';
                IF v_cols IS NOT NULL THEN
                    EXECUTE format('GRANT UPDATE (%s) ON prod.%I TO %I', v_cols, v_child, v_grantee);
                END IF;
            END IF;
        END LOOP;
    END LOOP;
END;
$fn$;
"""

DROP_SYNC_GRANTS_FN = "DROP FUNCTION IF EXISTS prod.fn_sync_partition_grants(text);"

# Same signature as 0064's version. Two behavioral changes only:
#   (a) each CREATE TABLE ... PARTITION OF is wrapped so a 42P17
#       (partition bound overlaps an existing, differently-named
#       partition) is logged and skipped instead of aborting the call;
#   (b) prod.fn_sync_partition_grants(v_parent) runs once per parent
#       after its windows are processed, repairing grants on every
#       current child (old and new) of that parent.
CREATE_FN_FIXED = """
CREATE OR REPLACE FUNCTION prod.fn_ensure_partitions(
    p_near_months      int DEFAULT 15,
    p_retention_lag    int DEFAULT 60,
    p_retention_months int DEFAULT 9,
    p_buffer_days      int DEFAULT 30
)
RETURNS TABLE (parent_name text, partition_name text, bounds text)
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_parent text;
    v_part   text;
    v_start  date;
    v_end    date;
    v_i      int;
BEGIN
    -- Pass 1: monthly tables keyed by fecha_retencion_hasta.
    FOR v_parent IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'prod'
          AND c.relkind = 'p'
          AND pg_get_partkeydef(c.oid) = 'RANGE (fecha_retencion_hasta)'
        ORDER BY c.relname
    LOOP
        FOR v_i IN 0..p_near_months LOOP
            v_start := (date_trunc('month', CURRENT_DATE)
                        + (v_i || ' month')::interval)::date;
            v_end   := (v_start + interval '1 month')::date;
            v_part  := format('%s_p_%s', v_parent, to_char(v_start, 'YYYY_MM'));
            IF to_regclass('prod.' || v_part) IS NULL THEN
                BEGIN
                    EXECUTE format(
                        'CREATE TABLE prod.%I PARTITION OF prod.%I '
                        'FOR VALUES FROM (%L) TO (%L)',
                        v_part, v_parent, v_start, v_end);
                    parent_name := v_parent;
                    partition_name := v_part;
                    bounds := format('%s..%s', v_start, v_end);
                    RETURN NEXT;
                EXCEPTION WHEN invalid_object_definition THEN
                    -- 42P17: bounds already covered by a differently-named
                    -- partition (e.g. 0001's "<table>_p_current" on a
                    -- same-day fresh bootstrap). Nothing to create.
                    RAISE NOTICE
                        '0075: % bounds %..% already covered by an '
                        'existing partition (overlap on %); skipping',
                        v_parent, v_start, v_end, v_part;
                END;
            END IF;
        END LOOP;

        FOR v_i IN p_retention_lag..(p_retention_lag + p_retention_months) LOOP
            v_start := (date_trunc('month', CURRENT_DATE)
                        + (v_i || ' month')::interval)::date;
            v_end   := (v_start + interval '1 month')::date;
            v_part  := format('%s_p_%s', v_parent, to_char(v_start, 'YYYY_MM'));
            IF to_regclass('prod.' || v_part) IS NULL THEN
                BEGIN
                    EXECUTE format(
                        'CREATE TABLE prod.%I PARTITION OF prod.%I '
                        'FOR VALUES FROM (%L) TO (%L)',
                        v_part, v_parent, v_start, v_end);
                    parent_name := v_parent;
                    partition_name := v_part;
                    bounds := format('%s..%s', v_start, v_end);
                    RETURN NEXT;
                EXCEPTION WHEN invalid_object_definition THEN
                    RAISE NOTICE
                        '0075: % bounds %..% already covered by an '
                        'existing partition (overlap on %); skipping',
                        v_parent, v_start, v_end, v_part;
                END;
            END IF;
        END LOOP;

        v_part := v_parent || '_default';
        IF to_regclass('prod.' || v_part) IS NULL THEN
            BEGIN
                EXECUTE format(
                    'CREATE TABLE prod.%I PARTITION OF prod.%I DEFAULT',
                    v_part, v_parent);
                parent_name := v_parent;
                partition_name := v_part;
                bounds := 'DEFAULT (safety net -- must stay empty)';
                RETURN NEXT;
            EXCEPTION WHEN invalid_object_definition THEN
                RAISE NOTICE
                    '0075: % DEFAULT partition already covered '
                    '(overlap on %); skipping', v_parent, v_part;
            END;
        END IF;

        -- Repair grants on every current child of this parent -- old
        -- (0001 "_p_current"/"_default") and new alike.
        PERFORM prod.fn_sync_partition_grants(v_parent);
    END LOOP;

    -- Pass 2: the daily buffer, plus a DEFAULT safety net.
    FOR v_parent IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'prod'
          AND c.relkind = 'p'
          AND pg_get_partkeydef(c.oid) = 'RANGE (buffered_at)'
        ORDER BY c.relname
    LOOP
        FOR v_i IN 0..p_buffer_days LOOP
            v_start := (CURRENT_DATE + v_i)::date;
            v_end   := (v_start + 1)::date;
            v_part  := format('%s_p_%s', v_parent, to_char(v_start, 'YYYY_MM_DD'));
            IF to_regclass('prod.' || v_part) IS NULL THEN
                BEGIN
                    EXECUTE format(
                        'CREATE TABLE prod.%I PARTITION OF prod.%I '
                        'FOR VALUES FROM (%L) TO (%L)',
                        v_part, v_parent, v_start, v_end);
                    parent_name := v_parent;
                    partition_name := v_part;
                    bounds := format('%s..%s', v_start, v_end);
                    RETURN NEXT;
                EXCEPTION WHEN invalid_object_definition THEN
                    RAISE NOTICE
                        '0075: % bounds %..% already covered by an '
                        'existing partition (overlap on %); skipping',
                        v_parent, v_start, v_end, v_part;
                END;
            END IF;
        END LOOP;

        v_part := v_parent || '_default';
        IF to_regclass('prod.' || v_part) IS NULL THEN
            BEGIN
                EXECUTE format(
                    'CREATE TABLE prod.%I PARTITION OF prod.%I DEFAULT',
                    v_part, v_parent);
                parent_name := v_parent;
                partition_name := v_part;
                bounds := 'DEFAULT (safety net -- must stay empty)';
                RETURN NEXT;
            EXCEPTION WHEN invalid_object_definition THEN
                RAISE NOTICE
                    '0075: % DEFAULT partition already covered '
                    '(overlap on %); skipping', v_parent, v_part;
            END;
        END IF;

        PERFORM prod.fn_sync_partition_grants(v_parent);
    END LOOP;
END;
$fn$;
"""

# The body 0064 itself installs (overlap-safe, no grant-sync yet) --
# restored on downgrade() so this revision's rollback leaves the function
# exactly as 0064 left it, not as this migration's enhanced version.
CREATE_FN_AS_LEFT_BY_0064 = """
CREATE OR REPLACE FUNCTION prod.fn_ensure_partitions(
    p_near_months      int DEFAULT 15,
    p_retention_lag    int DEFAULT 60,
    p_retention_months int DEFAULT 9,
    p_buffer_days      int DEFAULT 30
)
RETURNS TABLE (parent_name text, partition_name text, bounds text)
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_parent text;
    v_part   text;
    v_start  date;
    v_end    date;
    v_i      int;
BEGIN
    FOR v_parent IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'prod'
          AND c.relkind = 'p'
          AND pg_get_partkeydef(c.oid) = 'RANGE (fecha_retencion_hasta)'
        ORDER BY c.relname
    LOOP
        FOR v_i IN 0..p_near_months LOOP
            v_start := (date_trunc('month', CURRENT_DATE)
                        + (v_i || ' month')::interval)::date;
            v_end   := (v_start + interval '1 month')::date;
            v_part  := format('%s_p_%s', v_parent, to_char(v_start, 'YYYY_MM'));
            IF to_regclass('prod.' || v_part) IS NULL THEN
                BEGIN
                    EXECUTE format(
                        'CREATE TABLE prod.%I PARTITION OF prod.%I '
                        'FOR VALUES FROM (%L) TO (%L)',
                        v_part, v_parent, v_start, v_end);
                    parent_name := v_parent;
                    partition_name := v_part;
                    bounds := format('%s..%s', v_start, v_end);
                    RETURN NEXT;
                EXCEPTION WHEN invalid_object_definition THEN
                    RAISE NOTICE
                        '0064: % bounds %..% already covered by an '
                        'existing partition (overlap on %); skipping',
                        v_parent, v_start, v_end, v_part;
                END;
            END IF;
        END LOOP;

        FOR v_i IN p_retention_lag..(p_retention_lag + p_retention_months) LOOP
            v_start := (date_trunc('month', CURRENT_DATE)
                        + (v_i || ' month')::interval)::date;
            v_end   := (v_start + interval '1 month')::date;
            v_part  := format('%s_p_%s', v_parent, to_char(v_start, 'YYYY_MM'));
            IF to_regclass('prod.' || v_part) IS NULL THEN
                BEGIN
                    EXECUTE format(
                        'CREATE TABLE prod.%I PARTITION OF prod.%I '
                        'FOR VALUES FROM (%L) TO (%L)',
                        v_part, v_parent, v_start, v_end);
                    parent_name := v_parent;
                    partition_name := v_part;
                    bounds := format('%s..%s', v_start, v_end);
                    RETURN NEXT;
                EXCEPTION WHEN invalid_object_definition THEN
                    RAISE NOTICE
                        '0064: % bounds %..% already covered by an '
                        'existing partition (overlap on %); skipping',
                        v_parent, v_start, v_end, v_part;
                END;
            END IF;
        END LOOP;

        v_part := v_parent || '_default';
        IF to_regclass('prod.' || v_part) IS NULL THEN
            BEGIN
                EXECUTE format(
                    'CREATE TABLE prod.%I PARTITION OF prod.%I DEFAULT',
                    v_part, v_parent);
                parent_name := v_parent;
                partition_name := v_part;
                bounds := 'DEFAULT (safety net -- must stay empty)';
                RETURN NEXT;
            EXCEPTION WHEN invalid_object_definition THEN
                RAISE NOTICE
                    '0064: % DEFAULT partition already covered '
                    '(overlap on %); skipping', v_parent, v_part;
            END;
        END IF;
    END LOOP;

    FOR v_parent IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'prod'
          AND c.relkind = 'p'
          AND pg_get_partkeydef(c.oid) = 'RANGE (buffered_at)'
        ORDER BY c.relname
    LOOP
        FOR v_i IN 0..p_buffer_days LOOP
            v_start := (CURRENT_DATE + v_i)::date;
            v_end   := (v_start + 1)::date;
            v_part  := format('%s_p_%s', v_parent, to_char(v_start, 'YYYY_MM_DD'));
            IF to_regclass('prod.' || v_part) IS NULL THEN
                BEGIN
                    EXECUTE format(
                        'CREATE TABLE prod.%I PARTITION OF prod.%I '
                        'FOR VALUES FROM (%L) TO (%L)',
                        v_part, v_parent, v_start, v_end);
                    parent_name := v_parent;
                    partition_name := v_part;
                    bounds := format('%s..%s', v_start, v_end);
                    RETURN NEXT;
                EXCEPTION WHEN invalid_object_definition THEN
                    RAISE NOTICE
                        '0064: % bounds %..% already covered by an '
                        'existing partition (overlap on %); skipping',
                        v_parent, v_start, v_end, v_part;
                END;
            END IF;
        END LOOP;

        v_part := v_parent || '_default';
        IF to_regclass('prod.' || v_part) IS NULL THEN
            BEGIN
                EXECUTE format(
                    'CREATE TABLE prod.%I PARTITION OF prod.%I DEFAULT',
                    v_part, v_parent);
                parent_name := v_parent;
                partition_name := v_part;
                bounds := 'DEFAULT (safety net -- must stay empty)';
                RETURN NEXT;
            EXCEPTION WHEN invalid_object_definition THEN
                RAISE NOTICE
                    '0064: % DEFAULT partition already covered '
                    '(overlap on %); skipping', v_parent, v_part;
            END;
        END IF;
    END LOOP;
END;
$fn$;
"""

GRANT_PAIRING_TOKENS_UPDATE = (
    "GRANT UPDATE (used_at) ON prod.pairing_tokens TO rol_app;"
)
REVOKE_PAIRING_TOKENS_UPDATE = (
    "REVOKE UPDATE (used_at) ON prod.pairing_tokens FROM rol_app;"
)


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(text(SYNC_GRANTS_FN))
    bind.execute(text(CREATE_FN_FIXED))
    bind.execute(text(GRANT_PAIRING_TOKENS_UPDATE))

    # Re-run now: completes any still-missing forward partitions AND
    # backfills grants on every existing partition (old "_p_current"/
    # "_default" included) for environments that already ran 0064.
    created = bind.execute(
        text("SELECT count(*) FROM prod.fn_ensure_partitions()")
    ).scalar_one()
    print(
        f"0075: fn_ensure_partitions() created {created} additional "
        "partition(s); grants synced on every partition"
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(REVOKE_PAIRING_TOKENS_UPDATE))
    bind.execute(text(CREATE_FN_AS_LEFT_BY_0064))
    bind.execute(text(DROP_SYNC_GRANTS_FN))
