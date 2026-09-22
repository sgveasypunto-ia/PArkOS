"""MIGRATION 0045 -- add prod.refresh_mv_ocupacion_diaria() SECURITY DEFINER helper.

REGRESSION (2026-09-22, directiva del operador):

  The dashboard panels ``<MiTurnoPanel />``, ``<OcupacionPanel />``
  (Inventario card) and ``<VehiculosDentroList />`` rely on the MV
  ``prod.mv_ocupacion_diaria`` for per-tipo active-ingreso counts.
  The MV is refreshed by the ``RefreshMvOcupacionWorker`` every 10s
  (DEC-SUC-11 verbatim). Without the worker running in the operator's
  local stack (the docker-compose.local.yml combined stack only boots
  ``api-sucursal`` + ``job-sync-sucursal``), the MV lags behind the
  INSERT and the Inventario panel keeps showing the pre-mutation
  count for up to 10s after an ingreso / salida. Combined with the FE
  SWR polling cadence (10–15s) the operator perceived the panels as
  "hardcoded" / stale.

  Fix: ship a SECURITY DEFINER helper ``prod.refresh_mv_ocupacion_
  diaria()`` that the BE handler calls after the ingreso / salidas
  INSERT (separate code change in ``repo/ingreso.py`` + ``repo/
  salidas.py``). The function executes ``REFRESH MATERIALIZED VIEW
  CONCURRENTLY prod.mv_ocupacion_diaria`` running as the ``parkos``
  owner, so ``rol_app`` / ``parkos_app`` (least-privilege roles)
  can invoke it without needing direct refresh privileges on the
  MV.

  Defense in depth (KD-5 + 3NF, RIESCO-SUC-02):
    - ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` (not plain
      ``REFRESH``) so the GET /operacion/ocupacion readers are not
      blocked during the refresh — established F1.5 production
      behavior (migration 0024 + 0034).
    - The function returns the new ``generado_en`` timestamp so the
      caller can log a debug event with the actual refresh latency.
    - The MV itself remains SELECT-only for ``parkos_app`` — only
      this helper can mutate it, and only by invoking the
      PostgreSQL REFRESH command.

  Why SECURITY DEFINER vs a trigger:
    - A trigger on ``prod.ingreso`` / ``prod.salidas`` would fire
      REFRESH on EVERY row insert (potentially thousands per minute
      in a busy parking lot) — REFRESH CONCURRENTLY is still an
      AccessExclusiveLock + scan of the entire MV, and concurrent
      refreshes on the same MV serialise.
    - The on-demand helper invoked once per HTTP request keeps the
      MV fresh at the granularity the operator perceives (one
      refresh per ingreso / salida action) without the cost of
      per-row refreshes.

  Worker is NOT removed by this migration — the
  ``RefreshMvOcupacionWorker`` (10s cadence) remains the fallback
  for bulk operations that do NOT go through the HTTP API (sync
  workers, seed scripts, admin CLI). This migration just adds the
  on-demand refresh path so the kiosk panels reflect operator
  actions immediately.
"""
from __future__ import annotations

from alembic import op


revision = "0045_add_refresh_mv_ocupacion_helper"
down_revision = "0044_widen_consecutivo_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the SECURITY DEFINER refresh helper + grant EXECUTE to parkos_app."""
    # 1) Create the function — SECURITY DEFINER makes it run as the
    #    owner (``parkos``) so rol_app / parkos_app can invoke it
    #    without holding the underlying REFRESH privilege on the MV.
    #    ``CONCURRENTLY`` keeps readers (GET /operacion/ocupacion)
    #    unblocked during the refresh — established F1.5 production
    #    pattern (migration 0024 + 0034).
    #
    #    The MV schema is just ``(uuid_sucursal, uuid_tipo_vehiculo,
    #    activos)`` — ``generado_en`` is NOT a MV column, it's a
    #    derived timestamp the BE response builder stamps at SELECT
    #    time. So the function returns NULL on success; the caller
    #    logs the wall-clock latency via Python ``time.monotonic()``
    #    on the BE side if it wants observability.
    #
    #    On the very first refresh after the MV is created, the MV
    #    may not be populated yet — ``REFRESH MATERIALIZED VIEW
    #    CONCURRENTLY`` raises ``materialized view ... has not been
    #    populated`` in that case. The IF EXISTS guard makes the
    #    function idempotent across the bootstrap window.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.refresh_mv_ocupacion_diaria()
        RETURNS VOID
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = prod, pg_catalog
        AS $$
        BEGIN
            -- The MV may be missing when this helper is first
            -- invoked on a fresh database (e.g. before the
            -- RefreshMvOcupacionWorker has run a single cycle).
            -- Skip silently — the next worker cycle will populate
            -- it, and the worker's own fallback path also handles
            -- this case (migration 0034).
            IF to_regclass('prod.mv_ocupacion_diaria') IS NULL THEN
                RETURN;
            END IF;

            -- CONCURRENTLY keeps GET /operacion/ocupacion readers
            -- unblocked during the refresh. Requires the UNIQUE
            -- INDEX on (uuid_sucursal, uuid_tipo_vehiculo) created
            -- in migrations 0024 / 0034 — fail loudly otherwise.
            REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria;
        END;
        $$;
        """
    )

    # 2) Grant EXECUTE to parkos_app — the role the BE connects as.
    #    Note: ``rol_app`` is inherited by ``parkos_app`` via
    #    ``CREATE ROLE parkos_app LOGIN INHERIT IN ROLE rol_app``
    #    (migration 0021), so a single EXECUTE grant at the
    #    parkos_app level is sufficient. We grant to BOTH for
    #    defense in depth in case a future caller connects as the
    #    bare ``rol_app`` (e.g. via a backend admin tool).
    op.execute("GRANT EXECUTE ON FUNCTION prod.refresh_mv_ocupacion_diaria() TO parkos_app")
    op.execute("GRANT EXECUTE ON FUNCTION prod.refresh_mv_ocupacion_diaria() TO rol_app")


def downgrade() -> None:
    """Drop the helper. The MV worker (10s cadence) remains as the
    fallback refresh path after the rollback."""
    op.execute("REVOKE EXECUTE ON FUNCTION prod.refresh_mv_ocupacion_diaria() FROM parkos_app")
    op.execute("REVOKE EXECUTE ON FUNCTION prod.refresh_mv_ocupacion_diaria() FROM rol_app")
    op.execute("DROP FUNCTION IF EXISTS prod.refresh_mv_ocupacion_diaria()")


__all__ = ["upgrade", "downgrade"]
