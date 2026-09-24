"""MIGRATION 0049 -- ``calcular_cotizacion`` resuelve IVA por ``codigo``, no ``nombre``.

BUG REPRODUCIDO EN VIVO (2026-09-24): un operador reportó "error con el
valor de IVA que deriva en la tabla de salidas" al intentar generar una
salida en una instalación recién configurada ("desde pruebas").

**Causa raíz.** ``prod.impuestos`` tiene dos columnas que, hasta ahora,
podían usarse indistintamente para resolver la fila de IVA vigente:

  - ``codigo`` -- el UK01 real del catálogo (``modelo_datos_er.mmd:192``,
    ``UniqueConstraint("codigo", "vigente_desde")`` en
    ``models/V/impuestos.py``), y el ``natural_key`` declarado para
    identity-reconciliation entre cloud y sucursal
    (``sync/catalog/entries/sync_entries_v.py::_IMPUESTOS``).
  - ``nombre`` -- una etiqueta puramente cosmética, ``nullable``, SIN
    ninguna restricción de unicidad.

El PL/pgSQL ``calcular_cotizacion`` (desde la migration 0022) resolvía el
IVA vigente por ``WHERE nombre = 'IVA'``, mientras que TODO el resto del
sistema ya resolvía por ``codigo``:

  - ``repo/impuestos.py::obtener_iva_vigente`` / ``validar_iva_configurado``
    -- ``WHERE codigo = 'IVA'``.
  - ``repo/factura.py::crear_factura_impuesto_iva`` -- ``WHERE codigo ==
    "IVA"``.
  - El ``natural_key=("codigo",)`` de sync, usado por
    ``identity_reconciler`` para conciliar la fila entre cloud y
    sucursal.

Esta fuente de verdad partida es inherentemente frágil: cualquier
divergencia entre ``nombre`` y ``codigo`` en la fila activa rompe UN lado
sin romper el otro. Se confirmó que esto ya había ocurrido dos veces:

  1. 2026-09-23 (bug de factura): ``codigo`` corrupto
     (``'IVA-fafc78'``, con ``nombre='IVA'`` intacto) -- rompía
     ``crear_factura_impuesto_iva`` (paso del cobro) pero NO
     ``calcular_cotizacion`` (paso de la salida). Se corrigió a mano
     el dato (``codigo`` -> ``'IVA'``), sin tocar el código -- el
     defecto de fondo seguía latente.
  2. 2026-09-24 (este bug): la corrupción del dato provenía de dos
     fixtures de test (``test_calcular_cotizacion_db.py`` y
     ``test_calcular_cotizacion.py``) que sembraban ``codigo`` con un
     sufijo aleatorio (``f"IVA-{uuid4().hex[:6]}"``) dejando
     ``nombre='IVA'`` literal. Cuando esos tests corren con
     ``PARKOS_DOCKER_TEST=1`` (el modo documentado para ejecutar la
     suite dentro del contenedor desplegado, sin socket
     Docker-in-Docker -- ver ``backend/tests/conftest.py``), su
     ``TRUNCATE`` + reseed sobrescribe el ``prod.impuestos`` REAL de
     la instalación con ese dato corrupto, rompiendo esta vez
     ``calcular_cotizacion`` (que SÍ dependía de ``nombre``).

**Fix.** Cambiar el Step 4 de ``calcular_cotizacion`` para resolver por
``codigo = 'IVA'`` en vez de ``nombre = 'IVA'``, unificando la fuente de
verdad con el resto del sistema. Las dos fixtures de test se corrigieron
en el mismo cambio (``codigo="IVA"`` literal, sin sufijo aleatorio --
innecesario porque ``_truncate_tables`` limpia la tabla antes de cada
test).

``plan.md`` HU-F1.8 (líneas ~855, ~878) se actualiza en el mismo cambio
para reflejar ``codigo='IVA'`` como el criterio de aceptación correcto.

Revision ID: 0049_cotizar_iva_por_codigo
Revises: 0048_cotizar_dia_bogota_br4
Create Date: 2026-09-24

Diff vs 0048 (único cambio funcional): Step 4's ``WHERE nombre = 'IVA'``
se reemplaza por ``WHERE codigo = 'IVA'``. Todo lo demás (lock FOR SHARE,
IF NOT FOUND checks, jsonb envelope, COALESCE fecha_ingreso, CASE
obsoleta, GREATEST día Bogotá BR4) es verbatim del 0048.
"""
from __future__ import annotations

from alembic import op


revision = "0049_cotizar_iva_por_codigo"
down_revision = "0048_cotizar_dia_bogota_br4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """CREATE OR REPLACE prod.calcular_cotizacion resolviendo IVA por codigo."""
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
            --
            -- REGRESSION FIX (migration 0049): resuelve por ``codigo``
            -- (UK01 real del catálogo, modelo_datos_er.mmd:192; también
            -- el natural_key de sync en sync_entries_v.py::_IMPUESTOS),
            -- NO por ``nombre`` (columna cosmética sin restricción de
            -- unicidad). Antes de este fix, una fila con ``codigo``
            -- corrupto pero ``nombre='IVA'`` pasaba aquí pero fallaba
            -- en repo/factura.py::crear_factura_impuesto_iva (que ya
            -- resolvía por codigo) -- y viceversa. Ver el docstring del
            -- módulo de esta migración para el historial completo.
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
            -- Step 5: compute fiscal breakdown (CU-02 + BR4 Colombia day rollover)
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
    """Revierte al Step 4 keyed por ``nombre`` (bug pre-0049)."""
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

            v_inicio_dia_bogota :=
                ((NOW() AT TIME ZONE 'America/Bogota')::date)::timestamp
                AT TIME ZONE 'America/Bogota';
            v_fact_ingreso_para_calculo := GREATEST(
                COALESCE(v_ingreso.fecha_ingreso, v_ingreso.created_at),
                v_inicio_dia_bogota
            );
            v_tiempo_minutos := EXTRACT(EPOCH FROM (NOW() - v_fact_ingreso_para_calculo)) / 60.0;

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
