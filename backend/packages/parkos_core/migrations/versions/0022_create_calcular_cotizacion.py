"""create PL/pgSQL function ``prod.calcular_cotizacion`` for HU-F1.8

Revision ID: 0022_create_calcular_cotizacion
Revises: 0021_least_privilege_and_immutability_contract
Create Date: 2026-09-14 12:00:00.000000

**Scope.** Server-side quotation primitive for ``GET /operacion/cotizar``
(GAP-BE-09, ``plan.md:7423-7446``). HU-F1.7 (``POST /operacion/salidas``)
will reuse the function to validate ``cotizacion_expirada`` (410)
without re-querying the DB — the ``vigente_hasta = NOW() + INTERVAL '15
minutes'`` window is the only state carried across the boundary.

**Architecture.** The whole pricing formula lives in PL/pgSQL — the
Python handler is a thin adapter. This is the only way to guarantee
transactional atomicity between ``cotizar`` and ``POST /salidas``: the
``SELECT ... FOR SHARE`` lock on ``tarifas_sucursal`` (KD-1) holds for
the whole transaction.

**Key decisions applied (design.md §4):**

  - KD-1 lock ``SELECT ... FOR SHARE`` on ``tarifas_sucursal``.
  - KD-2 ``unidad_minutos`` resolved via a hardcoded ``CASE
    tipo_tarifa.tipo WHEN 'fraccion' THEN 15 WHEN 'hora' THEN 60 WHEN
    'nocturna' THEN 720 ELSE 1 END`` inside the function (no ER
    migration; no ``unidad_minutos`` column added).
  - KD-3 new typed error ``404 tarifa_no_vigente`` distinguished from
    ``ingreso_no_encontrado`` by the jsonb ``error`` key.
  - KD-IVA ``impuestos.IVA`` seeding is **out of scope** for this
    change; deployment-blocker until HU-F14.2 Parte II seeds the row.

**Volatility deviation (apply-time correction, design.md §4 / KD-1).**

  The function is declared ``VOLATILE``, NOT ``STABLE`` as design.md
  initially proposed. Postgres refuses ``SELECT ... FOR SHARE`` from
  inside a ``STABLE`` or ``IMMUTABLE`` function (the planner may call
  the function multiple times during a single scan, and per-statement
  lock acquisition has side effects incompatible with stable
  semantics — see ``FeatureNotSupportedError: SELECT FOR SHARE is not
  allowed in a non-volatile function``). KD-1 mandates ``FOR SHARE``
  on ``tarifas_sucursal`` to close the race window between cotizar
  and HU-F1.7 cobro, so the volatility MUST be ``VOLATILE``.

  The contract intent (no hidden INSERT/UPDATE/DELETE) is preserved by
  the AST guard ``tests/static/test_no_write_in_calcular_cotizacion.
  py``: it rejects ``INSERT|UPDATE|DELETE|TRUNCATE|MERGE`` in the
  body regardless of the volatility classification. REQ-OPS-025's
  STABLE requirement was relaxed in the AST guard to permit
  ``VOLATILE`` (a follow-up design amendment — see apply report).

**Precedents reused.**

  - ``api/v1/operacion.py:215-277`` — ``resolve_active_subscription_for_exit``
    ported inline as a ``SELECT INTO`` against ``subscripciones_cliente
    JOIN subscripcion_vehiculos JOIN vehiculos`` (R22 defense in depth:
    explicit ``uuid_sucursal`` filter in addition to sync scoping).
  - ``api/v1/operacion.py:152`` precedent for raw-SQL inside a handler
    (``session.execute(text(...))``).

**Precedence (REQ-OPS-024).** ``ingreso_no_encontrado > tarifa_no_
vigente > iva_no_configurado`` — first matching failure short-circuits
the rest of the body.
"""
from __future__ import annotations

from alembic import op

revision = "0022_create_calcular_cotizacion"
down_revision = "0021_least_privilege_and_immutability_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.calcular_cotizacion(p_uuid_ingreso uuid)
        RETURNS jsonb
        LANGUAGE plpgsql
        VOLATILE
        AS $$
        DECLARE
            v_ingreso record;
            v_tarifa record;
            v_impuesto record;
            v_subscripcion record;
            v_total numeric(18,4);
            v_iva numeric(18,4);
            v_subtotal numeric(18,4);
            v_tiempo_minutos numeric;
            v_unidad_minutos int;
            v_valor_plena numeric;
            v_vigente_hasta timestamptz;
        BEGIN
            ----------------------------------------------------------------------
            -- Step 1: ingreso existe y sigue abierto (sin salidas)
            ----------------------------------------------------------------------
            -- The canonical ``prod.salidas`` schema has NO ``estado``
            -- column (verified via psql backslash-d ``prod.salidas`` --
            -- the 10 columns are uuid, fecha_retencion_hasta,
            -- uuid_sucursal, uuid_ingreso, fecha_salida, created_at,
            -- created_by, sync_status, sync_timestamp, sync_attempts).
            -- Existence of a matching ``salidas`` row is the canonical
            -- ``cerrado`` signal per
            -- ``api/v1/operacion.py::get_ingreso_estado``. The design.md
            -- section 8 placeholder used ``s.estado <> 'anulada'`` --
            -- corrected here to match the actual schema.
            SELECT
                i.uuid_sucursal,
                i.placa,
                i.uuid_tipo_vehiculo,
                i.fecha_ingreso,
                EXISTS(
                    SELECT 1 FROM prod.salidas s
                    WHERE s.uuid_ingreso = i.uuid
                ) AS tiene_salida
              INTO v_ingreso
              FROM prod.ingreso i
             WHERE i.uuid = p_uuid_ingreso;
            IF NOT FOUND OR v_ingreso.tiene_salida THEN
                RETURN jsonb_build_object('error', 'ingreso_no_encontrado');
            END IF;

            ----------------------------------------------------------------------
            -- Step 2: mensualidad vigente (port de resolve_active_subscription_for_exit)
            ----------------------------------------------------------------------
            -- R22 defense in depth: explicit ``uuid_sucursal = v_ingreso.uuid_sucursal``
            -- filter in addition to the sync scoping — a stale or manually-inserted
            -- row for another branch is rejected even if present locally.
            SELECT sc.uuid
              INTO v_subscripcion
              FROM prod.subscripciones_cliente sc
              JOIN prod.subscripcion_vehiculos sv
                ON sv.uuid_subscripcion_cliente = sc.uuid
              JOIN prod.vehiculos v
                ON v.uuid = sv.uuid_vehiculo
             WHERE sc.uuid_sucursal = v_ingreso.uuid_sucursal
               AND sc.vigente_hasta IS NULL
               AND sc.estado = 'activo'
               AND sv.vigente_hasta IS NULL
               AND sv.estado = 'activo'
               AND v.vigente_hasta IS NULL
               AND v.estado = 'activo'
               AND v.placa = v_ingreso.placa
               AND (sc.fecha_vencimiento IS NULL OR sc.fecha_vencimiento >= CURRENT_DATE)
             ORDER BY sc.vigente_desde DESC
             LIMIT 1;
            IF FOUND THEN
                RETURN jsonb_build_object(
                    'cobrar', false,
                    'motivo', 'mensualidad_vigente'
                );
            END IF;

            ----------------------------------------------------------------------
            -- Step 3: tarifa vigente con lock FOR SHARE (KD-1)
            ----------------------------------------------------------------------
            -- The FOR SHARE lock is held for the whole transaction; HU-F1.7
            -- (POST /operacion/salidas) MUST replicate the same lock to close
            -- the race window between cotizar and cobro (design.md §4 KD-1).
            SELECT
                t.uuid AS tarifa_uuid,
                t.valor,
                t.valor_plena,
                tt.tipo AS tipo_tarifa
              INTO v_tarifa
              FROM prod.tarifas_sucursal t
              JOIN prod.tipo_tarifa tt ON tt.uuid = t.uuid_tipo_tarifa
             WHERE t.uuid_sucursal      = v_ingreso.uuid_sucursal
               AND t.uuid_tipo_vehiculo = v_ingreso.uuid_tipo_vehiculo
               AND t.estado             = 'activo'
               AND tt.estado            = 'activo'
               AND t.vigente_desde <= NOW()
               AND (t.vigente_hasta IS NULL OR t.vigente_hasta > NOW())
             ORDER BY t.vigente_desde DESC
             LIMIT 1
               FOR SHARE;
            IF NOT FOUND THEN
                RETURN jsonb_build_object('error', 'tarifa_no_vigente');
            END IF;

            ----------------------------------------------------------------------
            -- Step 4: impuesto IVA vigente (KD-IVA)
            ----------------------------------------------------------------------
            -- Seeding out of scope for F1.8 — owned by HU-F14.2 Parte II.
            -- Until the row lands, every quotation returns this error
            -- (deployment-blocker, documented in design.md §4 KD-IVA).
            SELECT porcentaje
              INTO v_impuesto
              FROM prod.impuestos
             WHERE nombre      = 'IVA'
               AND estado      = 'activo'
               AND vigente_desde <= NOW()
               AND (vigente_hasta IS NULL OR vigente_hasta > NOW())
               AND porcentaje > 0
             ORDER BY vigente_desde DESC
             LIMIT 1;
            IF NOT FOUND THEN
                RETURN jsonb_build_object('error', 'iva_no_configurado');
            END IF;

            ----------------------------------------------------------------------
            -- Step 5: compute fiscal breakdown (KD-2 hardcoded CASE)
            ----------------------------------------------------------------------
            -- unidad_minutos encapsulated in PL/pgSQL — no ER column added
            -- (KD-2 trade-off: if a new tipo_tarifa lands, the CASE must
            -- be updated via ALTER FUNCTION ... LANGUAGE plpgsql).
            v_unidad_minutos := CASE v_tarifa.tipo_tarifa
                WHEN 'fraccion' THEN 15
                WHEN 'hora'     THEN 60
                WHEN 'nocturna' THEN 720
                ELSE                  1
            END;

            v_tiempo_minutos := EXTRACT(EPOCH FROM (NOW() - v_ingreso.fecha_ingreso)) / 60.0;

            IF v_tarifa.valor_plena IS NOT NULL AND v_tarifa.valor_plena > 0 THEN
                v_valor_plena := (v_tarifa.valor_plena / v_tarifa.valor) * v_unidad_minutos;
                IF v_tiempo_minutos >= v_valor_plena THEN
                    v_total := v_tarifa.valor_plena;
                ELSE
                    v_total := v_tarifa.valor * CEIL(v_tiempo_minutos);
                END IF;
            ELSE
                v_total := v_tarifa.valor * CEIL(v_tiempo_minutos);
            END IF;

            v_iva        := ROUND(v_total * v_impuesto.porcentaje, 2);
            v_subtotal   := ROUND(v_total - v_iva, 2);
            v_total      := ROUND(v_total, 2);
            v_vigente_hasta := NOW() + INTERVAL '15 minutes';

            RETURN jsonb_build_object(
                'cobrar',          true,
                'subtotal',        v_subtotal,
                'iva',             v_iva,
                'total',           v_total,
                'tiempo_minutos',  v_tiempo_minutos,
                'tarifa_uuid',     v_tarifa.tarifa_uuid,
                'vigente_hasta',   v_vigente_hasta
            );
        END;
        $$;

        GRANT EXECUTE ON FUNCTION prod.calcular_cotizacion(uuid) TO parkos_app;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS prod.calcular_cotizacion(uuid);")


__all__ = ["downgrade", "upgrade"]
