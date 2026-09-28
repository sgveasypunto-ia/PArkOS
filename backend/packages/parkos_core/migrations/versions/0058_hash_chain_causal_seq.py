"""MIGRATION 0058 -- give the hash chain a causal order (per-chain ``seq``).

Why this exists
---------------
``prod.fn_extend_hash_chain()`` (0001) ordered each chain by
``(created_at, uuid)``, and both verifiers
(``repo.hash_chain._read_prior_hash`` and
``jobs.sync_cloud._verify_one_tenant_chain``) reconstructed the same order
to agree with it. That agreement only holds while ``created_at`` is
strictly increasing with insertion order. It is not: ``created_at`` is
stamped locally, per node, at insert time, so replication, backfill,
retry or a manual insert can all place a row *behind* rows already in the
chain.

Two concrete defects came out of that:

**1. Genesis bypass (compliance hole).** The trigger opened with::

    IF NEW.accion = 'inicializacion' AND NEW.hash_anterior IS NOT NULL
       AND NEW.hash_anterior = NEW.hash_actual THEN
        RETURN NEW;   -- skips EVERY check below
    END IF;

The escape valve was meant for the *first* row of a chain, but nothing
verified the chain was actually empty. A genesis row could therefore be
injected on top of a live chain, forking it permanently. The cloud's
GLOBAL chain carries exactly that: two ``inicializacion`` rows, the
second one (``d4c7fc74``, 2026-09-23 19:54:27) self-referential
(``hash_anterior = hash_actual = b839c1...``) on a chain that already had
rows since 19:40.

**2. Non-causal ordering (the fork mechanism).** At 2026-09-23 23:42:39
the branch chain took two rows in the same second. ``13ecad19`` chained
onto ``ce5521b173``; ``8e1e0488`` chained onto ``8c4bdd9e3e`` (= the
former's ``hash_actual``) -- both correct at write time. The successor
``93bb7218`` then chained onto ``8c4bdd9e3e`` too, which is only
consistent if ``8e1e0488`` was not yet present: it arrived late, with a
``created_at`` four hours behind rows already committed. A walk ordered by
``created_at`` therefore places ``8e1e0488`` mid-history and reports
``93bb7218`` as broken, on data that was never corrupted -- exactly the
false positive both docstrings already describe, which the ``created_at``
switch papered over without removing the cause.

What this migration changes
---------------------------
``seq BIGINT`` is allocated **at insert time, inside the trigger, under a
per-chain advisory lock**::

    PERFORM pg_advisory_xact_lock(<key derived from uuid_sucursal>);
    SELECT seq, hash_actual ... ORDER BY seq DESC LIMIT 1;
    NEW.seq := head.seq + 1;

The lock makes the read-head and allocate-seq steps atomic, so two
concurrent writers cannot both be handed ``head + 1``. From here the
chain order is the order the rows were *appended*, which no timestamp can
rewrite. Both defects close as a consequence:

- a genesis row is accepted only when ``NOT FOUND`` -- i.e. the chain is
  genuinely empty -- so the bypass no longer forks a live chain;
- a late row with a backdated ``created_at`` still receives the head
  ``seq``, so it can never appear mid-chain and make its successor look
  broken.

Verified against the live data in a rolled-back transaction, and re-verified
2026-09-26 against the live cloud DB: injecting a genesis row on the live
GLOBAL chain is now rejected, and a row with ``created_at`` backdated four
hours is given the head ``seq`` and links to the head hash. The historical
damage is three anomaly points from the two root causes above, all at
``seq < 50``: GLOBAL seq 1 (``d4c7fc74``, the self-referential genesis),
branch seq 21 (``8e1e0488``, the backdated intruder) and branch seq 22
(``13ecad19``, the legitimate row the intruder displaced in timestamp
order).

**History is not repaired here.** Those three rows stay exactly where they
are, and the backfill reproduces the historical ``(created_at, uuid)``
order precisely so the evidence is not quietly reshaped. Per-chain ``seq``
continues from the highest historical value. The cloud verifier is given a
watermark (``PARKOS_HASH_CHAIN_VERIFY_MIN_SEQ``, default 50, wired in
``jobs/sync_cloud.py`` and ``docker-compose.cloud.yml``) so those
pre-existing rows are reported as a known incident instead of re-alerting
every sweep; the walker's re-anchor means one value is safe for every
chain, and a break at or after the watermark still fires.

``revocacion_factura`` gets the column, backfill and a real unique
constraint (it is NOT partitioned, so the key needs no partition column),
but keeps its current enforcement model: it has never had a DB trigger, so
``repo.hash_chain.append`` remains the only allocator of its chain.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0058_hash_chain_causal_seq"
down_revision = "0057_sync_cursor_update_grant"
branch_labels = None
depends_on = None


# The trigger body is identical for both nodes; kept as a module constant so
# upgrade() and downgrade() cannot drift apart.
_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION prod.fn_extend_hash_chain() RETURNS trigger AS $$
DECLARE
    v_key       text   := coalesce(NEW.uuid_sucursal::text, 'GLOBAL');
    v_lock      bigint := ('x' || substr(md5(v_key), 1, 16))::bit(64)::bigint;
    v_head_seq  bigint;
    v_head_hash text;
BEGIN
    -- Read-head and allocate-seq must be atomic, or two concurrent inserts
    -- both read head N and both are handed N+1. The lock is per chain
    -- (keyed on uuid_sucursal, GLOBAL for the IS NULL chain), so chains
    -- for different tenants still extend concurrently.
    PERFORM pg_advisory_xact_lock(v_lock);

    SELECT seq, hash_actual INTO v_head_seq, v_head_hash
      FROM prod.log_transaccional
     WHERE uuid_sucursal IS NOT DISTINCT FROM NEW.uuid_sucursal
     ORDER BY seq DESC, created_at DESC, uuid DESC
     LIMIT 1;

    IF NOT FOUND THEN
        -- Genesis is legitimate ONLY on a genuinely empty chain. The old
        -- trigger took this branch for ANY inicializacion row with
        -- hash_anterior = hash_actual, which let a genesis row fork a
        -- chain that already had a head.
        IF NEW.accion = 'inicialización'
           AND NEW.hash_anterior IS NOT NULL
           AND NEW.hash_anterior = NEW.hash_actual THEN
            NEW.seq := 1;
            RETURN NEW;
        END IF;
        RAISE EXCEPTION
            'HASH_CHAIN_INTEGRITY_VIOLATION: no genesis row for uuid_sucursal=%',
            NEW.uuid_sucursal;
    END IF;

    IF NEW.accion = 'inicialización' AND NEW.hash_anterior = NEW.hash_actual THEN
        RAISE EXCEPTION
            'HASH_CHAIN_INTEGRITY_VIOLATION: genesis row on live chain uuid_sucursal=% (head seq=%)',
            NEW.uuid_sucursal, v_head_seq;
    END IF;

    NEW.seq := v_head_seq + 1;

    IF NEW.hash_anterior IS NULL THEN
        NEW.hash_anterior := v_head_hash;
    ELSIF NEW.hash_anterior <> v_head_hash THEN
        RAISE EXCEPTION
            'HASH_CHAIN_INTEGRITY_VIOLATION: hash_anterior=% expected=%',
            NEW.hash_anterior, v_head_hash;
    END IF;

    IF NEW.hash_actual IS NULL THEN
        NEW.hash_actual := encode(digest(
            coalesce(NEW.datos_nuevos::text, '') || '|'
            || coalesce(NEW.uuid_registro_afectado::text, '') || v_head_hash,
            'sha256'), 'hex');
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    """Allocate chain order at insert time; close the genesis bypass.

    Per ``openspec/config.yaml`` ``rules.tasks``, the ``[A]``-table trigger
    ships in the same migration that touches the table.
    """
    # -- 1) log_transaccional: the chain with a detected break ----------
    op.execute("ALTER TABLE prod.log_transaccional ADD COLUMN seq BIGINT;")

    # fn_log_transaccional_inmutable() rejects EVERY update, so the
    # append-only guarantee is lifted only for the backfill and restored
    # immediately after. Both statements run inside the transaction that
    # already holds the ACCESS EXCLUSIVE lock taken by the ALTER above, so
    # no concurrent writer can observe the window.
    op.execute(
        "ALTER TABLE prod.log_transaccional "
        "DISABLE TRIGGER log_transaccional_inmutable;"
    )
    # Backfill in the historical (created_at, uuid) order on purpose: the two
    # pre-existing breaks stay at the same rows, and the evidence is not
    # reshaped by this migration.
    op.execute(
        """
        UPDATE prod.log_transaccional t
           SET seq = b.rn
          FROM (SELECT uuid,
                       fecha_retencion_hasta,
                       row_number() OVER (PARTITION BY uuid_sucursal
                                          ORDER BY created_at, uuid) AS rn
                  FROM prod.log_transaccional) b
          WHERE t.uuid = b.uuid
            AND t.fecha_retencion_hasta = b.fecha_retencion_hasta
            AND t.seq IS DISTINCT FROM b.rn;
        """
    )
    op.execute(
        "ALTER TABLE prod.log_transaccional ENABLE TRIGGER log_transaccional_inmutable;"
    )

    # PostgreSQL requires a unique constraint on a partitioned table to
    # contain every partitioning column, so fecha_retencion_hasta is
    # unavoidably part of the key: this index is a per-partition aid that
    # also serves the trigger's head lookup, NOT the invariant's guard. The
    # guard is the trigger, which hands out seq under an advisory lock.
    op.execute(
        """
        CREATE UNIQUE INDEX log_transaccional_chain_seq_uk
            ON prod.log_transaccional (uuid_sucursal, seq, fecha_retencion_hasta)
            NULLS NOT DISTINCT;
        """
    )
    op.execute("ALTER TABLE prod.log_transaccional ALTER COLUMN seq SET NOT NULL;")

    # -- 2) revocacion_factura: same column, no DB trigger -------------
    # It is not partitioned, so the unique constraint needs no partition
    # column and NULLS NOT DISTINCT genuinely enforces one seq per chain
    # (including the IS NULL global chain). It has never had a DB trigger,
    # so repo.hash_chain.append stays its only allocator.
    op.execute("ALTER TABLE prod.revocacion_factura ADD COLUMN seq BIGINT;")
    op.execute(
        """
        UPDATE prod.revocacion_factura t
           SET seq = b.rn
          FROM (SELECT uuid,
                       row_number() OVER (PARTITION BY uuid_sucursal
                                          ORDER BY created_at, uuid) AS rn
                  FROM prod.revocacion_factura) b
         WHERE t.uuid = b.uuid
           AND t.seq IS DISTINCT FROM b.rn;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX revocacion_factura_chain_seq_uk
            ON prod.revocacion_factura (uuid_sucursal, seq)
            NULLS NOT DISTINCT;
        """
    )
    op.execute("ALTER TABLE prod.revocacion_factura ALTER COLUMN seq SET NOT NULL;")

    # -- 3) The causal trigger -----------------------------------------
    op.execute(_TRIGGER_FN)

    # -- 4) Audit evidence ----------------------------------------------
    # Audit-first: the schema change is itself recorded in the compliance
    # log. The new row's hash_anterior is the head's hash_actual (not its
    # hash_anterior) and hash_actual is left NULL so the trigger computes
    # it. On a database whose chains are all still empty this inserts
    # nothing, which is correct: there is no head to extend.
    op.execute(
        """
        INSERT INTO prod.log_transaccional
            (fecha_retencion_hasta, accion, tabla_afectada, datos_nuevos,
             created_at, hash_anterior, hash_actual)
        SELECT current_date,
               'migracion',
               'log_transaccional',
               '{"migration": "0058_hash_chain_causal_seq", '
               '"note": "per-chain seq allocated at insert time under an '
               'advisory lock; genesis bypass closed; historical breaks left '
               'in place"}'::jsonb,
               now(),
               hc.hash_actual,
               NULL
          FROM (SELECT hash_actual FROM prod.log_transaccional
                 WHERE uuid_sucursal IS NULL
                 ORDER BY seq DESC LIMIT 1) hc;
        """
    )


def downgrade() -> None:
    """Restore the pre-0058 trigger and drop ``seq``.

    This deliberately re-opens BOTH defects documented above: the genesis
    escape valve again skips every chain check, and both verifiers are once
    back to reconstructing chain order from ``created_at``. Written for
    symmetry with 0001, not as a supported configuration.
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.fn_extend_hash_chain() RETURNS trigger AS $$
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
                RAISE EXCEPTION
                    'HASH_CHAIN_INTEGRITY_VIOLATION: no genesis row for uuid_sucursal=%',
                    NEW.uuid_sucursal;
            END IF;
            IF NEW.hash_anterior IS NULL THEN
                NEW.hash_anterior := prev_hash;
            ELSIF NEW.hash_anterior <> prev_hash THEN
                RAISE EXCEPTION
                    'HASH_CHAIN_INTEGRITY_VIOLATION: hash_anterior=% expected=%',
                    NEW.hash_anterior, prev_hash;
            END IF;
            IF NEW.hash_actual IS NULL THEN
                NEW.hash_actual := encode(digest(
                    coalesce(NEW.datos_nuevos::text, '') || '|'
                    || coalesce(NEW.uuid_registro_afectado::text, '') || prev_hash,
                    'sha256'), 'hex');
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("DROP INDEX IF EXISTS prod.revocacion_factura_chain_seq_uk;")
    op.execute("ALTER TABLE prod.revocacion_factura DROP COLUMN IF EXISTS seq;")
    op.execute("DROP INDEX IF EXISTS prod.log_transaccional_chain_seq_uk;")
    op.execute("ALTER TABLE prod.log_transaccional DROP COLUMN IF EXISTS seq;")
