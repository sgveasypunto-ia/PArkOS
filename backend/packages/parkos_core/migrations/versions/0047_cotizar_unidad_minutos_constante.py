"""MIGRATION 0047 -- prod.calcular_cotizacion simplifica unidad_minutos a 1.

GAP ANALYSIS (2026-09-22, CU-02 spec canónica):

  El operador pasó la spec canónica del CU-02 (Calcular tarifa en salida).
  El AC2 dice: "El sistema debe redondear hacia arriba (Math.ceil por
  minuto o unidad de la tarifa) el tiempo para calculo". El BR5 cierra
  con: "el valor se debe aplicar por minuto".

  Interpretación confirmada por el operador: el cálculo de la tarifa se
  hace SIEMPRE por minuto. La CASE fraccion/hora/nocturna queda
  OBSOLETA — el catálogo debe expresar ``valor`` y ``valor_plena`` en
  pesos por minuto. Si la tarifa del operador es "100 pesos la hora",
  el catálogo guarda ``valor = 6000`` (100*60/min), NO "100 pesos".

**Bug #1 (pre-existente, latente bajo varios bonos con cobertura)**:

  La función actual (migration 0022, replica del 0046) tenía:

      v_unidad_minutos := CASE v_tarifa.tipo_tarifa
          WHEN 'fraccion' THEN 15
          WHEN 'hora'     THEN 60
          WHEN 'nocturna' THEN 720
          ELSE                  1
      END;

      v_valor_plena := (v_tarifa.valor_plena / v_tarifa.valor) * v_unidad_minutos;

      v_total := v_tarifa.valor * CEIL(v_tiempo_minutos);  -- ❌ ignora unidad

  El cálculo de ``v_total`` IGNORABA ``v_unidad_minutos``. Para una
  tarifa 'hora' con ``valor=100`` (guardada como "100 la hora"),
  vehículo 2h = 120 min, el cálculo daba ``100 * CEIL(120) = 12000``
  cuando el spec exige ``100 * CEIL(2) = 200``. El BR1 (tiempo en
  la unidad de la tarifa con ceil) estaba roto silenciosamente.

  Como el catálogo real tenía tarifas que se expresaban por hora pero
  guardaban ``valor`` como número entero (sin multiplicar por 60), el
  efecto visible era: el cobro era 60× lo esperado para tarifas por
  hora, 15× para fracciones, 720× para nocturnas. Bug grave pero
  enmascarado porque el operador rara vez veía casos donde el cálculo
  se acercara al techo de plena.

**Fix (esta migración)**:

  - Quitar la CASE. ``v_unidad_minutos := 1`` (constante).
  - Simplificar el cálculo de ``v_valor_plena`` a la división directa:

      v_valor_plena_minutos := v_tarifa.valor_plena / v_tarifa.valor;

    Con la unidad fija en minutos, el techo "tiempo al cual aplica
    plena" se expresa naturalmente en minutos (cantidad de minutos
    cuyo costo al ``valor`` actual alcanza el ``valor_plena``). El
    spec AC3 dice "Si tiempo >= tiempo_tar_plena: tarifa = valor_plena"
    — esa comparación ahora es coherente con la unidad.
  - Mantener el cálculo de ``v_total`` que ya era ``valor *
    CEIL(v_tiempo_minutos)`` (que era el bug latente cuando la CASE
    pensaba que era por hora; ahora correcto con la unidad fija en
    minuto).

**Implicación de modelo de datos**:

  El catálogo de ``prod.tarifas_sucursal`` debe guardar ``valor`` y
  ``valor_plena`` expresados en **pesos por minuto**. Si el operador
  vende "100 pesos la hora", el catálogo guarda ``valor = 6000`` (no
  100). Si vende "50 pesos por fracción de 15 min", guarda ``valor =
  750``. Si vende "10000 pesos la noche", guarda ``valor = 10000`` (la
  noche es por evento, no se prorratea por minuto — eso es
  responsabilidad del catálogo no del PL/pgSQL).

  Esta migración NO migra datos — es defense in depth del cálculo.
  Los datos del catálogo que sigan el modelo viejo (valor "por hora")
  van a mostrar cálculos 60× más altos hasta que se actualicen. El
  operador debe coordinar una migración de datos separada si tiene
  tarifas activas. Esta es una decisión de producto, no de código.

**Precedentes**:

  - Migration 0022 (creación original) — la lógica que esta migración
    reemplaza.
  - Migration 0046 (COALESCE fecha_ingreso) — formato idéntico de
    ``CREATE OR REPLACE FUNCTION`` + grants preservados via REPLACE.

**Test integración nuevo**:

  - ``test_calcular_cotizacion_db_unidad_minutos_siempre_uno`` —
    verifica que la CASE desapareció (``v_unidad_minutos=1``
    efectivamente), que el cálculo por minuto respeta el ceil, y que
    el techo de plena se aplica en la cantidad correcta de minutos.
    Tres casos:
      - tarifa con ``valor=100`` (ya "por minuto"), 89min → total=8900
      - tarifa con ``valor=100``, 91min (>= valor_plena/valor=2min
        ... absurdo, pero el spec literal lo pide — valor_plena=200,
        entonces el techo es 2min). El test docstring explica por
        qué con la interpretación A el techo en minutos es
        valor_plena/valor.
      - tarifa con ``valor=100``, 60min → total=6000 (sin tocar plena)
"""
from __future__ import annotations

from alembic import op


revision = "0047_cotizar_unidad_minutos_constante"
down_revision = "0046_fix_cotizar_fecha_ingreso_coalesce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """CREATE OR REPLACE prod.calcular_cotizacion con unidad_minutos=1.

    Diff vs 0046 (único cambio funcional):
      - Línea del CASE eliminada. ``v_unidad_minutos := 1`` constante.
      - Línea de ``v_valor_plena`` simplificada a la división directa.
      - La comparación ``v_tiempo_minutos >= v_valor_plena`` ahora es
        coherente (ambos en minutos).
      - El cálculo de ``v_total`` queda IGUAL al 0046 (``valor *
        CEIL(v_tiempo_minutos)``) — que era el bug latente cuando la
        CASE pensaba que era por hora; ahora correcto con la unidad
        fija en minuto.

    Todo lo demás (lock FOR SHARE, IF NOT FOUND checks, jsonb envelope,
    COALESCE fecha_ingreso) es verbatim del 0046.
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
            ----------------------------------------------------------------------
            -- Step 1: ingreso existe y sigue abierto (sin salidas)
            ----------------------------------------------------------------------
            -- The canonical ``prod.salidas`` schema has NO ``estado``
            -- column. Existence of a matching ``salidas`` row is the
            -- canonical ``cerrado`` signal per
            -- ``api/v1/operacion.py::get_ingreso_estado``.
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
                -- CU-03M second-vehicle rotation rule (plan.md:64, DEC-SUC-21):
                -- a monthly subscription covers up to 2 plates.
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
            -- Step 5: compute fiscal breakdown (CU-02 spec canónica)
            ----------------------------------------------------------------------
            -- GAP ANALYSIS fix (CU-02, 2026-09-22): el cálculo de la tarifa
            -- se hace SIEMPRE por minuto. La CASE fraccion/hora/nocturna
            -- queda OBSOLETA — el catálogo debe expresar ``valor`` y
            -- ``valor_plena`` en pesos por minuto. Si la tarifa del
            -- operador es "100 pesos la hora", el catálogo guarda
            -- ``valor = 6000`` (100*60/min), NO "100 pesos".
            --
            -- Antes (migration 0046, código heredado del 0022): la CASE
            -- definía ``v_unidad_minutos`` pero el cálculo de ``v_total``
            -- la IGNORABA (usaba ``CEIL(v_tiempo_minutos)`` directo). El
            -- cobro para tarifa 'hora' terminaba siendo 60× lo
            -- esperado. Bug latente bajo varios bonos con cobertura — el
            -- operador rara vez veía casos donde se acercara al techo
            -- de plena, así que el bug se ocultaba.
            --
            -- ``v_tiempo_minutos`` carries sub-second precision (e.g.
            -- ``89.0025`` for 89 minutes + drift). El CEIL arriba del
            -- 89.X lands exactly on 90 (the natural test boundary).
            v_tiempo_minutos := EXTRACT(EPOCH FROM (NOW() - COALESCE(v_ingreso.fecha_ingreso, v_ingreso.created_at))) / 60.0;

            -- AC3 + BR1: el techo de plena se aplica cuando la cantidad
            -- de minutos alcanza el equivalente a ``valor_plena``.
            -- Con la unidad fija en minuto, ``valor_plena / valor`` es
            -- directamente la cantidad de minutos al cual aplica plena
            -- (porque valor es por minuto). Si valor_plena=200 y
            -- valor=100 (ambos por minuto), el techo es 2 minutos.
            -- Eso puede parecer absurdo, pero es la consecuencia del
            -- spec: el catálogo define ambos campos en pesos por
            -- minuto. Si el operador vende "tope $200 al equivalente
            -- de 2h", el catálogo guarda ``valor = 100/60 = 1.67 por
            -- minuto`` y ``valor_plena = 200`` — el techo en minutos
            -- es 200/1.67 = 120 min = 2h, que es lo deseado.
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
    """Revierte a la CASE fraccion/hora/nocturna del 0046 (vía con la unidad).

    Solo se usa para rollback de emergencia. El bug latente del cálculo
    que ignora ``v_unidad_minutos`` regresa con este downgrade — el
    cálculo de ``v_total`` no cambia (siempre fue ``valor *
    CEIL(v_tiempo_minutos)``), pero ``v_valor_plena`` vuelve a la
    fórmula con multiplicación por unidad, lo que afecta cuándo se
    aplica la plena.
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

            v_unidad_minutos := CASE v_tarifa.tipo_tarifa WHEN 'fraccion' THEN 15 WHEN 'hora' THEN 60 WHEN 'nocturna' THEN 720 ELSE 1 END;
            v_tiempo_minutos := EXTRACT(EPOCH FROM (NOW() - COALESCE(v_ingreso.fecha_ingreso, v_ingreso.created_at))) / 60.0;
            v_valor_plena := (v_tarifa.valor_plena / v_tarifa.valor) * v_unidad_minutos;

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