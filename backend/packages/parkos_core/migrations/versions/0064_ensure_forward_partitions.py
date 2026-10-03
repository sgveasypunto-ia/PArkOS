"""0064_ensure_forward_partitions -- forward partitions for every partitioned table.

THE PROBLEM THIS PINS
---------------------
Eleven tables in ``prod`` are declaratively RANGE-partitioned, and the
initial migration (``0001_initial_schema.py``) created their partitions
like this::

    CREATE TABLE prod.salidas_p_current PARTITION OF prod.salidas
      FOR VALUES FROM (date_trunc('month', CURRENT_DATE)::date)
                    TO   (date_trunc('month', CURRENT_DATE)::date + interval '1 month');

``date_trunc('month', CURRENT_DATE)`` is evaluated ONCE, when the
migration runs. It is not a rolling window. The migration ran in
September 2026, so it created exactly one real partition per table:
``FOR VALUES FROM ('2026-09-01') TO ('2026-10-01')``. Since then,
nothing in the codebase creates a new partition.

Two failure modes fall out of that, and they are NOT the same severity:

1. HARD FAILURE -- ``sync_queue`` and ``sync_queue_lw_buffer`` have no
   DEFAULT partition. On 2026-10-01 every write whose partition key
   falls outside September raises::

       asyncpg.exceptions.CheckViolationError:
           no partition of relation "sync_queue" found for row
       DETAIL: Partition key of the failing row contains
               (fecha_retencion_hasta) = (2026-10-01).

   ``prod.login`` carries the ``login_enqueue_sync`` trigger, so this
   surfaces as HTTP 500 on ``POST /api/v1/auth/login``. Valid
   credentials return 500 because the audit-row INSERT cannot land.
   Every write into ``caja``, ``salidas``, ``arqueo``, the ``factura_*``
   tables and the ``log_transaccional`` hash chain is affected the same
   way.

2. SILENT DEGRADATION -- the other nine tables DO have a ``*_default``
   partition, so their October writes do not fail: they land in a
   partition with no bounds. Partition pruning is gone for those rows
   and all future data piles into one table until someone notices. This
   is the more dangerous mode because it never raises: ``log_transaccional``
   is the DIAN audit hash chain, and its rows have been silently routed
   to ``log_transaccional_default`` since 2026-10-01.

The whole system dies on the first of every month, permanently, until
a human notices and hand-writes CREATE TABLE statements.

WHY pg_partman DID NOT SAVE US (the real root cause)
------------------------------------------------------
``AGENTS.md``, ``docs/01-requisitos/no-funcionales.md`` (RNF-PERF-01)
and ``docs/02-arquitectura/modelo-datos.md`` section 6 all state that
these tables are "managed by pg_partman". pg_partman IS installed
(5.5.0), ``pg_partman_bgw`` IS in ``shared_preload_libraries``, and all
eight parents ARE present in ``partman.part_config`` with
``automatic_maintenance = 'on'``. Every one of those facts is true and
the system was still completely broken. Two independent defects:

DEFECT 1 -- the parent names never resolved. ``part_config.parent_table``
for the eight monthly tables was stored as ``parkos.prod.<table>`` --
database-qualified. pg_partman 5.x expects ``schema.table``. So the
background worker did this, on every run, forever::

    WARNING:  pg_partman maintenance skipped partition set for parent
              table parkos.prod.salidas: Given parent table not found
              in system catalogs: parkos.prod.salidas

A WARNING, not an ERROR. The worker exits 0, nothing alerts, and no
partition is ever created. ``maintenance_last_run`` was NULL on every
row, which is the observable symptom. The one parent registered
correctly -- ``prod.sync_queue_lw_buffer`` -- proves the intended
format. This migration repairs the prefix; see ``REPAIR_PART_CONFIG``.

DEFECT 2 -- nothing was scheduled. ``pg_cron`` is not available in the
image, so there is no scheduler to invoke ``run_maintenance_proc()``,
and the ``pg_partman_bgw`` worker had no trigger even once the names
were valid. Repairing defect 1 alone still leaves the tables
unmaintained, which is why this migration ALSO creates the partitions
explicitly rather than relying on pg_partman to get around to it. Wiring
a real scheduler is tracked in ADR-004; until then the static function
below is what actually runs.

The instructive part is that CI gate (h) in
``openspec/scripts/check_schema_match.py`` asserted all eight tables were
registered in ``part_config`` -- and it PASSED, because they were
registered. It checked that a registration existed, not that the
registration could resolve to a real relation, and not that a partition
covering today existed. A gate that asserts bookkeeping rather than
behaviour is worse than no gate: it manufactures confidence. The gate is
now coverage-based.

THIS MIGRATION IS THE STATIC PATCH, NOT THE FIX
------------------------------------------------
Per the maintainer's decision, this migration creates partitions
explicitly rather than registering pg_partman. That unblocks the system
today and leaves pg_partman as tracked follow-up work (ADR-004). The
function form is deliberate: no daemon runs, but the next person facing
this under pressure runs ONE call instead of hand-writing eleven CREATE
TABLE statements while the system is down.

``prod.fn_ensure_partitions()`` is idempotent and discovers its parents
from the catalog, so it is safe to call at any time.

TWO WINDOWS, AND WHY TWO
------------------------
``fecha_retencion_hasta`` is a POLYMORPHIC key: some writers stamp the
event date, others stamp ``today + 5 years`` (DIAN retention). This is
not a typo in the diagnosis, it is what the code does:

* ``repo/factura_detalle.py`` writes ``date.today()`` -- with a NOTE
  saying it was changed from ``today + 5*365`` precisely because a
  correct retention date "fell outside the only partition";
* ``dian/cloud/dispatcher.py`` writes ``_now_naive().date() + timedelta(days=365 * _DIAN_RETENTION_YEARS)``;
* ``prod.salidas_default`` already holds 8 rows dated 2028-09, proving
  ``salidas`` still writes real retention dates.

A single "current month" window cannot serve both semantics: a row
written today may belong in this month or in five years. So each parent
gets two windows -- a NEAR one covering now, and a RETENTION one
covering the +5y horizon. Tables that keep using ``date.today()`` land
in the near window; the ones that keep the DIAN horizon land in the
retention window; both are real partitions, so neither degrades.

MONTHLY KEY vs DAILY KEY
------------------------
``sync_queue_lw_buffer`` is partitioned ``RANGE (buffered_at)`` on a
DAILY cadence and had a single one-day partition (2026-09-23 ->
2026-09-24). It gets its own daily window plus a DEFAULT safety net: it
is an ephemeral buffer with a 24h TTL, so a row in DEFAULT is harmless,
whereas a 500 on the sync path is not.

EXACT WINDOW ARITHMETIC (the loops are INCLUSIVE on both ends)
--------------------------------------------------------------
Read this before changing the defaults, because the numbers do not match
the parameter names at a glance. Both ``0..p_near_months`` and
``p_retention_lag..(p_retention_lag + p_retention_months)`` are inclusive
PL/pgSQL ranges, so each contributes one MORE partition than its name
suggests:

* near window -- ``0..15`` = **16** monthly partitions, running
  2026-10 .. **2028-01** (the ``+ 15 month`` offset lands on January).
  The extra month is deliberate headroom: a deployment that forgets to
  re-run this function degrades in January 2028, not in November 2026.
* retention window -- ``60..69`` = **10** monthly partitions, running
  **2031-10 .. 2032-07**. Offset 60 months is a safety margin over the
  DIAN 5-year horizon so a ``today + 5y`` row never lands in DEFAULT.
* daily buffer -- ``0..30`` = **31** one-day partitions, plus DEFAULT.

Total on a fresh database: 10 monthly parents x (16 + 10 + 1 default)
+ 31 + 1 = 292, which is what this migration prints.

SAFETY NET AND THE ALARM ON THE ALARM
--------------------------------------
DEFAULT partitions are ADDED to every parent that lacks one --
``sync_queue`` and ``sync_queue_lw_buffer`` today -- so an unexpected
future date degrades instead of 500-ing. That trades a hard cliff for
silent degradation, which is only acceptable while something watches it:
``openspec/scripts/check_schema_match.py`` asserts BOTH that every parent
covers ``CURRENT_DATE`` AND that no ``*_default`` partition holds rows.
A row in DEFAULT fails the gate instead of sitting there unnoticed.

The gate can only enforce that on rows written AFTER this migration. The
rows written before it are listed in the next section -- that is why the
gate compares against a documented baseline instead of demanding zero.

ROW DATA ALREADY TRAPPED IN DEFAULT
-----------------------------------
``prod.salidas_default`` (8 rows, dated 2028-09) and
``prod.pairing_tokens_default`` (8 rows, dated 2026-09-23/27) already
hold rows that belong in a bounded partition. Creating a partition does
NOT move them, and moving them would require DELETE on ``prod.salidas``,
which the ``salidas_inmutable`` trigger and the REVOKE block. They stay
where they are and are documented; migrating them needs the immutability
story resolved first.

References: docs/02-arquitectura/decisiones-tecnicas.md (ADR-004)

IN-PLACE FIX (2026-10-02) -- WHY THIS REVISION, NOT A NEW ONE
----------------------------------------------------------------
Found during Fase 0 QA bootstrap: on ANY fresh database migrated
0001->head in a single run (the only way this revision is ever reached
from genesis), this function's near-window ``v_i = 0`` slot computes the
SAME bounds as the ``<table>_p_current`` partition ``0001_initial_schema``
just created seconds earlier in the SAME migration session (both use
``date_trunc('month', CURRENT_DATE)`` and CURRENT_DATE does not change
between consecutive statements of one run). PostgreSQL rejects attaching a
second, differently-named partition over bounds an existing partition
already covers::

    ERROR:  partition "arqueo_p_2026_10" would overlap partition
            "arqueo_p_current"          -- SQLSTATE 42P17

This is NOT a narrow edge case: it reproduces on every single fresh
bootstrap, on any calendar day, 100% of the time -- confirmed against a
disposable ``parkos-postgres:16-pgpartman`` container migrated 0001->0064.
It only went unnoticed because every existing environment (including this
project's own QA ``cloud-db``/``branch-db``) bootstrapped around it with a
manual, undocumented, data-level workaround rather than via a clean
``alembic upgrade head``.

This repo's migration chain is append-only for revisions that completed
successfully (see ``migrations/versions/README.md`` and the precedent
corrective migrations 0043/0052/0057/0069/0070, each fixing a GAP left by
an earlier, SUCCESSFULLY-APPLIED migration for environments that already
ran it). That precedent does not cover this case: no environment has ever
successfully completed THIS function body via a clean ``alembic upgrade
head`` -- it always crashes first. A later corrective migration can never
even be reached, because Alembic aborts the whole run on this exception
before advancing past 0064. The fix has to live where the crash is, or
`alembic upgrade head` from genesis never succeeds for anyone. Because
Alembic only executes a revision once per environment (tracked in
``alembic_version``), this in-place change is inert for every environment
that already recorded 0064 as applied (via the manual workaround) -- it
only changes behavior for NEW environments that have not run it yet.

The fix: each ``CREATE TABLE ... PARTITION OF`` call below is wrapped in a
``BEGIN/EXCEPTION WHEN invalid_object_definition`` block -- on a 42P17
overlap it logs a ``NOTICE`` and treats the slot as already covered
instead of aborting. Any other error still propagates unchanged.

The two OTHER defects found in the same bootstrap session -- missing
``rol_app``/``rol_admin_auditor`` grants on partitions this function
creates (and on the pre-existing ``_p_current``/``_default`` ones), and
``pairing_tokens`` missing ``UPDATE`` for its ``FOR UPDATE SKIP LOCKED``
lock -- do NOT block the chain (this function still returns successfully
without them), so those follow the normal forward-fix convention: see
``0075_fix_ensure_partitions_overlap_and_grants.py``, which also upgrades
this function to add automatic grant-sync on every call.
"""

from alembic import op
from sqlalchemy import text

revision = "0064_ensure_forward_partitions"
down_revision = "0063_fix_tarifas_sucursal_uk01"
branch_labels = None
depends_on = None


CREATE_FN = """
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
                    -- same-day fresh bootstrap). See the in-place-fix note
                    -- in this file's module docstring.
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

        -- DEFAULT safety net for monthly parents that lack one. As of this
        -- migration the only such parent is `sync_queue`; the other nine
        -- already had theirs. Written generically so a parent added later
        -- cannot reintroduce the hard cliff. See the docstring section
        -- "SAFETY NET AND THE ALARM ON THE ALARM" for why trading a
        -- CheckViolationError for a monitored DEFAULT partition is the
        -- right way round for an operational queue.
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

DROP_FN = """
DROP FUNCTION IF EXISTS prod.fn_ensure_partitions(
    int, int, int, int
);
"""

# Repairs defect 1 from the docstring: ``part_config.parent_table`` stored
# as ``parkos.prod.<table>`` instead of ``prod.<table>``. Idempotent --
# the WHERE clause matches nothing once the prefix is gone.
REPAIR_PART_CONFIG = """
DO $$
DECLARE
    v_fixed int;
BEGIN
    UPDATE partman.part_config
       SET parent_table = regexp_replace(parent_table, '^parkos\\.', '')
     WHERE parent_table ~ '^parkos\\.';
    GET DIAGNOSTICS v_fixed = ROW_COUNT;
    IF v_fixed > 0 THEN
        RAISE NOTICE
            '0064: repaired % part_config parent_table value(s) that were '
            'database-qualified (parkos.prod.* -> prod.*). pg_partman was '
            'silently skipping every one of them.', v_fixed;
    END IF;
END $$;
"""


def upgrade() -> None:
    bind = op.get_bind()

    # Order matters: repair pg_partman's bookkeeping FIRST so that if a
    # scheduler is present, the worker stops skipping these parents from
    # this point forward. Then create the partitions explicitly, because
    # defect 2 (no scheduler) means pg_partman still may not run today.
    bind.execute(text(REPAIR_PART_CONFIG))

    bind.execute(text(CREATE_FN))

    created = bind.execute(
        text("SELECT count(*) FROM prod.fn_ensure_partitions()")
    ).scalar_one()
    # Loud in the migration log: how many partitions this run produced.
    print(f"0064: fn_ensure_partitions() created {created} partitions")


def downgrade() -> None:
    """Drop the partitions this migration is responsible for.

    Deliberately scoped to the ``*_p_YYYY_MM`` / ``*_p_YYYY_MM_DD``
    naming introduced here. The legacy ``*_p_current`` partitions (the
    misleadingly named September ones from ``0001``) are left in place:
    they hold September data and downgrading must not destroy it.

    Reversibility caveat: this drops partitions regardless of whether
    they hold rows. A downgrade performed after the system has written
    into a 2026_10-or-later partition will lose that data. That is the
    nature of a down-migration on a partitioned table, and the reason
    this migration should not be downgraded in production.
    """
    bind = op.get_bind()
    bind.execute(
        text(
            """
            DO $$
            DECLARE
                r record;
            BEGIN
                FOR r IN
                    SELECT c.relname AS child, p.relname AS parent
                    FROM pg_inherits i
                    JOIN pg_class c ON c.oid = i.inhrelid
                    JOIN pg_class p ON p.oid = i.inhparent
                    JOIN pg_namespace n ON n.oid = p.relnamespace
                    WHERE n.nspname = 'prod'
                      AND c.relname ~ '^.+_p_[0-9]{4}_[0-9]{2}(_[0-9]{2})?$'
                LOOP
                    EXECUTE format('DROP TABLE prod.%I', r.child);
                END LOOP;
            END $$;
            """
        )
    )
    bind.execute(text(DROP_FN))
