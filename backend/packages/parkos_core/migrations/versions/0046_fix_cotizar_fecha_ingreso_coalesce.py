"""MIGRATION 0046 -- defense in depth: COALESCE fecha_ingreso con created_at en prod.calcular_cotizacion.

REGRESSION (2026-09-22, directiva del operador):

  El flujo de salida de rotación (``GET /api/v1/operacion/cotizar`` para
  un ingreso sin ``subscripcion_cliente``) retorna ``500 Internal Server
  Error`` cuando ``prod.ingreso.fecha_ingreso IS NULL``. El PL/pgSQL
  ``prod.calcular_cotizacion`` (migration ``0022``) hace:

      v_tiempo_minutos := EXTRACT(EPOCH FROM (NOW() - v_ingreso.fecha_ingreso)) / 60.0;

  Cuando ``fecha_ingreso`` es ``NULL``, la resta cascadea a ``NULL`` y
  todos los campos fiscales (``subtotal``, ``iva``, ``total``,
  ``tiempo_minutos``) salen ``NULL`` en el jsonb → Pydantic ``ValidationError``
  en el handler → 500 al operador. Bug abierto #2009 (memoria Engram) ya
  documentaba el INSERT path que no popula ``fecha_ingreso`` como causa
  raíz; este PR (#1) cierra la cascada en el PL/pgSQL como defensa en
  profundidad.

Defense in depth (KD-5 + RIESGO-INGRESO-01):

  1. **Root cause fix (PR parte):** el handler ``create_ingreso`` en
     ``backend/.../api/v1/operacion.py:333-346`` ahora setea
     ``new_attrs["fecha_ingreso"] = datetime.now(UTC).replace(tzinfo=None)``
     ANTES del INSERT, así los ingresos NUEVOS llegan con timestamp
     poblado y la rama COALESCE es redundante (no-op).

  2. **COALESCE en PL/pgSQL (esta migración):** preserva el cálculo
     correcto del ``tiempo_minutos`` para los registros HISTÓRICOS con
     ``fecha_ingreso IS NULL`` — sin esta defensa, todos los ingresos
     creados antes de este PR quedan con la salida de un daño en
     cascada.

  La columna ``prod.ingreso.fecha_ingreso`` es ``NULLABLE`` por diseño
  (no se hizo ``SET NOT NULL`` ni se le agregó ``DEFAULT`` en el schema
  inicial — verificar ``information_schema.columns`` confirma
  ``is_nullable=YES``, ``column_default=NULL``). Backfilling
  retroactivo sería más invasivo (afecta la auditoría del [L-E]) así
  que el COALESCE es la opción correcta: los registros NULL históricos
  quedan NULL pero el cálculo usa ``created_at`` como fallback semántico
  equivalente (la diferencia entre ``created_at`` y ``fecha_ingreso``
  en producción es de milisegundos — el INSERT y el row-creation
  ocurren en la misma transacción).

Por qué no se hace ``UPDATE prod.ingreso SET fecha_ingreso = created_at``:

  La tabla ``ingreso`` es ``[L-E]`` (insert-only event) por canon del
  ER (modelo_datos_er.mmd). El AST walk
  ``tests/static/test_no_write_after_insert.py`` rechaza UPDATE/DELETE
  sobre estas filas desde el blocco de aplicación. Backfilling desde
  una migración Alembic sería un workaround que evade el guard del
  CI; el principio ``[L-E] is append-only`` se respeta vía cálculo
  derivado, no vía mutación retroactiva.

Precedentes:

  - ``0022_create_calcular_cotizacion.py`` — la función original que
    esta migración reemplaza.
  - ``0045_add_refresh_mv_ocupacion_helper.py`` — patrón idéntico de
    ``CREATE OR REPLACE FUNCTION`` + ``GRANT EXECUTE`` a
    ``parkos_app`` / ``rol_app``.

PR companion:

  - PR #N (mismo branch ``fix/cotizar-fecha-ingreso-null-cascade``):
    el handler ``create_ingreso`` agrega ``fecha_ingreso`` al INSERT;
    test integración nuevo ``test_calcular_cotizacion_db_fecha_ingreso_
    null_coalesce_a_created_at``.
"""
from __future__ import annotations

from alembic import op


revision = "0046_fix_cotizar_fecha_ingreso_coalesce"
down_revision = "0045_add_refresh_mv_ocupacion_helper"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """CREATE OR REPLACE prod.calcular_cotizacion con COALESCE defensa.

    Diff vs 0022:
      - Único cambio funcional: línea 261 usa
        ``COALESCE(v_ingreso.fecha_ingreso, v_ingreso.created_at)`` en
        lugar de ``v_ingreso.fecha_ingreso`` directo. Todo lo demás
        (lock FOR SHARE, IF NOT FOUND checks, jsonb envelope) es
        verbatim del 0022 — preservamos el contrato de errores
        (REQ-OPS-024) y la atomicidad transaccional (KD-1).
      - El comentario in-body documenta el fallback para futuros
        mantenedores.

    Tests bloqueantes:
      - ``tests/integration/test_calcular_cotizacion_db.py`` agrega
        ``test_calcular_cotizacion_db_fecha_ingreso_null_coalesce_a_
        created_at`` que inserta un ingreso con ``fecha_ingreso=NULL``
        y verifica que el payload trae ``tiempo_minutos`` numérico
        positivo (no None) y ``total/subtotal/iva`` consistentes.
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
                ------------------------------------------------------------------
                -- CU-03M second-vehicle rotation rule (plan.md:64, DEC-SUC-21):
                -- a monthly subscription covers up to 2 plates. When the first
                -- plate is in the patio, this plate exits free
                -- (``motivo='mensualidad_vigente'``). When a SECOND plate of
                -- the same subscription is already inside the patio, the
                -- current plate must be treated as ROTATION pricing (DEC-SUC-21
                -- "detección de otra placa de la misma mensualidad ya en el
                -- patio") — the quotation primitive surfaces the new motivo
                -- so the salida handler (HU-F1.7 / HU-F7.2) applies the
                -- rotation pricing at cobro time.
                --
                -- The check is bi-temporal on ``subscripcion_vehiculos`` and
                -- ``vehiculos`` (both [V]; vigentes + activos) and on
                -- ``ingreso`` ([L-E] insert-only — "active" = no matching
                -- ``salidas`` row, mirroring the open-state derivation in
                -- Step 1). The plate filter ``i.placa = v2.placa`` AND
                -- ``i.placa <> v_ingreso.placa`` rejects the current row
                -- itself and any non-registered plate (a vehicle in patio
                -- whose placa is NOT in the subscription's ``subscripcion_
                -- vehiculos`` link table).
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

            -- REGRESSION fix (2026-09-22, directiva del operador): cuando
            -- ``fecha_ingreso`` es NULL (bug histórico del INSERT path que
            -- no la populaba — bug abierto #2009), ``NOW() - NULL = NULL``
            -- cascadea a todos los campos fiscales (subtotal/iva/total/
            -- tiempo_minutos) → Pydantic ValidationError 500 al operador.
            -- COALESCE con ``created_at`` (mismo timestamp de la
            -- transacción, diferencia de milisegundos) preserva el cálculo
            -- semánticamente correcto. Una vez el INSERT path esté fix
            -- (PR companion en operacion.py:create_ingreso), esta rama es
            -- un no-op para ingresos nuevos — defense in depth puro.
            v_tiempo_minutos := EXTRACT(EPOCH FROM (NOW() - COALESCE(v_ingreso.fecha_ingreso, v_ingreso.created_at))) / 60.0;

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
        """
    )
    # Grants ya existen del 0022 (GRANT EXECUTE TO parkos_app). CREATE OR
    # REPLACE preserva los grants — no es necesario re-grant.


def downgrade() -> None:
    """Revierte al COALESCE ausente (vuelve al cálculo original del 0022).

    Los registros con ``fecha_ingreso IS NULL`` vuelven a cascadear a
    NULL → 500 al operador; el fix del INSERT path (PR companion)
    sigue protegiendo a los ingresos nuevos. El downgrade es seguro
    solo si el PR companion está deployado simultáneamente.
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
              JOIN prod.subscripcion_vehiculos sv ON sv.uuid_subscripcion_cliente = sc.uuid
              JOIN prod.vehiculos v ON v.uuid = sv.uuid_vehiculo
             WHERE sc.uuid_sucursal = v_ingreso.uuid_sucursal
               AND sc.vigente_hasta IS NULL AND sc.estado = 'activo'
               AND sv.vigente_hasta IS NULL AND sv.estado = 'activo'
               AND v.vigente_hasta IS NULL  AND v.estado  = 'activo'
               AND v.placa = v_ingreso.placa
               AND (sc.fecha_vencimiento IS NULL OR sc.fecha_vencimiento >= CURRENT_DATE)
             ORDER BY sc.vigente_desde DESC
             LIMIT 1;
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
             ORDER BY t.vigente_desde DESC
             LIMIT 1 FOR SHARE;
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