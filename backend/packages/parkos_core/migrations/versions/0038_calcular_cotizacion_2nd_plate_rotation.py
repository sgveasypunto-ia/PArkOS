"""CU-03M / DEC-SUC-21 second-vehicle rotation: PL/pgSQL now falls through
to rotation pricing for the 2nd plate of the same subscription.

Revision ID: 0038_calcular_cotizacion_2nd_plate_rotation
Revises: 0037_add_uuid_subscripcion_cliente_to_facturas
Create Date: 2026-09-21

**Scope.** Close the end-to-end CU-03M / DEC-SUC-21 second-vehicle
rotation rule (plan.md:64 + plan.md:436, PR 40046e1). Migration 0022
added the PL/pgSQL count subquery that detects "another plate of the
same ``subscripciones_cliente.uuid`` is already inside the patio" — but
the implementation chose to early-return ``{cobrar: false, motivo:
'segunda_placa_misma_mensualidad'}`` which the salida handler (HU-F1.7,
``api/v1/operacion.py::create_salida``) interpreted as a FREE exit
because the existing derivation is ``tipo_salida = "MENSUALIDAD" if
cotizacion.get("cobrar") is False else "ROTACION"`` (line 481-483).

This migration flips the contract so the 2nd-plate quotation is
returned as ``CotizarFacturacion`` (cobrar=true + full fiscal
breakdown) with the ``motivo`` informational key
``'segunda_placa_misma_mensualidad'``. The handler's existing derivation
then naturally sets ``tipo_salida='ROTACION'`` and
``cotizacion_snapshot=CotizarFacturacion.model_validate(cotizacion)``
— no handler code change required.

**Why Option B over Option A.** Two paths were considered:

  - **A. Extend ``CotizarMensualidad`` with ``cobrar_rotacion`` flag.**
    Requires duplicating the tarifa+IVA computation block (Steps 3-5)
    into the 2nd-plate branch and threading the rotation fiscal fields
    through a discriminated variant of ``CotizarMensualidad``. Three
    artefacts to keep in sync (schema, migration, handler) for what is
    semantically a rotation invoice.

  - **B. Flip the PL/pgSQL output to ``CotizarFacturacion`` for the 2nd
    plate.** The function already has the tarifa+IVA computation in
    Steps 3-5; we just delete the early-return and set a
    ``v_motivo`` flag. The discriminated union ``CotizarResponse`` (by
    ``cobrar: bool``) picks ``CotizarFacturacion`` automatically — and
    the handler's existing ``tipo_salida`` derivation does the right
    thing without code changes. One migration, one additive field on
    ``CotizarFacturacion`` (optional ``motivo: str | None``), zero
    handler changes.

Picked B because:

  1. It is the minimum viable change — the handler step order
     (D-HU-F1.7-20) is preserved verbatim and the static AST walk
     ``tests/static/test_salida_handler_step_order.py`` still passes.
  2. The PL/pgSQL function's existing 4-step pipeline already covers
     tarifa lookup + IVA computation; the 2nd-plate case simply opts
     INTO that pipeline instead of opting out.
  3. The Pydantic discriminated union keeps a single ``cobrar=true``
     branch for any rotation scenario — no need to invent a third
     variant.

**Contract change (CU-03M end-to-end).** Before this migration:

    prod.calcular_cotizacion(:uuid) ->
        {cobrar: false, motivo: 'segunda_placa_misma_mensualidad'}
    # handler: tipo_salida=MENSUALIDAD, cotizacion_snapshot=None
    # → 2nd plate exits FREE (bug — should pay as rotation)

After this migration:

    prod.calcular_cotizacion(:uuid) ->
        {cobrar: true, subtotal, iva, total, tiempo_minutos,
         tarifa_uuid, vigente_hasta, motivo: 'segunda_placa_misma_mensualidad'}
    # handler: tipo_salida=ROTACION, cotizacion_snapshot=CotizarFacturacion(...)
    # → 2nd plate exits as ROTATION with full fiscal breakdown (correct)

The 1st-plate short-circuit (``{cobrar: false, motivo:
'mensualidad_vigente'}``) is preserved verbatim — single-plate
subscriptions are unaffected.

**Pre-flight.** No pre-flight needed: this migration only replaces a
PL/pgSQL function. No table / column / index / constraint changes. The
AST guard ``tests/static/test_no_write_in_calcular_cotizacion.py``
ensures the function body still contains no INSERT/UPDATE/DELETE/
TRUNCATE/MERGE — Option B preserves that contract (the function
remains read-only over the catalog tables).

**Volatility.** Unchanged (``VOLATILE`` per KD-1 — the
``SELECT ... FOR SHARE`` on ``tarifas_sucursal`` at Step 3 mandates it
even for the 2nd-plate path because the 2nd-plate case now also runs
Step 3).

**Downgrade.** Recreates the original migration-0022 function body
verbatim. The downgrade is the original early-return for
``v_count_other_plate > 0`` at lines 189-194 of 0022.

REFs:
  - plan.md:64 — DEC-SUC-21 "detección de otra placa de la misma
    mensualidad ya en el patio"
  - plan.md:436 — CU-03M 2nd-plate business rule
  - commit 40046e1 — original migration 0022 (the PL/pgSQL count
    subquery that this fix makes end-to-end-correct)
  - D-HU-F1.7-20 — handler 12-step validation chain (preserved
    verbatim; no handler code change in this migration)
"""
from __future__ import annotations

from alembic import op

revision = "0038_calcular_cotizacion_2nd_plate_rotation"
down_revision = "0037_add_uuid_subscripcion_cliente_to_facturas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Replace ``prod.calcular_cotizacion`` so the 2nd-plate case falls
    through to rotation pricing.

    The new function body is identical to migration 0022 except for
    the 2nd-plate branch:

      - **Before**: ``RETURN jsonb_build_object('cobrar', false, 'motivo',
        'segunda_placa_misma_mensualidad')`` — early-return at line
        189-194 of 0022, short-circuiting Steps 3-5.

      - **After**: ``v_motivo := 'segunda_placa_misma_mensualidad'`` and
        fall-through to Steps 3-5 (tarifa lookup + IVA computation +
        fiscal breakdown). The final ``RETURN`` includes the
        ``'motivo'`` key when ``v_motivo IS NOT NULL`` so the
        handler / auditors can trace the 2nd-plate provenance.

    ``CREATE OR REPLACE FUNCTION`` is idempotent — replaying this
    migration is a no-op (the body is byte-equivalent the second
    time).
    """
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
            v_count_other_plate int := 0;
            v_motivo text := NULL;
        BEGIN
            ----------------------------------------------------------------------
            -- Step 1: ingreso existe y sigue abierto (sin salidas)
            ----------------------------------------------------------------------
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
            -- filter in addition to the sync scoping.
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
                ------------------------------------------------------------------
                -- CU-03M second-vehicle rotation rule (plan.md:64, plan.md:436,
                -- DEC-SUC-21): a monthly subscription covers up to 2 plates.
                --
                --   - 1st plate (no other plate in patio): short-circuit with
                --     ``cobrar=false, motivo='mensualidad_vigente'``. The
                --     REQ-OPS-023 baseline. Handler derives
                --     tipo_salida='MENSUALIDAD'.
                --
                --   - 2nd plate (other plate of same subscription already in
                --     patio): set ``v_motivo := 'segunda_placa_misma_mensualidad'``
                --     and FALL THROUGH to Steps 3-5 (tarifa lookup + IVA + fiscal
                --     breakdown). The handler then sees ``cobrar=true`` and
                --     naturally derives ``tipo_salida='ROTACION'`` with
                --     ``cotizacion_snapshot=CotizarFacturacion(...)``.
                --
                -- The check is bi-temporal on ``subscripcion_vehiculos`` and
                -- ``vehiculos`` (both [V]; vigentes + activos) and on
                -- ``ingreso`` ([L-E] insert-only — "active" = no matching
                -- ``salidas`` row). The plate filter ``i.placa = v2.placa`` AND
                -- ``i.placa <> v_ingreso.placa`` rejects the current row
                -- itself and any non-registered plate.
                ------------------------------------------------------------------
                SELECT COUNT(*)
                  INTO v_count_other_plate
                  FROM prod.ingreso i
                  JOIN prod.subscripcion_vehiculos sv2
                    ON sv2.uuid_subscripcion_cliente = v_subscripcion.uuid
                   AND sv2.vigente_hasta IS NULL
                   AND sv2.estado = 'activo'
                  JOIN prod.vehiculos v2
                    ON v2.uuid = sv2.uuid_vehiculo
                   AND v2.vigente_hasta IS NULL
                   AND v2.estado = 'activo'
                 WHERE i.uuid_sucursal = v_ingreso.uuid_sucursal
                   AND i.placa = v2.placa
                   AND i.placa <> v_ingreso.placa
                   AND NOT EXISTS (
                       SELECT 1 FROM prod.salidas s
                        WHERE s.uuid_ingreso = i.uuid
                   );
                IF v_count_other_plate > 0 THEN
                    -- CU-03M: 2nd plate falls through to rotation pricing.
                    -- The motivo key is informational (handler reads it from
                    -- ``CotizarFacturacion.motivo`` for audit/observability);
                    -- it does NOT gate the tipo_salida derivation (handler
                    -- uses ``cobrar``).
                    v_motivo := 'segunda_placa_misma_mensualidad';
                    -- Intentional fall-through to Steps 3-5: tarifa lookup +
                    -- IVA computation + fiscal breakdown. NO RETURN here.
                ELSE
                    -- 1st plate: short-circuit. REQ-OPS-023 baseline.
                    RETURN jsonb_build_object(
                        'cobrar', false,
                        'motivo', 'mensualidad_vigente'
                    );
                END IF;
            END IF;

            ----------------------------------------------------------------------
            -- Step 3: tarifa vigente con lock FOR SHARE (KD-1)
            ----------------------------------------------------------------------
            -- The FOR SHARE lock is held for the whole transaction; HU-F1.7
            -- (POST /operacion/salidas) MUST replicate the same lock to close
            -- the race window between cotizar and cobro (design.md §4 KD-1).
            -- For the 2nd-plate path (v_motivo IS NOT NULL) we still acquire
            -- the lock because the pricing pipeline runs identically.
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

            -- Final return: always ``cobrar=true`` at this point. When the
            -- 2nd-plate rule fired (``v_motivo`` non-NULL), include the
            -- ``motivo`` key so the handler / auditor can trace why a
            -- subscription-having vehicle is paying as rotation. When
            -- v_motivo IS NULL (no subscription OR 1st-plate-only), the
            -- ``motivo`` key is omitted (no schema field to populate).
            IF v_motivo IS NOT NULL THEN
                RETURN jsonb_build_object(
                    'cobrar',          true,
                    'subtotal',        v_subtotal,
                    'iva',             v_iva,
                    'total',           v_total,
                    'tiempo_minutos',  v_tiempo_minutos,
                    'tarifa_uuid',     v_tarifa.tarifa_uuid,
                    'vigente_hasta',   v_vigente_hasta,
                    'motivo',          v_motivo
                );
            ELSE
                RETURN jsonb_build_object(
                    'cobrar',          true,
                    'subtotal',        v_subtotal,
                    'iva',             v_iva,
                    'total',           v_total,
                    'tiempo_minutos',  v_tiempo_minutos,
                    'tarifa_uuid',     v_tarifa.tarifa_uuid,
                    'vigente_hasta',   v_vigente_hasta
                );
            END IF;
        END;
        $$;

        GRANT EXECUTE ON FUNCTION prod.calcular_cotizacion(uuid) TO parkos_app;
        """
    )


def downgrade() -> None:
    """Restore the original migration-0022 function body (early-return
    on 2nd-plate; treats 2nd-plate as a free exit — the bug this
    migration closes).

    Idempotent: ``CREATE OR REPLACE FUNCTION`` on the original body is
    a no-op if downgrade is replayed.
    """
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
            v_count_other_plate int := 0;
        BEGIN
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
                SELECT COUNT(*)
                  INTO v_count_other_plate
                  FROM prod.ingreso i
                  JOIN prod.subscripcion_vehiculos sv2
                    ON sv2.uuid_subscripcion_cliente = v_subscripcion.uuid
                   AND sv2.vigente_hasta IS NULL
                   AND sv2.estado = 'activo'
                  JOIN prod.vehiculos v2
                    ON v2.uuid = sv2.uuid_vehiculo
                   AND v2.vigente_hasta IS NULL
                   AND v2.estado = 'activo'
                 WHERE i.uuid_sucursal = v_ingreso.uuid_sucursal
                   AND i.placa = v2.placa
                   AND i.placa <> v_ingreso.placa
                   AND NOT EXISTS (
                       SELECT 1 FROM prod.salidas s
                        WHERE s.uuid_ingreso = i.uuid
                   );
                IF v_count_other_plate > 0 THEN
                    RETURN jsonb_build_object(
                        'cobrar', false,
                        'motivo', 'segunda_placa_misma_mensualidad'
                    );
                END IF;
                RETURN jsonb_build_object(
                    'cobrar', false,
                    'motivo', 'mensualidad_vigente'
                );
            END IF;

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


__all__ = ["downgrade", "upgrade"]
