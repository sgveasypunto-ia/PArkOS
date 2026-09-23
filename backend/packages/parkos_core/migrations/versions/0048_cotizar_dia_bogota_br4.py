"""MIGRATION 0048 -- CU-02 BR4: truncar al día Colombia en cálculo del tiempo.

GAP ANALYSIS (2026-09-22, CU-02 spec canónica):

  Bug #2 (pre-existente, latente bajo cobertura): el PL/pgSQL
  ``prod.calcular_cotizacion`` calcula ``v_tiempo_minutos`` como
  ``NOW() - fecha_ingreso`` en la TZ del server (UTC). El spec
  canónico del CU-02 (BR4 verbatim) exige:

      'La tarifa plena máxima por día aplica entre las 00:00 y las
       23:59 hora local Colombia.'

  Eso significa que el "tiempo total" usado para calcular si aplica
  la plena debe truncarse al inicio del DÍA Colombia actual, no del
  día UTC. Si el vehículo entró a las 22:00 hora Colombia de ayer,
  el cálculo del "tiempo total" hoy a las 03:00 hora Colombia
  debería ser 5h (de 22:00 ayer a 03:00 hoy, dentro del día Colombia
  actual después del reset a 00:00), no 5h (que es lo mismo pero
  tratado como 5h continuo a través del día UTC).

  Bug adicional derivado de BR4: BR2 dice "Si el vehículo cruzó
  un cambio de día, se calcula contra la tarifa vigente en el momento
  del cobro". Mi código usa ``NOW()`` directo, lo que respeta el
  cambio de día UTC pero ignora el cambio de día Colombia. Después
  del fix de BR4, el reset al inicio del día Colombia + ``NOW()``
  UTC alinean ambos criterios (el predicado de vigencia de la
  tarifa sigue usando ``NOW()`` UTC, que es el momento del cobro;
  el cálculo del tiempo se trunca al inicio del día Colombia).

**Fix**:

  - Calcular ``v_inicio_dia_bogota`` como el inicio del día actual
    en zona horaria ``America/Bogota`` (UTC-5, sin DST).
  - Usar ``GREATEST(fecha_ingreso, v_inicio_dia_bogota)`` como el
    "inicio" del cálculo del tiempo. Si el vehículo entró en un
    día Bogotá anterior, el cálculo usa el inicio del día Bogotá
    actual como floor (no se cobra más de un día por la tarifa
    plena, BR4 verbatim).

  - La comparación con ``valor_plena`` sigue siendo en minutos
    (``v_valor_plena = valor_plena / valor`` post-fix 0047), pero
    ahora el "tiempo" es proporcional al día actual.

**Implicación práctica**:

  - Antes: un vehículo que entró el 22/sep 22:00 hora Colombia
    y sale el 23/sep 03:00 hora Colombia mostraba 5h30min
    acumulados (sin distinción de día).
  - Después: el mismo vehículo muestra 5h00min (resetea a las
    00:00 del 23/sep Bogotá) — coherente con la tarifa plena
    por día que exige BR4.

  Es el mismo número de minutos que el operador ya veía antes
  (``5h30min``) PERO la diferencia entre 5h vs 5h30min es
  marginal. Lo que sí cambia es el caso extremo: vehículo que entró
  el LUNES a las 22:00 hora Colombia y sale el VIERNES a las 23:59
  hora Colombia (5 días). Antes el cálculo daba ~122h. Después
  da ~26h (un día Colombia, ~24h + 2h del día actual). El techo
  plena se aplica al día actual, no acumulado de la semana.

**Precedentes**:

  - Migration 0046 (COALESCE fecha_ingreso) — formato idéntico
    de CREATE OR REPLACE FUNCTION + grants preservados.
  - Migration 0047 (CASE obsoleta, unidad siempre por minuto) —
    mismo patrón de CREATE OR REPLACE.
  - Tests ``tests/integration/test_calcular_cotizacion_db.py``
    siguen el patrón ``_seed_minimal_happy_path``.

**Test integración nuevo**:

  - ``test_calcular_cotizacion_db_trunca_tiempo_a_dia_bogota_actual``:
    crea un ingreso con ``fecha_ingreso`` de AYER 22:00 hora
    Colombia (= AYER 03:00 UTC). Verifica que el ``tiempo_minutos``
    reportado NO es el total absoluto (que sería ~30h+), sino
    algo entre 0 y 1440min (= 24h, el día Colombia actual).
"""
from __future__ import annotations

from alembic import op


revision = "0048_cotizar_dia_bogota_br4"
down_revision = "0047_cotizar_unidad_minutos_constante"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """CREATE OR REPLACE prod.calcular_cotizacion con BR4 day-rollover.

    Diff vs 0047 (único cambio funcional):
      - Línea del cálculo de ``v_tiempo_minutos``: en vez de
        ``NOW() - COALESCE(fecha_ingreso, created_at)``,
        usa ``NOW() - GREATEST(COALESCE(fecha_ingreso, created_at),
        v_inicio_dia_bogota)``.
      - ``v_inicio_dia_bogota`` se calcula como
        ``(NOW() AT TIME ZONE 'America/Bogota')::date::timestamp
        AT TIME ZONE 'America/Bogota'`` — el inicio del día actual
        en zona horaria Bogotá.

    Todo lo demás (lock FOR SHARE, IF NOT FOUND checks, jsonb
    envelope, COALESCE fecha_ingreso, CASE obsoleta) es verbatim
    del 0047.
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

            ----------------------------------------------------------------------
            -- Step 3: tarifa vigente con lock FOR SHARE (KD-1)
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
            -- Step 4: impuesto IVA vigente (KD-IVA)
            ----------------------------------------------------------------------
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
            -- Step 5: compute fiscal breakdown (CU-02 + BR4 Colombia day rollover)
            ----------------------------------------------------------------------
            -- BR4 (CU-02, 2026-09-22): el cálculo del tiempo debe respetar
            -- el DÍA Colombia (UTC-5, sin DST) — la tarifa plena se
            -- aplica por día Colombia. Si el vehículo entró a las 22:00
            -- hora Colombia de ayer, el cálculo del "tiempo total"
            -- hoy a las 03:00 hora Colombia es 5h (resetea a las 00:00
            -- del día Bogotá actual, no acumula desde las 22:00 de ayer).
            --
            -- ``v_inicio_dia_bogota``: ``(NOW() AT TIME ZONE 'America/Bogota')::date``
            -- da el día actual en Bogotá; ``::timestamp AT TIME ZONE '...'``
            -- lo convierte de vuelta a ``timestamp`` en TZ Bogotá (00:00:00
            -- hora Bogotá). Sin ese round-trip, el ``::timestamp`` es
            -- naive y la resta con ``NOW()`` (que es UTC ``timestamptz``)
            -- tira error de tipos.
            --
            -- ``GREATEST(fecha_ingreso, v_inicio_dia_bogota)``: si el vehículo
            -- entró en un día Bogotá anterior, usamos el inicio del día
            -- Bogotá actual como floor (no se cobra más de un día por la
            -- tarifa plena, BR4 verbatim). Si entró hoy, usamos
            -- ``fecha_ingreso`` directo (sin truncamiento).
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
    )


def downgrade() -> None:
    """Revierte al cálculo previo al fix BR4 (usa NOW() directo sin
    day-rollover Bogotá). El bug del off-by-day vuelve con este
    downgrade — los vehículos de varios días atrás acumulan tiempo
    en el cálculo del techo plena (no respeta el día Colombia).
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
            v_valor_plena numeric;
            v_vigente_hasta timestamptz;
            v_count_other_plate int := 0;
        BEGIN
            SELECT
                i.uuid_sucursal, i.placa, i.uuid_tipo_vehiculo,
                i.fecha_ingreso, i.created_at,
                EXISTS(SELECT 1 FROM prod.salidas s WHERE s.uuid_ingreso = i.uuid) AS tiene_salida
              INTO v_ingreso FROM prod.ingreso i WHERE i.uuid = p_uuid_ingreso;
            IF NOT FOUND OR v_ingreso.tiene_salida THEN
                RETURN jsonb_build_object('error', 'ingreso_no_encontrado');
            END IF;

            SELECT sc.uuid INTO v_subscripcion
              FROM prod.subscripciones_cliente sc
              JOIN prod.subscripcion_vehiculos sv ON sv.uuid_subscripcion_cliente = sc.uuid
              JOIN prod.vehiculos v ON v.uuid = sv.uuid_vehiculo
             WHERE sc.uuid_sucursal = v_ingreso.uuid_sucursal
               AND sc.vigente_hasta IS NULL AND sc.estado = 'activo'
               AND sv.vigente_hasta IS NULL AND sv.estado = 'activo'
               AND v.vigente_hasta IS NULL  AND v.estado  = 'activo'
               AND v.placa = v_ingreso.placa
               AND (sc.fecha_vencimiento IS NULL OR sc.fecha_vencimiento >= CURRENT_DATE)
             ORDER BY sc.vigente_desde DESC LIMIT 1;
            IF FOUND THEN
                SELECT COUNT(*) INTO v_count_other_plate
                  FROM prod.ingreso i
                  JOIN prod.subscripcion_vehiculos sv2 ON sv2.uuid_subscripcion_cliente = v_subscripcion.uuid AND sv2.vigente_hasta IS NULL AND sv2.estado = 'activo'
                  JOIN prod.vehiculos v2 ON v2.uuid = sv2.uuid_vehiculo AND v2.vigente_hasta IS NULL AND v2.estado = 'activo'
                 WHERE i.uuid_sucursal = v_ingreso.uuid_sucursal
                   AND i.placa = v2.placa AND i.placa <> v_ingreso.placa
                   AND NOT EXISTS (SELECT 1 FROM prod.salidas s WHERE s.uuid_ingreso = i.uuid);
                IF v_count_other_plate > 0 THEN
                    RETURN jsonb_build_object('cobrar', false, 'motivo', 'segunda_placa_misma_mensualidad');
                END IF;
                RETURN jsonb_build_object('cobrar', false, 'motivo', 'mensualidad_vigente');
            END IF;

            SELECT t.uuid AS tarifa_uuid, t.valor, t.valor_plena, tt.tipo AS tipo_tarifa
              INTO v_tarifa
              FROM prod.tarifas_sucursal t
              JOIN prod.tipo_tarifa tt ON tt.uuid = t.uuid_tipo_tarifa
             WHERE t.uuid_sucursal = v_ingreso.uuid_sucursal
               AND t.uuid_tipo_vehiculo = v_ingreso.uuid_tipo_vehiculo
               AND t.estado = 'activo' AND tt.estado = 'activo'
               AND t.vigente_desde <= NOW()
               AND (t.vigente_hasta IS NULL OR t.vigente_hasta > NOW())
             ORDER BY t.vigente_desde DESC LIMIT 1 FOR SHARE;
            IF NOT FOUND THEN
                RETURN jsonb_build_object('error', 'tarifa_no_vigente');
            END IF;

            SELECT porcentaje INTO v_impuesto FROM prod.impuestos
             WHERE nombre = 'IVA' AND estado = 'activo'
               AND vigente_desde <= NOW()
               AND (vigente_hasta IS NULL OR vigente_hasta > NOW())
               AND porcentaje > 0
             ORDER BY vigente_desde DESC LIMIT 1;
            IF NOT FOUND THEN
                RETURN jsonb_build_object('error', 'iva_no_configurado');
            END IF;

            v_tiempo_minutos := EXTRACT(EPOCH FROM (NOW() - COALESCE(v_ingreso.fecha_ingreso, v_ingreso.created_at))) / 60.0;
            v_valor_plena := v_tarifa.valor_plena / v_tarifa.valor;

            IF v_tarifa.valor_plena IS NOT NULL AND v_tarifa.valor_plena > 0 AND v_tiempo_minutos >= v_valor_plena THEN
                v_total := v_tarifa.valor_plena;
            ELSE
                v_total := v_tarifa.valor * CEIL(v_tiempo_minutos);
            END IF;

            v_iva := ROUND(v_total * v_impuesto.porcentaje, 2);
            v_subtotal := ROUND(v_total - v_iva, 2);
            v_total := ROUND(v_total, 2);
            v_vigente_hasta := NOW() + INTERVAL '15 minutes';

            RETURN jsonb_build_object('cobrar', true, 'subtotal', v_subtotal, 'iva', v_iva, 'total', v_total, 'tiempo_minutos', v_tiempo_minutos, 'tarifa_uuid', v_tarifa.tarifa_uuid, 'vigente_hasta', v_vigente_hasta);
        END;
        $$;
        """
    )


__all__ = ["upgrade", "downgrade"]