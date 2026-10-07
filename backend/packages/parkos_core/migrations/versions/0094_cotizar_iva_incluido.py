"""0094_cotizar_iva_incluido -- la cotizacion desglosa el IVA incluido en el precio.

Revision ID: 0094_cotizar_iva_incluido
Revises: 0093_deterministic_costos_servicios_uuids
Create Date: 2026-10-07

PROBLEMA
--------
``prod.calcular_cotizacion`` (0090) calculaba ``iva = ROUND(total * p, 2)`` y
``subtotal = total - iva``: aplicaba la tasa SOBRE el total (200 -> IVA 38 ->
subtotal 162, y 162 * 19% != 38). El precio de la tarifa ya incluye el IVA,
asi que el desglose correcto es ``subtotal = ROUND(total / (1 + p), 2)`` e
``iva = total - subtotal`` (200 -> subtotal 168.07, IVA 31.93; 168.07 * 19% =
31.93). Es el mismo desglose que ``repo.impuestos.desglosar_iva_incluido`` usa
en la suscripcion y ahora en ``factura_impuestos`` de la rotacion.

FIX
---
SOLO cambia el desglose subtotal/iva: ``total`` NO cambia, ni ningun otro
campo. Misma firma y propietario (``CREATE OR REPLACE`` preserva grants). No
toca facturas ya emitidas (compliance): solo las cotizaciones nuevas.

DOWNGRADE: restaura el cuerpo exacto de 0090.
"""
from __future__ import annotations

from alembic import op

revision = "0094_cotizar_iva_incluido"
down_revision = "0093_deterministic_costos_servicios_uuids"
branch_labels = None
depends_on = None

_COTIZAR_IVA_INCLUIDO = """
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
            v_valor_plena numeric;
            v_vigente_hasta timestamptz;
            v_count_other_plate int := 0;
            v_inicio_dia_bogota timestamp;
            v_fact_ingreso_para_calculo timestamp;
        BEGIN
            ----------------------------------------------------------------------
            -- Step 1: ingreso existe y sigue abierto (sin salidas)
            ----------------------------------------------------------------------
            SELECT
                i.uuid_sucursal,
                i.placa,
                i.uuid_tipo_vehiculo,
                i.fecha_ingreso,
                i.created_at,
                EXISTS(
                    SELECT 1 FROM prod.salidas s
                    WHERE s.uuid_ingreso = i.uuid
                      AND NOT EXISTS (
                          SELECT 1 FROM prod.anulaciones a
                          WHERE a.uuid_salida = s.uuid
                            AND a.tipo_anulable = 'salida'
                            AND a.estado = 'ejecutada'
                      )
                ) AS tiene_salida
              INTO v_ingreso
              FROM prod.ingreso i
             WHERE i.uuid = p_uuid_ingreso;
            IF NOT FOUND OR v_ingreso.tiene_salida THEN
                RETURN jsonb_build_object('error', 'ingreso_no_encontrado');
            END IF;

            ----------------------------------------------------------------------
            -- Step 2: tarifa vigente con lock FOR SHARE (KD-1)
            --
            -- MOVIDO (migration 0050): antes era Step 3. Ahora se calcula
            -- SIEMPRE, incluso cuando la placa tiene mensualidad vigente,
            -- para poder mostrar el desglose completo en la factura con
            -- descuento (ver docstring del modulo).
            ----------------------------------------------------------------------
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
            -- Step 3: impuesto IVA vigente (KD-IVA)
            --
            -- MOVIDO (migration 0050): antes era Step 4. Resuelve por
            -- ``codigo`` (fix de migration 0049), verbatim salvo el
            -- reordenamiento.
            ----------------------------------------------------------------------
            SELECT porcentaje
              INTO v_impuesto
              FROM prod.impuestos
             WHERE codigo      = 'IVA'
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
            -- Step 4: compute fiscal breakdown (CU-02 + BR4 Colombia day rollover)
            --
            -- MOVIDO (migration 0050): antes era Step 5. Se calcula SIEMPRE
            -- ahora, antes de decidir si hay mensualidad vigente (Step 5).
            ----------------------------------------------------------------------
            v_inicio_dia_bogota :=
                ((NOW() AT TIME ZONE 'America/Bogota')::date)::timestamp
                AT TIME ZONE 'America/Bogota';
            v_fact_ingreso_para_calculo := GREATEST(
                COALESCE(v_ingreso.fecha_ingreso, v_ingreso.created_at),
                v_inicio_dia_bogota
            );
            v_tiempo_minutos := EXTRACT(EPOCH FROM (NOW() - v_fact_ingreso_para_calculo)) / 60.0;

            v_valor_plena := v_tarifa.valor_plena / v_tarifa.valor;

            IF v_tarifa.valor_plena IS NOT NULL AND v_tarifa.valor_plena > 0
               AND v_tiempo_minutos >= v_valor_plena THEN
                v_total := v_tarifa.valor_plena;
            ELSE
                v_total := v_tarifa.valor * CEIL(v_tiempo_minutos);
            END IF;

            -- El precio YA incluye el IVA: base = total / (1 + p), iva = total - base
            -- (base + iva == total exacto). Antes: iva = total * p (sobre el total).
            v_total      := ROUND(v_total, 2);
            v_subtotal   := ROUND(v_total / (1 + v_impuesto.porcentaje), 2);
            v_iva        := v_total - v_subtotal;
            v_vigente_hasta := NOW() + INTERVAL '15 minutes';

            ----------------------------------------------------------------------
            -- Step 5: mensualidad vigente (port de resolve_active_subscription_for_exit)
            --
            -- MOVIDO (migration 0050): antes era Step 2 (short-circuit
            -- temprano). Ahora decide ``cobrar`` usando el desglose fiscal
            -- ya calculado en el Step 4. LEFT JOIN a tipo_subscripciones
            -- (no INNER): ``uuid_tipo_subscripcion`` es nullable y varios
            -- fixtures de test existentes lo dejan en NULL a proposito --
            -- un INNER JOIN aqui excluiria esas suscripciones por completo
            -- y regresionaria el short-circuit de mensualidad_vigente.
            ----------------------------------------------------------------------
            SELECT sc.uuid, ts.tipo, ts.cantidad_maxima_vehiculos
              INTO v_subscripcion
              FROM prod.subscripciones_cliente sc
              JOIN prod.subscripcion_vehiculos sv
                ON sv.uuid_subscripcion_cliente = sc.uuid
              JOIN prod.vehiculos v
                ON v.uuid = sv.uuid_vehiculo
              LEFT JOIN prod.tipo_subscripciones ts
                ON ts.uuid = sc.uuid_tipo_subscripcion
               AND ts.vigente_hasta IS NULL
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
                          AND NOT EXISTS (
                              SELECT 1 FROM prod.anulaciones a
                              WHERE a.uuid_salida = s.uuid
                                AND a.tipo_anulable = 'salida'
                                AND a.estado = 'ejecutada'
                          )
                   );

                IF v_count_other_plate > 0 THEN
                    IF v_subscripcion.cantidad_maxima_vehiculos > 2 THEN
                        -- Plan empresa/flota (BUGFIX + regla de negocio
                        -- 2026-09-24): varios vehiculos simultaneos es lo
                        -- normal, cada uno sale sin cobro.
                        RETURN jsonb_build_object(
                            'cobrar',                    false,
                            'motivo',                     'multiple_vehiculos_plan_empresa',
                            'subtotal',                   v_subtotal,
                            'iva',                         v_iva,
                            'total',                       v_total,
                            'tiempo_minutos',              v_tiempo_minutos,
                            'tarifa_uuid',                 v_tarifa.tarifa_uuid,
                            'vigente_hasta',               v_vigente_hasta,
                            'uuid_subscripcion_cliente',   v_subscripcion.uuid,
                            'concepto_descuento',          COALESCE(v_subscripcion.tipo, 'Suscripcion')
                        );
                    END IF;
                    -- Plan personal (cantidad_maxima_vehiculos <= 2 o NULL):
                    -- BUGFIX (restaura migration 0038, regresado
                    -- silenciosamente por 0046..0049): la 2da placa
                    -- simultanea paga como ROTACION normal, sin descuento.
                    RETURN jsonb_build_object(
                        'cobrar',          true,
                        'subtotal',        v_subtotal,
                        'iva',             v_iva,
                        'total',           v_total,
                        'tiempo_minutos',  v_tiempo_minutos,
                        'tarifa_uuid',     v_tarifa.tarifa_uuid,
                        'vigente_hasta',   v_vigente_hasta,
                        'motivo',          'segunda_placa_misma_mensualidad'
                    );
                END IF;

                -- 1era placa (unica en patio): mensualidad vigente. Sin
                -- cobro, pero con el desglose completo + el nombre del
                -- plan para armar la factura con descuento (feature
                -- 2026-09-24).
                RETURN jsonb_build_object(
                    'cobrar',                    false,
                    'motivo',                     'mensualidad_vigente',
                    'subtotal',                   v_subtotal,
                    'iva',                         v_iva,
                    'total',                       v_total,
                    'tiempo_minutos',              v_tiempo_minutos,
                    'tarifa_uuid',                 v_tarifa.tarifa_uuid,
                    'vigente_hasta',               v_vigente_hasta,
                    'uuid_subscripcion_cliente',   v_subscripcion.uuid,
                    'concepto_descuento',          COALESCE(v_subscripcion.tipo, 'Suscripcion')
                );
            END IF;

            ----------------------------------------------------------------------
            -- Step 6: sin suscripcion (walk-in) -> cobrar=true
            ----------------------------------------------------------------------
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
"""

_COTIZAR_IVA_SOBRE_TOTAL_0090 = """
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
            v_valor_plena numeric;
            v_vigente_hasta timestamptz;
            v_count_other_plate int := 0;
            v_inicio_dia_bogota timestamp;
            v_fact_ingreso_para_calculo timestamp;
        BEGIN
            ----------------------------------------------------------------------
            -- Step 1: ingreso existe y sigue abierto (sin salidas)
            ----------------------------------------------------------------------
            SELECT
                i.uuid_sucursal,
                i.placa,
                i.uuid_tipo_vehiculo,
                i.fecha_ingreso,
                i.created_at,
                EXISTS(
                    SELECT 1 FROM prod.salidas s
                    WHERE s.uuid_ingreso = i.uuid
                      AND NOT EXISTS (
                          SELECT 1 FROM prod.anulaciones a
                          WHERE a.uuid_salida = s.uuid
                            AND a.tipo_anulable = 'salida'
                            AND a.estado = 'ejecutada'
                      )
                ) AS tiene_salida
              INTO v_ingreso
              FROM prod.ingreso i
             WHERE i.uuid = p_uuid_ingreso;
            IF NOT FOUND OR v_ingreso.tiene_salida THEN
                RETURN jsonb_build_object('error', 'ingreso_no_encontrado');
            END IF;

            ----------------------------------------------------------------------
            -- Step 2: tarifa vigente con lock FOR SHARE (KD-1)
            --
            -- MOVIDO (migration 0050): antes era Step 3. Ahora se calcula
            -- SIEMPRE, incluso cuando la placa tiene mensualidad vigente,
            -- para poder mostrar el desglose completo en la factura con
            -- descuento (ver docstring del modulo).
            ----------------------------------------------------------------------
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
            -- Step 3: impuesto IVA vigente (KD-IVA)
            --
            -- MOVIDO (migration 0050): antes era Step 4. Resuelve por
            -- ``codigo`` (fix de migration 0049), verbatim salvo el
            -- reordenamiento.
            ----------------------------------------------------------------------
            SELECT porcentaje
              INTO v_impuesto
              FROM prod.impuestos
             WHERE codigo      = 'IVA'
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
            -- Step 4: compute fiscal breakdown (CU-02 + BR4 Colombia day rollover)
            --
            -- MOVIDO (migration 0050): antes era Step 5. Se calcula SIEMPRE
            -- ahora, antes de decidir si hay mensualidad vigente (Step 5).
            ----------------------------------------------------------------------
            v_inicio_dia_bogota :=
                ((NOW() AT TIME ZONE 'America/Bogota')::date)::timestamp
                AT TIME ZONE 'America/Bogota';
            v_fact_ingreso_para_calculo := GREATEST(
                COALESCE(v_ingreso.fecha_ingreso, v_ingreso.created_at),
                v_inicio_dia_bogota
            );
            v_tiempo_minutos := EXTRACT(EPOCH FROM (NOW() - v_fact_ingreso_para_calculo)) / 60.0;

            v_valor_plena := v_tarifa.valor_plena / v_tarifa.valor;

            IF v_tarifa.valor_plena IS NOT NULL AND v_tarifa.valor_plena > 0
               AND v_tiempo_minutos >= v_valor_plena THEN
                v_total := v_tarifa.valor_plena;
            ELSE
                v_total := v_tarifa.valor * CEIL(v_tiempo_minutos);
            END IF;

            v_iva        := ROUND(v_total * v_impuesto.porcentaje, 2);
            v_subtotal   := ROUND(v_total - v_iva, 2);
            v_total      := ROUND(v_total, 2);
            v_vigente_hasta := NOW() + INTERVAL '15 minutes';

            ----------------------------------------------------------------------
            -- Step 5: mensualidad vigente (port de resolve_active_subscription_for_exit)
            --
            -- MOVIDO (migration 0050): antes era Step 2 (short-circuit
            -- temprano). Ahora decide ``cobrar`` usando el desglose fiscal
            -- ya calculado en el Step 4. LEFT JOIN a tipo_subscripciones
            -- (no INNER): ``uuid_tipo_subscripcion`` es nullable y varios
            -- fixtures de test existentes lo dejan en NULL a proposito --
            -- un INNER JOIN aqui excluiria esas suscripciones por completo
            -- y regresionaria el short-circuit de mensualidad_vigente.
            ----------------------------------------------------------------------
            SELECT sc.uuid, ts.tipo, ts.cantidad_maxima_vehiculos
              INTO v_subscripcion
              FROM prod.subscripciones_cliente sc
              JOIN prod.subscripcion_vehiculos sv
                ON sv.uuid_subscripcion_cliente = sc.uuid
              JOIN prod.vehiculos v
                ON v.uuid = sv.uuid_vehiculo
              LEFT JOIN prod.tipo_subscripciones ts
                ON ts.uuid = sc.uuid_tipo_subscripcion
               AND ts.vigente_hasta IS NULL
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
                          AND NOT EXISTS (
                              SELECT 1 FROM prod.anulaciones a
                              WHERE a.uuid_salida = s.uuid
                                AND a.tipo_anulable = 'salida'
                                AND a.estado = 'ejecutada'
                          )
                   );

                IF v_count_other_plate > 0 THEN
                    IF v_subscripcion.cantidad_maxima_vehiculos > 2 THEN
                        -- Plan empresa/flota (BUGFIX + regla de negocio
                        -- 2026-09-24): varios vehiculos simultaneos es lo
                        -- normal, cada uno sale sin cobro.
                        RETURN jsonb_build_object(
                            'cobrar',                    false,
                            'motivo',                     'multiple_vehiculos_plan_empresa',
                            'subtotal',                   v_subtotal,
                            'iva',                         v_iva,
                            'total',                       v_total,
                            'tiempo_minutos',              v_tiempo_minutos,
                            'tarifa_uuid',                 v_tarifa.tarifa_uuid,
                            'vigente_hasta',               v_vigente_hasta,
                            'uuid_subscripcion_cliente',   v_subscripcion.uuid,
                            'concepto_descuento',          COALESCE(v_subscripcion.tipo, 'Suscripcion')
                        );
                    END IF;
                    -- Plan personal (cantidad_maxima_vehiculos <= 2 o NULL):
                    -- BUGFIX (restaura migration 0038, regresado
                    -- silenciosamente por 0046..0049): la 2da placa
                    -- simultanea paga como ROTACION normal, sin descuento.
                    RETURN jsonb_build_object(
                        'cobrar',          true,
                        'subtotal',        v_subtotal,
                        'iva',             v_iva,
                        'total',           v_total,
                        'tiempo_minutos',  v_tiempo_minutos,
                        'tarifa_uuid',     v_tarifa.tarifa_uuid,
                        'vigente_hasta',   v_vigente_hasta,
                        'motivo',          'segunda_placa_misma_mensualidad'
                    );
                END IF;

                -- 1era placa (unica en patio): mensualidad vigente. Sin
                -- cobro, pero con el desglose completo + el nombre del
                -- plan para armar la factura con descuento (feature
                -- 2026-09-24).
                RETURN jsonb_build_object(
                    'cobrar',                    false,
                    'motivo',                     'mensualidad_vigente',
                    'subtotal',                   v_subtotal,
                    'iva',                         v_iva,
                    'total',                       v_total,
                    'tiempo_minutos',              v_tiempo_minutos,
                    'tarifa_uuid',                 v_tarifa.tarifa_uuid,
                    'vigente_hasta',               v_vigente_hasta,
                    'uuid_subscripcion_cliente',   v_subscripcion.uuid,
                    'concepto_descuento',          COALESCE(v_subscripcion.tipo, 'Suscripcion')
                );
            END IF;

            ----------------------------------------------------------------------
            -- Step 6: sin suscripcion (walk-in) -> cobrar=true
            ----------------------------------------------------------------------
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
"""


def upgrade() -> None:
    """CREATE OR REPLACE prod.calcular_cotizacion con IVA incluido en el precio."""
    op.execute(_COTIZAR_IVA_INCLUIDO)


def downgrade() -> None:
    """Restaura prod.calcular_cotizacion tal cual la dejo 0090."""
    op.execute(_COTIZAR_IVA_SOBRE_TOTAL_0090)
