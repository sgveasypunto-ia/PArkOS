/**
 * `reporteriaSchema.hu-f17-2.test.ts` -- zod round-trip tests for the
 * HU-F17.2 additions: ``ReporteOperacionalResponse``'s new
 * ``ingresos``/``tiempos_estancia`` fields, and the new
 * ``ReporteOcupacionHeatmapResponse`` (cross-branch heatmap + BR2 ratio).
 *
 * Named distinctly from a hypothetical ``reporteriaSchema.test.ts`` since
 * no such file exists yet for the HU-F17.1 schemas in this feature --
 * this file covers only what HU-F17.2 adds.
 */
import { describe, expect, it } from 'vitest';

import {
  reporteOperacionalResponseSchema,
  reporteOperacionalIngresoItemSchema,
  reporteEstanciaItemSchema,
  reporteOcupacionHeatmapResponseSchema,
} from './reporteriaSchema';

const BASE_OPERACIONAL = {
  uuid_sucursal: '00000000-0000-0000-0000-000000000001',
  fecha_desde: '2026-09-01',
  fecha_hasta: '2026-09-30',
  items: [],
  totales: {
    fecha: null,
    ingresos_count: 0,
    ingresos_activos_count: 0,
    salidas_count: 0,
    facturas_emitidas_count: 0,
    monto_facturado_total: 0,
    monto_cobrado_total: 0,
  },
  generado_en: '2026-09-30T10:00:00',
};

describe('reporteOperacionalResponseSchema (HU-F17.2 additions)', () => {
  it('parses a legacy payload with no HU-F17.2 fields at all (defaults apply)', () => {
    const r = reporteOperacionalResponseSchema.safeParse(BASE_OPERACIONAL);
    expect(r.success).toBe(true);
    if (r.success) {
      expect(r.data.ingresos).toEqual([]);
      expect(r.data.ingresos_next_cursor).toBeNull();
      expect(r.data.tiempos_estancia).toEqual([]);
    }
  });

  it('parses a payload carrying ingresos + tiempos_estancia', () => {
    const payload = {
      ...BASE_OPERACIONAL,
      ingresos: [
        {
          uuid: '00000000-0000-0000-0000-000000000002',
          uuid_sucursal: BASE_OPERACIONAL.uuid_sucursal,
          uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000003',
          placa: 'ABC123',
          consecutivo: null,
          fecha_ingreso: '2026-09-15T08:00:00',
          fecha_salida: '2026-09-15T09:00:00',
          tiempo_estancia_segundos: 3600,
        },
      ],
      ingresos_next_cursor: 'opaque-cursor',
      tiempos_estancia: [
        {
          fecha: '2026-09-15',
          muestras: 1,
          promedio_segundos: 3600,
          maximo_segundos: 3600,
          minimo_segundos: 3600,
        },
      ],
    };
    const r = reporteOperacionalResponseSchema.safeParse(payload);
    expect(r.success).toBe(true);
  });

  it('rejects an ingreso item with a null-missing required field', () => {
    const r = reporteOperacionalIngresoItemSchema.safeParse({
      uuid: 'not-a-uuid',
      uuid_sucursal: null,
      uuid_tipo_vehiculo: null,
      placa: null,
      consecutivo: null,
      fecha_ingreso: null,
      fecha_salida: null,
      tiempo_estancia_segundos: null,
    });
    expect(r.success).toBe(false);
  });

  it('estancia item requires numeric stats', () => {
    const r = reporteEstanciaItemSchema.safeParse({
      fecha: '2026-09-15',
      muestras: 2,
      promedio_segundos: 1800,
      maximo_segundos: 3000,
      minimo_segundos: 600,
    });
    expect(r.success).toBe(true);
  });
});

describe('reporteOcupacionHeatmapResponseSchema (HU-F17.2)', () => {
  it('parses an empty cross-branch heatmap', () => {
    const r = reporteOcupacionHeatmapResponseSchema.safeParse({
      sucursales: [],
      data: [],
      ocupacion_agregada: { ocupados: 0, capacidad: 0, porcentaje: null },
      desde: '2026-09-24',
      hasta: '2026-09-30',
      generado_en: '2026-09-30T10:00:00',
    });
    expect(r.success).toBe(true);
  });

  it('parses a populated heatmap with two branches', () => {
    const r = reporteOcupacionHeatmapResponseSchema.safeParse({
      sucursales: [
        { uuid: '00000000-0000-0000-0000-000000000001', nombre: 'Suc A' },
        { uuid: '00000000-0000-0000-0000-000000000002', nombre: null },
      ],
      data: [
        {
          uuid_sucursal: '00000000-0000-0000-0000-000000000001',
          hora: 8,
          ingresos_count: 5,
        },
      ],
      ocupacion_agregada: { ocupados: 3, capacidad: 6, porcentaje: 50 },
      desde: '2026-09-24',
      hasta: '2026-09-30',
      generado_en: '2026-09-30T10:00:00',
    });
    expect(r.success).toBe(true);
  });

  it('rejects a cell missing uuid_sucursal', () => {
    const r = reporteOcupacionHeatmapResponseSchema.safeParse({
      sucursales: [],
      data: [{ hora: 8, ingresos_count: 5 }],
      ocupacion_agregada: { ocupados: 0, capacidad: 0, porcentaje: null },
      desde: '2026-09-24',
      hasta: '2026-09-30',
      generado_en: '2026-09-30T10:00:00',
    });
    expect(r.success).toBe(false);
  });
});
